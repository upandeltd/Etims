import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	summary = get_summary(data)
	return columns, data, None, chart, summary


def get_columns():
	return [
		{"fieldname": "payment_entry", "label": _("Payment Entry"), "fieldtype": "Link",
		 "options": "Payment Entry", "width": 160},
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "paid_amount", "label": _("Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "mode_of_payment", "label": _("Channel"), "fieldtype": "Data", "width": 120},
		{"fieldname": "party", "label": _("Party"), "fieldtype": "Data", "width": 160},
		{"fieldname": "linked_invoice", "label": _("Linked Invoice"), "fieldtype": "Data", "width": 160},
		{"fieldname": "invoice_type", "label": _("Type"), "fieldtype": "Data", "width": 100},
		{"fieldname": "etims_status", "label": _("eTIMS Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "backed", "label": _("Backed"), "fieldtype": "Data", "width": 80},
	]


def get_data(filters):
	pe_filters = {"docstatus": 1}
	if filters.get("from_date") and filters.get("to_date"):
		pe_filters["posting_date"] = ["between", [filters["from_date"], filters["to_date"]]]
	if filters.get("company"):
		pe_filters["company"] = filters["company"]
	if filters.get("mode_of_payment"):
		pe_filters["mode_of_payment"] = filters["mode_of_payment"]

	payments = frappe.get_all("Payment Entry", filters=pe_filters,
		fields=["name", "posting_date", "paid_amount", "mode_of_payment",
				"party_type", "party", "payment_type"],
		limit_page_length=0)

	data = []
	for pe in payments:
		# Find linked invoices via Payment Entry Reference
		refs = frappe.get_all("Payment Entry Reference",
			filters={"parent": pe.name},
			fields=["reference_doctype", "reference_name", "allocated_amount"])

		if not refs:
			data.append({
				"payment_entry": pe.name,
				"posting_date": pe.posting_date,
				"paid_amount": pe.paid_amount,
				"mode_of_payment": pe.mode_of_payment or "Unknown",
				"party": pe.party,
				"linked_invoice": "No linked invoice",
				"invoice_type": "",
				"etims_status": "Unbacked",
				"backed": "No",
			})
			continue

		for ref in refs:
			etims_status = "N/A"
			backed = "No"

			if ref.reference_doctype == "Sales Invoice":
				transmitted = frappe.db.get_value("Sales Invoice", ref.reference_name,
					"custom_update_sales_to_etims")
				etims_status = "Transmitted" if transmitted else "Not Transmitted"
				backed = "Yes" if transmitted else "No"

			elif ref.reference_doctype == "Purchase Invoice":
				match_status = frappe.db.get_value("Purchase Invoice", ref.reference_name,
					"custom_kra_match_status")
				etims_status = match_status or "Unknown"
				backed = "Yes" if match_status == "Matched" else "No"

			data.append({
				"payment_entry": pe.name,
				"posting_date": pe.posting_date,
				"paid_amount": ref.allocated_amount,
				"mode_of_payment": pe.mode_of_payment or "Unknown",
				"party": pe.party,
				"linked_invoice": ref.reference_name,
				"invoice_type": ref.reference_doctype,
				"etims_status": etims_status,
				"backed": backed,
			})

	return sorted(data, key=lambda x: x["posting_date"], reverse=True)


def get_summary(data):
	total = sum(d["paid_amount"] for d in data)
	backed_total = sum(d["paid_amount"] for d in data if d["backed"] == "Yes")
	unbacked_total = sum(d["paid_amount"] for d in data if d["backed"] == "No")

	return [
		{"value": total, "label": _("Total Payments"), "datatype": "Currency"},
		{"value": backed_total, "label": _("Backed by eTIMS"), "datatype": "Currency",
		 "indicator": "green"},
		{"value": unbacked_total, "label": _("Unbacked"), "datatype": "Currency",
		 "indicator": "red"},
	]


def get_chart(data):
	backed = sum(d["paid_amount"] for d in data if d["backed"] == "Yes")
	unbacked = sum(d["paid_amount"] for d in data if d["backed"] == "No")

	return {
		"data": {
			"labels": [_("Backed"), _("Unbacked")],
			"datasets": [{"values": [backed, unbacked]}],
		},
		"type": "donut",
		"colors": ["#2ecc71", "#e74c3c"],
	}
