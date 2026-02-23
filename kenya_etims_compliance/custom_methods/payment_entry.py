"""
Payment Entry Validation Module for KRA eTIMS Compliance

This module validates that Purchase Invoices are verified with KRA eTIMS
before allowing payments to be made - a critical requirement for 2026
tax compliance.

All expenses must be eTIMS compliant to be tax-deductible.
"""

import frappe
from frappe import _
from kenya_etims_compliance.utils.etims_utils import eTIMS


def validate_payment_for_etims_invoice(doc, method):
    """Validate that invoice is verified before allowing payment

    This is called from Payment Entry before submission.
    It checks if all referenced Purchase Invoices have been verified
    with KRA eTIMS system.

    Args:
        doc: Payment Entry document
        method: The method being called (before_submit)

    Raises:
        frappe.ValidationError: If any invoice is not verified
    """
    from kenya_etims_compliance.doctype.etims_settings.etims_settings import get_etims_settings

    # Get eTIMS settings
    settings = get_etims_settings()

    # If verification is not enforced, skip validation
    if not settings.get("enforce_invoice_verification", 1):
        return

    # Check if manual override is allowed
    allow_override = settings.get("allow_payment_unverified", 0)

    # Track unverified invoices
    unverified_invoices = []
    manual_verified_invoices = []

    # Check each referenced invoice
    for reference in doc.references:
        if reference.reference_doctype == "Purchase Invoice":
            invoice = frappe.get_doc("Purchase Invoice", reference.reference_name)

            # Check if verified
            invoice_verified = invoice.get("custom_invoice_verified", 0)
            kra_invoice_number = invoice.get("custom_kra_invoice_number", "")

            # Track manually verified invoices
            if invoice_verified and kra_invoice_number == "MANUAL_OVERRIDE":
                manual_verified_invoices.append({
                    "invoice": invoice.name,
                    "supplier": invoice.supplier,
                    "amount": invoice.grand_total,
                    "reason": invoice.get("custom_verification_override_reason", "Not specified")
                })
            elif not invoice_verified:
                unverified_invoices.append({
                    "invoice": invoice.name,
                    "supplier": invoice.supplier,
                    "amount": reference.allocated_amount
                })

    # Handle unverified invoices
    if unverified_invoices:
        if allow_override:
            # Warning mode - allow payment with warning
            invoice_list = "\n".join([
                f"  - {inv['invoice']} ({inv['supplier']}): {inv['amount']}"
                for inv in unverified_invoices
            ])

            frappe.msgprint(
                _("<b>Warning:</b> The following invoices have not been verified with KRA eTIMS:\n{0}\n\n"
                  "Payment is allowed because manual override is enabled. "
                  "Please verify these invoices when possible.").format(invoice_list),
                indicator="orange",
                alert=True
            )

            # Log the override
            eTIMS.log_errors(
                f"Payment allowed for unverified invoices: {doc.name}",
                f"Invoices: {[inv['invoice'] for inv in unverified_invoices]}, User: {frappe.session.user}"
            )
        else:
            # Block payment
            invoice_list = "\n".join([
                f"  - {inv['invoice']} ({inv['supplier']}): {inv['amount']}"
                for inv in unverified_invoices
            ])

            frappe.throw(
                _("<b>Cannot make payment for unverified invoices.</b><br><br>"
                  "The following Purchase Invoices have not been verified with KRA eTIMS:<br>{0}<br><br>"
                  "Please verify each invoice before making payment.<br>"
                  "Go to Purchase Invoice > Click 'Verify Invoice with KRA' button.<br><br>"
                  "If you need to make an exception, please enable 'Allow Payment Without Verification' "
                  "in eTIMS Settings or mark the invoice as manually verified.").format(
                    "<br>" + invoice_list
                  )
            )

    # Warn about manually verified invoices
    if manual_verified_invoices:
        invoice_list = "\n".join([
            f"  - {inv['invoice']} ({inv['supplier']}): {inv['amount']} - Reason: {inv['reason']}"
            for inv in manual_verified_invoices
        ])

        frappe.msgprint(
            _("<b>Notice:</b> The following invoices were manually verified (override):\n{0}\n\n"
              "These may not be accepted by KRA for tax deduction.").format(invoice_list),
            indicator="yellow",
            alert=True
        )


@frappe.whitelist()
def check_payment_eligibility(payment_entry_name):
    """Check if a payment entry can be submitted based on invoice verification

    Useful for:
    - Dashboard indicators
    - Pre-submission validation
    - UI warnings

    Args:
        payment_entry_name: Payment Entry document name

    Returns:
        {
            "eligible": True/False,
            "unverified_invoices": [...],
            "manual_verified_invoices": [...],
            "message": "..."
        }
    """
    try:
        doc = frappe.get_doc("Payment Entry", payment_entry_name)

        unverified_invoices = []
        manual_verified_invoices = []

        for reference in doc.references:
            if reference.reference_doctype == "Purchase Invoice":
                invoice = frappe.get_doc("Purchase Invoice", reference.reference_name)

                invoice_verified = invoice.get("custom_invoice_verified", 0)
                kra_invoice_number = invoice.get("custom_kra_invoice_number", "")

                if invoice_verified and kra_invoice_number == "MANUAL_OVERRIDE":
                    manual_verified_invoices.append({
                        "invoice": invoice.name,
                        "supplier": invoice.supplier,
                        "amount": invoice.grand_total,
                        "reason": invoice.get("custom_verification_override_reason", "Not specified")
                    })
                elif not invoice_verified:
                    unverified_invoices.append({
                        "invoice": invoice.name,
                        "supplier": invoice.supplier,
                        "amount": reference.allocated_amount
                    })

        eligible = len(unverified_invoices) == 0

        if eligible and manual_verified_invoices:
            message = "Payment can be made. Note: Some invoices were manually verified."
        elif eligible:
            message = "All invoices are verified. Payment can be made."
        else:
            message = f"{len(unverified_invoices)} invoice(s) not verified. Please verify before payment."

        return {
            "eligible": eligible,
            "unverified_invoices": unverified_invoices,
            "manual_verified_invoices": manual_verified_invoices,
            "message": message
        }

    except Exception as e:
        return {
            "eligible": False,
            "error": str(e),
            "message": f"Error checking eligibility: {str(e)}"
        }


@frappe.whitelist()
def get_payment_verification_summary(from_date=None, to_date=None):
    """Get summary of payment verification status

    Useful for:
    - Compliance dashboards
    - Management reports
    - Audit trails

    Args:
        from_date: Start date (optional)
        to_date: End date (optional)

    Returns:
        {
            "total_payments": n,
            "verified_payments": m,
            "unverified_payments": k,
            "manual_override_payments": j,
            "verification_rate": "xx%"
        }
    """
    try:
        filters = {"docstatus": 1}

        if from_date:
            filters["posting_date"] = [">=", from_date]
        if to_date:
            if "posting_date" in filters:
                filters["posting_date"].append("<=", to_date)
            else:
                filters["posting_date"] = ["<=", to_date]

        # Get all payment entries
        payments = frappe.db.get_all(
            "Payment Entry",
            filters=filters,
            fields=["name"]
        )

        total_payments = len(payments)
        verified_payments = 0
        unverified_payments = 0
        manual_override_payments = 0

        # Check each payment's invoice verification status
        for payment in payments:
            payment_doc = frappe.get_doc("Payment Entry", payment.name)
            has_unverified = False
            has_manual_override = False

            for reference in payment_doc.references:
                if reference.reference_doctype == "Purchase Invoice":
                    invoice = frappe.get_doc("Purchase Invoice", reference.reference_name)
                    invoice_verified = invoice.get("custom_invoice_verified", 0)
                    kra_invoice_number = invoice.get("custom_kra_invoice_number", "")

                    if not invoice_verified:
                        has_unverified = True
                    elif kra_invoice_number == "MANUAL_OVERRIDE":
                        has_manual_override = True

            if has_unverified:
                unverified_payments += 1
            elif has_manual_override:
                manual_override_payments += 1
            else:
                verified_payments += 1

        verification_rate = (verified_payments / total_payments * 100) if total_payments > 0 else 0

        return {
            "total_payments": total_payments,
            "verified_payments": verified_payments,
            "unverified_payments": unverified_payments,
            "manual_override_payments": manual_override_payments,
            "verification_rate": f"{verification_rate:.1f}%"
        }

    except Exception as e:
        return {
            "error": str(e),
            "total_payments": 0,
            "verified_payments": 0,
            "unverified_payments": 0,
            "manual_override_payments": 0,
            "verification_rate": "N/A"
        }


@frappe.whitelist()
def get_unpaid_invoices_summary():
    """Get summary of unpaid invoices by verification status

    Useful for:
    - Cash flow planning
    - Prioritizing invoice verification
    - Accounts payable dashboard

    Returns:
        {
            "unverified_unpaid": n,
            "verified_unpaid": m,
            "total_unpaid": n + m,
            "unverified_amount": xxx,
            "verified_amount": yyy
        }
    """
    try:
        # Get all unpaid (not fully paid) submitted purchase invoices
        unpaid_invoices = frappe.db.get_all(
            "Purchase Invoice",
            filters={
                "docstatus": 1,
                "status": ["!=", "Paid"]
            },
            fields=["name", "custom_invoice_verified", "grand_total"]
        )

        unverified_unpaid = 0
        verified_unpaid = 0
        unverified_amount = 0
        verified_amount = 0

        for invoice in unpaid_invoices:
            if invoice.get("custom_invoice_verified", 0):
                verified_unpaid += 1
                verified_amount += invoice.get("grand_total", 0)
            else:
                unverified_unpaid += 1
                unverified_amount += invoice.get("grand_total", 0)

        return {
            "unverified_unpaid": unverified_unpaid,
            "verified_unpaid": verified_unpaid,
            "total_unpaid": unverified_unpaid + verified_unpaid,
            "unverified_amount": unverified_amount,
            "verified_amount": verified_amount
        }

    except Exception as e:
        return {
            "error": str(e),
            "unverified_unpaid": 0,
            "verified_unpaid": 0,
            "total_unpaid": 0,
            "unverified_amount": 0,
            "verified_amount": 0
        }
