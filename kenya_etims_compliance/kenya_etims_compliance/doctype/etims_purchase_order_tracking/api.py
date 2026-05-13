# Copyright (c) 2026, Upande Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from kenya_etims_compliance.utils.permissions import can_modify_doctype


@frappe.whitelist()
def get_tracking_summary(purchase_order):
	"""Get tracking summary for a Purchase Order"""
	if not can_modify_doctype("eTIMS Purchase Order Tracking", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	tracking = frappe.db.get_value(
		"eTIMS Purchase Order Tracking",
		{"purchase_order": purchase_order},
		["name", "status", "invoice", "invoice_verified", "payment_entry"],
	)

	if tracking:
		return {
			"tracking_id": tracking[0],
			"status": tracking[1],
			"invoice": tracking[2],
			"verified": tracking[3],
			"paid": bool(tracking[4]),
		}

	return None


@frappe.whitelist()
def reconcile_invoice(invoice_name):
	"""Reconcile invoice with Purchase Order tracking"""
	if not can_modify_doctype("eTIMS Purchase Order Tracking", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	from kenya_etims_compliance.custom_methods.purchase_order import reconcile_purchase_with_invoice

	return reconcile_purchase_with_invoice(invoice_name)
