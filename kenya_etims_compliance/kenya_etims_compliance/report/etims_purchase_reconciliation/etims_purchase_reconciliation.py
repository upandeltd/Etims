import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import flt

from kenya_etims_compliance.utils.etims_utils import KRA_TAX_BANDS


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
		{
			"fieldname": "local_pi",
			"label": _("Local PI"),
			"fieldtype": "Link",
			"options": "Purchase Invoice",
			"width": 150,
		},
		{"fieldname": "local_amount", "label": _("Local Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "variance", "label": _("Variance"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "match_status", "label": _("Status"), "fieldtype": "Data", "width": 140},
		{"fieldname": "band_code", "label": _("Band"), "fieldtype": "Data", "width": 60},
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
		fields=[
			"kra_invoice_number",
			"supplier_pin",
			"supplier_name",
			"invoice_date",
			"total_amount",
			"matched_purchase_invoice",
			"etims_purchase_invoice",
			"variance_amount",
			"match_status",
		],
		order_by="invoice_date desc",
		limit_page_length=5000,
	)

	# Batch fetch local amounts to avoid N+1 queries
	pi_names = [e.matched_purchase_invoice for e in entries if e.matched_purchase_invoice]
	local_amounts = {}
	if pi_names:
		for pi in frappe.get_all(
			"Purchase Invoice", filters={"name": ["in", pi_names]}, fields=["name", "base_grand_total"]
		):
			local_amounts[pi.name] = pi.base_grand_total

	data = []
	for e in entries:
		local_amount = local_amounts.get(e.matched_purchase_invoice, 0)
		data.append(
			{
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
				"band_code": "",
			}
		)

	data.extend(_get_band_mismatch_rows(entries))
	return data


def _get_band_mismatch_rows(entries):
	"""Same KRA-vs-local A-E band comparison the reconciliation engine files
	as exceptions, surfaced live here too so a preparer sees a wrong VAT
	band classification before a period is even reconciled and closed.

	Batches both sides' lookups (one query each, not one pair per matched
	row) the same way the caller already batches local_amounts above.
	"""
	matched = [e for e in entries if e.matched_purchase_invoice and e.etims_purchase_invoice]
	if not matched:
		return []

	band_fields = [f"taxable_amount_{code.lower()}" for code in KRA_TAX_BANDS] + [
		f"tax_amt_{code.lower()}" for code in KRA_TAX_BANDS
	]
	kra_by_pinv = {
		row.name: row
		for row in frappe.get_all(
			"eTIMS Purchase Invoice",
			filters={"name": ["in", [e.etims_purchase_invoice for e in matched]]},
			fields=["name", *band_fields],
		)
	}

	child = frappe.qb.DocType("Purchase Taxes and Charges")
	local_rows = (
		frappe.qb.from_(child)
		.where(child.parent.isin([e.matched_purchase_invoice for e in matched]))
		.where(child.custom_code.isin(list(KRA_TAX_BANDS)))
		.groupby(child.parent, child.custom_code)
		.select(
			child.parent.as_("pi_name"),
			child.custom_code.as_("tax_code"),
			Sum(child.custom_total_taxable_amount).as_("taxable_amount"),
			Sum(child.base_tax_amount_after_discount_amount).as_("tax_amount"),
		)
		.run(as_dict=True)
	)
	local_by_pi = {}
	for row in local_rows:
		local_by_pi.setdefault(row.pi_name, {})[row.tax_code] = {
			"taxable_amount": flt(row.taxable_amount),
			"tax_amount": flt(row.tax_amount),
		}

	zero = {"taxable_amount": 0.0, "tax_amount": 0.0}
	rows = []
	for e in matched:
		kra_row = kra_by_pinv.get(e.etims_purchase_invoice)
		if not kra_row:
			continue
		local_bands = local_by_pi.get(e.matched_purchase_invoice, {})
		for code in KRA_TAX_BANDS:
			kra = {
				"taxable_amount": flt(kra_row.get(f"taxable_amount_{code.lower()}")),
				"tax_amount": flt(kra_row.get(f"tax_amt_{code.lower()}")),
			}
			local = local_bands.get(code, zero)
			variance = kra["tax_amount"] - local["tax_amount"]
			if abs(variance) <= 1 and abs(kra["taxable_amount"] - local["taxable_amount"]) <= 1:
				continue
			rows.append(
				{
					"source": "KRA",
					"kra_invoice_number": e.kra_invoice_number,
					"supplier_pin": e.supplier_pin,
					"supplier_name": e.supplier_name,
					"invoice_date": e.invoice_date,
					"kra_amount": kra["tax_amount"],
					"local_pi": e.matched_purchase_invoice,
					"local_amount": local["tax_amount"],
					"variance": variance,
					"match_status": "Band Mismatch",
					"band_code": code,
				}
			)
	return rows


def _get_not_in_kra_entries(filters):
	"""Local PIs KRA has no record of, including the ones already accepted.

	An accepted row is resolved, not deleted — it keeps its own status so the
	red "Not in KRA" tile only counts what still needs a decision.
	"""
	pi_filters = {
		"docstatus": 1,
		"custom_kra_match_status": ["in", ["Not in KRA", "Accepted"]],
	}
	if filters.get("from_date") and filters.get("to_date"):
		pi_filters["posting_date"] = ["between", [filters["from_date"], filters["to_date"]]]
	if filters.get("branch"):
		pi_filters["custom_tax_branch_office"] = filters["branch"]

	pis = frappe.get_all(
		"Purchase Invoice",
		filters=pi_filters,
		fields=["name", "supplier", "tax_id", "posting_date", "base_grand_total", "custom_kra_match_status"],
		order_by="posting_date desc",
		limit_page_length=2000,
	)

	data = []
	for pi in pis:
		data.append(
			{
				"source": "Local",
				"kra_invoice_number": None,
				"supplier_pin": pi.tax_id,
				"supplier_name": pi.supplier,
				"invoice_date": pi.posting_date,
				"kra_amount": 0,
				"local_pi": pi.name,
				"local_amount": pi.base_grand_total,
				"variance": pi.base_grand_total,
				"match_status": pi.custom_kra_match_status,
				"band_code": "",
			}
		)

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
