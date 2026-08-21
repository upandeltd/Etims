from datetime import datetime, time

import frappe

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
	"""Daily: Fetch KRA purchase data and create register entries."""
	if not frappe.db.exists("DocType", "eTIMS Purchase Register Entry"):
		return

	from kenya_etims_compliance.utils.etims_utils import eTIMS

	last_fetch = frappe.db.get_single_value("eTIMS Purchase Information", "last_search_date_and_time")
	if not last_fetch:
		last_fetch = "20260101000000"
	else:
		last_fetch = eTIMS.strf_datetime_format(last_fetch)

	result = KRAClient().post("selectTrnsPurchaseSalesList", {"lastReqDt": last_fetch})
	if "Success" not in result or not result["Success"]:
		return

	data = result["Success"]
	invoices = data.get("saleList") if isinstance(data, dict) else []

	inserted = 0
	max_sale_date = None

	for inv in invoices or []:
		supplier_pin = inv.get("spplrTin", "")
		kra_inv_no = inv.get("spplrInvcNo", 0)

		sale_date = None
		try:
			sale_date = eTIMS.strp_date_object(inv.get("salesDt"))
		except Exception as e:
			frappe.log_error("eTIMS: Task error", str(e))

		# Advance the watermark over every record the pull returned, not only
		# the newly inserted ones. A window whose newest row is already stored
		# would otherwise leave the watermark behind and be re-requested on
		# every tick.
		if sale_date and (max_sale_date is None or sale_date > max_sale_date):
			max_sale_date = sale_date

		if frappe.db.exists(
			"eTIMS Purchase Register Entry",
			{
				"supplier_pin": supplier_pin,
				"kra_invoice_number": kra_inv_no,
			},
		):
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
				"fetch_date": frappe.utils.now_datetime(),
				"match_status": "Pending",
			}
		).insert(ignore_permissions=True)
		inserted += 1

	frappe.db.commit()

	if max_sale_date:
		# `last_search_date_and_time` is a Datetime column, and the read at the
		# top of this function feeds `strf_datetime_format`, which only parses
		# "%Y-%m-%d %H:%M:%S[.%f]". KRA's `salesDt` is "%Y%m%d", so widen it to
		# a datetime here. Midnight of the newest day seen re-requests that day
		# on the next tick; the dedup check above absorbs the repeat.
		frappe.db.set_single_value(
			"eTIMS Purchase Information",
			"last_search_date_and_time",
			datetime.combine(max_sale_date, time.min).strftime("%Y-%m-%d %H:%M:%S"),
		)
		frappe.db.commit()
		frappe.logger().info(
			"eTIMS fetch_purchase_transactions: inserted %s, advanced watermark to %s",
			inserted,
			max_sale_date,
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
