# Copyright (c) 2026, Upande Ltd and contributors
# For license information, please see license.txt
"""X Daily Report (TIS Spec 15).

The X Report is an interim report showing data since the last Z Report.
Unlike the Z Report, it does not reset counters.
"""

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime

# Reuse the Z Report's data generation logic
from kenya_etims_compliance.kenya_etims_compliance.report.etims_z_daily_report.etims_z_daily_report import (
    get_columns as z_get_columns,
)


def execute(filters=None):
    columns = z_get_columns()
    data, report_summary, chart = get_data(filters)
    return columns, data, None, chart, report_summary


def get_data(filters):
    branch = filters.get("branch")
    company = filters.get("company")

    # Determine the date range: from last Z report date to now
    last_z_date = _get_last_z_report_date(branch)
    today = getdate()

    conditions = [
        "si.docstatus = 1",
        "si.custom_update_invoice_in_tims = 1",
    ]
    params = {}

    if last_z_date:
        conditions.append("si.posting_date > %(from_date)s")
        params["from_date"] = last_z_date
    # Always up to today
    conditions.append("si.posting_date <= %(to_date)s")
    params["to_date"] = today

    if branch:
        conditions.append("si.custom_tax_branch_office = %(branch)s")
        params["branch"] = branch
    if company:
        conditions.append("si.company = %(company)s")
        params["company"] = company

    where = " AND ".join(conditions)

    data = []

    # Header
    company_name = company or frappe.defaults.get_user_default("Company")
    company_doc = frappe.get_cached_doc("Company", company_name) if company_name else None
    tis_info = {}
    if branch:
        tis_info = frappe.db.get_value(
            "TIS Device Initialization", {"branch_id": branch, "active": 1},
            ["pin", "sales_control_unit_id"], as_dict=True
        ) or {}

    data.append({"category": "Report Type", "description": "X (Interim)", "count": None, "amount": None})
    data.append({"category": "Since Last Z Report", "description": str(last_z_date) if last_z_date else "No previous Z Report", "count": None, "amount": None})
    data.append({"category": "Up To", "description": str(today), "count": None, "amount": None})
    data.append({"category": "Generated At", "description": str(now_datetime()), "count": None, "amount": None})
    if company_doc:
        data.append({"category": "Trade Name", "description": company_doc.company_name, "count": None, "amount": None})
        data.append({"category": "PIN", "description": company_doc.tax_id or "", "count": None, "amount": None})
    if tis_info:
        data.append({"category": "TIS Designation", "description": tis_info.get("sales_control_unit_id", ""), "count": None, "amount": None})

    data.append({"category": "", "description": "", "count": None, "amount": None})

    # Receipt type breakdown
    receipt_data = frappe.db.sql(
        """
        SELECT
            COALESCE(si.custom_receipt_label, 'NS') AS label,
            COUNT(*) AS cnt,
            SUM(ABS(si.base_grand_total)) AS total
        FROM `tabSales Invoice` si
        WHERE {where}
        GROUP BY COALESCE(si.custom_receipt_label, 'NS')
        ORDER BY label
        """.format(where=where),
        params,
        as_dict=True,
    )

    label_names = {
        "NS": "Normal Sale", "NC": "Normal Credit",
        "CS": "Copy Sale", "CC": "Copy Credit",
        "TS": "Training Sale", "TC": "Training Credit",
        "PS": "Proforma Sale",
    }

    data.append({"category": "RECEIPT TYPE BREAKDOWN", "description": "", "count": None, "amount": None})
    total_count = 0
    total_amount = 0
    for row in receipt_data:
        name = label_names.get(row.label, row.label)
        data.append({"category": f"  {row.label}", "description": name, "count": row.cnt, "amount": row.total})
        total_count += row.cnt
        total_amount += row.total or 0

    data.append({"category": "  TOTAL", "description": "", "count": total_count, "amount": total_amount})
    data.append({"category": "", "description": "", "count": None, "amount": None})

    # Tax breakdown
    tax_data = frappe.db.sql(
        """
        SELECT
            stc.custom_code AS tax_code,
            SUM(ABS(stc.custom_total_taxable_amount)) AS taxable_amount,
            SUM(ABS(stc.base_tax_amount_after_discount_amount)) AS tax_amount
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
        data.append({"category": f"  Rate {row.tax_code} — Taxable", "description": "", "count": None, "amount": row.taxable_amount})
        data.append({"category": f"  Rate {row.tax_code} — Tax", "description": "", "count": None, "amount": row.tax_amount})
        total_taxable += row.taxable_amount or 0
        total_tax += row.tax_amount or 0

    data.append({"category": "  Total Taxable", "description": "", "count": None, "amount": total_taxable})
    data.append({"category": "  Total Tax", "description": "", "count": None, "amount": total_tax})
    data.append({"category": "", "description": "", "count": None, "amount": None})

    # Payment breakdown
    payment_data = frappe.db.sql(
        """
        SELECT
            sip.mode_of_payment,
            COUNT(DISTINCT si.name) AS cnt,
            SUM(ABS(sip.amount)) AS total
        FROM `tabSales Invoice Payment` sip
        INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
        WHERE {where}
            AND sip.amount > 0
        GROUP BY sip.mode_of_payment
        ORDER BY total DESC
        """.format(where=where),
        params,
        as_dict=True,
    )

    data.append({"category": "PAYMENT METHOD BREAKDOWN", "description": "", "count": None, "amount": None})
    for row in payment_data:
        data.append({"category": f"  {row.mode_of_payment}", "description": "", "count": row.cnt, "amount": row.total})

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
