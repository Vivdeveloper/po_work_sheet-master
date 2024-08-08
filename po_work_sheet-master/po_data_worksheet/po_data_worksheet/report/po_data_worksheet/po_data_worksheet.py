# Copyright (c) 2023, admin and contributors
# For license information, please see license.txt

from operator import itemgetter
from typing import Any, Dict, List, Optional, TypedDict
from frappe.model.create_new import get_new_doc
import ast

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Coalesce, CombineDatetime,IfNull, Locate, Replace, Sum
from frappe.utils import add_days, cint, date_diff, flt, getdate
from frappe.utils.nestedset import get_descendants_of

import erpnext
from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions
from erpnext.stock.doctype.warehouse.warehouse import apply_warehouse_filter
from erpnext.stock.utils import get_stock_balance
from datetime import timedelta


class PODataWorksheetFilter(TypedDict):
	company: Optional[str]
	from_date: str
	to_date: str
	item_group: Optional[str]
	item: Optional[str]
	warehouse: Optional[str]
	warehouse_type: Optional[str]
	include_uom: Optional[str]  # include extra info in converted UOM
	show_calculation: bool


SLEntry = Dict[str, Any]


def execute(filters: Optional[PODataWorksheetFilter] = None):
	if not filters.price_list:
			frappe.throw(_("Price List is required"))
	if frappe.db.get_value("Warehouse", filters.warehouse, "company") != filters.company:
		frappe.throw(f"Warehouse does not belong to the selected company")
	return PODataWorksheetReport(filters).run()


class PODataWorksheetReport(object):
	def __init__(self, filters: Optional[PODataWorksheetFilter]) -> None:
		self.filters = frappe._dict(filters or {})
		self.from_date = getdate(filters.get("from_date"))
		self.to_date = getdate(filters.get("to_date"))

		self.start_from = None
		self.data = []
		self.columns = []
		self.sle_entries: List[SLEntry] = []
		self.branch_columns = []
		self.set_company_currency()


	def set_company_currency(self) -> None:
		if self.filters.get("company"):
			self.company_currency = erpnext.get_company_currency(self.filters.get("company"))
		else:
			self.company_currency = frappe.db.get_single_value("Global Defaults", "default_currency")

		
	def run(self):
			operator="<"
			self.float_precision = cint(frappe.db.get_default("float_precision")) or 3
			self.get_stock_ledger_entries()
			self.get_branch_columns()

			for item in self.sle_entries:
				item['alternative_item'],item['brand'],item['car'],item['identification']=frappe.db.get_value("Item",item.item_code,["custom_alternative_item","brand","car","identification"])
				three_month_sale=	self.get_sale(item.item_code, item.warehouse,self.from_date,self.to_date)
				if three_month_sale==None:
					three_month_sale=0.0
				item['3month_sales']=three_month_sale
				twelve_month_sale=	self.get_sale(item.item_code, item.warehouse,getdate(self.to_date)- timedelta(days=365) ,getdate(self.to_date))
				if twelve_month_sale==None:
					twelve_month_sale=0.0
				item['12month_sales']=twelve_month_sale
				item['half_sales_of_3month']=three_month_sale/2
				item['avg_3month_sales']=three_month_sale/3
				item['safety_stock']=three_month_sale*2
				item['reorder_qty']=abs(item['safety_stock']-item['current_stock'])
				item['difference']=item['current_stock']-item['half_sales_of_3month']
				item['excess_short']=round(item['difference'])
				price_list=frappe.db.sql(
					"""select ip.price_list_rate from `tabPrice List` pl inner join 
					`tabItem Price` ip on pl.name=ip.price_list where pl.custom_use_for_calculation=1 and pl.selling=1 and ip.price_list=%s and ip.item_code=%s 
					order by ip.valid_from DESC limit 1""",
					(self.filters.get("price_list"),item.item_code),as_dict=1)
				if price_list:
					item['price_list_rate']=price_list[0].price_list_rate
				else:
					item['price_list_rate']=0
				if item['excess_short']>0:
					item['excess_short_value']='Excess'
				else:
					item['excess_short_value']='Short'
				
				

				for branch_column in self.branch_columns:
					#orderd_qty = frappe.db.get_value('Bin',filters={"item_code":item.item_code,"warehouse":branch_column["warehouse"]},fieldname="ordered_qty") or 0
					stock_qty = frappe.db.get_value('Bin',filters={"item_code":item.item_code,"warehouse":branch_column["warehouse"]},fieldname="actual_qty") or 0
					three_m_sale = self.get_sale(item.item_code,branch_column["warehouse"],getdate(self.filters.get("from_date")),getdate(self.filters.get("to_date")))
					item[branch_column["fieldname"]+"_excess"] = stock_qty - (three_m_sale*2)
					#item[branch_column["fieldname"]+"_ordered"] = orderd_qty
				
				self.data.append(item)

			if not self.columns:
				self.columns = self.get_columns()


			return self.columns, self.data
	
	def get_sale(self,item_code,warehouse,from_date,to_date):
		return frappe.db.sql(
					"""select sum(CASE WHEN voucher_type in ("Sales Invoice","Delivery Note") THEN abs(actual_qty) ELSE 0 END)as 3month_sales   from `tabStock Ledger Entry`
					where item_code=%(item_code)s and warehouse=%(warehouse)s  and 
					posting_date BETWEEN %(from_date)s and %(to_date)s and 
					is_cancelled=0
					order by posting_date desc,creation desc
					limit 1""",
					{"item_code":item_code,"warehouse": warehouse,"from_date":from_date,"to_date":to_date},as_dict=1)[0]["3month_sales"] or 0
	
	def get_stock_ledger_entries(self):
		item_table = frappe.qb.DocType("Item")
		company = frappe.db.get_value("Warehouse",self.filters.warehouse,"company")


		query = (
			frappe.qb.from_(item_table)
			.select(
				item_table.item_code,
				item_table.item_group,
				item_table.stock_uom,
				item_table.description,
				item_table.abc,
				item_table.min_order_qty
			)
		)
		query = self.apply_items_filters(query, item_table)

		sle_entries = query.run(as_dict=True)

		#add warehouse and current stock
		current_stocks = frappe.db.sql("SELECT item_code,actual_qty as current_stock from `tabBin` where warehouse = %(warehouse)s",{'warehouse':self.filters.warehouse},as_dict=1)
		stocks = {}
		for stock in current_stocks:
			stocks[stock.item_code] = stock.current_stock

		for sle_entry in sle_entries:
			#add FMS row
			res = frappe.db.sql("SELECT fms,branch_wh from `tabFMS` where parent = %(item)s and branch_wh = %(warehouse)s",{"item":sle_entry.item_code,'warehouse':sle_entry.warehouse},as_dict=1)
			if len(res)>0:
				sle_entry.fms = res[0].fms
			else:
				sle_entry.fms = "N"
			
			#add current stock and warehouse
			if sle_entry.item_code in stocks.keys():
				sle_entry.warehouse = self.filters.warehouse
				sle_entry.current_stock = stocks[sle_entry.item_code]
				sle_entry.company = company
			else:
				sle_entry.warehouse = self.filters.warehouse
				sle_entry.current_stock = 0
				sle_entry.company = company

		self.sle_entries = sle_entries


	def apply_warehouse_filters(self, query, wh_table):
		if self.filters.get("company"):
				query = (
					query
					.where(wh_table.company==self.filters.get("company"))
				)
		if self.filters.get("warehouse"):
			query = query.where(wh_table.name.isnull() | wh_table.name == self.filters.get("warehouse"))
		return query

	def apply_items_filters(self, query, item_table) -> str:
		if item_group := self.filters.get("item_group"):
			query = query.where(item_table.item_group.isin([item_group]))

		for field in ["item_code", "brand"]:
			if not self.filters.get(field):
				continue
			elif field == "item_code":
				query = query.where(item_table.name == self.filters.get(field))
			else:
				query = query.where(item_table[field] == self.filters.get(field))

		return query

	def apply_date_filters(self, query, sle) -> str:

		if self.to_date:
			query = query.where(sle.posting_date>=self.from_date and sle.posting_date <= self.to_date)

		return query


	def get_columns(self):
			columns = [
				{
					"label": _("Item Group"),
					"fieldname": "item_group",
					"fieldtype": "Link",
					"options": "Item Group",
					"width": 100,
				},
				{
					"label": _("ItemCode"),
					"fieldname": "item_code",
					"fieldtype": "Link",
					"options": "Item",
					"width": 100,
				},
				{
					"label": _("ItemDescription"),
					"fieldname": "description",
					"fieldtype": "Data",
					"width": 100,
				},
				{
					"label": _("Alternative Item"),
					"fieldname": "alternative_item",
					"fieldtype": "Link",
					"options": "Item",
					"width": 100,
				},
				{
					"label": _("Brand"),
					"fieldname": "brand",
					"fieldtype": "Link",
					"options": "Brand",
					"width": 100,
				},
				{
					"label": _("Car"),			
					"fieldname": "car",
					"fieldtype": "Link",
					"options": "Car",
					"width": 100,
				},
				{
					"label": _("Identification"),			
					"fieldname": "identification",
					"fieldtype": "Data",
					"width": 100,
				},
				{
					"label": _("FMS Classification"),
					"fieldname": "fms",
					"fieldtype": "Data",
					"width": 100,
				},
				{
					"label": _("MOQ"),
					"fieldname": "min_order_qty",
					"fieldtype": "Float",
					"width": 100,
				},
				{
					"label": _("List Price"),
					"fieldname": "price_list_rate",
					"fieldtype": "Float",
					"width": 100,
				},
				{
					"label": _("Current Stock(Branch)"),
					"fieldname": "current_stock",
					"fieldtype": "Float",
					"width": 100,
				},
				
				{
					"label": _("Average of Last 3 Months sales"),
					"fieldname": "avg_3month_sales",
					"fieldtype": "Float",
					"width": 100,
				},
				{
					"label": _("Safety Stock"),
					"fieldname": "safety_stock",
					"fieldtype": "Float",
					"width": 100,
				},
				{
					"label": _("Excess/Short"),
					"fieldname": "excess_short",
					"fieldtype": "Float",
					"width": 100,
				},
				{
					"label": _("Reorder"),
					"fieldname": "reorder_qty",
					"fieldtype": "Float",
					"width": 100,
				},
			]
			if self.filters.get('show_calculation')==1:
				columns += [
				{
					"label": _(" Last 3 Months sales"),
					"fieldname": "3month_sales",
					"fieldtype": "Float",
					"width": 100,
				},
				{
					"label": _("Half of 3 Months Sales"),
					"fieldname": "half_sales_of_3month",
					"fieldtype": "Float",
					"width": 100,
				},
				{
					"label": _("Difference"),
					"fieldname": "difference",
					"fieldtype": "Float",
					"width": 100,
				},
				{
					"label": _("Excess/Short value"),
					"fieldname": "excess_short_value",
					"fieldtype": "Data",
					"width": 100,
				},
				{
					"label": _(" Last 12 Months sales"),
					"fieldname": "12month_sales",
					"fieldtype": "Float",
					"width": 100,
				},
				]
			for column in self.branch_columns:
				columns.append({
					"label":column["label"] + "(Excess)",
					"fieldname":column["fieldname"]+"_excess",
					"fieldtype":"Float",
					"width":150,
					"warehouse":column["warehouse"]
				})
				#columns.append({
				#	"label":column["label"] + "(Ordered)",
				#	"fieldname":column["fieldname"]+"_ordered",
				#	"fieldtype":"Float",
				#	"width":150,
				#	"warehouse":column["warehouse"]
				#})
				
			return columns

	def get_branch_columns(self):
		warehouse_list = frappe.db.sql("""SELECT w.* FROM `tabWarehouse` as w JOIN `tabBranch` as b on w.branch = b.name WHERE w.is_group = 0 AND w.company = %(company)s""",{"company" : self.filters.get("company")},as_dict=1)
		for warehouse in warehouse_list:
			col_data = {
					"label": _(warehouse.branch),
					"fieldname": warehouse.branch.lower().replace(" ","_"),
					"warehouse": warehouse.name,
			}
			self.branch_columns.append(col_data)


@frappe.whitelist()
def get_po(items=None):
    doc = get_new_doc("Purchase Order")
    items_list = ast.literal_eval(items)
    for item in items_list:
        doc.append(
            "items",
            {
                "item_code": item["item_code"],
                "item_name": frappe.db.get_value(
                    "Item", item["item_code"], "item_name"
                ),
                "description": item["description"],
                "qty": item["reorder_qty"],
                "uom": item["stock_uom"],
                "stock_uom": item["stock_uom"],
            },
        )
    return doc
