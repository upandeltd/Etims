"""Bulk eTIMS operations — item registration, invoice submission, verification."""

import frappe
from frappe import _
from frappe.utils import flt

from kenya_etims_compliance.utils.permissions import require


@frappe.whitelist()
def bulk_update_and_register_items(items=None):
	"""Bulk "Update Item To TIMS" + register to KRA in one pass.

	For each selected item: pre-validate, then enable ``custom_update_item_to_tims``
	and save (which autofills the eTIMS fields via the before_save hook), then
	register the item to KRA. Invalid items are skipped and returned with their
	specific errors so the caller can show a summary.

	Args:
		items: JSON list of item names.

	Returns:
		{"total", "success", "failed", "invalid": [{"item", "errors": [...]}]}
	"""
	frappe.has_permission("Item", "write", throw=True)
	import json

	from kenya_etims_compliance.custom_methods.item import validate_item_for_etims
	from kenya_etims_compliance.utils.etims_utils import eTIMS

	if isinstance(items, str):
		items = json.loads(items)
	if not items:
		return {"total": 0, "success": 0, "failed": 0, "invalid": []}

	total = len(items)
	success = 0
	invalid = []

	for i, name in enumerate(items):
		frappe.publish_realtime(
			"etims_bulk_progress", {"current": i + 1, "total": total, "item": name}
		)

		# Skip & report: pre-validate with structured errors before mutating.
		check = validate_item_for_etims(name)
		if not check.get("valid"):
			invalid.append({"item": name, "errors": check.get("errors", [])})
			continue

		# Per-item savepoint so a failure rolls back ONLY this item, not the batch.
		frappe.db.savepoint("etims_bulk_item")
		try:
			doc = frappe.get_doc("Item", name)
			if not doc.custom_update_item_to_tims:
				# Triggers autofill_tims_info (before_save): validates + fills eTIMS fields.
				doc.custom_update_item_to_tims = 1
				doc.save()

			result = eTIMS.itemSaveReq(name)
			if result and "Success" in result:
				success += 1
			else:
				frappe.db.rollback(save_point="etims_bulk_item")
				err = (result or {}).get("Error") or _("KRA registration failed")
				invalid.append({"item": name, "errors": [err]})
		except Exception as e:
			frappe.db.rollback(save_point="etims_bulk_item")
			invalid.append({"item": name, "errors": [str(e)]})

	return {
		"total": total,
		"success": success,
		"failed": total - success,
		"invalid": invalid,
	}


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

	return {
		"total": len(items),
		"success": success,
		"failed": failed + len(invalid_items),
		"invalid": invalid_items,
	}


@frappe.whitelist()
def bulk_submit_invoices(doctype, from_date=None, to_date=None):
	"""Submit unsubmitted invoices to eTIMS in batch.

	CRITICAL 7: the old version wrote raw KRA wire names (``saveTrnsSalesOsdc``)
	into ``api_endpoint`` where the dispatcher expects the logical names
	``save_sales`` / ``insert_purchase``, and wrote no ``payload`` / ``branch_id``
	— so ``json.loads(None)`` blew up at queue_processor.py:99 and the
	``process_queue_entry`` job was never enqueued. Fix: build entries via
	the working single-invoice ``enqueue_invoice`` path so the dispatcher and
	processor can actually consume them.
	"""
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

	from kenya_etims_compliance.custom_methods.queue_processor import enqueue_invoice

	total = len(invoices)
	queued = 0
	failed = []

	for inv in invoices:
		try:
			doc = frappe.get_doc(doctype, inv.name)
			payload, branch_id = _build_invoice_payload(doc)
			api_endpoint = "save_sales" if doctype == "Sales Invoice" else "insert_purchase"
			enqueue_invoice(
				doc=doc,
				payload=payload,
				api_endpoint=api_endpoint,
				branch_id=branch_id,
			)
			queued += 1
		except Exception as e:
			failed.append({"invoice": inv.name, "error": str(e)[:500]})

	return {"total": total, "queued": queued, "failed": failed}


def _build_invoice_payload(doc):
	"""Build the KRA payload and resolve branch_id for ``bulk_submit_invoices``.

	Sales Invoices reuse the standalone ``build_sales_payload``. Purchase
	Invoices have no equivalent helper (the payload is inline in the
	``trnsPurchaseSaveReq`` hook owned by InvoiceLifecycle), so we inline the
	same dict here, reusing the existing ``etims_pur_item_list`` /
	``get_supplier_details`` / ``apply_tax_bands`` / ``purchase_return_information``
	helpers. ``abs(flt(...))`` is mandatory — ``custom_total_taxable_amount``
	is None until ERPNext's validate step runs (CRITICAL 18 None-arithmetic).
	"""
	if doc.doctype == "Sales Invoice":
		from kenya_etims_compliance.custom_methods.sales_invoice import build_sales_payload

		payload = build_sales_payload(doc)
		branch_id = None
		try:
			from kenya_etims_compliance.utils.kra_client import KRAClient

			branch_id = KRAClient()._get_user_branch_id()
		except Exception:
			frappe.log_error(
				title=f"eTIMS: bulk_submit branch lookup failed: {doc.name}"[:140],
				message=frappe.get_traceback(),
			)
		return payload, branch_id

	# Purchase Invoice path
	from datetime import datetime

	from kenya_etims_compliance.custom_methods.purchase_invoice import (
		etims_pur_item_list,
		get_supplier_details,
		get_tax_account_rate,
		purchase_return_information,
	)
	from kenya_etims_compliance.utils.etims_utils import apply_tax_bands, eTIMS

	supplier_details = get_supplier_details(doc.supplier)
	date_str = eTIMS.strf_date_object(doc.posting_date)
	date_time_str = datetime.now().strftime("%Y%m%d%H%M%S")
	conc_datetime_str = eTIMS.strf_datetime_format(doc.modified)

	count = len(doc.items or [])
	payload = {
		"invcNo": doc.custom_invoice_number,
		"orgInvcNo": doc.custom_original_invoice_number,
		"spplrTin": supplier_details.get("supp_pin"),
		"spplrBhfId": supplier_details.get("supp_bhid"),
		"spplrNm": doc.supplier,
		"spplrInvcNo": doc.bill_no,
		"regTyCd": doc.custom_registration_type_code,
		"pchsTyCd": doc.custom_purchase_type_code,
		"rcptTyCd": doc.custom_receipt_type_code,
		"pmtTyCd": doc.custom_payment_type_code,
		"pchsSttsCd": doc.custom_purchase_status_code,
		"cfmDt": date_time_str,
		"pchsDt": date_str,
		"totItemCnt": count,
		"totTaxblAmt": abs(flt(doc.custom_total_taxable_amount)),
		"totTaxAmt": abs(flt(doc.base_total_taxes_and_charges)),
		"totAmt": abs(flt(doc.grand_total)),
		"remark": doc.remarks,
		"regrId": doc.owner,
		"regrNm": doc.owner,
		"modrId": doc.modified_by,
		"modrNm": doc.modified_by,
		"itemList": etims_pur_item_list(doc),
	}
	apply_tax_bands(payload, doc.taxes, get_tax_account_rate)

	if getattr(doc, "is_return", 0) == 1:
		return_status = purchase_return_information(doc)
		if return_status == "partial":
			payload["rfdDt"] = conc_datetime_str
		elif return_status == "full":
			payload["wrhsDt"] = date_time_str
			payload["cnclReqDt"] = conc_datetime_str
			payload["cnclDt"] = conc_datetime_str

	branch_id = None
	try:
		from kenya_etims_compliance.utils.kra_client import KRAClient

		branch_id = KRAClient()._get_user_branch_id()
	except Exception:
		frappe.log_error(
			title=f"eTIMS: bulk_submit branch lookup failed: {doc.name}"[:140],
			message=frappe.get_traceback(),
		)
	return payload, branch_id


@frappe.whitelist()
def bulk_verify_purchase_invoices(from_date=None, to_date=None):
	"""Verify unverified Purchase Invoices with KRA in batch."""
	# CRITICAL 9 — bulk verification writes custom_invoice_verified=1 and the
	# payment-eligibility check (check_payment_eligibility) trusts that bit.
	# require() gives us the base write grant; we narrow further so a plain
	# Purchase Clerk cannot drive unlimited KRA traffic and trip the
	# site-global 5-failure circuit breaker (HIGH API/permissions finding).
	require("Purchase Invoice", "write")
	from kenya_etims_compliance.utils.permissions import is_etims_admin, is_etims_manager

	if not (is_etims_admin() or is_etims_manager()):
		frappe.throw(
			_("Bulk verification requires eTIMS Manager or Administrator role."),
			frappe.PermissionError,
		)

	# Bound the batch — HIGH finding noted that bulk endpoints can otherwise
	# fan-out to unlimited KRA calls.
	MAX_BATCH = 50

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
		limit=MAX_BATCH,
	)

	from kenya_etims_compliance.custom_methods.invoice_checker import check_invoice_validity

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
			# NOTE: drop update_modified=False so a tabVersion row is written
			# (audit trail). The C-4 commit is also dropped — Frappe commits
			# at end-of-request automatically; explicit commits inside a
			# whitelisted endpoint bypass the framework's rollback guarantee.
			frappe.db.set_value(
				"Purchase Invoice",
				inv.name,
				{
					"custom_invoice_verified": 1,
					"custom_verification_date": frappe.utils.now_datetime(),
				},
			)
			verified += 1
		else:
			failed += 1

	return {"total": total, "verified": verified, "failed": failed, "limit": MAX_BATCH}
