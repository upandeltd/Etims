import frappe
import requests
from frappe import _


@frappe.whitelist()
def check_connection(branch_id=None):
	"""Check OSCU/VSCU connection status (Spec 6.8, 21.7.8).

	Whitelisted endpoint for the eTIMS Settings "Test Connection" button.

	Returns:
	    dict: {connected: bool, response_time_ms: int, error: str}
	"""
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
	current = frappe.db.get_value("Sales Invoice", invoice_name, "custom_receipt_copy_count") or 0
	new_count = current + 1
	frappe.db.set_value(
		"Sales Invoice",
		invoice_name,
		{
			"custom_receipt_copy_count": new_count,
		},
		update_modified=False,
	)
	return {"count": new_count}
