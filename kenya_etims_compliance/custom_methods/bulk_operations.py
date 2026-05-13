"""Bulk eTIMS operations — item registration, invoice submission, verification."""

import frappe
from frappe import _


@frappe.whitelist()
def bulk_register_items(items=None):
	"""Register multiple items to eTIMS in batch.

	Args:
		items: JSON list of item names, or None to auto-detect unregistered items
	"""
	frappe.has_permission("Item", "write", throw=True)
	import json

	from kenya_etims_compliance.custom_methods.item import validate_items_for_etims
	from kenya_etims_compliance.utils.etims_utils import eTIMS

	if isinstance(items, str):
		items = json.loads(items)

	if not items:
		items = frappe.get_all(
			"Item",
			filters={
				"custom_registered_in_tims": 0,
				"custom_item_classification_code": ["is", "set"],
				"disabled": 0,
			},
			fields=["name"],
			limit=200,
		)
		items = [i.name for i in items]

	# Pre-validate all items
	validation = validate_items_for_etims(items)
	valid_items = validation.get("valid", [])
	invalid_items = validation.get("invalid", [])

	if not valid_items:
		return {
			"total": len(items),
			"success": 0,
			"failed": len(items),
			"invalid": invalid_items,
		}

	total = len(valid_items)
	success = 0
	failed = 0

	for i, item_name in enumerate(valid_items):
		frappe.publish_realtime(
			"etims_bulk_progress",
			{
				"current": i + 1,
				"total": total,
				"item": item_name,
			},
		)

		result = eTIMS.itemSaveReq(item_name)
		if result and "Success" in result:
			success += 1
		else:
			failed += 1

	frappe.db.commit()
	return {
		"total": len(items),
		"success": success,
		"failed": failed + len(invalid_items),
		"invalid": invalid_items,
	}


@frappe.whitelist()
def bulk_submit_invoices(doctype, from_date=None, to_date=None):
	"""Submit unsubmitted invoices to eTIMS in batch."""
	frappe.has_permission("eTIMS Invoice Queue", "create", throw=True)
	flag_field = (
		"custom_update_invoice_in_tims" if doctype == "Sales Invoice" else "custom_update_purchase_in_tims"
	)

	filters = {
		flag_field: 1,
		"docstatus": 1,
		"custom_invoice_number": ["is", "not set"],
	}
	if from_date and to_date:
		filters["posting_date"] = ["between", [from_date, to_date]]

	invoices = frappe.get_all(doctype, filters=filters, fields=["name"], limit=100)

	total = len(invoices)
	queued = 0

	for inv in invoices:
		frappe.get_doc(
			{
				"doctype": "eTIMS Invoice Queue",
				"reference_doctype": doctype,
				"reference_name": inv.name,
				"api_endpoint": "saveTrnsSalesOsdc" if doctype == "Sales Invoice" else "insertTrnsPurchase",
				"status": "Queued",
			}
		).insert(ignore_permissions=True)
		queued += 1

	frappe.db.commit()
	return {"total": total, "queued": queued}


@frappe.whitelist()
def bulk_verify_purchase_invoices(from_date=None, to_date=None):
	"""Verify unverified Purchase Invoices with KRA in batch."""
	frappe.has_permission("Purchase Invoice", "write", throw=True)
	from kenya_etims_compliance.custom_methods.invoice_checker import check_invoice_validity

	filters = {
		"docstatus": 1,
		"custom_invoice_verified": 0,
	}
	if from_date and to_date:
		filters["posting_date"] = ["between", [from_date, to_date]]

	invoices = frappe.get_all(
		"Purchase Invoice",
		filters=filters,
		fields=["name", "custom_invoice_number", "custom_supplier_pin", "posting_date", "base_grand_total"],
		limit=100,
	)

	total = len(invoices)
	verified = 0
	failed = 0

	for i, inv in enumerate(invoices):
		frappe.publish_realtime(
			"etims_bulk_progress",
			{
				"current": i + 1,
				"total": total,
				"item": inv.name,
			},
		)

		if not inv.custom_supplier_pin or not inv.custom_invoice_number:
			failed += 1
			continue

		result = check_invoice_validity(
			invoice_no=str(inv.custom_invoice_number),
			supplier_pin=inv.custom_supplier_pin,
			invoice_date=str(inv.posting_date),
			total_amount=inv.base_grand_total,
		)

		if result and result.get("verified"):
			frappe.db.set_value(
				"Purchase Invoice",
				inv.name,
				{
					"custom_invoice_verified": 1,
					"custom_verification_date": frappe.utils.now_datetime(),
				},
				update_modified=False,
			)
			verified += 1
		else:
			failed += 1

	frappe.db.commit()
	return {"total": total, "verified": verified, "failed": failed}
