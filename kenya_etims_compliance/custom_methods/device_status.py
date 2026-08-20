import frappe
import requests
from frappe import _

from kenya_etims_compliance.utils.permissions import require


@frappe.whitelist()
def check_connection(branch_id=None):
	"""Check OSCU/VSCU connection status (Spec 6.8, 21.7.8).

	Whitelisted endpoint for the eTIMS Settings "Test Connection" button.

	Returns:
	    dict: {connected: bool, response_time_ms: int, error: str}
	"""
	# HIGH — read-only probe but fires a real KRA call. Gate to a write-or-
	# read on TIS Device Initialization so anonymous probes don't burn quota.
	require("TIS Device Initialization", "read")

	from kenya_etims_compliance.utils.kra_client import KRAClient

	try:
		client = KRAClient(branch_id=branch_id or None)
		if not client.headers:
			return {
				"connected": False,
				"response_time_ms": 0,
				"error": _("No active TIS Device Initialization found for this branch"),
			}
		return client.check_status()
	except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
		return {"connected": False, "response_time_ms": 0, "error": str(e)}


@frappe.whitelist()
def increment_copy_count(invoice_name):
	"""Increment the copy receipt count and set the copy flag (Spec 4.1.2).

	Returns:
	    dict: {count: int} — the new copy count
	"""
	# HIGH — ungated state-changing. Anyone with read on Sales Invoice
	# could bump the copy count and trigger a "Training" copy mode.
	require("Sales Invoice", "write")
	current = frappe.db.get_value("Sales Invoice", invoice_name, "custom_receipt_copy_count") or 0
	new_count = current + 1
	# Drop update_modified=False — the receipt-copy audit trail must keep
	# a Version row.
	frappe.db.set_value(
		"Sales Invoice",
		invoice_name,
		{
			"custom_receipt_copy_count": new_count,
		},
	)
	return {"count": new_count}

