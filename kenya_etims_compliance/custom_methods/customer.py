import frappe
import requests
from frappe import _

from kenya_etims_compliance.utils.kra_client import KRAClient
from kenya_etims_compliance.utils.permissions import require


@frappe.whitelist()
def check_pin_with_kra(pin):
	"""Validate a KRA PIN via the developer.go.ke PIN Checker by PIN API.

	Validates against the full KRA iTax taxpayer registry (not branch-scoped).

	Returns:
	    {"found": True, "data": {pin, name, type, status}}
	    {"found": False, "message": "..."}
	"""
	# HIGH — this is a national taxpayer-registry oracle running on the
	# company's OAuth credentials with no rate limit. Gate it and bound it.
	require("Customer", "read")

	pin = (pin or "").strip().upper()
	if not pin:
		return {"found": False, "message": _("PIN is required"), "code": "EMPTY_PIN"}

	# Per-user rate limit: 30 calls / 5 minutes. The pin_checker service is
	# itself a shared resource, so we bound per session, not globally.
	cache_key = f"etims_pin_check:{frappe.session.user}"
	hits = frappe.cache.get_value(cache_key) or 0
	if int(hits) >= 30:
		frappe.throw(
			_("Too many PIN checks in the last 5 minutes. Please slow down."),
			frappe.RateLimitExceededError,
		)
	frappe.cache.set_value(cache_key, int(hits) + 1, expires_in_sec=300)

	from kenya_etims_compliance.utils.pin_checker import check_pin

	result = check_pin(pin)

	if result.get("valid"):
		d = result["data"]
		return {
			"found": True,
			"data": {
				"taxpayer_pin": d.get("KRAPIN"),
				"taxpayer_name": d.get("Name"),
				"taxpayer_type": d.get("TypeOfTaxpayer"),
				"status_of_pin": d.get("StatusOfPIN"),
			},
		}

	return {"found": False, "message": result.get("message"), "code": result.get("code")}


@frappe.whitelist()
def bhfCustSaveReq(doc_name):
	# HIGH — ungated, POSTs customer PII to KRA *before* the doc.save()
	# permission check is reached. Gate first so a denied caller never
	# triggers an outbound disclosure.
	require("Customer", "write")

	item = frappe.get_doc("Customer", doc_name)

	customer = {
		"custNo": item.get("custom_customer_number"),
		"custTin": item.get("tax_id"),
		"custNm": item.get("custom_customer_name"),
		"adrs": item.get("custom_address"),
		"telNo": item.get("custom_contact"),
		"email": item.get("custom_email"),
		"faxNo": item.get("custom_fax_number"),
		"useYn": item.get("custom_used_yn"),
		"remark": item.get("custom_remark"),
		"regrId": item.get("custom_registration_id"),
		"regrNm": item.get("custom_registration_name"),
		"modrId": item.get("custom_modifier_id"),
		"modrNm": item.get("custom_modifier_name"),
	}

	try:
		result = KRAClient().post("saveBhfCustomer", customer)

		if result.get("Error"):
			frappe.logger().debug("Customer registration error: {0}".format(result.get("Error")))
			return {"Error": result.get("Error")}

		item.custom_is_registered = 1
		item.save()

		return {"Success": result.get("Success")}

	except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
		frappe.log_error("eTIMS: Customer registration error", str(e))
		return {"Error": "Oops Bad Request!"}
