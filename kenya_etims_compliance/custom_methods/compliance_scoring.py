"""Monthly eTIMS Compliance Scoring.

Generates a scorecard per month per branch:
- Transmission (35%): % of SI + PI successfully transmitted
- Reconciliation (25%): % of KRA entries matched
- Supplier health (15%): average supplier compliance score
- Error rate (10%): % of submissions that succeeded without retry
- Filing timeliness (15%): stub — tracks if scoring ran before 20th
"""

import calendar

import frappe
from frappe.utils import add_months, flt, getdate, now_datetime


def generate_monthly_score(period=None, branch=None):
	"""Generate compliance score for a month.

	Args:
		period: YYYY-MM (defaults to previous month)
		branch: Tax Branch Office (optional)
	"""
	if not period:
		last_month = add_months(getdate(), -1)
		period = last_month.strftime("%Y-%m")

	year, month = period.split("-")
	from_date = f"{year}-{month}-01"
	last_day = calendar.monthrange(int(year), int(month))[1]
	to_date = f"{year}-{month}-{last_day}"

	transmission = _transmission_score(from_date, to_date, branch)
	reconciliation = _reconciliation_score(from_date, to_date, branch)
	supplier_health = _supplier_health_score()
	error_rate = _error_rate_score(from_date, to_date)
	filing = _filing_timeliness_score()

	overall = (
		transmission * 0.35
		+ reconciliation * 0.25
		+ supplier_health * 0.15
		+ error_rate * 0.10
		+ filing * 0.15
	)

	grade = "A" if overall >= 90 else "B" if overall >= 75 else "C" if overall >= 60 else "D"

	# Build name matching autoname format:{period}-{branch}
	# When branch is None, Frappe generates "{period}-" so match that
	doc_name = f"{period}-{branch}" if branch else f"{period}-"

	description = _build_description(grade, transmission, reconciliation, supplier_health)

	values = {
		"transmission_score": transmission,
		"reconciliation_score": reconciliation,
		"filing_timeliness_score": filing,
		"supplier_health_score": supplier_health,
		"error_rate_score": error_rate,
		"overall_score": overall,
		"grade": grade,
		"generated_on": now_datetime(),
		"description": description,
	}

	if frappe.db.exists("eTIMS Compliance Score", doc_name):
		frappe.db.set_value("eTIMS Compliance Score", doc_name, values)
	else:
		frappe.get_doc(
			{
				"doctype": "eTIMS Compliance Score",
				"period": period,
				"branch": branch,
				**values,
			}
		).insert(ignore_permissions=True)

	frappe.db.commit()
	return {"period": period, "overall": round(overall, 1), "grade": grade}


def _transmission_score(from_date, to_date, branch=None):
	"""% of SI + PI successfully transmitted to eTIMS."""
	total = 0
	transmitted = 0

	# Sales Invoices
	si_filters = {
		"docstatus": 1,
		"posting_date": ["between", [from_date, to_date]],
		"custom_update_invoice_in_tims": 1,
	}
	if branch:
		si_filters["custom_tax_branch_office"] = branch

	si_total = frappe.db.count("Sales Invoice", filters=si_filters)
	si_transmitted = frappe.db.count(
		"Sales Invoice",
		filters={
			**si_filters,
			"custom_update_sales_to_etims": 1,
		},
	)

	# Purchase Invoices
	pi_filters = {
		"docstatus": 1,
		"posting_date": ["between", [from_date, to_date]],
		"custom_update_purchase_in_tims": 1,
	}
	if branch:
		pi_filters["custom_tax_branch_office"] = branch

	pi_total = frappe.db.count("Purchase Invoice", filters=pi_filters)
	pi_transmitted = frappe.db.count(
		"Purchase Invoice",
		filters={
			**pi_filters,
			"custom_invoice_number": [">", 0],
		},
	)

	total = si_total + pi_total
	transmitted = si_transmitted + pi_transmitted

	if not total:
		return 100
	return round((transmitted / total) * 100)


def _reconciliation_score(from_date, to_date, branch=None):
	"""% of KRA purchase register entries matched."""
	if not frappe.db.exists("DocType", "eTIMS Purchase Register Entry"):
		return 100

	filters = {"invoice_date": ["between", [from_date, to_date]]}
	if branch:
		filters["branch"] = branch

	total = frappe.db.count("eTIMS Purchase Register Entry", filters=filters)
	if not total:
		return 100

	matched = frappe.db.count(
		"eTIMS Purchase Register Entry",
		filters={
			**filters,
			"match_status": ["in", ["Matched", "Matched (Auto-Created)"]],
		},
	)
	return round((matched / total) * 100)


def _filing_timeliness_score():
	"""Score based on whether scoring is being run regularly.

	Returns 100 if this function is called (meaning the scheduler is active).
	In future, integrate with actual iTax filing date tracking.
	"""
	today = getdate()
	if today.day <= 20:
		return 100  # Still within filing window
	return 70  # Past the 20th — mild penalty as reminder


def _supplier_health_score():
	"""Average supplier compliance score using Frappe ORM."""
	suppliers = frappe.get_all(
		"Supplier",
		filters={
			"disabled": 0,
			"custom_supplier_pin": ["is", "set"],
			"custom_etims_compliance_score": [">", 0],
		},
		fields=["custom_etims_compliance_score"],
		limit_page_length=0,
	)

	if not suppliers:
		return 50

	total_score = sum(flt(s.custom_etims_compliance_score) for s in suppliers)
	return round(total_score / len(suppliers))


def _error_rate_score(from_date, to_date):
	"""% of submissions that succeeded without retry."""
	if not frappe.db.exists("DocType", "eTIMS Invoice Queue"):
		return 100

	total = frappe.db.count(
		"eTIMS Invoice Queue",
		filters={
			"creation": ["between", [from_date, to_date]],
		},
	)
	if not total:
		return 100

	first_try_success = frappe.db.count(
		"eTIMS Invoice Queue",
		filters={
			"creation": ["between", [from_date, to_date]],
			"status": "Sent",
			"retry_count": ["<=", 1],
		},
	)
	return round((first_try_success / total) * 100)


def _build_description(grade, transmission, reconciliation, supplier_health):
	"""Generate actionable summary based on scores."""
	lines = []

	if grade == "A":
		lines.append("Excellent compliance. Audit-ready.")
	elif grade == "B":
		lines.append("Good standing. Minor improvements possible.")
	elif grade == "C":
		lines.append("Needs attention. Review the areas below.")
	else:
		lines.append("High risk. Immediate action required.")

	if transmission < 90:
		lines.append(f"Transmission at {transmission}% — check for pending/failed invoice submissions.")
	if reconciliation < 80:
		lines.append(
			f"Reconciliation at {reconciliation}% — run purchase reconciliation and resolve mismatches."
		)
	if supplier_health < 60:
		lines.append(
			f"Supplier health at {supplier_health}% — verify supplier PINs and check eTIMS registration."
		)

	return " ".join(lines)
