"""eTIMS Compliance Dashboard data methods."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from kenya_etims_compliance.utils.permissions import require


def _branch_scope_filter():
	"""Return a branch-scoping filter to apply to monetary dashboard queries.

	Branch isolation is a hard policy when ``enforce_branch_isolation`` is on:
	non-Admin users must not see other branches' VAT exposure. We compute the
	user's effective branch via the same logic as ``validate_branch_access``.
	"""
	from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
		is_branch_isolation_enforced,
		is_cross_branch_allowed,
	)
	from kenya_etims_compliance.utils.permissions import (
		is_etims_admin,
		is_etims_manager,
	)

	if not is_branch_isolation_enforced():
		return None
	if (
		is_etims_admin()
		or is_etims_manager()
		or "System Manager" in frappe.get_roles()
		or frappe.session.user == "Administrator"
	):
		if is_cross_branch_allowed():
			return None
		# Even when branch isolation is enforced, the manager sees ALL
		# branches unless cross-branch is also explicitly disabled.
		return None

	branch = frappe.db.get_value(
		"User Permission",
		{"user": frappe.session.user, "allow": "Tax Branch Office", "is_default": 1},
		"for_value",
	)
	if not branch:
		devices = frappe.db.get_all(
			"TIS Device Initialization", filters={"active": 1}, fields=["branch_id"], limit=2
		)
		if len(devices) == 1:
			branch = devices[0].get("branch_id")
	return branch


@frappe.whitelist()
def get_dashboard_data():
	"""Get all dashboard metrics in a single call."""
	# HIGH — was ungated. Read-only, but reads VAT-exposure totals across the
	# whole company. Require at least read on Sales Invoice + Purchase Invoice
	# so a portal user can't enumerate company-wide compliance state.
	require("Sales Invoice", "read")

	today = getdate()
	# Five filters below window on the current month. Without this the whole
	# method raised NameError, so the dashboard returned nothing at all.
	month_start = today.replace(day=1)

	# Sales transmitted this month
	sales_transmitted = frappe.db.count(
		"Sales Invoice",
		filters={
			"docstatus": 1,
			"posting_date": [">=", month_start],
			"custom_update_sales_to_etims": 1,
		},
	)

	# Sales pending
	sales_pending = frappe.db.count(
		"Sales Invoice",
		filters={
			"docstatus": 1,
			"posting_date": [">=", month_start],
			"custom_update_invoice_in_tims": 1,
			"custom_update_sales_to_etims": 0,
		},
	)

	# Purchase matched
	purchase_matched = frappe.db.count(
		"Purchase Invoice",
		filters={
			"docstatus": 1,
			"posting_date": [">=", month_start],
			"custom_kra_match_status": "Matched",
		},
	)

	# Purchase unmatched
	purchase_unmatched = frappe.db.count(
		"Purchase Invoice",
		filters={
			"docstatus": 1,
			"posting_date": [">=", month_start],
			"custom_kra_match_status": ["not in", ["Matched", ""]],
		},
	)

	# Input VAT at risk
	input_vat_at_risk = get_input_vat_at_risk()

	# Queue status
	queue_pending = 0
	queue_failed = 0
	if frappe.db.exists("DocType", "eTIMS Invoice Queue"):
		queue_pending = frappe.db.count("eTIMS Invoice Queue", filters={"status": "Queued"})
		queue_failed = frappe.db.count("eTIMS Invoice Queue", filters={"status": "Failed"})

	# Days to filing deadline (20th of next month)
	days_to_deadline = get_days_to_filing_deadline()

	# Supplier verification
	total_suppliers = frappe.db.count(
		"Supplier",
		filters={
			"disabled": 0,
			"custom_supplier_pin": ["is", "set"],
		},
	)
	verified_suppliers = frappe.db.count(
		"Supplier",
		filters={
			"disabled": 0,
			"custom_supplier_pin": ["is", "set"],
			"custom_kra_pin_verified": 1,
		},
	)

	# Sales success rate
	sales_success_rate = get_sales_success_rate()

	# Compliance score
	compliance_score = get_compliance_score()

	# Errors this month
	errors_this_month = 0
	if frappe.db.exists("DocType", "Error Logging"):
		errors_this_month = frappe.db.count(
			"Error Logging",
			filters={
				"creation": [">=", month_start],
			},
		)

	return {
		"sales_transmitted": sales_transmitted,
		"sales_pending": sales_pending,
		"purchase_matched": purchase_matched,
		"purchase_unmatched": purchase_unmatched,
		"input_vat_at_risk": input_vat_at_risk,
		"queue_pending": queue_pending,
		"queue_failed": queue_failed,
		"days_to_deadline": days_to_deadline,
		"total_suppliers": total_suppliers,
		"verified_suppliers": verified_suppliers,
		"sales_success_rate": sales_success_rate,
		"compliance_score": compliance_score,
		"errors_this_month": errors_this_month,
	}


@frappe.whitelist()
def get_sales_success_rate():
	"""Return percentage of invoices marked for TIMS that were transmitted."""
	require("Sales Invoice", "read")
	month_start = getdate().replace(day=1)
	total = frappe.db.count(
		"Sales Invoice",
		filters={
			"docstatus": 1,
			"posting_date": [">=", month_start],
			"custom_update_invoice_in_tims": 1,
		},
	)
	if not total:
		return 100.0

	transmitted = frappe.db.count(
		"Sales Invoice",
		filters={
			"docstatus": 1,
			"posting_date": [">=", month_start],
			"custom_update_sales_to_etims": 1,
		},
	)
	return round((transmitted / total) * 100, 1)


@frappe.whitelist()
def get_input_vat_at_risk():
	"""Return sum of taxes on unmatched purchase invoices this month."""
	# HIGH — monetary company-wide exposure. Force a write-on-Purchase-Invoice
	# check (the data is sensitive) AND scope to the caller's branch when
	# isolation is on so non-Admin users can't see other branches' VAT risk.
	require("Purchase Invoice", "write")

	month_start = getdate().replace(day=1)
	filters = {
		"docstatus": 1,
		"posting_date": [">=", month_start],
		"custom_kra_match_status": ["not in", ["Matched", ""]],
	}

	# When branch isolation is on and the caller is not a cross-branch
	# exempt role, narrow the query to their branch.
	branch = _branch_scope_filter()
	if branch:
		filters["custom_target_tax_branch_office"] = branch

	at_risk_pis = frappe.get_all(
		"Purchase Invoice",
		filters=filters,
		fields=["base_total_taxes_and_charges"],
		limit_page_length=0,
	)
	return sum(flt(p.base_total_taxes_and_charges) for p in at_risk_pis)


@frappe.whitelist()
def get_compliance_score():
	"""Return average of latest eTIMS compliance scores, or 0 if none."""
	# HIGH — ungated. Compliance-score doctype is internal-only.
	require("eTIMS Compliance Score", "read")
	if not frappe.db.exists("DocType", "eTIMS Compliance Score"):
		return 0

	result = frappe.db.sql(
		"""
		SELECT AVG(overall_score) as avg_score
		FROM `tabeTIMS Compliance Score`
		WHERE docstatus < 2
		""",
		as_dict=True,
	)
	if not result:
		return 0
	row = result[0]
	avg_score = row.get("avg_score") if isinstance(row, dict) else 0
	return round(flt(avg_score), 1)


@frappe.whitelist()
def get_days_to_filing_deadline():
	"""Return days remaining until the 20th of next month."""
	# HIGH — ungated, but at least it leaks no PII. Gate it lightly.
	require("Sales Invoice", "read")
	import calendar

	today = getdate()
	filing_day = 20
	if today.day <= filing_day:
		return filing_day - today.day

	days_in_month = calendar.monthrange(today.year, today.month)[1]
	return (days_in_month - today.day) + filing_day
