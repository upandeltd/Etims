# Copyright (c) 2026, Upande Ltd and contributors
# For license information, please see license.txt

import frappe


@frappe.whitelist()
def get_tracking_summary(purchase_order):
	"""Get tracking summary for a Purchase Order"""
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
	from kenya_etims_compliance.custom_methods.purchase_order import reconcile_purchase_with_invoice

	return reconcile_purchase_with_invoice(invoice_name)
