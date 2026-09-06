"""Payment-side eTIMS advisory for KRA compliance.

Expenses are only deductible if the purchase is on KRA's records, so a Payment
Entry that settles an invoice KRA has never confirmed carries real risk. That
risk is reported here and enforced at the period close
(`custom_methods.reconciliation.close_period`) - never by blocking the payment
itself, because KRA's purchase register is only populated when the *supplier*
files, routinely after payment falls due.
"""

import frappe
from frappe import _

from kenya_etims_compliance.utils.etims_utils import eTIMS
from kenya_etims_compliance.utils.permissions import can_modify_doctype


def _reference_status(doc):
	"""eTIMS state of every Purchase Invoice this Payment Entry settles."""
	rows = []

	for reference in doc.references:
		if reference.reference_doctype != "Purchase Invoice":
			continue

		invoice = frappe.db.get_value(
			"Purchase Invoice",
			reference.reference_name,
			[
				"supplier",
				"grand_total",
				"custom_invoice_verified",
				"custom_kra_invoice_number",
				"custom_kra_match_status",
				"custom_verification_override_reason",
			],
			as_dict=True,
		)
		if not invoice:
			continue

		rows.append(
			{
				"invoice": reference.reference_name,
				"supplier": invoice.supplier,
				"amount": reference.allocated_amount or invoice.grand_total,
				"verified": bool(invoice.custom_invoice_verified),
				"manual": invoice.custom_kra_invoice_number == "MANUAL_OVERRIDE",
				"match_status": invoice.custom_kra_match_status or _("Pending"),
				"reason": invoice.custom_verification_override_reason,
			}
		)

	return rows


def validate_payment_for_etims_invoice(doc, method):
	"""Warn about invoices KRA has not confirmed. Never blocks the payment.

	Named `validate_*` because `hooks.py` wires it to `before_submit`; it is an
	advisory, so it names the invoices and their current KRA match status
	instead of raising. Unresolved exceptions are what stop a period from
	closing, and the close is what the filing depends on.
	"""
	rows = [row for row in _reference_status(doc) if not row["verified"] or row["manual"]]
	if not rows:
		return

	lines = "".join(
		"<li>{invoice} — {supplier} — {amount} — {state}</li>".format(
			invoice=row["invoice"],
			supplier=row["supplier"],
			amount=frappe.format_value(row["amount"], {"fieldtype": "Currency"}),
			state=(
				_("manually verified: {0}").format(row["reason"] or _("no reason given"))
				if row["manual"]
				else _("not confirmed by KRA (match status: {0})").format(row["match_status"])
			),
		)
		for row in rows
	)

	frappe.msgprint(
		_(
			"<b>eTIMS:</b> these invoices are not confirmed against KRA's purchase register:"
			"<ul>{0}</ul>Payment is not blocked, but the expense is only deductible once KRA "
			"holds the purchase. Run eTIMS purchase reconciliation for the period, and accept "
			"or fix each exception before closing it."
		).format(lines),
		title=_("Unconfirmed with KRA"),
		indicator="orange",
	)

	eTIMS.log_errors(
		f"Payment submitted against unconfirmed invoices: {doc.name}",
		f"Invoices: {[row['invoice'] for row in rows]}, User: {frappe.session.user}",
	)


@frappe.whitelist()
def get_payment_etims_status(payment_entry_name):
	"""KRA confirmation state of a Payment Entry's invoices, for dashboards.

	Reports; it does not gate. Nothing about payment is refused on this basis,
	so there is no "eligible" answer to give - `unconfirmed` is the number that
	matters, and each row carries the invoice's current KRA match status.
	"""
	if not can_modify_doctype("Purchase Invoice", "read"):
		frappe.throw(
			_("Permission Denied: you do not have read permission for {0}.").format("Purchase Invoice"),
			frappe.PermissionError,
		)

	rows = _reference_status(frappe.get_doc("Payment Entry", payment_entry_name))
	unconfirmed = [row for row in rows if not row["verified"]]
	manual = [row for row in rows if row["manual"]]

	return {
		"invoices": rows,
		"unconfirmed": unconfirmed,
		"manual_verified": manual,
		"message": (
			_("All {0} invoice(s) are confirmed with KRA.").format(len(rows))
			if not unconfirmed
			else _("{0} of {1} invoice(s) not yet confirmed by KRA.").format(len(unconfirmed), len(rows))
		),
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
	if not can_modify_doctype("Purchase Invoice", "read"):
		frappe.throw(
			_("Permission Denied: you do not have read permission for {0}.").format("Purchase Invoice"),
			frappe.PermissionError,
		)

	try:
		filters = {"docstatus": 1}

		if from_date and to_date:
			filters["posting_date"] = ["between", [from_date, to_date]]
		elif from_date:
			filters["posting_date"] = [">=", from_date]
		elif to_date:
			filters["posting_date"] = ["<=", to_date]

		# Get all payment entries
		payments = frappe.db.get_all("Payment Entry", filters=filters, fields=["name"])

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
			"verification_rate": f"{verification_rate:.1f}%",
		}

	except (frappe.DoesNotExistError, frappe.DataError) as e:
		return {
			"error": str(e),
			"total_payments": 0,
			"verified_payments": 0,
			"unverified_payments": 0,
			"manual_override_payments": 0,
			"verification_rate": "N/A",
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
	if not can_modify_doctype("Purchase Invoice", "read"):
		frappe.throw(
			_("Permission Denied: you do not have read permission for {0}.").format("Purchase Invoice"),
			frappe.PermissionError,
		)

	try:
		# Get all unpaid (not fully paid) submitted purchase invoices
		unpaid_invoices = frappe.db.get_all(
			"Purchase Invoice",
			filters={"docstatus": 1, "status": ["!=", "Paid"]},
			fields=["name", "custom_invoice_verified", "grand_total"],
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
			"verified_amount": verified_amount,
		}

	except frappe.DataError as e:
		return {
			"error": str(e),
			"unverified_unpaid": 0,
			"verified_unpaid": 0,
			"total_unpaid": 0,
			"unverified_amount": 0,
			"verified_amount": 0,
		}
