# Copyright (c) 2026, Upande Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class eTIMSPurchaseOrderTracking(Document):
    """eTIMS Purchase Order Tracking Document Controller

    Tracks Purchase Orders for audit trail and invoice reconciliation
    as part of Kenya's 2026 eTIMS tax compliance requirements.
    """

    def autoname(self):
        """Generate name automatically"""
        if self.purchase_order:
            self.name = f"PO-TRACK-{self.purchase_order}"

    def validate(self):
        """Validate document before saving"""
        # Ensure status is valid
        valid_statuses = ["Pending Invoice", "Invoiced", "Verified", "Paid"]
        if self.status and self.status not in valid_statuses:
            frappe.throw(f"Status must be one of: {', '.join(valid_statuses)}")

        # Validate amounts
        if self.total_amount and self.total_amount <= 0:
            frappe.throw("Total Amount must be greater than zero")

        if self.invoice_amount and self.invoice_amount <= 0:
            frappe.throw("Invoice Amount must be greater than zero")

    def on_update(self):
        """Update tracking information"""
        if not self.reconciled_by:
            self.reconciled_by = frappe.session.user
            self.reconciled_on = frappe.utils.now()

    def before_save(self):
        """Set items summary if not provided"""
        if not self.items_summary and self.purchase_order:
            self.items_summary = self.get_items_summary_from_po()

    def get_items_summary_from_po(self):
        """Get items summary from linked Purchase Order"""
        try:
            po = frappe.get_doc("Purchase Order", self.purchase_order)
            if po.items:
                item_names = [item.item_code for item in po.items[:3]]
                count = len(po.items)
                if count <= 3:
                    return f"{count} item(s): {', '.join(item_names)}"
                else:
                    return f"{count} item(s): {', '.join(item_names)} + {count - 3} more"
        except Exception as e:
            frappe.log_error("eTIMS: Purchase order tracking error", str(e))
            pass
        return "No items summary available"
