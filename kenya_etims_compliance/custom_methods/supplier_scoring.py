"""Supplier eTIMS Compliance Scoring.

Calculates a 0-100 compliance score for each supplier based on:
- PIN verification status (30%)
- eTIMS registration (25%)
- Invoice transmission rate (25%)
- Credit note ratio (10%)
- Payment history (10%)
"""
import frappe
from frappe.utils import now_datetime, add_days, flt, getdate


def calculate_supplier_scores(limit=200):
	"""Recalculate compliance scores for active suppliers."""
	suppliers = frappe.get_all("Supplier", filters={
		"disabled": 0,
		"custom_supplier_pin": ["is", "set"],
	}, fields=["name", "custom_supplier_pin", "custom_kra_pin_verified",
			   "custom_kra_pin_verified_date", "custom_etims_registered"],
	   limit=limit)

	for supplier in suppliers:
		score = _calculate_score(supplier)
		status = _score_to_status(score)

		frappe.db.set_value("Supplier", supplier.name, {
			"custom_etims_compliance_score": score,
			"custom_etims_compliance_status": status,
		}, update_modified=False)

	frappe.db.commit()
	return {"processed": len(suppliers)}


def _calculate_score(supplier):
	score = 0

	# PIN Valid (30%) — verified within last 30 days
	if supplier.custom_kra_pin_verified:
		if supplier.custom_kra_pin_verified_date:
			days_since = (getdate() - getdate(supplier.custom_kra_pin_verified_date)).days
			if days_since <= 30:
				score += 30
			elif days_since <= 90:
				score += 15
		else:
			score += 15

	# eTIMS Registered (25%)
	if supplier.custom_etims_registered:
		score += 25

	# Transmission Rate (25%) — % of PIs from this supplier found in KRA
	transmission_score = _get_transmission_rate(supplier.name)
	score += round(transmission_score * 0.25)

	# Credit Note Ratio (10%) — lower is better
	credit_score = _get_credit_note_score(supplier.name)
	score += round(credit_score * 0.10)

	# Payment History (10%) — has payments on time
	payment_score = _get_payment_score(supplier.name)
	score += round(payment_score * 0.10)

	return min(score, 100)


def _get_transmission_rate(supplier_name):
	"""% of Purchase Invoices from this supplier that have KRA match."""
	total = frappe.db.count("Purchase Invoice", filters={
		"supplier": supplier_name, "docstatus": 1,
	})
	if not total:
		return 50  # No data — neutral score

	matched = frappe.db.count("Purchase Invoice", filters={
		"supplier": supplier_name, "docstatus": 1,
		"custom_kra_match_status": ["in", ["Matched", "Mismatched"]],
	})

	rate = (matched / total) * 100
	# Update transmission rate field
	frappe.db.set_value("Supplier", supplier_name,
		"custom_etims_transmission_rate", rate, update_modified=False)
	return rate


def _get_credit_note_score(supplier_name):
	"""Score based on credit note frequency — lower ratio = higher score."""
	total = frappe.db.count("Purchase Invoice", filters={
		"supplier": supplier_name, "docstatus": 1,
	})
	if not total:
		return 100

	returns = frappe.db.count("Purchase Invoice", filters={
		"supplier": supplier_name, "docstatus": 1, "is_return": 1,
	})

	ratio = returns / total
	if ratio <= 0.05:
		return 100
	elif ratio <= 0.15:
		return 70
	elif ratio <= 0.30:
		return 40
	return 10


def _get_payment_score(supplier_name):
	"""Score based on whether payments exist for this supplier."""
	has_payments = frappe.db.count("Payment Entry", filters={
		"party_type": "Supplier", "party": supplier_name, "docstatus": 1,
	})
	return 100 if has_payments else 50


def _score_to_status(score):
	if score >= 75:
		return "Compliant"
	elif score >= 50:
		return "At Risk"
	elif score > 0:
		return "Non-Compliant"
	return "Unknown"
