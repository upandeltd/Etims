import traceback

import frappe
from frappe.utils import add_days, cint, get_datetime, now, now_datetime

from kenya_etims_compliance.utils.kra_client import KRAClient


def fetch_kra_notices():
	"""Daily: Fetch new KRA notices from eTIMS."""
	from kenya_etims_compliance.utils.etims_utils import eTIMS

	if not eTIMS.get_headers():
		return

	result = KRAClient().post("selectNoticeList", {})
	if "Success" not in result or not result["Success"]:
		return

	notices = result["Success"]
	if isinstance(notices, dict):
		notices = notices.get("noticeList", [])

	for notice in notices or []:
		ntc_no = notice.get("ntcNo")
		if ntc_no and not frappe.db.exists("eTIMS Notice", {"notice_number": ntc_no}):
			frappe.get_doc(
				{
					"doctype": "eTIMS Notice",
					"notice_number": ntc_no,
					"title": notice.get("title", ""),
					"contents": notice.get("cont", ""),
					"detail_url": notice.get("dtlUrl", ""),
				}
			).insert(ignore_permissions=True)

	frappe.db.commit()


def verify_supplier_pins():
	"""Weekly: Batch verify active supplier PINs.

	HIGH (Jobs/scheduler): the old code made up to 100 sequential KRA calls in a
	single transaction, with a single trailing commit. On the 300s short-queue
	timeout ``execute_job`` rolled back the entire batch and the ``order_by``
	re-picked the same 100 next week — no progress was ever made. Fix:
	commit per supplier so the cursor (``custom_kra_pin_verified_date``) is
	advanced even if we time out, and break the work into batches so a single
	timeout can't erase progress on suppliers we already verified.
	"""
	from kenya_etims_compliance.utils.etims_utils import eTIMS

	BATCH_SIZE = 25

	TICK_BATCH = 100

	suppliers = frappe.get_all(
		"Supplier",
		filters={
			"disabled": 0,
			"custom_supplier_pin": ["is", "set"],
		},
		fields=["name", "custom_supplier_pin"],
		order_by="custom_kra_pin_verified_date asc",
		limit=TICK_BATCH,
	)

	if not suppliers:
		return

	verified = 0
	failed = 0

	for i, s in enumerate(suppliers):
		result = eTIMS.verify_supplier_pin(s.custom_supplier_pin)
		frappe.db.set_value(
			"Supplier",
			s.name,
			{
				"custom_kra_pin_verified": 1 if "Success" in result else 0,
				"custom_kra_pin_verified_date": frappe.utils.now_datetime(),
			},
			update_modified=False,
		)
		if "Success" in result:
			verified += 1
		else:
			failed += 1

		# Commit every BATCH_SIZE suppliers so a job timeout (or crash) does
		# not roll back suppliers we have already verified. The cursor is
		# advanced on every row, but a per-row commit would issue ~100 commits
		# per weekly tick — BATCH_SIZE keeps the DB load reasonable.
		if (i + 1) % BATCH_SIZE == 0:
			frappe.db.commit()

	frappe.db.commit()
	frappe.logger().info(
		"eTIMS verify_supplier_pins: verified=%s failed=%s of %s",
		verified,
		failed,
		len(suppliers),
	)


def fetch_purchase_transactions():
	"""Daily: pull KRA's purchase worklist and mirror it into the register.

	``selectTrnsPurchaseSalesList`` returns the purchases KRA holds against
	this PIN that have not yet been confirmed back with ``insertTrnsPurchase``
	- a worklist that drains on confirmation, not a change feed. So the request
	window is a rolling lookback and is deliberately never advanced forward: a
	high-water mark would permanently skip an invoice a supplier files late for
	an earlier date, and that invoice is exactly the one reconciliation must
	catch. Repeat rows are absorbed by the dedup below.
	"""
	if not frappe.db.exists("DocType", "eTIMS Purchase Register Entry"):
		return

	from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_purchase_information.etims_purchase_information import (
		upsert_purchase_invoice,
	)
	from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
		DEFAULT_PURCHASE_FETCH_LOOKBACK_DAYS,
		get_etims_settings,
	)
	from kenya_etims_compliance.utils.etims_utils import eTIMS

	lookback = (
		cint(get_etims_settings().get("purchase_fetch_lookback_days"))
		or DEFAULT_PURCHASE_FETCH_LOOKBACK_DAYS
	)
	window_start = add_days(now_datetime(), -lookback)

	# The stored timestamp is a record of the last look, not a high-water mark.
	# When it predates the rolling window - a site that has not fetched in
	# months, or a fresh install seeded with an old date - ask from the older
	# of the two so the gap is actually covered instead of quietly skipped.
	stored = frappe.db.get_single_value("eTIMS Purchase Information", "last_search_date_and_time")
	if stored:
		window_start = min(get_datetime(stored), window_start)

	last_req_dt = eTIMS.strf_datetime_format(window_start)

	result = KRAClient().post("selectTrnsPurchaseSalesList", {"lastReqDt": last_req_dt})
	if "Success" not in result or not result["Success"]:
		return

	data = result["Success"]
	invoices = (data.get("saleList") if isinstance(data, dict) else None) or []

	inserted = linked = failed = 0

	for idx, inv in enumerate(invoices):
		supplier_pin = inv.get("spplrTin", "")
		kra_inv_no = inv.get("spplrInvcNo", 0)

		try:
			sale_date = eTIMS.strp_date_object(inv.get("salesDt"))
		except (TypeError, ValueError) as e:
			# invoice_date is mandatory on the register entry, so a row with an
			# unparseable salesDt cannot be reconciled at all - drop it loudly
			# instead of failing the whole pull at insert time.
			failed += 1
			frappe.log_error(
				title="eTIMS: unparseable KRA salesDt",
				message=f"supplier={supplier_pin} invoice={kra_inv_no} salesDt={inv.get('salesDt')!r}: {e}",
			)
			continue

		# One malformed row must not cost the whole day's pull, and must not
		# take the rows already written down with it.
		save_point = f"etims_purchase_row_{idx}"
		frappe.db.savepoint(save_point)
		try:
			# KRA's own per-band decomposition and item lines live only here,
			# so store them even when the register row already exists -
			# reconciliation compares band by band, not on one total.
			etims_pinv = upsert_purchase_invoice(inv)

			existing = frappe.db.get_value(
				"eTIMS Purchase Register Entry",
				{"supplier_pin": supplier_pin, "kra_invoice_number": kra_inv_no},
				["name", "etims_purchase_invoice"],
				as_dict=True,
			)
			if existing:
				# Backfill the detail link on entries written before the raw
				# purchase document was stored alongside them.
				if etims_pinv and not existing.etims_purchase_invoice:
					frappe.db.set_value(
						"eTIMS Purchase Register Entry",
						existing.name,
						"etims_purchase_invoice",
						etims_pinv,
						update_modified=False,
					)
					linked += 1
				frappe.db.release_savepoint(save_point)
				continue

			frappe.get_doc(
				{
					"doctype": "eTIMS Purchase Register Entry",
					"supplier_pin": supplier_pin,
					"supplier_name": inv.get("spplrNm", ""),
					"kra_invoice_number": kra_inv_no,
					"invoice_date": sale_date,
					"total_amount": inv.get("totAmt", 0),
					"tax_amount": inv.get("totTaxAmt", 0),
					"item_count": inv.get("totItemCnt", 0),
					"etims_purchase_invoice": etims_pinv,
					"fetch_date": now_datetime(),
					"match_status": "Pending",
				}
			).insert(ignore_permissions=True)
			inserted += 1
			frappe.db.release_savepoint(save_point)
		except Exception:
			frappe.db.rollback(save_point=save_point)
			failed += 1
			frappe.log_error(
				title="eTIMS: purchase register row failed",
				message=f"supplier={supplier_pin} invoice={kra_inv_no}\n{traceback.format_exc()}",
			)

	# Stamped for the operator only - see the docstring on why it is not the
	# request key.
	frappe.db.set_single_value("eTIMS Purchase Information", "last_search_date_and_time", now())
	frappe.db.commit()

	frappe.logger().info(
		"eTIMS fetch_purchase_transactions: %s rows since %s - %s new, %s linked, %s failed",
		len(invoices),
		last_req_dt,
		inserted,
		linked,
		failed,
	)


def run_reconciliation_task():
	"""Daily (after fetch): Run purchase reconciliation for previous month."""
	if not frappe.db.exists("DocType", "eTIMS Purchase Register Entry"):
		return

	from kenya_etims_compliance.custom_methods.reconciliation import run_reconciliation

	result = run_reconciliation()
	frappe.logger().info("eTIMS Reconciliation: %s", result)


def calculate_supplier_scores():
	"""Weekly: Recalculate supplier compliance scores."""
	from kenya_etims_compliance.custom_methods.supplier_scoring import calculate_supplier_scores as calc

	result = calc()
	frappe.logger().info("Supplier scoring: %s", result)


def generate_compliance_score():
	"""Monthly: Generate compliance scorecard for previous month."""
	if not frappe.db.exists("DocType", "eTIMS Compliance Score"):
		return
	from kenya_etims_compliance.custom_methods.compliance_scoring import generate_monthly_score

	result = generate_monthly_score()
	frappe.logger().info("Compliance score: %s", result)


def fetch_import_items():
	"""Daily: Fetch and process pending import items from KRA."""
	from kenya_etims_compliance.custom_methods.import_workflow import fetch_and_process_imports

	result = fetch_and_process_imports()
	frappe.logger().info("Import items: %s", result)


def send_deadline_reminders():
	"""Daily: Send VAT filing deadline reminders (5 days and 1 day before 20th)."""
	from kenya_etims_compliance.custom_methods.notifications import send_filing_deadline_reminder

	send_filing_deadline_reminder()
