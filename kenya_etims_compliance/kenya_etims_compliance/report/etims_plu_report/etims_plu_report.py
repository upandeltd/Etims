# Copyright (c) 2026, Upande Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
        {"label": _("Qty Sold"), "fieldname": "qty_sold", "fieldtype": "Float", "width": 100},
        {"label": _("Total Amount"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 130},
        {"label": _("Tax Code"), "fieldname": "tax_code", "fieldtype": "Data", "width": 80},
        {"label": _("Tax Amount"), "fieldname": "tax_amount", "fieldtype": "Currency", "width": 130},
        {"label": _("Net Amount"), "fieldname": "net_amount", "fieldtype": "Currency", "width": 130},
        {"label": _("Transaction Count"), "fieldname": "trx_count", "fieldtype": "Int", "width": 120},
    ]


def get_data(filters):
    conditions = get_conditions(filters)

    data = frappe.db.sql(
        """
        SELECT
            sii.item_code,
            sii.item_name,
            SUM(ABS(sii.qty)) AS qty_sold,
            SUM(ABS(sii.base_amount)) AS total_amount,
            sii.custom_tax_code AS tax_code,
            SUM(ABS(sii.base_amount) - ABS(sii.base_net_amount)) AS tax_amount,
            SUM(ABS(sii.base_net_amount)) AS net_amount,
            COUNT(DISTINCT si.name) AS trx_count
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1
            AND si.custom_update_invoice_in_tims = 1
            {conditions}
        GROUP BY sii.item_code, sii.custom_tax_code
        ORDER BY qty_sold DESC
        """.format(conditions=conditions),
        filters,
        as_dict=True,
    )

    return data


def get_conditions(filters):
    conditions = []

    if filters.get("from_date"):
        conditions.append("AND si.posting_date >= %(from_date)s")
    if filters.get("to_date"):
        conditions.append("AND si.posting_date <= %(to_date)s")
    if filters.get("company"):
        conditions.append("AND si.company = %(company)s")
    if filters.get("branch"):
        conditions.append("AND si.custom_tax_branch_office = %(branch)s")

    return " ".join(conditions)
