
import frappe
import json
from openpyxl import Workbook
from io import BytesIO

@frappe.whitelist()
def get_excel(items = None,columns = None):
	wb = Workbook()
	ws = wb.active
	cols = []
	for column in columns:
		cols.append(column['label'])
	ws.append(cols)
	for row in items:
		row_data = []
		for column in columns:
			row_data.append(row[column['fieldname']])
		ws.append(row_data)
	xlsx_file = BytesIO()
	wb.save(xlsx_file)
	frappe.response["filename"] = "PO Data Worksheet" + ".xlsx"
	frappe.response["filecontent"] = xlsx_file.getvalue()
	frappe.response["type"] = "binary"