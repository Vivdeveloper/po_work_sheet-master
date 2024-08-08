// Copyright (c) 2023, admin and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["PO data worksheet"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"width": "80",
			"options": "Company",
			"default": frappe.defaults.get_default("company")
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"width": "80",
			"read_only": 1,
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"width": "80",
			"reqd": 1,
			"default": frappe.datetime.get_today(),
			"on_change": function (query_report) {
				var to_date = query_report.get_values().to_date;

				frappe.query_report.set_filter_value({
					from_date: frappe.datetime.add_months(to_date, -3)
				});
			}
		},
		{
			"fieldname": "item_code",
			"label": __("Item"),
			"fieldtype": "Link",
			"width": "80",
			"options": "Item",
			"get_query": function () {
				return {
					query: "erpnext.controllers.queries.item_query",
				};
			}
		},
		{
			"fieldname": "warehouse",
			"label": __("Warehouse"),
			"fieldtype": "Link",
			"width": "80",
			"options": "Warehouse",
			"reqd": 1,
			get_query: () => {
				let warehouse_type = frappe.query_report.get_filter_value("warehouse_type");
				let company = frappe.query_report.get_filter_value("company");

				return {
					filters: {
						...warehouse_type && { warehouse_type },
						...company && { company }
					}
				}
			}
		},
		{
			"fieldname": "item_group",
			"label": __("Item Group"),
			"fieldtype": "Link",
			"width": "80",
			"options": "Item Group",
		},
		{
			"fieldname": "price_list",
			"label": __("Price List"),
			"fieldtype": "Link",
			"width": "80",
			"options": "Price List",
			"default": "Current Rate",
			"reqd": 1,
			get_query: () => {
				return { filters: { "selling": 1, "custom_use_for_calculation": 1 } }
			}
		},
		{
			"fieldname": "show_calculation",
			"label": __("Show Calculation"),
			"fieldtype": "Check",
		},


	],
	onload: function (report) {
		report.page.add_inner_button(__("Make Purchase Order"), function () {
			var filters = report.get_values();
			let checked_rows_indexes = report.datatable.rowmanager.getCheckedRows();
			let checked_rows = checked_rows_indexes.map(i => report.data[i]);
			if (checked_rows.length > 0) {
				items_list = [];
				$.each(checked_rows, function (index, element) {
					items_list.push({
						item_code: element.item_code,
						description: element.description,
						reorder_qty: element.reorder_qty,
						stock_uom: element.stock_uom
					})
				});
				frappe.prompt({
					label: __("Select Supplier"),
					fieldname: "supplier",
					fieldtype: "Link",
					reqd: 1,
					options: 'Supplier',
					description: __('Select a Supplier to create Purchase Order'),
					get_query: () => {
						return {
							filters: {
								'disabled': 0,
							}
						};
					}
				}, function (values) {
					frappe.call({
						method: 'po_data_worksheet.po_data_worksheet.report.po_data_worksheet.po_data_worksheet.get_po',
						args: {
							"items": items_list
						},
						callback: function (r) {
							frappe.model.sync(r.message);
							frappe.model.set_value(r.message.doctype, r.message.name, "company", filters.company);
							frappe.model.set_value(r.message.doctype, r.message.name, "set_warehouse", filters.warehouse);
							frappe.model.set_value(r.message.doctype, r.message.name, "supplier", values.supplier);
							frappe.get_doc(
								r.message.doctype,
								r.message.name
							).__run_link_triggers = true;
							frappe.set_route("purchase-order", r.message.name);
						}
					});
				});
			}
			else {
				msgprint('Please select records to create purchase order', 'Alert');
			}

		});

		//make internal purchase order form selected items
		report.page.add_inner_button(__("Create Branch Transfer"), function () {
			var filters = report.get_values();
			let checked_rows_indexes = report.datatable.rowmanager.getCheckedRows();
			let checked_rows = checked_rows_indexes.map(i => report.data[i]);
			if (checked_rows.length > 0) {
				items_list = [];
				$.each(checked_rows, function (index, element) {
					items_list.push({
						item_code: element.item_code,
						description: element.description,
						reorder_qty: element.reorder_qty,
						stock_uom: element.stock_uom
					})
				});
					frappe.call({
						method: 'po_data_worksheet.po_data_worksheet.report.po_data_worksheet.po_data_worksheet.get_po',
						args: {
							"items": items_list,
							"company": filters.company,
							"supplier":"Imperial Motor Store - Internal",
							"warehouse":filters.warehouse
						},
						callback: function (r) {
							frappe.model.sync(r.message);
							frappe.model.set_value(r.message.doctype, r.message.name, "company", filters.company);
							frappe.model.set_value(r.message.doctype, r.message.name, "set_warehouse", filters.warehouse);
							frappe.model.set_value(r.message.doctype, r.message.name, "supplier", "Imperial Motor Store - Internal");
							frappe.get_doc(
								r.message.doctype,
								r.message.name
							).__run_link_triggers = true;
							frappe.set_route("purchase-order", r.message.name);
						}
					});
			
			}
			else {
				msgprint('Please select records to create purchase order', 'Alert');
			}

		});
		report.page.add_inner_button(__("Download"), function () {
			let checked_rows_indexes = report.datatable.rowmanager.getCheckedRows();
			let checked_rows = checked_rows_indexes.map(i => report.data[i]);
			fetch('/api/method/po_data_worksheet.overrides.po_worksheet_report.get_excel', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
			 		'X-Frappe-CSRF-Token': frappe.csrf_token
			 	},
				body: JSON.stringify({
					'items':checked_rows,
					'columns':report.columns
				})
			}).then(function (t) {
				console.log(report);
				t.blob().then((b) => {
					var url = URL.createObjectURL(b);
					const anchorElement = document.createElement('a');
					anchorElement.href = url;
					anchorElement.download = "PO Data Worksheet.xlsx";
					anchorElement.click();
				});
			});
		});
		setTimeout(function() {
			$('[data-label="Download%20Report"]').hide();
    	}, 1500);
	},
	get_datatable_options(options) {
		return Object.assign(options, {
			checkboxColumn: true
		});
	}
};
