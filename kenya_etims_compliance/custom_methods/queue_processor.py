import json
import traceback

import frappe
import requests
from frappe import _
from frappe.utils import add_to_date, now_datetime
from rq.timeouts import JobTimeoutException

from kenya_etims_compliance.custom_methods.notifications import send_queue_failure_alert
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
		queue="long",
		timeout=600,
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
	locked_status = frappe.db.sql(
		"SELECT status FROM `tabeTIMS Invoice Queue` WHERE name=%s FOR UPDATE",
		queue_entry_name,
		as_dict=True,
	)
	if not locked_status or locked_status[0].status not in ("Queued", "Failed"):
		return  # Already processing or sent

	queue_entry = frappe.get_doc("eTIMS Invoice Queue", queue_entry_name)

	# Cancel-guard (CRITICAL 3): the source doc may have been cancelled or
	# amended away after the queue entry was written but before we get here.
	# Without this check, a cancelled invoice still gets signed as a valid
	# sale. The cancel hook (InvoiceLifecycle) marks the entry Cancelled;
	# this guard also catches "docstatus dropped" cases the hook missed.
	try:
		ref_doc = frappe.get_doc(
			queue_entry.reference_doctype, queue_entry.reference_name
		)
		if ref_doc.docstatus != 1:
			queue_entry.status = "Cancelled"
			queue_entry.last_error = (
				f"Reference {queue_entry.reference_doctype} {queue_entry.reference_name} "
				f"is no longer submitted (docstatus={ref_doc.docstatus}). Skipping KRA submission."
			)
			queue_entry.save(ignore_permissions=True)
			frappe.db.commit()
			_update_source_status(queue_entry, "Cancelled")
			return
	except frappe.DoesNotExistError:
		queue_entry.status = "Cancelled"
		queue_entry.last_error = (
			f"Reference {queue_entry.reference_doctype} {queue_entry.reference_name} no longer exists."
		)
		queue_entry.save(ignore_permissions=True)
		frappe.db.commit()
		_update_source_status(queue_entry, "Cancelled")
		return

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
			preflight = client.check_status()
			error_msg = preflight.get("error", "")
			is_404_preflight = "404" in error_msg or "invalid JSON" in error_msg.lower()

			if not preflight.get("connected") and not is_404_preflight:
				# OSCU/VSCU is genuinely down — leave in Queued state for retry later.
				# CRITICAL 5 fix: bump retry_count so the exhaustion guard can fire.
				queue_entry.reload()
				queue_entry.retry_count = (queue_entry.retry_count or 0) + 1
				exhausted = queue_entry.retry_count >= (queue_entry.max_retries or 3)
				queue_entry.status = "Failed" if exhausted else "Queued"
				queue_entry.last_error = f"Pre-flight check failed: {error_msg}"
				queue_entry.next_retry_at = None if exhausted else _calculate_next_retry(queue_entry.retry_count)
				queue_entry.save(ignore_permissions=True)
				frappe.db.commit()
				_update_source_status(queue_entry, queue_entry.status)
				if queue_entry.status == "Failed":
					_handle_exhausted(queue_entry)
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

	except JobTimeoutException:
		# RQ timeout — let it propagate so the worker marks the job failed and
		# the scheduler can retry on the next tick. Do NOT swallow as Failed
		# (CRITICAL 5/timeout bug): the worker must NOT silently re-enqueue.
		frappe.db.rollback()
		raise
	except frappe.ValidationError:
		# Validation errors are deterministic and should bubble up to the user
		# (e.g. a stale branch_id after a credentials rotation). Retrying is
		# pointless and the original ValidationError is more informative than
		# a generic Failed retry path.
		frappe.db.rollback()
		raise
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
		queue_entry.retry_count = (queue_entry.retry_count or 0) + 1
		new_retry_count = queue_entry.retry_count
		queue_entry.status = "Failed"
		if new_retry_count >= (queue_entry.max_retries or 3):
			queue_entry.last_error = (
				f"Exhausted after {new_retry_count} attempts: {error_msg}"
			)
			queue_entry.next_retry_at = None
		else:
			queue_entry.last_error = error_msg
			queue_entry.next_retry_at = _calculate_next_retry(new_retry_count)
		frappe.db.commit()

		_update_source_status(queue_entry, "Failed", error_msg)

		frappe.log_error(
			title=f"eTIMS Queue Error: {queue_entry.reference_name}",
			message=traceback.format_exc(),
		)

		if queue_entry.status == "Failed" and new_retry_count >= (queue_entry.max_retries or 3):
			_handle_exhausted(queue_entry)


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
			queue="long",
			timeout=600,
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

	frappe.enqueue(
		"kenya_etims_compliance.custom_methods.queue_processor.process_queue_entry",
		queue="long",
		timeout=600,
		queue_entry_name=entry.name,
	)
	return {"status": "enqueued"}


@frappe.whitelist()
def bulk_retry_failed():
	"""Retry all failed entries that haven't exceeded max retries.

	HIGH (Jobs/scheduler): bound the batch (was unbounded — `get_all` defaults
	to unlimited and could enqueue thousands in a single HTTP request) and
	schedule the dispatch as a background job so the user request returns
	immediately instead of holding a transaction open across every enqueue.
	"""
	frappe.has_permission("eTIMS Invoice Queue", "write", throw=True)
	frappe.enqueue(
		"kenya_etims_compliance.custom_methods.queue_processor._bulk_retry_failed_job",
		queue="long",
		timeout=600,
	)
	return {"scheduled": True}


def _bulk_retry_failed_job():
	"""Background worker half of `bulk_retry_failed`.

	Processes at most 200 entries per tick — a runaway retry storm should not
	hammer KRA all at once. The next manual click resumes from where this left
	off (queue entries have stable ``name`` autoincrements).
	"""
	failed = frappe.get_all(
		"eTIMS Invoice Queue",
		filters={"status": "Failed"},
		fields=["name", "retry_count", "max_retries"],
		limit=200,
	)
	count = 0
	for entry in failed:
		if (entry.retry_count or 0) < (entry.max_retries or 3):
			frappe.enqueue(
				"kenya_etims_compliance.custom_methods.queue_processor.process_queue_entry",
				queue="long",
				timeout=600,
				queue_entry_name=entry.name,
			)
			count += 1
	return {"enqueued": count}


def _calculate_next_retry(retry_count):
	"""Exponential backoff: 1m, 2m, 4m, 8m, 16m, 30m (cap).

	HIGH (Jobs/scheduler): with retry_count=0 the old `2 ** (retry_count - 1)`
	produced 2**-1 = 0.5 — pinned at the floor — combined with the CRITICAL 5
	pre-flight path that pinned every retry at 30s forever. Clamp the minimum
	at 1 minute and cap at 30 minutes.
	"""
	delay_minutes = min(max(2 ** (retry_count - 1), 1), 30)
	return add_to_date(now_datetime(), minutes=delay_minutes)



def _handle_exhausted(queue_entry):
	"""Mark an exhausted queue entry and notify the eTIMS administrators.

	CRITICAL 6: the old path left exhausted entries on Failed with no alert —
	a 10-minute outage would silently abandon every invoice queued in that
	window. The DocType status options are
	``Queued / Processing / Sent / Failed / Cancelled``; per the project
	contract we use ``Failed`` as the terminal status (no dedicated
	``Exhausted`` option exists in the JSON) and rely on the explicit
	"Exhausted after N attempts" prefix on ``last_error`` plus this alert to
	flag the entry for operator attention. Re-running this helper is a no-op:
	the entry is already Failed and the alert is re-fireable, so a manual
	retry + re-exhaustion sends a fresh alert.
	"""
	try:
		send_queue_failure_alert(queue_entry.name)
	except Exception:
		frappe.log_error(
			title=f"eTIMS exhausted alert FAILED: {queue_entry.reference_name}"[:140],
			message=traceback.format_exc(),
		)


# HIGH (Jobs/scheduler): bounded retention for terminal entries. Without this
# the queue grows one row per invoice forever and is polled four times per
# scheduler tick on unindexed columns. Sent + Failed entries older than this
# are deleted (their KRA fiscal receipt is already in the eTIMS Notice /
# register tables; the queue row is just a transient audit pointer).
# Cancelled entries are kept for 30 days to give operators time to investigate
# a cancellation that fired after the queue was already populated.
TERMINAL_RETENTION_DAYS = 90
CANCELLED_RETENTION_DAYS = 30
FAILED_RETENTION_DAYS = 180


def cleanup_terminal_queue_entries():
	"""Daily scheduler: prune terminal eTIMS Invoice Queue entries.

	HIGH (Jobs/scheduler): without this the table grows one row per invoice
	forever and is polled four times per scheduler tick on unindexed columns.
	Retention windows:
	  - Sent:   90 days (KRA fiscal receipt lives in the register tables; the
	            queue row is just a transient audit pointer).
	  - Cancelled: 30 days (give operators time to investigate a cancellation
	               that fired after the queue was already populated).
	  - Failed: 180 days (long — Failed entries are the ones that triggered
	            an operator alert; we keep the trail through audit cycles).
	"""
	now = now_datetime()
	sent_cutoff = add_to_date(now, days=-TERMINAL_RETENTION_DAYS)
	cancelled_cutoff = add_to_date(now, days=-CANCELLED_RETENTION_DAYS)
	failed_cutoff = add_to_date(now, days=-FAILED_RETENTION_DAYS)

	sent_deleted = frappe.db.delete(
		"eTIMS Invoice Queue",
		{"status": "Sent", "sent_at": ["<", sent_cutoff]},
	)
	cancelled_deleted = frappe.db.delete(
		"eTIMS Invoice Queue",
		{"status": "Cancelled", "modified": ["<", cancelled_cutoff]},
	)
	failed_deleted = frappe.db.delete(
		"eTIMS Invoice Queue",
		{"status": "Failed", "modified": ["<", failed_cutoff]},
	)

	if sent_deleted or cancelled_deleted or failed_deleted:
		frappe.db.commit()
		frappe.logger().info(
			"eTIMS queue retention: deleted Sent=%s Cancelled=%s Failed=%s",
			sent_deleted,
			cancelled_deleted,
			failed_deleted,
		)
	return {
		"sent_deleted": sent_deleted,
		"cancelled_deleted": cancelled_deleted,
		"failed_deleted": failed_deleted,
	}


def _update_source_status(queue_entry, status, error_msg=None, commit=True):
	"""Update the source document's eTIMS queue status fields.

	``commit=False`` leaves the write in the caller's transaction so it can be
	made atomic with related work.
	"""
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
	if commit:
		frappe.db.commit()


def _handle_success(queue_entry, result):
	"""Update the source document with KRA response data after successful API call.

	KRA has already accepted the submission, so "Sent" must survive whatever
	happens below — re-transmitting would create a duplicate fiscal receipt.

	The status write is deliberately left uncommitted so it lands in the SAME
	transaction as the signature/QR its sub-handler writes. Committing "Sent"
	first opened a window in which a poller could read a Sent row whose invoice
	still had no signature. If the supplementary work fails we roll its partial
	writes back, persist "Sent" alone, and leave the rest to
	``repair_sent_without_signature``.
	"""
	data = result.get("Success") or {}
	doctype = queue_entry.reference_doctype
	docname = queue_entry.reference_name

	_update_source_status(queue_entry, "Sent", commit=False)

	try:
		if doctype == "Sales Invoice":
			_handle_sales_invoice_success(docname, data, queue_entry)
		elif doctype == "Purchase Invoice":
			_handle_purchase_invoice_success(docname, data, queue_entry)
		elif doctype == "Stock Entry":
			_handle_stock_entry_success(docname, data, queue_entry)
		else:
			# No sub-handler for this doctype — nothing else will commit.
			frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		_update_source_status(queue_entry, "Sent")
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


# A Sales Invoice is only fully fiscalised once the SCU signature landed on the
# document. `_handle_success` deliberately swallows a post-success failure so a
# QR/attachment error cannot bounce an already-accepted entry back to Failed and
# re-POST it (that would mint a DUPLICATE fiscal receipt at KRA). The cost is a
# durable split-brain: the queue row says Sent, the invoice has no signature, no
# QR and no receipt, and nothing ever retries it. This window also opens on a
# hard worker kill between the Sent commit and `_handle_success`.
REPAIR_LOOKBACK_DAYS = 7


def repair_sent_without_signature():
	"""Hourly scheduler: replay post-success work for Sent-but-unsigned entries.

	Replays from the queue row's stored `response_data`, so KRA is never
	contacted and no second fiscal receipt can be created. Idempotent: an entry
	whose invoice already carries the signature is skipped, and each replay is
	the same code path the worker would have run.
	"""
	cutoff = add_to_date(now_datetime(), days=-REPAIR_LOOKBACK_DAYS)
	candidates = frappe.get_all(
		"eTIMS Invoice Queue",
		filters={
			"status": "Sent",
			"reference_doctype": "Sales Invoice",
			"sent_at": [">", cutoff],
		},
		fields=["name", "reference_name", "response_data"],
		limit=200,
	)

	repaired = 0
	for entry in candidates:
		if not entry.response_data:
			continue
		if frappe.db.get_value(
			"Sales Invoice", entry.reference_name, "custom_receipt_signature"
		):
			continue

		try:
			data = json.loads(entry.response_data)
		except (ValueError, TypeError):
			continue
		if not data.get("sdcDateTime"):
			# Not a signing response (e.g. a stock-master ack) — nothing to replay.
			continue

		queue_entry = frappe.get_doc("eTIMS Invoice Queue", entry.name)
		try:
			_handle_sales_invoice_success(entry.reference_name, data, queue_entry)
			frappe.db.commit()
			repaired += 1
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title=f"eTIMS repair replay failed: {entry.reference_name}"[:140],
				message=traceback.format_exc(),
			)

	if repaired:
		frappe.logger().info(f"eTIMS: repaired {repaired} Sent-but-unsigned invoice(s)")
	return repaired
