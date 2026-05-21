"""Supplier custom hooks for eTIMS compliance."""

import re

import frappe
from frappe import _
from frappe.utils import now_datetime

# KRA PIN format per eTIMS spec: letter (A or P) + 9 digits + uppercase letter
KRA_PIN_REGEX = re.compile(r"^[AP]\d{9}[A-Z]$")


@frappe.whitelist()
def verify_supplier(supplier_name):
	"""Verify the supplier's KRA PIN against KRA's master taxpayer database.

	Uses the developer.go.ke PIN Checker by PIN API (real validation, not
	branch-scoped). Stores the verification result on the Supplier doc.

	Returns:
	    {"status": "success", "message": "..."} when PIN is valid (Active)
	    {"status": "warning", "message": "..."} when PIN is valid but Suspended/Cancelled/Stopped
	    {"status": "error",   "message": "..."} when not found / invalid format / network error
	"""
	from kenya_etims_compliance.utils.pin_checker import check_pin

	supplier = frappe.get_doc("Supplier", supplier_name)
	pin = (supplier.get("custom_supplier_pin") or supplier.get("tax_id") or "").strip().upper()

	if not pin:
		return {"status": "error", "message": _("No PIN on this supplier. Set Tax ID or Supplier PIN first.")}

	result = check_pin(pin)
	if not result.get("valid"):
		return {"status": "error", "message": result.get("message", "PIN not found")}

	data = result["data"]
	status_of_pin = data.get("StatusOfPIN", "")

	# Write verification stamps back to the supplier
	updates = {
		"custom_kra_pin_verified": 1 if status_of_pin == "Active" else 0,
		"custom_kra_pin_verified_date": now_datetime(),
	}
	frappe.db.set_value("Supplier", supplier_name, updates, update_modified=False)

	if status_of_pin == "Active":
		return {
			"status": "success",
			"message": _("PIN verified — Active. Taxpayer: {0} ({1})").format(
				data.get("Name", "-"), data.get("TypeOfTaxpayer", "-")
			),
		}
	return {
		"status": "warning",
		"message": _("PIN is {0}. Taxpayer: {1}").format(status_of_pin, data.get("Name", "-")),
	}


def validate(doc, method):
	"""Validate the KRA PIN on Supplier save."""
	# Check both the standard tax_id field and the custom_supplier_pin field
	for fieldname, label in (("tax_id", "Tax ID"), ("custom_supplier_pin", "Supplier PIN")):
		pin = (doc.get(fieldname) or "").strip().upper()
		if not pin:
			continue
		# Auto-uppercase any lowercase input
		doc.set(fieldname, pin)
		if not KRA_PIN_REGEX.match(pin):
			frappe.throw(
				_("{0} <b>{1}</b> is not a valid KRA PIN. Expected format: letter (A or P) + 9 digits + uppercase letter (e.g. P051234567T).").format(
					label, pin
				),
				title=_("Invalid KRA PIN"),
			)
