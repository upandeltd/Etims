# Copyright (c) 2026, Upande Ltd and contributors
# For license information, please see license.txt
"""VAT Return Preview.

Aggregates Output VAT (sales transmitted to eTIMS) and Input VAT (KRA-matched
purchase invoices) by the KRA A-E tax bands using the same
``custom_total_taxable_amount`` / ``base_tax_amount_after_discount_amount``
fields that ``apply_tax_bands`` writes into every KRA payload.

This is what reconciles with what was sent to KRA — the previous implementation
hardcoded ``tax_rate = 16`` on every row and read
``base_total_taxes_and_charges`` (which sums freight, service charges and
every non-VAT row), so the totals could never agree with the transmitted
payloads.

Sign convention: credit notes (is_return=1) carry negative tax amounts in
ERPNext; we SUM with the natural sign so a refund lowers the day's VAT, just
as in the Z/X reports.
"""

import frappe
from frappe import _
from frappe.utils import flt

from kenya_etims_compliance.kenya_etims_compliance.utils.etims_utils import (
	KRA_TAX_BANDS,
)


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	summary = get_summary(data)
	return columns, data, None, chart, summary


def get_columns():
	return [
		{"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
		{"fieldname": "tax_code", "label": _("Tax Code"), "fieldtype": "Data", "width": 80},
		{"fieldname": "taxable_amount", "label": _("Taxable Amount"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "tax_rate", "label": _("Rate %"), "fieldtype": "Percent", "width": 80},
		{"fieldname": "tax_amount", "label": _("Tax Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "count", "label": _("Invoices"), "fieldtype": "Int", "width": 80},
	]


def get_data(filters):
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	company = filters.get("company")

	if not from_date or not to_date:
		return []

	# A-E band totals. Each value is the SUM of every tax row belonging to
	# that band, with the natural sign so credit notes reduce the totals.
	output_bands = _aggregate_sales_bands(from_date, to_date, company)
	supported_input_bands = _aggregate_purchase_bands(
		from_date, to_date, company, match_status="Matched"
	)
	at_risk_input_bands = _aggregate_purchase_bands(
		from_date, to_date, company, match_status="not matched"
	)

	# Counts for the summary columns.
	si_transmitted_count = _count_sales_transmitted(from_date, to_date, company)
	pi_matched_count = _count_purchase_with_status(from_date, to_date, company, "Matched")
	pi_unmatched_count = _count_purchase_with_status(
		from_date, to_date, company, ["not in", ["Matched", ""]]
	)

	data = []

	for code in KRA_TAX_BANDS:
		b = output_bands.get(code)
		if not b or (not b["taxable_amount"] and not b["tax_amount"]):
			continue
		data.append(
			{
				"category": "OUTPUT VAT (Sales)",
				"tax_code": code,
				"taxable_amount": b["taxable_amount"],
				"tax_rate": b["tax_rate"],
				"tax_amount": b["tax_amount"],
				"status": "Transmitted",
				"count": si_transmitted_count,
			}
		)

	for code in KRA_TAX_BANDS:
		b = supported_input_bands.get(code)
		if not b or (not b["taxable_amount"] and not b["tax_amount"]):
			continue
		data.append(
			{
				"category": "INPUT VAT (Supported)",
				"tax_code": code,
				"taxable_amount": b["taxable_amount"],
				"tax_rate": b["tax_rate"],
				"tax_amount": b["tax_amount"],
				"status": "KRA Matched",
				"count": pi_matched_count,
			}
		)

	for code in KRA_TAX_BANDS:
		b = at_risk_input_bands.get(code)
		if not b or (not b["taxable_amount"] and not b["tax_amount"]):
			continue
		data.append(
			{
				"category": "INPUT VAT (At Risk)",
				"tax_code": code,
				"taxable_amount": b["taxable_amount"],
				"tax_rate": b["tax_rate"],
				"tax_amount": b["tax_amount"],
				"status": "Not matched — may be rejected",
				"count": pi_unmatched_count,
			}
		)

	output_tax = sum(flt(d["tax_amount"]) for d in data if d["category"] == "OUTPUT VAT (Sales)")
	supported_tax = sum(flt(d["tax_amount"]) for d in data if d["category"] == "INPUT VAT (Supported)")
	net_vat = output_tax - supported_tax

	data.append(
		{
			"category": "NET VAT PAYABLE",
			"tax_code": "",
			"taxable_amount": sum(
				flt(d["taxable_amount"])
				for d in data
				if d["category"] in ("OUTPUT VAT (Sales)", "INPUT VAT (Supported)")
			),
			"tax_rate": "",
			"tax_amount": net_vat,
			"status": "Due by 20th",
			"count": "",
		}
	)

	return data


def _aggregate_sales_bands(from_date, to_date, company):
	"""Aggregate Sales Taxes and Charges rows by KRA A-E band.

	Sums the same fields ``apply_tax_bands`` sums in the KRA payload
	(``custom_total_taxable_amount`` / ``base_tax_amount_after_discount_amount``)
	with the natural sign so credit notes reduce the totals. The rate is
	taken from the linked Account row at query time, not hardcoded.
	"""
	company_clause = "AND par.company = %(company)s" if company else ""

	rows = frappe.db.sql(
		f"""
        SELECT
            child.custom_code AS tax_code,
            SUM(child.custom_total_taxable_amount) AS taxable_amount,
            SUM(child.base_tax_amount_after_discount_amount) AS tax_amount,
            acc.tax_rate AS tax_rate
        FROM `tabSales Taxes and Charges` child
        INNER JOIN `tabSales Invoice` par ON par.name = child.parent
        LEFT JOIN `tabAccount` acc ON acc.name = child.account_head
        WHERE child.custom_code IN %(codes)s
            AND par.docstatus = 1
            AND par.custom_update_invoice_in_tims = 1
            AND par.posting_date BETWEEN %(from_date)s AND %(to_date)s
            {company_clause}
        GROUP BY child.custom_code, acc.tax_rate
        """,
		{
			"codes": list(KRA_TAX_BANDS),
			"from_date": from_date,
			"to_date": to_date,
			"company": company,
		},
		as_dict=True,
	)

	return _collect_bands(rows)


def _aggregate_purchase_bands(from_date, to_date, company, match_status):
	"""Aggregate Purchase Taxes and Charges rows by KRA A-E band."""
	company_clause = "AND par.company = %(company)s" if company else ""

	if match_status == "Matched":
		match_clause = "AND par.custom_kra_match_status = 'Matched'"
	elif match_status == "not matched":
		match_clause = (
			"AND (par.custom_kra_match_status IS NULL "
			"OR par.custom_kra_match_status = '' "
			"OR par.custom_kra_match_status NOT IN ('Matched', 'Matched'))"
		)
	else:
		match_clause = ""

	rows = frappe.db.sql(
		f"""
        SELECT
            child.custom_code AS tax_code,
            SUM(child.custom_total_taxable_amount) AS taxable_amount,
            SUM(child.base_tax_amount_after_discount_amount) AS tax_amount,
            acc.tax_rate AS tax_rate
        FROM `tabPurchase Taxes and Charges` child
        INNER JOIN `tabPurchase Invoice` par ON par.name = child.parent
        LEFT JOIN `tabAccount` acc ON acc.name = child.account_head
        WHERE child.custom_code IN %(codes)s
            AND par.docstatus = 1
            AND par.posting_date BETWEEN %(from_date)s AND %(to_date)s
            {company_clause}
            {match_clause}
        GROUP BY child.custom_code, acc.tax_rate
        """,
		{
			"codes": list(KRA_TAX_BANDS),
			"from_date": from_date,
			"to_date": to_date,
			"company": company,
		},
		as_dict=True,
	)

	return _collect_bands(rows)


def _collect_bands(rows):
	"""Collapse per-rate rows into a single band entry; last rate wins."""
	bands = {}
	for row in rows:
		code = row.tax_code
		if code not in KRA_TAX_BANDS:
			continue
		acc = bands.setdefault(code, {"taxable_amount": 0.0, "tax_amount": 0.0, "tax_rate": 0.0})
		acc["taxable_amount"] += flt(row.taxable_amount)
		acc["tax_amount"] += flt(row.tax_amount)
		acc["tax_rate"] = flt(row.tax_rate)
	return bands


def _count_sales_transmitted(from_date, to_date, company):
	filters = {
		"docstatus": 1,
		"posting_date": ["between", [from_date, to_date]],
		"custom_update_invoice_in_tims": 1,
	}
	if company:
		filters["company"] = company
	return frappe.db.count("Sales Invoice", filters=filters) or 0


def _count_purchase_with_status(from_date, to_date, company, status):
	filters = {
		"docstatus": 1,
		"posting_date": ["between", [from_date, to_date]],
		"custom_kra_match_status": status,
	}
	if company:
		filters["company"] = company
	return frappe.db.count("Purchase Invoice", filters=filters) or 0


def get_summary(data):
	output_tax = sum(flt(d["tax_amount"]) for d in data if d["category"] == "OUTPUT VAT (Sales)")
	supported_tax = sum(flt(d["tax_amount"]) for d in data if d["category"] == "INPUT VAT (Supported)")
	at_risk_tax = sum(flt(d["tax_amount"]) for d in data if d["category"] == "INPUT VAT (At Risk)")

	return [
		{"value": output_tax, "label": _("Output VAT"), "datatype": "Currency"},
		{
			"value": supported_tax,
			"label": _("Supported Input VAT"),
			"datatype": "Currency",
			"indicator": "green",
		},
		{
			"value": at_risk_tax,
			"label": _("At-Risk Input VAT"),
			"datatype": "Currency",
			"indicator": "red",
		},
		{
			"value": output_tax - supported_tax,
			"label": _("Net VAT Payable"),
			"datatype": "Currency",
			"indicator": "blue",
		},
	]


def get_chart(data):
	output_tax = sum(flt(d["tax_amount"]) for d in data if d["category"] == "OUTPUT VAT (Sales)")
	supported_tax = sum(flt(d["tax_amount"]) for d in data if d["category"] == "INPUT VAT (Supported)")
	at_risk_tax = sum(flt(d["tax_amount"]) for d in data if d["category"] == "INPUT VAT (At Risk)")

	return {
		"data": {
			"labels": [_("Output VAT"), _("Supported Input"), _("At-Risk Input")],
			"datasets": [{"values": [output_tax, supported_tax, at_risk_tax]}],
		},
		"type": "bar",
		"colors": ["#2490ef", "#2ecc71", "#e74c3c"],
	}
