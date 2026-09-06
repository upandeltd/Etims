"""eTIMS Purchase Reconciliation Engine.

Matches KRA's auto-populated purchase data against local Purchase Invoices.
Builds on existing eTIMS Purchase Invoice DocType which stores raw KRA data.
"""

import calendar

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import add_months, flt, getdate, now_datetime

from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
	get_etims_settings,
)
from kenya_etims_compliance.utils.etims_utils import KRA_TAX_BANDS


def run_reconciliation(period=None, branch=None):
	"""Reconcile a period's purchases against KRA's register and file its exceptions.

	The eTIMS Reconciliation Log for a (period, branch) pair *is* the period
	document: re-running updates it in place and rebuilds its exception table,
	so there is one authoritative statement of where the books and KRA's
	purchase register disagree. A Closed period is a filed snapshot - it is
	refused rather than silently rewritten.

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

	log = _get_period_log(period, branch)
	if log and log.status == "Closed":
		return {
			"error": _("Period {0} is closed. Re-open it before reconciling again.").format(period),
			"period": period,
			"log": log.name,
		}

	# Step 0: Mark auto-created (from-eTIMS) PIs as Matched. Their corresponding
	# KRA register entries are still counted once by the main loop below, so the
	# count must NOT be added again — doing so double-counted them and pushed
	# match_rate above 100%.
	_prematch_auto_created(from_date, to_date, branch)

	kra_entries = _get_kra_entries(from_date, to_date, branch)
	local_pis = _get_local_purchase_invoices(from_date, to_date, branch)

	matched = 0
	mismatched = 0
	missing_locally = 0
	total_variance = 0
	matched_pi_names = set()
	exceptions = []

	for entry in kra_entries:
		if entry.match_status in ("Matched", "Matched (Auto-Created)"):
			matched += 1
			if entry.matched_purchase_invoice:
				matched_pi_names.add(entry.matched_purchase_invoice)
				exceptions.extend(_band_exceptions(entry, entry.matched_purchase_invoice))
			continue

		result = _match_entry(entry, local_pis, matched_pi_names)

		if result["status"] == "Matched":
			matched += 1
			matched_pi_names.add(result["pi_name"])
			exceptions.extend(_band_exceptions(entry, result["pi_name"]))
			continue

		if result["status"] == "Amount Mismatch":
			mismatched += 1
			total_variance += abs(flt(result.get("variance")))
			matched_pi_names.add(result["pi_name"])
			exceptions.extend(_band_exceptions(entry, result["pi_name"]))
		else:
			missing_locally += 1

		exceptions.append(_kra_exception(entry, result))

	# Local invoices KRA never received. Accepted ones stay in the table as
	# accepted rows - dropping them would make a resolved exception look like
	# it never existed.
	not_in_kra = 0
	for pi in local_pis:
		if pi.name in matched_pi_names or pi.custom_kra_match_status == "Matched":
			continue

		accepted = pi.custom_kra_match_status == "Accepted"
		if not accepted:
			frappe.db.set_value(
				"Purchase Invoice", pi.name, "custom_kra_match_status", "Not in KRA", update_modified=False
			)
		not_in_kra += 1
		exceptions.append(_local_exception(pi, accepted))

	total_entries = len(kra_entries)
	match_rate = round((matched / total_entries) * 100, 1) if total_entries > 0 else 0
	unresolved = len([e for e in exceptions if not e["accepted"]])
	band_mismatches = len([e for e in exceptions if e["exception_type"] == "Band Mismatch"])

	log_name = _write_period_log(
		log,
		{
			"period": period,
			"branch": branch,
			"run_date": now_datetime(),
			"run_by": frappe.session.user,
			"total_kra_entries": total_entries,
			"match_rate": match_rate,
			"total_matched": matched,
			"total_mismatched": mismatched,
			"total_missing_locally": missing_locally,
			"total_not_in_kra": not_in_kra,
			"total_band_mismatches": band_mismatches,
			"total_variance": total_variance,
			"total_exceptions": len(exceptions),
			"unresolved_exceptions": unresolved,
		},
		exceptions,
	)

	return {
		"period": period,
		"log": log_name,
		"total_kra_entries": total_entries,
		"matched": matched,
		"match_rate": match_rate,
		"mismatched": mismatched,
		"missing_locally": missing_locally,
		"not_in_kra": not_in_kra,
		"band_mismatches": band_mismatches,
		"total_variance": total_variance,
		"exceptions": len(exceptions),
		"unresolved": unresolved,
	}


def _get_period_log(period, branch=None):
	"""The newest reconciliation log for this period+branch, or None."""
	filters = {"period": period, "branch": branch if branch else ["in", ["", None]]}
	return frappe.db.get_value(
		"eTIMS Reconciliation Log",
		filters,
		["name", "status"],
		as_dict=True,
		order_by="creation desc",
	)


def _write_period_log(log, summary, exceptions):
	"""Create or refresh the period's log. Returns its name."""
	doc = (
		frappe.get_doc("eTIMS Reconciliation Log", log.name)
		if log
		else frappe.new_doc("eTIMS Reconciliation Log")
	)
	doc.update(summary)
	doc.status = "Draft"
	doc.set("exceptions", exceptions)
	doc.save(ignore_permissions=True)
	return doc.name


def _kra_exception(entry, result):
	pi = result.get("pi")
	return {
		"source": "KRA",
		"exception_type": result["status"],
		"supplier_pin": entry.supplier_pin,
		"supplier_name": entry.supplier_name,
		"kra_invoice_number": entry.kra_invoice_number,
		"invoice_date": entry.invoice_date,
		"kra_amount": entry.total_amount,
		"local_amount": flt(pi.base_grand_total) if pi else 0,
		"variance_amount": flt(result.get("variance")),
		"register_entry": entry.name,
		"purchase_invoice": pi.name if pi else None,
		"accepted": 1 if entry.variance_accepted else 0,
		"accepted_reason": entry.variance_reason,
	}


def _local_exception(pi, accepted):
	return {
		"source": "Local",
		"exception_type": "Not in KRA",
		"supplier_pin": pi.tax_id,
		"supplier_name": pi.supplier,
		"kra_invoice_number": pi.bill_no,
		"invoice_date": pi.posting_date,
		"kra_amount": 0,
		"local_amount": pi.base_grand_total,
		"variance_amount": flt(pi.base_grand_total),
		"purchase_invoice": pi.name,
		"accepted": 1 if accepted else 0,
		"accepted_reason": pi.custom_kra_acceptance_reason if accepted else None,
	}


def _prematch_auto_created(from_date, to_date, branch=None):
	filters = {
		"custom_purchase_is_from_etims": 1,
		"docstatus": 1,
		"posting_date": ["between", [from_date, to_date]],
	}
	if branch:
		filters["custom_tax_branch_office"] = branch

	auto_pis = frappe.get_all("Purchase Invoice", filters=filters, fields=["name"], limit_page_length=0)

	for pi in auto_pis:
		frappe.db.set_value(
			"Purchase Invoice", pi.name, "custom_kra_match_status", "Matched", update_modified=False
		)

	return len(auto_pis)


def _get_kra_entries(from_date, to_date, branch=None):
	filters = {"invoice_date": ["between", [from_date, to_date]]}
	if branch:
		filters["branch"] = branch

	return frappe.get_all(
		"eTIMS Purchase Register Entry",
		filters=filters,
		fields=[
			"name",
			"supplier_pin",
			"supplier_name",
			"kra_invoice_number",
			"invoice_date",
			"total_amount",
			"tax_amount",
			"match_status",
			"matched_purchase_invoice",
			"etims_purchase_invoice",
			"variance_accepted",
			"variance_reason",
		],
		limit_page_length=0,
	)


def _get_local_purchase_invoices(from_date, to_date, branch=None):
	filters = {
		"docstatus": 1,
		"posting_date": ["between", [from_date, to_date]],
	}
	if branch:
		filters["custom_tax_branch_office"] = branch

	return frappe.get_all(
		"Purchase Invoice",
		filters=filters,
		fields=[
			"name",
			"supplier",
			"tax_id",
			"posting_date",
			"base_grand_total",
			"base_total_taxes_and_charges",
			"custom_invoice_number",
			"custom_purchase_is_from_etims",
			"custom_kra_match_status",
			"custom_kra_acceptance_reason",
			"bill_no",
		],
		limit_page_length=0,
	)


def _normalise_invoice_no(value):
	"""Comparable form of a supplier invoice number.

	KRA stores ``spplrInvcNo`` as an integer sequence, ERPNext stores the same
	number as free text in ``bill_no``, so "0544", 544 and " 544 " all have to
	compare equal.
	"""
	text = str(value or "").strip().upper()
	return text.lstrip("0") or text


def _match_entry(entry, local_pis, already_matched):
	"""Match one KRA register entry to a local Purchase Invoice.

	Identity first: KRA's ``spplrInvcNo`` is the supplier's own invoice number,
	which this app already transmits from ``bill_no`` (purchase_invoice.py) and
	stores back on verification. When both sides carry it the pair is certain,
	and any difference in money is then a real amount discrepancy rather than a
	bad guess. Only when the number is missing or unmatched does the date+amount
	heuristic run, and it stays tight - a wrong pairing files a wrong return.
	"""
	kra_invoice_no = _normalise_invoice_no(entry.kra_invoice_number)
	candidates = []

	for pi in local_pis:
		if pi.name in already_matched:
			continue
		# Only match submitted (not cancelled) PIs
		if (pi.tax_id or "") != entry.supplier_pin:
			continue

		variance = flt(pi.base_grand_total) - flt(entry.total_amount)

		if kra_invoice_no and _normalise_invoice_no(pi.bill_no) == kra_invoice_no:
			# No date window here: a supplier's invoice number is unique within
			# their own sequence, and late filing is exactly the case where the
			# dates legitimately differ by more than the tolerance.
			return _settle(entry, pi, variance)

		# Date tolerance: allow +/- 2 days for transmission delays
		date_diff = abs((getdate(pi.posting_date) - getdate(entry.invoice_date)).days)
		if date_diff > 2:
			continue

		candidates.append({"pi": pi, "variance": variance, "date_diff": date_diff})

	if not candidates:
		frappe.db.set_value(
			"eTIMS Purchase Register Entry",
			entry.name,
			"match_status",
			"Missing Locally",
			update_modified=False,
		)
		return {"status": "Missing Locally"}

	# Closest date first, then closest amount. The previous code re-sorted on
	# amount alone immediately afterwards, throwing the date preference away.
	candidates.sort(key=lambda c: (c["date_diff"], abs(c["variance"])))
	best = candidates[0]

	return _settle(entry, best["pi"], best["variance"])


def _settle(entry, pi, variance):
	# 1 KES absorbs rounding between KRA's own totals and ERPNext's.
	status = "Matched" if abs(variance) <= 1 else "Amount Mismatch"
	_record_match(entry, pi, status, 0 if status == "Matched" else variance)
	return {"status": status, "pi_name": pi.name, "pi": pi, "variance": variance}


def _record_match(entry, pi, status, variance):
	frappe.db.set_value(
		"eTIMS Purchase Register Entry",
		entry.name,
		{
			"match_status": status,
			"matched_purchase_invoice": pi.name,
			"variance_amount": variance,
		},
		update_modified=False,
	)

	pi_status = "Matched" if status == "Matched" else "Mismatched"
	frappe.db.set_value(
		"Purchase Invoice",
		pi.name,
		{
			"custom_kra_match_status": pi_status,
			"custom_kra_variance_amount": variance,
		},
		update_modified=False,
	)


def _get_kra_bands(etims_purchase_invoice):
	"""KRA's own per-band decomposition for one already-stored purchase row.

	eTIMS Purchase Invoice is the only place this ever lands (see
	upsert_purchase_invoice) - the register entry itself only carries a
	single total_amount/tax_amount pair.
	"""
	fields = [f"taxable_amount_{code.lower()}" for code in KRA_TAX_BANDS] + [
		f"tax_amt_{code.lower()}" for code in KRA_TAX_BANDS
	]
	row = frappe.db.get_value("eTIMS Purchase Invoice", etims_purchase_invoice, fields, as_dict=True)
	if not row:
		return {}
	return {
		code: {
			"taxable_amount": flt(row.get(f"taxable_amount_{code.lower()}")),
			"tax_amount": flt(row.get(f"tax_amt_{code.lower()}")),
		}
		for code in KRA_TAX_BANDS
	}


def _get_local_purchase_bands(pi_name):
	"""One Purchase Invoice's own tax rows, aggregated by KRA A-E band.

	Same custom_code / custom_total_taxable_amount /
	base_tax_amount_after_discount_amount fields the VAT Return Preview
	report aggregates across a period, scoped here to a single invoice.
	"""
	child = frappe.qb.DocType("Purchase Taxes and Charges")
	rows = (
		frappe.qb.from_(child)
		.where(child.parent == pi_name)
		.where(child.custom_code.isin(list(KRA_TAX_BANDS)))
		.groupby(child.custom_code)
		.select(
			child.custom_code.as_("tax_code"),
			Sum(child.custom_total_taxable_amount).as_("taxable_amount"),
			Sum(child.base_tax_amount_after_discount_amount).as_("tax_amount"),
		)
		.run(as_dict=True)
	)
	return {
		row.tax_code: {"taxable_amount": flt(row.taxable_amount), "tax_amount": flt(row.tax_amount)}
		for row in rows
	}


def _band_exceptions(entry, pi_name):
	"""Compare KRA's per-band decomposition against the matched PI's own tax
	rows. A clean total match can still hide a wrong VAT band classification
	- e.g. a standard-rated item recorded as exempt nets the same grand
	total but files the wrong return - so every matched pair is checked
	band by band, not just on the total that already agreed.
	"""
	if not entry.etims_purchase_invoice:
		return []

	kra_bands = _get_kra_bands(entry.etims_purchase_invoice)
	if not kra_bands:
		return []
	local_bands = _get_local_purchase_bands(pi_name)

	zero = {"taxable_amount": 0.0, "tax_amount": 0.0}
	exceptions = []
	for code in KRA_TAX_BANDS:
		kra = kra_bands.get(code, zero)
		local = local_bands.get(code, zero)
		variance = kra["tax_amount"] - local["tax_amount"]
		# Same 1 KES rounding tolerance _settle uses for the invoice total.
		if abs(variance) <= 1 and abs(kra["taxable_amount"] - local["taxable_amount"]) <= 1:
			continue

		exceptions.append(
			{
				"source": "KRA",
				"exception_type": "Band Mismatch",
				"supplier_pin": entry.supplier_pin,
				"supplier_name": entry.supplier_name,
				"kra_invoice_number": entry.kra_invoice_number,
				"invoice_date": entry.invoice_date,
				"band_code": code,
				"kra_amount": kra["tax_amount"],
				"local_amount": local["tax_amount"],
				"variance_amount": variance,
				"register_entry": entry.name,
				"purchase_invoice": pi_name,
				"accepted": 1 if entry.variance_accepted else 0,
				"accepted_reason": entry.variance_reason,
			}
		)
	return exceptions


@frappe.whitelist()
def run_reconciliation_manual(period=None, branch=None):
	"""Whitelisted method for manual reconciliation trigger."""
	frappe.has_permission("eTIMS Reconciliation Log", "create", throw=True)
	result = run_reconciliation(period, branch)
	if result.get("error"):
		frappe.throw(result["error"])
	frappe.msgprint(
		_(
			"{period}: {matched} matched ({match_rate}%), {mismatched} mismatched, "
			"{missing_locally} missing locally, {not_in_kra} not in KRA, "
			"{band_mismatches} band mismatches. "
			"{unresolved} of {exceptions} exceptions unresolved."
		).format(**result)
	)
	return result


@frappe.whitelist()
def accept_local_exception(purchase_invoice, reason):
	"""Accept a purchase KRA has no record of, so it stops blocking the close.

	Acceptance lives on the source record, never on the log's exception row, so
	it survives a re-run: the next reconciliation rebuilds the table and reads
	the acceptance back. The KRA side of the same decision is the register
	entry's own `variance_accepted` field, which its form already exposes.
	"""
	if not reason:
		frappe.throw(_("A reason is required to accept a reconciliation exception."))

	frappe.has_permission("Purchase Invoice", "write", throw=True)
	frappe.db.set_value(
		"Purchase Invoice",
		purchase_invoice,
		{
			"custom_kra_match_status": "Accepted",
			"custom_kra_acceptance_reason": reason,
		},
		update_modified=False,
	)
	return {"status": "success"}


@frappe.whitelist()
def close_period(period, branch=None):
	"""Freeze a period once its exceptions are resolved.

	A close is only meaningful over freshly computed numbers, so this re-runs
	the reconciliation first and refuses while anything is still unresolved -
	that refusal is the whole control. `enforce_invoice_verification` turns it
	into advice instead of a block for businesses that reconcile after filing.
	"""
	frappe.has_permission("eTIMS Reconciliation Log", "write", throw=True)

	result = run_reconciliation(period, branch)
	if result.get("error"):
		frappe.throw(result["error"])

	unresolved = result["unresolved"]
	if unresolved and get_etims_settings().get("enforce_invoice_verification", 1):
		frappe.throw(
			_(
				"{0} unresolved {1} in {2}. Accept each one with a reason, or fix the "
				"underlying invoice and re-run, before closing the period."
			).format(unresolved, _("exception") if unresolved == 1 else _("exceptions"), period)
		)

	frappe.db.set_value(
		"eTIMS Reconciliation Log",
		result["log"],
		{
			"status": "Closed",
			"closed_by": frappe.session.user,
			"closed_on": now_datetime(),
		},
	)
	return result


@frappe.whitelist()
def reopen_period(log_name, reason):
	"""Reopen a closed period. Auditable, and deliberately not silent."""
	frappe.has_permission("eTIMS Reconciliation Log", "write", throw=True)
	if not reason:
		frappe.throw(_("A reason is required to reopen a closed period."))

	doc = frappe.get_doc("eTIMS Reconciliation Log", log_name)
	doc.status = "Draft"
	doc.closed_by = None
	doc.closed_on = None
	doc.save()
	doc.add_comment("Info", _("Period reopened: {0}").format(reason))
	return {"status": "success", "log": doc.name}


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

	kra_credit_notes = frappe.get_all(
		"eTIMS Purchase Register Entry",
		filters=kra_filters,
		fields=["name", "supplier_pin", "invoice_date", "total_amount", "match_status"],
		limit_page_length=0,
	)

	# Local return Purchase Invoices
	pi_filters = {
		"docstatus": 1,
		"is_return": 1,
		"posting_date": ["between", [from_date, to_date]],
	}
	if branch:
		pi_filters["custom_tax_branch_office"] = branch

	local_returns = frappe.get_all(
		"Purchase Invoice",
		filters=pi_filters,
		fields=[
			"name",
			"tax_id",
			"posting_date",
			"base_grand_total",
			"return_against",
			"custom_kra_match_status",
		],
		limit_page_length=0,
	)

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

	orphaned_kra = len(
		[c for c in kra_credit_notes if c.match_status not in ("Matched", "Matched (Auto-Created)")]
	)
	orphaned_local = len([p for p in local_returns if p.name not in matched_pi_names])

	frappe.db.commit()
	return {"matched": matched, "orphaned_kra": orphaned_kra, "orphaned_local": orphaned_local}
