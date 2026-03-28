import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	summary = get_summary(data)
	return columns, data, None, chart, summary


def get_columns():
	return [
		{"fieldname": "source", "label": _("Source"), "fieldtype": "Data", "width": 70},
		{"fieldname": "kra_invoice_number", "label": _("KRA Invoice #"), "fieldtype": "Int", "width": 100},
		{"fieldname": "supplier_pin", "label": _("Supplier PIN"), "fieldtype": "Data", "width": 120},
		{"fieldname": "supplier_name", "label": _("Supplier"), "fieldtype": "Data", "width": 160},
		{"fieldname": "invoice_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "kra_amount", "label": _("KRA Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "local_pi", "label": _("Local PI"), "fieldtype": "Link",
		 "options": "Purchase Invoice", "width": 150},
		{"fieldname": "local_amount", "label": _("Local Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "variance", "label": _("Variance"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "match_status", "label": _("Status"), "fieldtype": "Data", "width": 140},
	]


def get_data(filters):
	data = []

	# Part 1: KRA Register Entries (what KRA says we purchased)
	if frappe.db.exists("DocType", "eTIMS Purchase Register Entry"):
		data.extend(_get_kra_entries(filters))

	# Part 2: Local PIs marked "Not in KRA" (what we have but KRA doesn't)
	if filters.get("show_not_in_kra") or not filters.get("match_status"):
		data.extend(_get_not_in_kra_entries(filters))

	return data


def _get_kra_entries(filters):
	entry_filters = {}
	if filters.get("from_date") and filters.get("to_date"):
		entry_filters["invoice_date"] = ["between", [filters["from_date"], filters["to_date"]]]
	if filters.get("match_status"):
		entry_filters["match_status"] = filters["match_status"]
	if filters.get("branch"):
		entry_filters["branch"] = filters["branch"]

	entries = frappe.get_all(
		"eTIMS Purchase Register Entry",
		filters=entry_filters,
		fields=["kra_invoice_number", "supplier_pin", "supplier_name", "invoice_date",
				"total_amount", "matched_purchase_invoice", "variance_amount", "match_status"],
		order_by="invoice_date desc",
		limit_page_length=5000,
	)

	# Batch fetch local amounts to avoid N+1 queries
	pi_names = [e.matched_purchase_invoice for e in entries if e.matched_purchase_invoice]
	local_amounts = {}
	if pi_names:
		for pi in frappe.get_all("Purchase Invoice",
			filters={"name": ["in", pi_names]},
			fields=["name", "base_grand_total"]):
			local_amounts[pi.name] = pi.base_grand_total

	data = []
	for e in entries:
		local_amount = local_amounts.get(e.matched_purchase_invoice, 0)
		data.append({
			"source": "KRA",
			"kra_invoice_number": e.kra_invoice_number,
			"supplier_pin": e.supplier_pin,
			"supplier_name": e.supplier_name,
			"invoice_date": e.invoice_date,
			"kra_amount": e.total_amount,
			"local_pi": e.matched_purchase_invoice,
			"local_amount": local_amount,
			"variance": e.variance_amount or 0,
			"match_status": e.match_status,
		})

	return data


def _get_not_in_kra_entries(filters):
	"""Local PIs that have no matching KRA entry."""
	pi_filters = {
		"docstatus": 1,
		"custom_kra_match_status": "Not in KRA",
	}
	if filters.get("from_date") and filters.get("to_date"):
		pi_filters["posting_date"] = ["between", [filters["from_date"], filters["to_date"]]]
	if filters.get("branch"):
		pi_filters["custom_tax_branch_office"] = filters["branch"]

	pis = frappe.get_all("Purchase Invoice", filters=pi_filters,
		fields=["name", "supplier", "tax_id", "posting_date", "base_grand_total"],
		order_by="posting_date desc", limit_page_length=2000)

	data = []
	for pi in pis:
		data.append({
			"source": "Local",
			"kra_invoice_number": None,
			"supplier_pin": pi.tax_id,
			"supplier_name": pi.supplier,
			"invoice_date": pi.posting_date,
			"kra_amount": 0,
			"local_pi": pi.name,
			"local_amount": pi.base_grand_total,
			"variance": pi.base_grand_total,
			"match_status": "Not in KRA",
		})

	return data


def get_summary(data):
	total = len(data)
	matched = len([d for d in data if d["match_status"] in ("Matched", "Matched (Auto-Created)")])
	mismatched = len([d for d in data if d["match_status"] == "Amount Mismatch"])
	missing = len([d for d in data if d["match_status"] == "Missing Locally"])
	not_in_kra = len([d for d in data if d["match_status"] == "Not in KRA"])
	total_variance = sum(abs(d["variance"]) for d in data if d["variance"])

	return [
		{"value": total, "label": _("Total Entries"), "datatype": "Int"},
		{"value": matched, "label": _("Matched"), "datatype": "Int", "indicator": "green"},
		{"value": mismatched, "label": _("Amount Mismatch"), "datatype": "Int", "indicator": "orange"},
		{"value": missing, "label": _("Missing Locally"), "datatype": "Int", "indicator": "red"},
		{"value": not_in_kra, "label": _("Not in KRA"), "datatype": "Int", "indicator": "red"},
		{"value": total_variance, "label": _("Total Variance"), "datatype": "Currency", "indicator": "red"},
	]


def get_chart(data):
	matched = len([d for d in data if d["match_status"] in ("Matched", "Matched (Auto-Created)")])
	mismatched = len([d for d in data if d["match_status"] == "Amount Mismatch"])
	missing = len([d for d in data if d["match_status"] == "Missing Locally"])
	not_in_kra = len([d for d in data if d["match_status"] == "Not in KRA"])
	pending = len([d for d in data if d["match_status"] == "Pending"])

	return {
		"data": {
			"labels": [_("Matched"), _("Mismatch"), _("Missing Locally"), _("Not in KRA"), _("Pending")],
			"datasets": [{"values": [matched, mismatched, missing, not_in_kra, pending]}],
		},
		"type": "donut",
		"colors": ["#2ecc71", "#f39c12", "#e74c3c", "#e67e22", "#95a5a6"],
	}
