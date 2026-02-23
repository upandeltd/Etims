"""
Invoice Checker Module for KRA eTIMS Compliance

This module provides functionality to verify supplier invoices against
the KRA eTIMS system - a critical requirement for 2026 tax compliance.

All expenses and purchases must be eTIMS compliant to be tax-deductible.
"""

import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS


@frappe.whitelist()
def check_invoice_validity(invoice_no, supplier_pin, invoice_date, total_amount):
    """Verify if supplier invoice is valid in KRA eTIMS system

    This is the main entry point for invoice verification. It can be called from:
    - Purchase Invoice form (via "Verify Invoice" button)
    - Payment Entry validation (before allowing payment)
    - Automated verification jobs

    Args:
        invoice_no: Supplier invoice number
        supplier_pin: Supplier Tax PIN (format: A000000000)
        invoice_date: Invoice date (YYYY-MM-DD)
        total_amount: Total invoice amount

    Returns:
        {
            "valid": True/False,
            "invoice_details": {...},
            "qr_code": "...",
            "verification_date": "...",
            "message": "..."
        }
    """
    try:
        # Validate inputs
        if not invoice_no:
            return {
                "valid": False,
                "error": "Invoice number is required",
                "message": "Please provide a valid invoice number"
            }

        if not supplier_pin:
            return {
                "valid": False,
                "error": "Supplier PIN is required",
                "message": "Please provide the supplier's Tax PIN"
            }

        if not invoice_date:
            return {
                "valid": False,
                "error": "Invoice date is required",
                "message": "Please provide the invoice date"
            }

        if not total_amount or float(total_amount) <= 0:
            return {
                "valid": False,
                "error": "Invalid invoice amount",
                "message": "Invoice amount must be greater than zero"
            }

        # Call the Invoice Checker API
        result = eTIMS.invoiceCheckerReq(
            invoice_no=invoice_no,
            supplier_pin=supplier_pin,
            invoice_date=invoice_date,
            total_amount=float(total_amount)
        )

        if "Success" in result:
            invoice_details = result["Success"]
            return {
                "valid": True,
                "invoice_details": invoice_details,
                "qr_code": invoice_details.get("qrCode", ""),
                "verification_date": frappe.utils.now(),
                "message": "Invoice verified successfully with KRA eTIMS",
                "kra_invoice_number": invoice_details.get("invcNo"),
                "supplier_pin": invoice_details.get("spplrTin"),
                "invoice_date": invoice_details.get("invcDt"),
                "total_amount": invoice_details.get("totAmt")
            }
        else:
            error_msg = result.get("Error", "Unknown error")
            # Log the failed verification attempt
            eTIMS.log_errors(
                f"Invoice Verification Failed: {invoice_no}",
                f"Supplier PIN: {supplier_pin}, Error: {error_msg}"
            )
            return {
                "valid": False,
                "error": error_msg,
                "message": f"Invoice could not be verified: {error_msg}"
            }

    except Exception as e:
        eTIMS.log_errors("Invoice Verification Exception", str(e))
        return {
            "valid": False,
            "error": str(e),
            "message": f"An error occurred during verification: {str(e)}"
        }


@frappe.whitelist()
def bulk_verify_invoices(invoice_list):
    """Verify multiple invoices in bulk

    Useful for:
    - Catching up on unverified invoices
    - Batch verification processes
    - Auditing and compliance reviews

    Args:
        invoice_list: List of dicts with invoice details
            [{
                "invoice_no": "...",
                "supplier_pin": "...",
                "invoice_date": "...",
                "total_amount": ...
            }]

    Returns:
        {
            "results": [...],
            "summary": {
                "total": n,
                "verified": m,
                "failed": k
            }
        }
    """
    results = []
    verified_count = 0
    failed_count = 0

    for invoice_data in invoice_list:
        result = check_invoice_validity(
            invoice_no=invoice_data.get("invoice_no"),
            supplier_pin=invoice_data.get("supplier_pin"),
            invoice_date=invoice_data.get("invoice_date"),
            total_amount=invoice_data.get("total_amount")
        )
        result["invoice_no"] = invoice_data.get("invoice_no")
        results.append(result)

        if result.get("valid"):
            verified_count += 1
        else:
            failed_count += 1

    return {
        "results": results,
        "summary": {
            "total": len(invoice_list),
            "verified": verified_count,
            "failed": failed_count
        }
    }


@frappe.whitelist()
def get_verification_status(purchase_invoice):
    """Get the verification status of a purchase invoice

    Args:
        purchase_invoice: Purchase Invoice name/ID

    Returns:
        {
            "verified": True/False,
            "verification_date": "...",
            "qr_code": "...",
            "kra_invoice_number": "..."
        }
    """
    try:
        doc = frappe.get_doc("Purchase Invoice", purchase_invoice)

        # Check if invoice has been verified
        invoice_verified = doc.get("custom_invoice_verified", 0)

        if invoice_verified:
            return {
                "verified": True,
                "verification_date": doc.get("custom_verification_date"),
                "qr_code": doc.get("custom_qr_code"),
                "kra_invoice_number": doc.get("custom_kra_invoice_number"),
                "message": "Invoice is verified"
            }
        else:
            return {
                "verified": False,
                "message": "Invoice has not been verified with KRA"
            }

    except Exception as e:
        return {
            "verified": False,
            "error": str(e),
            "message": f"Error checking verification status: {str(e)}"
        }


@frappe.whitelist()
def get_unverified_invoices(limit=100):
    """Get list of unverified purchase invoices

    Useful for:
    - Dashboard widgets
    - Compliance reports
    - Batch verification processes

    Args:
        limit: Maximum number of invoices to return

    Returns:
        List of unverified invoices with key details
    """
    try:
        invoices = frappe.db.get_all(
            "Purchase Invoice",
            filters={
                "docstatus": 1,  # Only submitted invoices
                "custom_invoice_verified": 0  # Not verified
            },
            fields=[
                "name",
                "supplier",
                "bill_no",
                "bill_date",
                "posting_date",
                "grand_total",
                "custom_supplier_pin"
            ],
            order_by="posting_date desc",
            limit=limit
        )

        return {
            "success": True,
            "invoices": invoices,
            "count": len(invoices)
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "invoices": [],
            "count": 0
        }
