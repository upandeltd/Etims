"""eTIMS Purchase Reconciliation Engine.

Matches KRA's auto-populated purchase data against local Purchase Invoices.
Builds on existing eTIMS Purchase Invoice DocType which stores raw KRA data.
"""
import calendar

import frappe
from frappe import _
from frappe.utils import now_datetime, flt, add_months, getdate


def run_reconciliation(period=None, branch=None):
	"""Run purchase reconciliation for a given period.

	Args:
		period: YYYY-MM string (defaults to previous month)
		branch: Tax Branch Office name (optional)

	Returns:
		dict with reconciliation summary
	"""
	if not frappe.db.exists("DocType", "eTIMS Purchase Register Entry"):
		return {"error": "eTIMS Purchase Register Entry DocType not found"}

	if not period:
		last_month = add_months(getdate(), -1)
		period = last_month.strftime("%Y-%m")

	year, month = period.split("-")
	from_date = f"{year}-{month}-01"
	last_day = calendar.monthrange(int(year), int(month))[1]
	to_date = f"{year}-{month}-{last_day}"

	# Step 0: Pre-match auto-created PIs
	auto_matched = _prematch_auto_created(from_date, to_date, branch)

	# Step 1: Get KRA entries
	kra_entries = _get_kra_entries(from_date, to_date, branch)

	# Step 2: Get local PIs
	local_pis = _get_local_purchase_invoices(from_date, to_date, branch)

	# Step 3: Run matching
	matched = 0
	mismatched = 0
	missing_locally = 0
	total_variance = 0
	matched_pi_names = set()

	for entry in kra_entries:
		if entry.match_status in ("Matched", "Matched (Auto-Created)"):
			matched += 1
			if entry.matched_purchase_invoice:
				matched_pi_names.add(entry.matched_purchase_invoice)
			continue

		result = _match_entry(entry, local_pis, matched_pi_names)

		if result["status"] == "Matched":
			matched += 1
			matched_pi_names.add(result["pi_name"])
		elif result["status"] == "Amount Mismatch":
			mismatched += 1
			total_variance += abs(result.get("variance", 0))
			matched_pi_names.add(result["pi_name"])
		else:
			missing_locally += 1

	# Step 4: Find local PIs not in KRA
	not_in_kra = 0
	for pi in local_pis:
		if pi.name not in matched_pi_names and pi.custom_kra_match_status != "Matched":
			frappe.db.set_value("Purchase Invoice", pi.name,
				"custom_kra_match_status", "Not in KRA", update_modified=False)
			not_in_kra += 1

	# Step 5: Log
	total_matched_all = matched + auto_matched
	total_entries = len(kra_entries)
	match_rate = round((total_matched_all / total_entries) * 100, 1) if total_entries > 0 else 0

	frappe.get_doc({
		"doctype": "eTIMS Reconciliation Log",
		"period": period,
		"branch": branch,
		"run_date": now_datetime(),
		"run_by": frappe.session.user,
		"total_kra_entries": total_entries,
		"match_rate": match_rate,
		"total_matched": total_matched_all,
		"total_mismatched": mismatched,
		"total_missing_locally": missing_locally,
		"total_not_in_kra": not_in_kra,
		"total_variance": total_variance,
	}).insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		"period": period,
		"total_kra_entries": total_entries,
		"matched": total_matched_all,
		"match_rate": match_rate,
		"mismatched": mismatched,
		"missing_locally": missing_locally,
		"not_in_kra": not_in_kra,
		"total_variance": total_variance,
	}


def _prematch_auto_created(from_date, to_date, branch=None):
	filters = {
		"custom_purchase_is_from_etims": 1,
		"docstatus": 1,
		"posting_date": ["between", [from_date, to_date]],
	}
	if branch:
		filters["custom_tax_branch_office"] = branch

	auto_pis = frappe.get_all("Purchase Invoice", filters=filters,
		fields=["name"], limit_page_length=0)

	for pi in auto_pis:
		frappe.db.set_value("Purchase Invoice", pi.name,
			"custom_kra_match_status", "Matched", update_modified=False)

	return len(auto_pis)


def _get_kra_entries(from_date, to_date, branch=None):
	filters = {"invoice_date": ["between", [from_date, to_date]]}
	if branch:
		filters["branch"] = branch

	return frappe.get_all("eTIMS Purchase Register Entry", filters=filters,
		fields=["name", "supplier_pin", "supplier_name", "kra_invoice_number",
			"invoice_date", "total_amount", "tax_amount", "match_status",
			"matched_purchase_invoice"],
		limit_page_length=0)


def _get_local_purchase_invoices(from_date, to_date, branch=None):
	filters = {
		"docstatus": 1,
		"posting_date": ["between", [from_date, to_date]],
	}
	if branch:
		filters["custom_tax_branch_office"] = branch

	return frappe.get_all("Purchase Invoice", filters=filters,
		fields=["name", "supplier", "tax_id", "posting_date",
			"base_grand_total", "base_total_taxes_and_charges",
			"custom_invoice_number", "custom_purchase_is_from_etims",
			"custom_kra_match_status"],
		limit_page_length=0)


def _match_entry(entry, local_pis, already_matched):
	candidates = []

	for pi in local_pis:
		if pi.name in already_matched:
			continue
		# Only match submitted (not cancelled) PIs
		if (pi.tax_id or "") != entry.supplier_pin:
			continue
		# Date tolerance: allow +/- 2 days for transmission delays
		date_diff = abs((getdate(pi.posting_date) - getdate(entry.invoice_date)).days)
		if date_diff > 2:
			continue

		variance = flt(pi.base_grand_total) - flt(entry.total_amount)
		candidates.append({"pi": pi, "variance": variance, "date_diff": date_diff})

	# Sort by: exact date first, then closest amount
	candidates.sort(key=lambda x: (x["date_diff"], abs(x["variance"])))

	if not candidates:
		frappe.db.set_value("eTIMS Purchase Register Entry", entry.name,
			"match_status", "Missing Locally", update_modified=False)
		return {"status": "Missing Locally"}

	candidates.sort(key=lambda x: abs(x["variance"]))
	best = candidates[0]

	if abs(best["variance"]) <= 1:
		_record_match(entry, best["pi"], "Matched", 0)
		return {"status": "Matched", "pi_name": best["pi"].name}
	else:
		_record_match(entry, best["pi"], "Amount Mismatch", best["variance"])
		return {"status": "Amount Mismatch", "pi_name": best["pi"].name,
			"variance": best["variance"]}


def _record_match(entry, pi, status, variance):
	frappe.db.set_value("eTIMS Purchase Register Entry", entry.name, {
		"match_status": status,
		"matched_purchase_invoice": pi.name,
		"variance_amount": variance,
	}, update_modified=False)

	pi_status = "Matched" if status == "Matched" else "Mismatched"
	frappe.db.set_value("Purchase Invoice", pi.name, {
		"custom_kra_match_status": pi_status,
		"custom_kra_variance_amount": variance,
	}, update_modified=False)


@frappe.whitelist()
def run_reconciliation_manual(period=None, branch=None):
	"""Whitelisted method for manual reconciliation trigger."""
	result = run_reconciliation(period, branch)
	frappe.msgprint(
		_("Reconciliation: {matched} matched, {mismatched} mismatched, "
		  "{missing_locally} missing locally, {not_in_kra} not in KRA").format(**result)
	)
	return result


@frappe.whitelist()
def accept_variance(entry_name, reason):
	"""Accept a variance with a reason."""
	frappe.db.set_value("eTIMS Purchase Register Entry", entry_name, {
		"variance_accepted": 1,
		"variance_reason": reason,
	})
	frappe.db.commit()
	return {"status": "success"}


def reconcile_credit_notes(period=None, branch=None):
	"""Reconcile credit notes — KRA negative entries vs local return PIs.

	Credit notes appear in KRA purchase register as negative total_amount
	or specific receipt type codes. Match against local is_return=1 PIs.
	"""
	if not frappe.db.exists("DocType", "eTIMS Purchase Register Entry"):
		return {"matched": 0, "orphaned_kra": 0, "orphaned_local": 0}

	if not period:
		from frappe.utils import add_months, getdate
		last_month = add_months(getdate(), -1)
		period = last_month.strftime("%Y-%m")

	year, month = period.split("-")
	import calendar
	from_date = f"{year}-{month}-01"
	last_day = calendar.monthrange(int(year), int(month))[1]
	to_date = f"{year}-{month}-{last_day}"

	# KRA credit notes — negative amounts
	kra_filters = {
		"invoice_date": ["between", [from_date, to_date]],
		"total_amount": ["<", 0],
	}
	if branch:
		kra_filters["branch"] = branch

	kra_credit_notes = frappe.get_all("eTIMS Purchase Register Entry",
		filters=kra_filters,
		fields=["name", "supplier_pin", "invoice_date", "total_amount", "match_status"],
		limit_page_length=0)

	# Local return Purchase Invoices
	pi_filters = {
		"docstatus": 1,
		"is_return": 1,
		"posting_date": ["between", [from_date, to_date]],
	}
	if branch:
		pi_filters["custom_tax_branch_office"] = branch

	local_returns = frappe.get_all("Purchase Invoice", filters=pi_filters,
		fields=["name", "tax_id", "posting_date", "base_grand_total",
				"return_against", "custom_kra_match_status"],
		limit_page_length=0)

	matched = 0
	matched_pi_names = set()

	for cn in kra_credit_notes:
		if cn.match_status in ("Matched", "Matched (Auto-Created)"):
			matched += 1
			continue

		# Find matching local return
		for pi in local_returns:
			if pi.name in matched_pi_names:
				continue
			if (pi.tax_id or "") != cn.supplier_pin:
				continue
			if str(pi.posting_date) != str(cn.invoice_date):
				continue

			# Credit note amounts are negative in both systems
			variance = abs(flt(pi.base_grand_total)) - abs(flt(cn.total_amount))
			if abs(variance) <= 1:
				_record_match(cn, pi, "Matched", 0)
				matched_pi_names.add(pi.name)
				matched += 1
				break

	orphaned_kra = len([c for c in kra_credit_notes
		if c.match_status not in ("Matched", "Matched (Auto-Created)")])
	orphaned_local = len([p for p in local_returns if p.name not in matched_pi_names])

	frappe.db.commit()
	return {"matched": matched, "orphaned_kra": orphaned_kra, "orphaned_local": orphaned_local}
