"""eTIMS Compliance Dashboard data methods."""

import frappe
from frappe import _
from frappe.utils import flt, getdate


@frappe.whitelist()
def get_dashboard_data():
	"""Get all dashboard metrics in a single call."""
	today = getdate()
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
	month_start = getdate().replace(day=1)
	at_risk_pis = frappe.get_all(
		"Purchase Invoice",
		filters={
			"docstatus": 1,
			"posting_date": [">=", month_start],
			"custom_kra_match_status": ["not in", ["Matched", ""]],
		},
		fields=["base_total_taxes_and_charges"],
		limit_page_length=0,
	)
	return sum(flt(p.base_total_taxes_and_charges) for p in at_risk_pis)


@frappe.whitelist()
def get_compliance_score():
	"""Return average of latest eTIMS compliance scores, or 0 if none."""
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
	import calendar

	today = getdate()
	filing_day = 20
	if today.day <= filing_day:
		return filing_day - today.day

	days_in_month = calendar.monthrange(today.year, today.month)[1]
	return (days_in_month - today.day) + filing_day
