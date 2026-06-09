import json
import traceback

import frappe
import requests
from frappe import _
from frappe.utils import add_to_date, now_datetime

from kenya_etims_compliance.utils.etims_utils import eTIMS
from kenya_etims_compliance.utils.kra_client import KRAClient


def should_use_queue():
	"""Return whether the queue should be used based on eTIMS settings."""
	from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
		get_etims_settings,
	)

	settings = get_etims_settings()
	return settings.get("enable_queue", 1)


def enqueue_invoice(doc, payload, api_endpoint, branch_id=None):
	"""Create queue entry and enqueue background job.

	Args:
	    doc: The source document (Sales Invoice, Purchase Invoice, Stock Entry)
	    payload: Dict payload to send to KRA API
	    api_endpoint: KRA endpoint method name on KRAClient
	    branch_id: Optional branch ID for KRAClient

	Returns:
	    The created eTIMS Invoice Queue doc name
	"""
	queue_entry = frappe.get_doc(
		{
			"doctype": "eTIMS Invoice Queue",
			"reference_doctype": doc.doctype,
			"reference_name": doc.name,
			"status": "Queued",
			"api_endpoint": api_endpoint,
			"payload": json.dumps(payload, default=str),
			"branch_id": branch_id or "",
			"queued_at": now_datetime(),
		}
	)
	queue_entry.insert(ignore_permissions=True)

	# Set status on the source document
	frappe.db.set_value(
		doc.doctype,
		doc.name,
		{
			"custom_etims_queue_status": "Queued",
			"custom_etims_queue_entry": queue_entry.name,
		},
		update_modified=False,
	)

	frappe.enqueue(
		"kenya_etims_compliance.custom_methods.queue_processor.process_queue_entry",
		queue="short",
		queue_entry_name=queue_entry.name,
		enqueue_after_commit=True,
	)

	return queue_entry.name


def process_queue_entry(queue_entry_name):
	"""Process a single queue entry - called by background worker.

	Locks the row with FOR UPDATE to prevent duplicate processing.
	Calls the KRA API and updates both the queue entry and source document.
	"""
	# Lock the queue entry to prevent concurrent processing
	status = frappe.db.sql(
		"SELECT status FROM `tabeTIMS Invoice Queue` WHERE name=%s FOR UPDATE",
		queue_entry_name,
		as_dict=True,
	)
	if not status or status[0].status not in ("Queued", "Failed"):
		return  # Already processing or sent

	queue_entry = frappe.get_doc("eTIMS Invoice Queue", queue_entry_name)
	queue_entry.status = "Processing"
	queue_entry.processing_at = now_datetime()
	queue_entry.save(ignore_permissions=True)
	frappe.db.commit()

	# Update source doc status
	_update_source_status(queue_entry, "Processing")

	# Idempotency barrier: once KRA accepts the submission, the fiscal receipt
	# exists at KRA — a later failure must NEVER re-transmit (duplicate receipt).
	kra_accepted = False

	try:
		payload = json.loads(queue_entry.payload)
		client = KRAClient(branch_id=queue_entry.branch_id or None)

		# Connection pre-flight check (Spec 6.7)
		# NOTE: Some physical OSCU devices do not support selectOrgUsrInfo
		# and return 404. In that case we still attempt the actual submission
		# because saveTrnsSalesOsdc may work fine (the original app behaviour).
		if client.headers:
			status = client.check_status()
			error_msg = status.get("error", "")
			is_404_preflight = "404" in error_msg or "invalid JSON" in error_msg.lower()

			if not status.get("connected") and not is_404_preflight:
				# OSCU/VSCU is genuinely down — leave in Queued state for retry later
				queue_entry.reload()
				queue_entry.status = "Queued"
				queue_entry.last_error = f"Pre-flight check failed: {error_msg}"
				queue_entry.next_retry_at = _calculate_next_retry(queue_entry.retry_count or 0)
				queue_entry.save(ignore_permissions=True)
				frappe.db.commit()
				_update_source_status(queue_entry, "Queued")
				return

		# Fail fast if no authentication headers — prevents cryptic KRA error 900
		if not client.headers:
			raise ValueError(
				f"No active TIS Device Initialization found for branch '{queue_entry.branch_id or 'default'}'. "
				"Cannot send to KRA without authentication headers (tin, bhfId, cmcKey)."
			)

		# Call the appropriate KRA API method
		api_method = getattr(client, queue_entry.api_endpoint, None)
		if not api_method:
			raise ValueError(f"Unknown API endpoint: {queue_entry.api_endpoint}")

		result = api_method(payload)

		if "Error" in result:
			raise ValueError(result["Error"])

		# KRA accepted — past this point a failure must not downgrade to Failed.
		kra_accepted = True

		# Success
		queue_entry.status = "Sent"
		queue_entry.sent_at = now_datetime()
		queue_entry.response_data = json.dumps(result.get("Success", result), default=str)
		queue_entry.save(ignore_permissions=True)
		frappe.db.commit()

		# Update the source document with KRA response data
		_handle_success(queue_entry, result)

	except Exception as e:
		frappe.db.rollback()

		if kra_accepted:
			# KRA already accepted — only post-success processing (QR/receipt/
			# source-status) failed. Keep "Sent"; re-transmitting would create a
			# DUPLICATE fiscal receipt. The invoice may lack QR/signature until
			# reprocessed manually — this is logged loudly as a known residual.
			frappe.db.set_value(
				"eTIMS Invoice Queue",
				queue_entry_name,
				{"status": "Sent", "last_error": ("Post-success processing failed: " + str(e))[:2000]},
				update_modified=False,
			)
			frappe.db.commit()
			frappe.log_error(
				title=f"eTIMS post-success FAILED — kept Sent, NOT retried: {queue_entry.reference_name}"[:140],
				message=traceback.format_exc(),
			)
			return

		error_msg = str(e)[:2000]

		queue_entry.reload()
		queue_entry.status = "Failed"
		queue_entry.retry_count = (queue_entry.retry_count or 0) + 1
		queue_entry.last_error = error_msg
		queue_entry.next_retry_at = _calculate_next_retry(queue_entry.retry_count)
		queue_entry.save(ignore_permissions=True)
		frappe.db.commit()

		_update_source_status(queue_entry, "Failed", error_msg)

		frappe.log_error(
			title=f"eTIMS Queue Error: {queue_entry.reference_name}",
			message=traceback.format_exc(),
		)


# A fresh enqueue is processed by its enqueue_after_commit job within seconds;
# only treat a still-"Queued" entry as orphaned once it is older than this.
ORPHAN_QUEUED_MINUTES = 15

# A real process_queue_entry run finishes in well under a minute (API timeout is
# ~30s). Anything in "Processing" longer than this means the worker died mid-run.
PROCESSING_STALE_MINUTES = 30


def _reset_stuck_processing(now):
	"""Reset entries stuck in "Processing" (worker crashed mid-run) back to Queued.

	Safe to re-drive: if the crash happened AFTER KRA accepted, re-sending the same
	invcNo is rejected by KRA as a duplicate (error_codes "already submitted"), so
	no duplicate fiscal receipt is created — the entry lands Failed/incomplete and
	can be recovered via "Search Sales Transaction". The threshold is far beyond the
	API timeout so only dead workers are affected.
	"""
	stuck = frappe.get_all(
		"eTIMS Invoice Queue",
		filters={
			"status": "Processing",
			"processing_at": ["<", add_to_date(now, minutes=-PROCESSING_STALE_MINUTES)],
		},
		pluck="name",
	)
	for name in stuck:
		frappe.db.set_value(
			"eTIMS Invoice Queue",
			name,
			{"status": "Queued", "next_retry_at": now},
			update_modified=False,
		)
		frappe.log_error(
			title=f"eTIMS: reset stale Processing -> Queued: {name}"[:140],
			message="Worker likely crashed mid-run; re-queued. KRA rejects duplicate "
			"invcNo, so no duplicate receipt risk.",
		)
	if stuck:
		frappe.db.commit()
	return stuck


def retry_failed_invoices():
	"""Scheduled job (every 5 min): re-drive queue entries that are stuck.

	Rescues three classes, deduped:
	  1. "Failed" entries whose backoff (next_retry_at) has elapsed.
	  2. "Queued" entries reset by the pre-flight-down path (have next_retry_at).
	  3. Orphaned fresh enqueues whose enqueue_after_commit job was lost (worker
	     crash / redis flush): next_retry_at is null but queued_at is old.

	Double-picking a fresh entry is harmless — process_queue_entry's FOR UPDATE
	lock + status guard ("Queued"/"Failed" only) absorbs the race.
	"""
	now = now_datetime()
	cols = ["name", "retry_count", "max_retries"]

	# Reset dead-worker "Processing" entries to Queued first so they are rescued
	# by the Queued bucket below in this same run.
	_reset_stuck_processing(now)

	entries = frappe.get_all(
		"eTIMS Invoice Queue",
		filters={"status": "Failed", "next_retry_at": ["<=", now]},
		fields=cols, order_by="queued_at asc", limit=50,
	)
	entries += frappe.get_all(
		"eTIMS Invoice Queue",
		filters={"status": "Queued", "next_retry_at": ["<=", now]},
		fields=cols, order_by="queued_at asc", limit=50,
	)
	entries += frappe.get_all(
		"eTIMS Invoice Queue",
		filters={
			"status": "Queued",
			"next_retry_at": ["is", "not set"],
			"queued_at": ["<", add_to_date(now, minutes=-ORPHAN_QUEUED_MINUTES)],
		},
		fields=cols, order_by="queued_at asc", limit=50,
	)

	seen = set()
	for entry in entries:
		if entry.name in seen:
			continue
		seen.add(entry.name)
		if (entry.retry_count or 0) >= (entry.max_retries or 3):
			continue

		frappe.enqueue(
			"kenya_etims_compliance.custom_methods.queue_processor.process_queue_entry",
			queue="short",
			queue_entry_name=entry.name,
		)


@frappe.whitelist()
def get_queue_status():
	"""Return queue statistics for the dashboard."""
	frappe.has_permission("eTIMS Invoice Queue", "read", throw=True)
	stats = {}
	for status in ("Queued", "Processing", "Sent", "Failed", "Cancelled"):
		stats[status] = frappe.db.count("eTIMS Invoice Queue", filters={"status": status})
	stats["total"] = sum(stats.values())
	return stats


@frappe.whitelist()
def retry_single_entry(queue_entry_name):
	"""Manually retry a single failed queue entry."""
	frappe.has_permission("eTIMS Invoice Queue", "write", throw=True)
	entry = frappe.get_doc("eTIMS Invoice Queue", queue_entry_name)
	if entry.status != "Failed":
		frappe.throw(_("Only failed entries can be retried"))

	entry.status = "Queued"
	entry.next_retry_at = None
	entry.save(ignore_permissions=True)

	frappe.enqueue(
		"kenya_etims_compliance.custom_methods.queue_processor.process_queue_entry",
		queue="short",
		queue_entry_name=entry.name,
	)
	return {"status": "enqueued"}


@frappe.whitelist()
def bulk_retry_failed():
	"""Retry all failed entries that haven't exceeded max retries."""
	frappe.has_permission("eTIMS Invoice Queue", "write", throw=True)
	failed = frappe.get_all(
		"eTIMS Invoice Queue",
		filters={"status": "Failed"},
		fields=["name", "retry_count", "max_retries"],
	)
	count = 0
	for entry in failed:
		if (entry.retry_count or 0) < (entry.max_retries or 3):
			frappe.enqueue(
				"kenya_etims_compliance.custom_methods.queue_processor.process_queue_entry",
				queue="short",
				queue_entry_name=entry.name,
			)
			count += 1
	return {"enqueued": count}


def _calculate_next_retry(retry_count):
	"""Exponential backoff: 1m, 2m, 4m, 8m, 16m, 30m (cap)."""
	delay_minutes = min(2 ** (retry_count - 1), 30)
	return add_to_date(now_datetime(), minutes=delay_minutes)


def _update_source_status(queue_entry, status, error_msg=None):
	"""Update the source document's eTIMS queue status fields."""
	update_dict = {"custom_etims_queue_status": status}
	if error_msg:
		update_dict["custom_etims_last_error"] = error_msg[:2000]
		update_dict["custom_etims_retry_count"] = queue_entry.retry_count or 0
	frappe.db.set_value(
		queue_entry.reference_doctype,
		queue_entry.reference_name,
		update_dict,
		update_modified=False,
	)
	frappe.db.commit()


def _handle_success(queue_entry, result):
	"""Update the source document with KRA response data after successful API call.

	Mark status as "Sent" FIRST — KRA already accepted the submission, so the
	queue status must reflect that even if downstream work (QR/attachments/stock
	IO) fails. Wrap the supplementary work so a failure there does not leave the
	queue entry stuck on "Processing".
	"""
	_update_source_status(queue_entry, "Sent")

	data = result.get("Success") or {}
	doctype = queue_entry.reference_doctype
	docname = queue_entry.reference_name

	try:
		if doctype == "Sales Invoice":
			_handle_sales_invoice_success(docname, data, queue_entry)
		elif doctype == "Purchase Invoice":
			_handle_purchase_invoice_success(docname, data, queue_entry)
		elif doctype == "Stock Entry":
			_handle_stock_entry_success(docname, data, queue_entry)
	except Exception:
		frappe.log_error(
			title=f"eTIMS post-success processing failed: {docname}"[:140],
			message=traceback.format_exc(),
		)


def _handle_sales_invoice_success(docname, data, queue_entry):
	"""Update Sales Invoice with SCU response data, QR code, and sales receipt."""
	from kenya_etims_compliance.custom_methods.sales_invoice import (
		create_attachment,
		create_qr_code,
		create_sales_receipt,
		stockIOSaveReq,
	)

	doc = frappe.get_doc("Sales Invoice", docname)

	control_unit_date_time = eTIMS.strp_datetime_object(data.get("sdcDateTime"))
	control_unit_date = eTIMS.strp_date_object(data.get("sdcDateTime")[0:8])
	control_unit_time = eTIMS.strp_time_object(data.get("sdcDateTime")[8:14])

	doc.custom_current_receipt_number = data.get("curRcptNo")
	doc.custom_total_receipt_number = data.get("totRcptNo")
	doc.custom_internal_data = data.get("intrlData")
	doc.custom_receipt_signature = data.get("rcptSign")
	doc.custom_control_unit_date_time = control_unit_date_time
	doc.custom_control_unit_date = control_unit_date
	doc.custom_control_unit_time = control_unit_time

	client = KRAClient(branch_id=queue_entry.branch_id or None)
	file_name, qr_url = create_qr_code(
		client.headers.get("tin"),
		client.headers.get("bhfId"),
		data.get("rcptSign"),
	)
	attachment_url = create_attachment(file_name, doc.name)

	doc.custom_receipt_qr_code = attachment_url
	doc.custom_receipt_qr_url = qr_url
	doc.custom_update_sales_to_etims = 1

	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	# Notify any waiting POS terminal that this invoice is now signed.
	# Site-wide broadcast (no room/user args) — frontend filters by `invoice`.
	frappe.publish_realtime(
		"etims_invoice_signed",
		{
			"invoice": doc.name,
			"status": "Sent",
			"qr_url": doc.custom_receipt_qr_url,
		},
		after_commit=True,
	)

	create_sales_receipt(data, doc.name)

	# Trigger stock IO (synchronous, local branch operation)
	date_str = eTIMS.strf_date_object(doc.posting_date)
	try:
		stockIOSaveReq(doc, date_str)
	except Exception:
		frappe.log_error(
			title=f"eTIMS Stock IO Error (post-queue): {doc.name}",
			message=traceback.format_exc(),
		)


def _handle_purchase_invoice_success(docname, data, queue_entry):
	"""Update Purchase Invoice after successful KRA submission."""
	from kenya_etims_compliance.custom_methods.purchase_invoice import stockIOSaveReq
	from kenya_etims_compliance.utils.etims_utils import eTIMS

	doc = frappe.get_doc("Purchase Invoice", docname)
	doc.custom_item_updated_in_tims = 1
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	date_str = eTIMS.strf_date_object(doc.posting_date)
	try:
		stockIOSaveReq(doc, date_str)
	except Exception:
		frappe.log_error(
			title=f"eTIMS Stock IO Error (post-queue): {doc.name}",
			message=traceback.format_exc(),
		)


def _handle_stock_entry_success(docname, data, queue_entry):
	"""Update Stock Entry after successful KRA submission."""
	frappe.db.set_value(
		"Stock Entry",
		docname,
		{"custom_updated_in_etims": 1},
		update_modified=False,
	)
	frappe.db.commit()
