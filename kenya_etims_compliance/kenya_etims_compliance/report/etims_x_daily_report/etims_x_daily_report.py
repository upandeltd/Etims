# Copyright (c) 2026, Upande Ltd and contributors
# For license information, please see license.txt
"""X Daily Report (TIS Spec 15).

The X Report is an interim report showing data since the last Z Report.
Unlike the Z Report, it does not reset counters.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Count, Sum
from frappe.utils import getdate, now_datetime
from pypika import Order

# Reuse the Z Report's data generation logic
from kenya_etims_compliance.kenya_etims_compliance.report.etims_z_daily_report.etims_z_daily_report import (
	get_columns as z_get_columns,
)


def execute(filters=None):
	columns = z_get_columns()
	data, report_summary, chart = get_data(filters)
	return columns, data, None, chart, report_summary


def _filter_invoices(query, si, branch, company, last_z_date, today):
	"""Apply the shared Sales Invoice filters used by every X report query."""
	query = query.where(si.docstatus == 1).where(si.custom_update_invoice_in_tims == 1)
	if last_z_date:
		query = query.where(si.posting_date > last_z_date)
	# Always up to today
	query = query.where(si.posting_date <= today)
	if branch:
		query = query.where(si.custom_tax_branch_office == branch)
	if company:
		query = query.where(si.company == company)
	return query


def get_data(filters):
	branch = filters.get("branch")
	company = filters.get("company")

	# Determine the date range: from last Z report date to now
	last_z_date = _get_last_z_report_date(branch)
	today = getdate()

	data = []

	# Header
	company_name = company or frappe.defaults.get_user_default("Company")
	company_doc = frappe.get_cached_doc("Company", company_name) if company_name else None
	tis_info = {}
	if branch:
		tis_info = (
			frappe.db.get_value(
				"TIS Device Initialization",
				{"branch_id": branch, "active": 1},
				["pin", "sales_control_unit_id"],
				as_dict=True,
			)
			or {}
		)

	data.append({"category": "Report Type", "description": "X (Interim)", "count": None, "amount": None})
	data.append(
		{
			"category": "Since Last Z Report",
			"description": str(last_z_date) if last_z_date else "No previous Z Report",
			"count": None,
			"amount": None,
		}
	)
	data.append({"category": "Up To", "description": str(today), "count": None, "amount": None})
	data.append(
		{"category": "Generated At", "description": str(now_datetime()), "count": None, "amount": None}
	)
	if company_doc:
		data.append(
			{"category": "Trade Name", "description": company_doc.company_name, "count": None, "amount": None}
		)
		data.append(
			{"category": "PIN", "description": company_doc.tax_id or "", "count": None, "amount": None}
		)
	if tis_info:
		data.append(
			{
				"category": "TIS Designation",
				"description": tis_info.get("sales_control_unit_id", ""),
				"count": None,
				"amount": None,
			}
		)

	data.append({"category": "", "description": "", "count": None, "amount": None})

	# Receipt type breakdown — sign-correct (credit notes are negative in ERPNext)
	si = frappe.qb.DocType("Sales Invoice")
	receipt_label = Coalesce(si.custom_receipt_label, "NS")
	receipt_query = _filter_invoices(
		frappe.qb.from_(si).select(
			receipt_label.as_("label"),
			Count("*").as_("cnt"),
			Sum(si.base_grand_total).as_("total"),
		),
		si,
		branch,
		company,
		last_z_date,
		today,
	).groupby(receipt_label).orderby(receipt_label)
	receipt_data = receipt_query.run(as_dict=True)

	label_names = {
		"NS": "Normal Sale",
		"NC": "Normal Credit",
		"CS": "Copy Sale",
		"CC": "Copy Credit",
		"TS": "Training Sale",
		"TC": "Training Credit",
		"PS": "Proforma Sale",
	}

	data.append({"category": "RECEIPT TYPE BREAKDOWN", "description": "", "count": None, "amount": None})
	total_count = 0
	total_amount = 0
	for row in receipt_data:
		name = label_names.get(row.label, row.label)
		data.append(
			{"category": f"  {row.label}", "description": name, "count": row.cnt, "amount": row.total}
		)
		total_count += row.cnt
		total_amount += row.total or 0

	data.append({"category": "  TOTAL", "description": "", "count": total_count, "amount": total_amount})
	data.append({"category": "", "description": "", "count": None, "amount": None})

	# Tax breakdown — sign-correct (credit notes are negative)
	stc = frappe.qb.DocType("Sales Taxes and Charges")
	si = frappe.qb.DocType("Sales Invoice")
	tax_query = (
		frappe.qb.from_(stc)
		.inner_join(si)
		.on(si.name == stc.parent)
		.select(
			stc.custom_code.as_("tax_code"),
			Sum(stc.custom_total_taxable_amount).as_("taxable_amount"),
			Sum(stc.base_tax_amount_after_discount_amount).as_("tax_amount"),
		)
		.where(stc.custom_code.isnotnull())
		.where(stc.custom_code != "")
		.groupby(stc.custom_code)
		.orderby(stc.custom_code)
	)
	tax_data = _filter_invoices(tax_query, si, branch, company, last_z_date, today).run(as_dict=True)

	data.append({"category": "TAX BREAKDOWN BY RATE", "description": "", "count": None, "amount": None})
	total_taxable = 0
	total_tax = 0
	for row in tax_data:
		data.append(
			{
				"category": f"  Rate {row.tax_code} — Taxable",
				"description": "",
				"count": None,
				"amount": row.taxable_amount,
			}
		)
		data.append(
			{
				"category": f"  Rate {row.tax_code} — Tax",
				"description": "",
				"count": None,
				"amount": row.tax_amount,
			}
		)
		total_taxable += row.taxable_amount or 0
		total_tax += row.tax_amount or 0

	data.append({"category": "  Total Taxable", "description": "", "count": None, "amount": total_taxable})
	data.append({"category": "  Total Tax", "description": "", "count": None, "amount": total_tax})
	data.append({"category": "", "description": "", "count": None, "amount": None})
	# Payment breakdown — sign-correct; drop the AND sip.amount > 0 clause that
	# was hiding refund payment legs
	sip = frappe.qb.DocType("Sales Invoice Payment")
	si = frappe.qb.DocType("Sales Invoice")
	payment_total = Sum(sip.amount).as_("total")
	payment_query = (
		frappe.qb.from_(sip)
		.inner_join(si)
		.on(si.name == sip.parent)
		.select(
			sip.mode_of_payment,
			Count(si.name).distinct().as_("cnt"),
			payment_total,
		)
		.groupby(sip.mode_of_payment)
		.orderby(payment_total, order=Order.desc)
	)
	payment_data = _filter_invoices(payment_query, si, branch, company, last_z_date, today).run(as_dict=True)
	data.append({"category": "PAYMENT METHOD BREAKDOWN", "description": "", "count": None, "amount": None})

	for row in payment_data:
		data.append(
			{"category": f"  {row.mode_of_payment}", "description": "", "count": row.cnt, "amount": row.total}
		)

	# Summary
	report_summary = [
		{"value": total_count, "label": _("Transactions"), "datatype": "Int"},
		{"value": total_amount, "label": _("Gross Amount"), "datatype": "Currency"},
		{"value": total_tax, "label": _("Total Tax"), "datatype": "Currency"},
	]

	chart = None
	if receipt_data:
		chart = {
			"data": {
				"labels": [r.label for r in receipt_data],
				"datasets": [{"name": _("Amount"), "values": [r.total or 0 for r in receipt_data]}],
			},
			"type": "bar",
			"colors": ["#f39c12"],
		}

	return data, report_summary, chart


def _get_last_z_report_date(branch=None):
	"""Get the last Z report generation date from TIS Device Initialization.

	Falls back to None if no Z report has been generated yet.
	"""
	if branch:
		val = frappe.db.get_value(
			"TIS Device Initialization",
			{"branch_id": branch, "active": 1},
			"custom_last_z_report_date",
		)
		if val:
			return getdate(val)
	return None
