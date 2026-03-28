import frappe


def retry_failed_submissions():
    """Hourly: Retry invoices that failed eTIMS submission."""
    for doctype, flag_field in [
        ("Sales Invoice", "custom_update_invoice_in_tims"),
        ("Purchase Invoice", "custom_update_purchase_in_tims"),
    ]:
        failed = frappe.get_all(
            doctype,
            filters={flag_field: 1, "docstatus": 1},
            fields=["name", "custom_invoice_number"],
            limit=50,
        )
        for doc in failed:
            if not doc.custom_invoice_number:
                try:
                    method = (
                        "kenya_etims_compliance.custom_methods.sales_invoice.trnsSalesSaveWrReq"
                        if doctype == "Sales Invoice"
                        else "kenya_etims_compliance.custom_methods.purchase_invoice.trnsPurchaseSaveReq"
                    )
                    frappe.enqueue(method, docname=doc.name, queue="short")
                except Exception:
                    frappe.log_error(title=f"eTIMS Retry Failed: {doc.name}")
    frappe.db.commit()


def fetch_kra_notices():
    """Daily: Fetch new KRA notices from eTIMS."""
    from kenya_etims_compliance.utils.etims_utils import eTIMS

    headers = eTIMS.get_headers()
    if not headers:
        return

    result = eTIMS.make_request("selectNoticeList", {}, headers)
    if "Success" not in result or not result["Success"]:
        return

    notices = result["Success"]
    if isinstance(notices, dict):
        notices = notices.get("noticeList", [])

    for notice in (notices or []):
        ntc_no = notice.get("ntcNo")
        if ntc_no and not frappe.db.exists("eTIMS Notice", {"notice_number": ntc_no}):
            frappe.get_doc({
                "doctype": "eTIMS Notice",
                "notice_number": ntc_no,
                "title": notice.get("title", ""),
                "contents": notice.get("cont", ""),
                "detail_url": notice.get("dtlUrl", ""),
            }).insert(ignore_permissions=True)

    frappe.db.commit()


def verify_supplier_pins():
    """Weekly: Batch verify active supplier PINs."""
    from kenya_etims_compliance.utils.etims_utils import eTIMS

    suppliers = frappe.get_all("Supplier", filters={
        "disabled": 0,
        "custom_supplier_pin": ["is", "set"],
    }, fields=["name", "custom_supplier_pin"],
       order_by="custom_kra_pin_verified_date asc",
       limit=100)

    for s in suppliers:
        result = eTIMS.verify_supplier_pin(s.custom_supplier_pin)
        frappe.db.set_value("Supplier", s.name, {
            "custom_kra_pin_verified": 1 if "Success" in result else 0,
            "custom_kra_pin_verified_date": frappe.utils.now_datetime(),
        }, update_modified=False)

    frappe.db.commit()


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

    result = eTIMS.make_request("selectTrnsPurchaseSalesList", {"lastReqDt": last_fetch})
    if "Success" not in result or not result["Success"]:
        return

    data = result["Success"]
    invoices = data.get("saleList") if isinstance(data, dict) else []

    for inv in (invoices or []):
        supplier_pin = inv.get("spplrTin", "")
        kra_inv_no = inv.get("spplrInvcNo", 0)

        if frappe.db.exists("eTIMS Purchase Register Entry", {
            "supplier_pin": supplier_pin, "kra_invoice_number": kra_inv_no,
        }):
            continue

        sale_date = None
        try:
            sale_date = eTIMS.strp_date_object(inv.get("salesDt"))
        except Exception:
            pass

        frappe.get_doc({
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
        }).insert(ignore_permissions=True)

    frappe.db.commit()


def run_reconciliation_task():
    """Daily (after fetch): Run purchase reconciliation for previous month."""
    if not frappe.db.exists("DocType", "eTIMS Purchase Register Entry"):
        return

    from kenya_etims_compliance.custom_methods.reconciliation import run_reconciliation
    result = run_reconciliation()
    frappe.logger().info("eTIMS Reconciliation: %s", result)


def process_submission_queue():
    """Every 15 min: Process queued eTIMS submissions with exponential backoff."""
    if not frappe.db.exists("DocType", "eTIMS Submission Queue"):
        return

    # Check circuit breaker
    failure_count = frappe.cache.get_value("etims_failures") or 0
    if failure_count >= 5:
        return

    now = frappe.utils.now_datetime()

    entries = frappe.get_all(
        "eTIMS Submission Queue",
        filters={
            "status": ["in", ["Queued", "Failed"]],
            "next_retry_at": ["<=", now],
        },
        fields=["name"],
        order_by="creation asc",
        limit=20,
    )

    # Also get entries with no next_retry_at (new entries)
    new_entries = frappe.get_all(
        "eTIMS Submission Queue",
        filters={
            "status": "Queued",
            "next_retry_at": ["is", "not set"],
        },
        fields=["name"],
        order_by="creation asc",
        limit=20,
    )

    all_entries = {e.name for e in entries} | {e.name for e in new_entries}

    for entry_name in all_entries:
        try:
            doc = frappe.get_doc("eTIMS Submission Queue", entry_name)
            doc.process()
        except Exception:
            frappe.log_error(title=f"Queue Processing Error: {entry_name}")


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
