"""eTIMS Compliance Dashboard data methods."""

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime


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

	# Input VAT at risk
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
	input_vat_at_risk = sum(p.base_total_taxes_and_charges or 0 for p in at_risk_pis)

	# Queue status
	queue_pending = 0
	queue_failed = 0
	if frappe.db.exists("DocType", "eTIMS Invoice Queue"):
		queue_pending = frappe.db.count("eTIMS Invoice Queue", filters={"status": "Queued"})
		queue_failed = frappe.db.count("eTIMS Invoice Queue", filters={"status": "Failed"})

	# Days to filing deadline (20th of next month)
	filing_day = 20
	if today.day <= filing_day:
		days_to_deadline = filing_day - today.day
	else:
		import calendar

		days_in_month = calendar.monthrange(today.year, today.month)[1]
		days_to_deadline = (days_in_month - today.day) + filing_day

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

	return {
		"sales_transmitted": sales_transmitted,
		"sales_pending": sales_pending,
		"purchase_matched": purchase_matched,
		"input_vat_at_risk": input_vat_at_risk,
		"queue_pending": queue_pending,
		"queue_failed": queue_failed,
		"days_to_deadline": days_to_deadline,
		"total_suppliers": total_suppliers,
		"verified_suppliers": verified_suppliers,
	}
