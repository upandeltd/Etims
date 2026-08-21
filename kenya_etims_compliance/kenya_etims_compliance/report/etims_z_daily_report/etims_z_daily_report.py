# Copyright (c) 2026, Upande Ltd and contributors
# For license information, please see license.txt
"""Z Daily Report (TIS Spec 16).

The Z Report is the official end-of-day accounting record. It summarizes
all transactions for a given date and branch, grouped by receipt type,
tax rate, and payment method.
"""

import frappe
from frappe import _
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


def get_data(filters):
	report_date = getdate(filters.get("date")) if filters.get("date") else getdate()
	branch = filters.get("branch")
	company = filters.get("company")

	conditions = ["si.docstatus = 1", "si.posting_date = %(date)s", "si.custom_update_invoice_in_tims = 1"]
	params = {"date": report_date}

	if branch:
		conditions.append("si.custom_tax_branch_office = %(branch)s")
		params["branch"] = branch
	if company:
		conditions.append("si.company = %(company)s")
		params["company"] = company

	where = " AND ".join(conditions)

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
	receipt_data = frappe.db.sql(
		"""
        SELECT
            COALESCE(si.custom_receipt_label, 'NS') AS label,
            COUNT(*) AS cnt,
            SUM(si.base_grand_total) AS total
        FROM `tabSales Invoice` si
        WHERE {where}
        GROUP BY COALESCE(si.custom_receipt_label, 'NS')
        ORDER BY label
        """.format(where=where),
		params,
		as_dict=True,
	)

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

	data.append({"category": "  TOTAL", "description": "", "count": total_count, "amount": total_amount})
	data.append({"category": "", "description": "", "count": None, "amount": None})

	# --- Tax breakdown by rate (A-E) ---
	# Sign-correct: credit notes carry negative base_tax_amount_after_discount_amount;
	# SUM with the natural sign so a refund lowers Total Tax. Outer ABS would inflate.
	# Per apply_tax_bands the KRA payload uses abs() per row — that is the right place
	# to flip the sign, but the report must reflect the declared day's net.
	tax_data = frappe.db.sql(
		"""
        SELECT
            stc.custom_code AS tax_code,
            SUM(stc.custom_total_taxable_amount) AS taxable_amount,
            SUM(stc.base_tax_amount_after_discount_amount) AS tax_amount
        FROM `tabSales Taxes and Charges` stc
        INNER JOIN `tabSales Invoice` si ON si.name = stc.parent
        WHERE {where}
            AND stc.custom_code IS NOT NULL
            AND stc.custom_code != ''
        GROUP BY stc.custom_code
        ORDER BY stc.custom_code
        """.format(where=where),
		params,
		as_dict=True,
	)

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

	# --- Payment method breakdown ---

	payment_data = frappe.db.sql(
		"""
        SELECT
            sip.mode_of_payment,
            COUNT(DISTINCT si.name) AS cnt,
            SUM(sip.amount) AS total
        FROM `tabSales Invoice Payment` sip
        INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
        WHERE {where}
        GROUP BY sip.mode_of_payment
        ORDER BY total DESC
        """.format(where=where),
		params,
		as_dict=True,
	)

	data.append({"category": "PAYMENT METHOD BREAKDOWN", "description": "", "count": None, "amount": None})
	for row in payment_data:
		data.append(
			{"category": f"  {row.mode_of_payment}", "description": "", "count": row.cnt, "amount": row.total}
		)

	data.append({"category": "", "description": "", "count": None, "amount": None})

	# --- Discounts ---
	discount_data = frappe.db.sql(
		"""
        SELECT
            COUNT(*) AS cnt,
            SUM(si.custom_total_discount_amount) AS total_discount
        FROM `tabSales Invoice` si
        WHERE {where}
            AND si.custom_total_discount_amount != 0
        """.format(where=where),
		params,
		as_dict=True,
	)

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
	item_count = frappe.db.sql(
		"""
        SELECT SUM(ABS(sii.qty)) AS total_items
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE {where}
        """.format(where=where),
		params,
		as_dict=True,
	)

	data.append(
		{
			"category": "Total Items Sold",
			"description": "",
			"count": int(item_count[0].total_items or 0) if item_count else 0,
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

# --- Stamp the Z-report watermark so the X report knows the lower bound ---
# Without this write the X report silently aggregates all history while
# printing "No previous Z Report" (it reads custom_last_z_report_date, which
# nothing else in the app ever sets). Z is the end-of-day boundary that resets
# X; the watermark belongs on the device initialization record.
	if branch:
		frappe.db.set_value(
			"TIS Device Initialization",
			{"branch_id": branch, "active": 1},
			"custom_last_z_report_date",
			now_datetime(),
			update_modified=False,
	)


	return data, report_summary, chart
