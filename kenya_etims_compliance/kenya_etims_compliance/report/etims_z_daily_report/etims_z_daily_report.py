# Copyright (c) 2026, Upande Ltd and contributors
# For license information, please see license.txt
"""Z Daily Report (TIS Spec 16).

The Z Report is the official end-of-day accounting record. It summarizes
all transactions for a given date and branch, grouped by receipt type,
tax rate, and payment method.
"""

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Coalesce, Count, Sum
from frappe.utils import getdate, now_datetime


def execute(filters=None):
	columns = get_columns()
	data, report_summary, chart = get_data(filters)
	return columns, data, None, chart, report_summary


def get_columns():
	return [
		{"label": _("Category"), "fieldname": "category", "fieldtype": "Data", "width": 200},
		{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 250},
		{"label": _("Count"), "fieldname": "count", "fieldtype": "Int", "width": 80},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 150},
	]


def _filter_invoices(query, si, report_date, branch, company, docstatus=1):
	"""Apply the shared Sales Invoice filters used by every Z report query."""
	query = (
		query.where(si.docstatus == docstatus)
		.where(si.posting_date == report_date)
		.where(si.custom_update_invoice_in_tims == 1)
	)
	if branch:
		query = query.where(si.custom_tax_branch_office == branch)
	if company:
		query = query.where(si.company == company)
	return query


def get_data(filters):
	report_date = getdate(filters.get("date")) if filters.get("date") else getdate()
	branch = filters.get("branch")
	company = filters.get("company")

	data = []

	# --- Header info ---
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

	data.append({"category": "Report Type", "description": "Z (End-of-Day)", "count": None, "amount": None})
	data.append({"category": "Report Date", "description": str(report_date), "count": None, "amount": None})
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

	# --- Receipt type breakdown (NS/NC/CS/CC/TS/TC/PS) ---
	si = frappe.qb.DocType("Sales Invoice")
	receipt_label = Coalesce(si.custom_receipt_label, "NS")
	receipt_query = _filter_invoices(
		frappe.qb.from_(si).select(
			receipt_label.as_("label"),
			Count("*").as_("cnt"),
			Sum(si.base_grand_total).as_("total"),
		),
		si,
		report_date,
		branch,
		company,
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
		label = row.label
		name = label_names.get(label, label)
		data.append({"category": f"  {label}", "description": name, "count": row.cnt, "amount": row.total})
		total_count += row.cnt
		total_amount += row.total or 0

	# PS (Proforma Sale) receipts are draft (docstatus=0) invoices — get_receipt_label()
	# only ever returns "PS" pre-submit, so the submitted-only query above can never
	# surface them. Query drafts separately; shown informationally, NOT folded into
	# TOTAL below (a proforma isn't a completed sale).
	si = frappe.qb.DocType("Sales Invoice")
	ps_data = _filter_invoices(
		frappe.qb.from_(si).select(Count("*").as_("cnt"), Sum(si.base_grand_total).as_("total")),
		si,
		report_date,
		branch,
		company,
		docstatus=0,
	).run(as_dict=True)
	if ps_data and ps_data[0].cnt:
		data.append(
			{
				"category": "  PS",
				"description": "Proforma Sale (draft, not a completed sale)",
				"count": ps_data[0].cnt,
				"amount": ps_data[0].total,
			}
		)

	data.append({"category": "  TOTAL", "description": "", "count": total_count, "amount": total_amount})
	data.append({"category": "", "description": "", "count": None, "amount": None})

	# --- Tax breakdown by rate (A-E) ---
	# Sign-correct: credit notes carry negative base_tax_amount_after_discount_amount;
	# SUM with the natural sign so a refund lowers Total Tax. Outer ABS would inflate.
	# Per apply_tax_bands the KRA payload uses abs() per row — that is the right place
	# to flip the sign, but the report must reflect the declared day's net.
	stc = frappe.qb.DocType("Sales Taxes and Charges")
	si = frappe.qb.DocType("Sales Invoice")
	tax_query = (
		frappe.qb.from_(stc)
		.inner_join(si)
		.on(si.name == stc.parent)
		.select(
			stc.custom_code.as_("tax_code"),
			si.is_return.as_("is_return"),
			Sum(stc.custom_total_taxable_amount).as_("taxable_amount"),
			Sum(stc.base_tax_amount_after_discount_amount).as_("tax_amount"),
		)
		.where(stc.custom_code.isnotnull())
		.where(stc.custom_code != "")
		.groupby(stc.custom_code, si.is_return)
		.orderby(stc.custom_code)
		.orderby(si.is_return)
	)
	tax_data = _filter_invoices(tax_query, si, report_date, branch, company).run(as_dict=True)

	# TIS Spec §16.1.10/§16.1.11/§16.1.17 require Sale and Credit Note amounts
	# reported separately per band/payment method, never netted together.
	data.append({"category": "TAX BREAKDOWN BY RATE", "description": "", "count": None, "amount": None})
	total_taxable = 0
	total_tax = 0
	for row in tax_data:
		receipt_kind = "Credit Note" if row.is_return else "Sale"
		data.append(
			{
				"category": f"  Rate {row.tax_code} ({receipt_kind}) — Taxable",
				"description": "",
				"count": None,
				"amount": row.taxable_amount,
			}
		)
		data.append(
			{
				"category": f"  Rate {row.tax_code} ({receipt_kind}) — Tax",
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

	# --- Payment method breakdown ---

	sip = frappe.qb.DocType("Sales Invoice Payment")
	si = frappe.qb.DocType("Sales Invoice")
	payment_query = (
		frappe.qb.from_(sip)
		.inner_join(si)
		.on(si.name == sip.parent)
		.select(
			sip.mode_of_payment,
			si.is_return.as_("is_return"),
			Count(si.name).distinct().as_("cnt"),
			Sum(sip.amount).as_("total"),
		)
		.groupby(sip.mode_of_payment, si.is_return)
		.orderby(sip.mode_of_payment)
		.orderby(si.is_return)
	)
	payment_data = _filter_invoices(payment_query, si, report_date, branch, company).run(as_dict=True)

	data.append({"category": "PAYMENT METHOD BREAKDOWN", "description": "", "count": None, "amount": None})
	for row in payment_data:
		receipt_kind = "Credit Note" if row.is_return else "Sale"
		data.append(
			{
				"category": f"  {row.mode_of_payment} ({receipt_kind})",
				"description": "",
				"count": row.cnt,
				"amount": row.total,
			}
		)

	data.append({"category": "", "description": "", "count": None, "amount": None})

	# --- Discounts ---
	si = frappe.qb.DocType("Sales Invoice")
	discount_data = _filter_invoices(
		frappe.qb.from_(si).select(
			Count("*").as_("cnt"), Sum(si.custom_total_discount_amount).as_("total_discount")
		),
		si,
		report_date,
		branch,
		company,
	).where(si.custom_total_discount_amount != 0).run(as_dict=True)

	if discount_data and discount_data[0].total_discount:
		data.append(
			{
				"category": "DISCOUNTS",
				"description": "",
				"count": discount_data[0].cnt,
				"amount": discount_data[0].total_discount,
			}
		)
	else:
		data.append({"category": "DISCOUNTS", "description": "None", "count": 0, "amount": 0})

	# --- Item count ---
	# Signed, net per row (matching the tax breakdown's own documented sign
	# convention above): a credit note's negative qty must reduce, not inflate,
	# the count. ABS-then-SUM double counted returns as extra sales.
	sii = frappe.qb.DocType("Sales Invoice Item")
	si = frappe.qb.DocType("Sales Invoice")
	item_count_query = (
		frappe.qb.from_(sii)
		.inner_join(si)
		.on(si.name == sii.parent)
		.select(
			Sum(Case().when(sii.qty > 0, sii.qty).else_(0)).as_("sold"),
			Sum(Case().when(sii.qty < 0, -sii.qty).else_(0)).as_("returned"),
		)
	)
	item_count = _filter_invoices(item_count_query, si, report_date, branch, company).run(as_dict=True)

	data.append(
		{
			"category": "Total Items Sold",
			"description": "",
			"count": int(item_count[0].sold or 0) if item_count else 0,
			"amount": None,
		}
	)
	data.append(
		{
			"category": "Total Items Returned",
			"description": "",
			"count": int(item_count[0].returned or 0) if item_count else 0,
			"amount": None,
		}
	)

	# --- Opening Deposit (TIS Spec §16.1.12) ---
	# No POS Opening Entry / till-float workflow is wired to TIS branches in
	# this app, so there is no real figure to report. Show 0 rather than
	# inventing one; wire this to a cash-float doctype if the business starts
	# tracking it.
	data.append(
		{"category": "Opening Deposit", "description": "Not tracked by this app", "count": None, "amount": 0}
	)

	# --- Number of Incomplete Sales (TIS Spec §16.1.20) ---
	# "Incomplete sale" (started at the till, never finalized) has no tracked
	# signal here — a Sales Invoice document only exists once created, and a
	# draft (docstatus=0) is already reported above as PS. Show 0 rather than
	# a misleading proxy.
	data.append(
		{
			"category": "Number of Incomplete Sales",
			"description": "Not tracked by this app",
			"count": 0,
			"amount": None,
		}
	)

	# --- Report summary cards ---
	report_summary = [
		{"value": total_count, "label": _("Transactions"), "datatype": "Int"},
		{"value": total_amount, "label": _("Gross Amount"), "datatype": "Currency"},
		{"value": total_tax, "label": _("Total Tax"), "datatype": "Currency"},
	]

	# --- Chart ---
	chart = None
	if receipt_data:
		chart = {
			"data": {
				"labels": [r.label for r in receipt_data],
				"datasets": [{"name": _("Amount"), "values": [r.total or 0 for r in receipt_data]}],
			},
			"type": "bar",
			"colors": ["#2490ef"],
		}

	return data, report_summary, chart


@frappe.whitelist()
def close_z_report(date, branch, company=None):
	"""Explicitly close the Z report for ``date``/``branch``.

	This is the ONLY place allowed to stamp ``custom_last_z_report_date`` — a
	Z report is the immutable end-of-day closing record and the X report uses
	this watermark as its lower bound (etims_x_daily_report.py). Writing it as
	a side effect of merely viewing/filtering the report (the previous
	behavior) silently moved the boundary forward on every page load and
	corrupted the audit trail. This must be a deliberate, once-per-day action
	triggered from the report's "Close Z Report" button.
	"""
	if "System Manager" not in frappe.get_roles() and "eTIMS Administrator" not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	report_date = getdate(date)
	device = frappe.db.get_value(
		"TIS Device Initialization",
		{"branch_id": branch, "active": 1},
		["name", "custom_last_z_report_date"],
		as_dict=True,
	)
	if not device:
		frappe.throw(_("No active TIS Device Initialization found for branch {0}").format(branch))

	if device.custom_last_z_report_date and getdate(device.custom_last_z_report_date) >= report_date:
		frappe.throw(
			_("The Z report for {0} (branch {1}) is already closed as of {2}. It cannot be re-closed.").format(
				report_date, branch, device.custom_last_z_report_date
			)
		)

	frappe.db.set_value(
		"TIS Device Initialization",
		device.name,
		"custom_last_z_report_date",
		report_date,
		update_modified=False,
	)
	return {"status": "success", "closed_date": str(report_date), "branch": branch}
