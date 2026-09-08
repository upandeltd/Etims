import frappe


@frappe.whitelist()
def submit_invoice(doc_name):

    # Get ALL merge logs linked to this POS Closing Entry
    merge_logs = frappe.get_all(
        "POS Invoice Merge Log",
        filters={
            "pos_closing_entry": doc_name
        },
        fields=["name", "consolidated_invoice"]
    )

    if not merge_logs:
        frappe.throw(
            f"No POS Invoice Merge Log found for POS Closing Entry {doc_name}"
        )

    submitted_invoices = []
    skipped_invoices = []
    failed_invoices = []

    for merge_log in merge_logs:

        consolidated_invoice = merge_log.get("consolidated_invoice")

        if not consolidated_invoice:
            continue

        sales_invoice_rec = frappe.db.exists(
            "Sales Invoice",
            consolidated_invoice
        )

        if not sales_invoice_rec:
            failed_invoices.append(consolidated_invoice)
            continue

        sales_invoice = frappe.get_doc(
            "Sales Invoice",
            sales_invoice_rec
        )

        # Already submitted
        if sales_invoice.docstatus == 1:
            skipped_invoices.append(sales_invoice.name)
            continue

        try:
            sales_invoice.custom_pos_closing_entry = doc_name

            sales_invoice.save(ignore_permissions=True)

            sales_invoice.submit()

            submitted_invoices.append(sales_invoice.name)

        except Exception:
            failed_invoices.append(sales_invoice.name)

            frappe.log_error(
                frappe.get_traceback(),
                f"POS Closing Submit Failed: {sales_invoice.name}"
            )

    # ---------------------------------------------------------
    # Update POS Closing Entry if ALL invoices are submitted
    # ---------------------------------------------------------
    total_logs = len(merge_logs)

    total_successful = (
        len(submitted_invoices) +
        len(skipped_invoices)
    )

    if total_logs == total_successful:

        frappe.db.set_value(
            "POS Closing Entry",
            doc_name,
            "custom_all_invoices_submitted",
            1
        )

    frappe.db.commit()

    # ---------------------------------------------------------
    # Messages
    # ---------------------------------------------------------
    if submitted_invoices:
        frappe.msgprint(
            "Submitted Invoices:<br>" +
            "<br>".join(submitted_invoices)
        )

    if skipped_invoices:
        frappe.msgprint(
            "Already Submitted:<br>" +
            "<br>".join(skipped_invoices)
        )

    if failed_invoices:
        frappe.msgprint(
            "Failed Invoices:<br>" +
            "<br>".join(failed_invoices)
        )

    return {
        "submitted": submitted_invoices,
        "skipped": skipped_invoices,
        "failed": failed_invoices
    }