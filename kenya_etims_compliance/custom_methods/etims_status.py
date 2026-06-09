import frappe

_FIELDS = [
    "custom_update_invoice_in_tims",
    "custom_etims_queue_status",
    "custom_update_sales_to_etims",
    "custom_receipt_qr_url",
    "custom_invoice_number",
]


@frappe.whitelist()
def get_etims_signing_status(invoice_name):
    """Read-only signing status for the POS wait-gate. Permission-checked."""
    frappe.has_permission("Sales Invoice", "read", doc=invoice_name, throw=True)
    row = frappe.db.get_value("Sales Invoice", invoice_name, _FIELDS, as_dict=True)
    if not row:
        return {
            "signing_enabled": False,
            "status": None,
            "signed": False,
            "qr_url": None,
            "invoice_number": None,
        }
    return {
        "signing_enabled": bool(row.get("custom_update_invoice_in_tims")),
        "status": row.get("custom_etims_queue_status"),
        "signed": bool(row.get("custom_update_sales_to_etims")),
        "qr_url": row.get("custom_receipt_qr_url"),
        "invoice_number": row.get("custom_invoice_number"),
    }
