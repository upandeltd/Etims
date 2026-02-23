"""
Purchase Order Tracking Module for KRA eTIMS Compliance

This module tracks Purchase Orders for audit trail and invoice
reconciliation - an important part of the 2026 tax compliance
requirements.

While Purchase Orders may not sync directly to KRA, tracking them
ensures a complete audit trail from PO to invoice to payment.
"""

import frappe
from frappe import _
from kenya_etims_compliance.utils.etims_utils import eTIMS


@frappe.whitelist()
def send_purchase_order_to_etims(purchase_order_name):
    """Send purchase order to eTIMS for tracking

    Note: Purchase Orders may not need to sync to KRA directly,
    but we need to track them for when invoices are received.

    This creates a local record of the PO for reconciliation.

    Args:
        purchase_order_name: Purchase Order document name

    Returns:
        {
            "success": True/False,
            "tracking_id": "...",
            "message": "..."
        }
    """
    try:
        po = frappe.get_doc("Purchase Order", purchase_order_name)

        # Check if tracking already exists
        existing = frappe.db.exists("eTIMS Purchase Order Tracking", {
            "purchase_order": purchase_order_name
        })

        if existing:
            return {
                "success": True,
                "tracking_id": existing,
                "message": "Purchase Order already tracked"
            }

        # Create eTIMS tracking record
        tracking_doc = frappe.new_doc("eTIMS Purchase Order Tracking")
        tracking_doc.purchase_order = po.name
        tracking_doc.supplier = po.supplier
        tracking_doc.transaction_date = po.transaction_date
        tracking_doc.delivery_date = po.schedule_date or po.transaction_date
        tracking_doc.total_amount = po.grand_total
        tracking_doc.items_summary = get_items_summary(po.items)
        tracking_doc.status = "Pending Invoice"
        tracking_doc.insert()

        return {
            "success": True,
            "tracking_id": tracking_doc.name,
            "message": "Purchase Order tracking created"
        }

    except Exception as e:
        eTIMS.log_errors("PO Tracking Error", str(e))
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to track Purchase Order: {str(e)}"
        }


@frappe.whitelist()
def reconcile_purchase_with_invoice(invoice_name):
    """Match Purchase Invoice with original Purchase Order

    Called when Purchase Invoice is submitted to update the
    tracking record with the invoice details.

    Args:
        invoice_name: Purchase Invoice document name

    Returns:
        {
            "reconciled": True/False,
            "tracking_id": "...",
            "message": "..."
        }
    """
    try:
        invoice = frappe.get_doc("Purchase Invoice", invoice_name)

        if not invoice.purchase_order:
            return {
                "reconciled": False,
                "message": "No purchase order linked to this invoice"
            }

        # Find tracking record
        tracking = frappe.db.get_value("eTIMS Purchase Order Tracking", {
            "purchase_order": invoice.purchase_order
        })

        if tracking:
            tracking_doc = frappe.get_doc("eTIMS Purchase Order Tracking", tracking)
            tracking_doc.invoice = invoice_name
            tracking_doc.invoice_date = invoice.posting_date
            tracking_doc.invoice_amount = invoice.grand_total
            tracking_doc.invoice_verified = invoice.get("custom_invoice_verified", 0)
            tracking_doc.verification_date = invoice.get("custom_verification_date")

            # Update status based on verification
            if tracking_doc.invoice_verified:
                tracking_doc.status = "Verified"
            else:
                tracking_doc.status = "Invoiced"

            tracking_doc.save()

            return {
                "reconciled": True,
                "tracking_id": tracking,
                "message": "Invoice reconciled with Purchase Order"
            }

        return {
            "reconciled": False,
            "message": "No tracking record found for this Purchase Order"
        }

    except Exception as e:
        eTIMS.log_errors("PO Reconciliation Error", str(e))
        return {
            "reconciled": False,
            "error": str(e),
            "message": f"Failed to reconcile: {str(e)}"
        }


@frappe.whitelist()
def update_po_payment_status(invoice_name, payment_entry):
    """Update PO tracking when invoice is paid

    Called when Payment Entry is submitted for a Purchase Invoice.

    Args:
        invoice_name: Purchase Invoice document name
        payment_entry: Payment Entry document name

    Returns:
        {"success": True/False, "message": "..."}
    """
    try:
        invoice = frappe.get_doc("Purchase Invoice", invoice_name)

        if not invoice.purchase_order:
            return {
                "success": True,
                "message": "No PO linked - nothing to update"
            }

        # Find and update tracking record
        tracking = frappe.db.get_value("eTIMS Purchase Order Tracking", {
            "purchase_order": invoice.purchase_order
        })

        if tracking:
            tracking_doc = frappe.get_doc("eTIMS Purchase Order Tracking", tracking)
            tracking_doc.payment_entry = payment_entry
            tracking_doc.status = "Paid"
            tracking_doc.payment_date = frappe.utils.now()
            tracking_doc.save()

        return {
            "success": True,
            "message": "Payment status updated"
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def get_items_summary(items):
    """Get a summary of items in a PO or Invoice

    Args:
        items: List of item documents (from doc.items)

    Returns:
        String summary like "5 items: Item A, Item B, ..."
    """
    if not items:
        return "No items"

    item_names = [item.item_code for item in items[:5]]  # First 5 items
    count = len(items)

    if count <= 5:
        return f"{count} item(s): {', '.join(item_names)}"
    else:
        return f"{count} item(s): {', '.join(item_names)} + {count - 5} more"


@frappe.whitelist()
def get_po_tracking_summary(purchase_order):
    """Get tracking summary for a Purchase Order

    Useful for dashboard widgets and status indicators.

    Args:
        purchase_order: Purchase Order name

    Returns:
        {
            "tracked": True/False,
            "status": "...",
            "invoice": "...",
            "verified": True/False,
            "paid": True/False
        }
    """
    try:
        tracking = frappe.db.get_value("eTIMS Purchase Order Tracking", {
            "purchase_order": purchase_order
        })

        if not tracking:
            return {
                "tracked": False,
                "status": "Not Tracked"
            }

        tracking_doc = frappe.get_doc("eTIMS Purchase Order Tracking", tracking)

        return {
            "tracked": True,
            "status": tracking_doc.status,
            "invoice": tracking_doc.invoice,
            "verified": tracking_doc.invoice_verified,
            "paid": tracking_doc.status == "Paid",
            "tracking_id": tracking
        }

    except Exception as e:
        return {
            "tracked": False,
            "error": str(e)
        }


@frappe.whitelist()
def get_all_unreconciled_pos():
    """Get all Purchase Orders awaiting invoice reconciliation

    Useful for:
    - Dashboard reports
    - Follow-up with suppliers
    - Cash flow planning

    Returns:
        {
            "unreconciled_pos": [...],
            "count": n,
            "total_amount": xxx
        }
    """
    try:
        tracking_records = frappe.db.get_all(
            "eTIMS Purchase Order Tracking",
            filters={
                "status": ["in", ["Pending Invoice", "Invoiced"]]
            },
            fields=[
                "name",
                "purchase_order",
                "supplier",
                "transaction_date",
                "total_amount",
                "status",
                "invoice"
            ],
            order_by="transaction_date desc"
        )

        total_amount = sum(record.get("total_amount", 0) for record in tracking_records)

        return {
            "unreconciled_pos": tracking_records,
            "count": len(tracking_records),
            "total_amount": total_amount
        }

    except Exception as e:
        return {
            "unreconciled_pos": [],
            "count": 0,
            "total_amount": 0,
            "error": str(e)
        }


@frappe.whitelist()
def get_supplier_po_status(supplier):
    """Get Purchase Order status for a supplier

    Useful for supplier relationship management.

    Args:
        supplier: Supplier name

    Returns:
        {
            "supplier": "...",
            "total_pos": n,
            "pending_invoices": m,
            "invoiced_not_verified": k,
            "verified": j,
            "paid": p
        }
    """
    try:
        tracking_records = frappe.db.get_all(
            "eTIMS Purchase Order Tracking",
            filters={"supplier": supplier},
            fields=["status", "invoice_verified"]
        )

        pending_invoices = sum(1 for r in tracking_records if r.get("status") == "Pending Invoice")
        invoiced_not_verified = sum(1 for r in tracking_records if r.get("status") == "Invoiced")
        verified = sum(1 for r in tracking_records if r.get("status") == "Verified")
        paid = sum(1 for r in tracking_records if r.get("status") == "Paid")

        return {
            "supplier": supplier,
            "total_pos": len(tracking_records),
            "pending_invoices": pending_invoices,
            "invoiced_not_verified": invoiced_not_verified,
            "verified": verified,
            "paid": paid
        }

    except Exception as e:
        return {
            "error": str(e),
            "supplier": supplier
        }
