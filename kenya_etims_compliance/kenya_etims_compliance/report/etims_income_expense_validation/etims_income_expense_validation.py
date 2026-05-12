import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	report_summary = get_summary(data)
	return columns, data, None, chart, report_summary


def get_columns():
	return [
		{"fieldname": "document_type", "label": _("Type"), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "document",
			"label": _("Document"),
			"fieldtype": "Dynamic Link",
			"options": "document_type",
			"width": 180,
		},
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "party", "label": _("Party"), "fieldtype": "Data", "width": 180},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "tax_amount", "label": _("Tax"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "etims_status", "label": _("eTIMS Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "invoice_number", "label": _("eTIMS Invoice #"), "fieldtype": "Int", "width": 100},
		{"fieldname": "backed", "label": _("Backed"), "fieldtype": "Data", "width": 80},
	]


def get_data(filters):
	data = []
	date_filters = {}
	if filters.get("from_date") and filters.get("to_date"):
		date_filters["posting_date"] = ["between", [filters["from_date"], filters["to_date"]]]

	company_filter = {"company": filters["company"]} if filters.get("company") else {}
	branch_filter = {"custom_tax_branch_office": filters["branch"]} if filters.get("branch") else {}
	status_filter = filters.get("status")

	# Sales Invoices
	si_filters = {"docstatus": 1, **date_filters, **company_filter, **branch_filter}

	# Apply status filter at DB level where possible
	if status_filter == "Success":
		si_filters["custom_update_invoice_in_tims"] = 1
		si_filters["custom_update_sales_to_etims"] = 1
	elif status_filter == "Pending":
		si_filters["custom_update_invoice_in_tims"] = 1
		si_filters["custom_update_sales_to_etims"] = 0
	elif status_filter == "Failed":
		si_filters["custom_update_invoice_in_tims"] = 1
		si_filters["custom_update_sales_to_etims"] = 0
	elif status_filter == "Not Required":
		si_filters["custom_update_invoice_in_tims"] = 0

	for si in frappe.get_all(
		"Sales Invoice",
		filters=si_filters,
		fields=[
			"name",
			"posting_date",
			"customer",
			"base_grand_total",
			"base_total_taxes_and_charges",
			"custom_invoice_number",
			"custom_update_invoice_in_tims",
			"custom_update_sales_to_etims",
		],
		order_by="posting_date desc",
		limit_page_length=5000,
	):
		status = _get_status(si.custom_update_invoice_in_tims, si.custom_update_sales_to_etims)
		backed = "Yes" if si.custom_invoice_number else "No"
		data.append(
			{
				"document_type": "Sales Invoice",
				"document": si.name,
				"posting_date": si.posting_date,
				"party": si.customer,
				"amount": si.base_grand_total,
				"tax_amount": si.base_total_taxes_and_charges,
				"etims_status": status,
				"invoice_number": si.custom_invoice_number,
				"backed": backed,
			}
		)

	# Purchase Invoices
	pi_filters = {"docstatus": 1, **date_filters, **company_filter, **branch_filter}

	if status_filter == "Success":
		pi_filters["custom_update_purchase_in_tims"] = 1
		pi_filters["custom_invoice_number"] = [">", 0]
	elif status_filter == "Pending":
		pi_filters["custom_update_purchase_in_tims"] = 1
		pi_filters["custom_invoice_number"] = ["in", [0, None]]
	elif status_filter == "Failed":
		pi_filters["custom_update_purchase_in_tims"] = 1
		pi_filters["custom_invoice_number"] = ["in", [0, None]]
	elif status_filter == "Not Required":
		pi_filters["custom_update_purchase_in_tims"] = ["in", [0, None]]

	for pi in frappe.get_all(
		"Purchase Invoice",
		filters=pi_filters,
		fields=[
			"name",
			"posting_date",
			"supplier",
			"base_grand_total",
			"base_total_taxes_and_charges",
			"custom_invoice_number",
			"custom_update_purchase_in_tims",
		],
		order_by="posting_date desc",
		limit_page_length=5000,
	):
		has_invoice = pi.custom_invoice_number and pi.custom_invoice_number > 0
		status = _get_status(pi.custom_update_purchase_in_tims, has_invoice)
		backed = "Yes" if has_invoice else "No"
		data.append(
			{
				"document_type": "Purchase Invoice",
				"document": pi.name,
				"posting_date": pi.posting_date,
				"party": pi.supplier,
				"amount": pi.base_grand_total,
				"tax_amount": pi.base_total_taxes_and_charges,
				"etims_status": status,
				"invoice_number": pi.custom_invoice_number,
				"backed": backed,
			}
		)

	return data


def _get_status(flag_in, flag_out):
	if not flag_in:
		return "Not Required"
	if flag_out:
		return "Success"
	return "Pending"


def get_summary(data):
	total_income = sum(d["amount"] for d in data if d["document_type"] == "Sales Invoice")
	total_expense = sum(d["amount"] for d in data if d["document_type"] == "Purchase Invoice")
	backed_income = sum(
		d["amount"] for d in data if d["document_type"] == "Sales Invoice" and d["backed"] == "Yes"
	)
	backed_expense = sum(
		d["amount"] for d in data if d["document_type"] == "Purchase Invoice" and d["backed"] == "Yes"
	)
	total = total_income + total_expense
	compliance = round((backed_income + backed_expense) / total * 100, 1) if total > 0 else 0

	return [
		{"value": total_income, "label": _("Total Income"), "datatype": "Currency"},
		{"value": backed_income, "label": _("Backed Income"), "datatype": "Currency", "indicator": "green"},
		{"value": total_expense, "label": _("Total Expenses"), "datatype": "Currency"},
		{
			"value": backed_expense,
			"label": _("Backed Expenses"),
			"datatype": "Currency",
			"indicator": "green",
		},
		{
			"value": compliance,
			"label": _("Compliance %"),
			"datatype": "Percent",
			"indicator": "green" if compliance >= 90 else "orange" if compliance >= 70 else "red",
		},
	]


def get_chart(data):
	backed = len([d for d in data if d["backed"] == "Yes"])
	not_backed = len([d for d in data if d["backed"] == "No"])
	return {
		"data": {
			"labels": [_("Backed"), _("Not Backed")],
			"datasets": [{"values": [backed, not_backed]}],
		},
		"type": "donut",
		"colors": ["#2ecc71", "#e74c3c"],
	}
