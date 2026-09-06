# Copyright (c) 2026, Upande Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Abs, Count, Sum
from pypika import Order


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("Qty Sold"), "fieldname": "qty_sold", "fieldtype": "Float", "width": 100},
		{"label": _("Total Amount"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Tax Code"), "fieldname": "tax_code", "fieldtype": "Data", "width": 80},
		{"label": _("Tax Amount"), "fieldname": "tax_amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Net Amount"), "fieldname": "net_amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Transaction Count"), "fieldname": "trx_count", "fieldtype": "Int", "width": 120},
	]


def get_data(filters):
	filters = filters or {}
	sii = frappe.qb.DocType("Sales Invoice Item")
	si = frappe.qb.DocType("Sales Invoice")

	qty_sold = Sum(Abs(sii.qty)).as_("qty_sold")
	query = (
		frappe.qb.from_(sii)
		.inner_join(si)
		.on(si.name == sii.parent)
		.where(si.docstatus == 1)
		.where(si.custom_update_invoice_in_tims == 1)
		.groupby(sii.item_code, sii.custom_tax_code)
		.orderby(qty_sold, order=Order.desc)
		.select(
			sii.item_code,
			sii.item_name,
			qty_sold,
			Sum(Abs(sii.base_amount)).as_("total_amount"),
			sii.custom_tax_code.as_("tax_code"),
			Sum(Abs(sii.base_amount) - Abs(sii.base_net_amount)).as_("tax_amount"),
			Sum(Abs(sii.base_net_amount)).as_("net_amount"),
			Count(si.name).distinct().as_("trx_count"),
		)
	)

	if filters.get("from_date"):
		query = query.where(si.posting_date >= filters["from_date"])
	if filters.get("to_date"):
		query = query.where(si.posting_date <= filters["to_date"])
	if filters.get("company"):
		query = query.where(si.company == filters["company"])
	if filters.get("branch"):
		query = query.where(si.custom_tax_branch_office == filters["branch"])

	return query.run(as_dict=True)
