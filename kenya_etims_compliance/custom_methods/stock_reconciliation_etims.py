"""eTIMS Stock Movement Reconciliation.

Compares KRA stock movement records against ERPNext Stock Ledger.
Handles item code mapping (KRA eTIMS code vs ERPNext item_code).
"""
import frappe
from frappe.utils import flt


def run_stock_reconciliation(from_date, to_date, branch=None):
	"""Compare KRA stock movements against ERPNext Stock Ledger."""
	if not frappe.db.exists("DocType", "eTIMS Stock Register Entry"):
		return []

	# Build item code mapping: eTIMS code → ERPNext item_code
	etims_to_erpnext = _build_item_code_map()

	# Get KRA data aggregated by item
	kra_summary = _get_kra_summary(from_date, to_date, branch)

	# Get ERPNext SLE data using SQL aggregation (not loading all rows)
	local_summary = _get_local_summary(from_date, to_date, branch)

	# Compare — check both directions
	all_items = set()
	for key in kra_summary:
		all_items.add(key)
	for item_code in local_summary:
		# Map to KRA key format
		all_items.add((item_code, ""))

	results = []

	# Items in KRA
	for key, kra in kra_summary.items():
		etims_code = kra["item_code"]
		# Map KRA eTIMS code to ERPNext item_code
		erpnext_code = etims_to_erpnext.get(etims_code, etims_code)
		local = local_summary.get(erpnext_code, {"qty_in": 0, "qty_out": 0})

		variance_in = flt(local["qty_in"]) - flt(kra["qty_in"])
		variance_out = flt(local["qty_out"]) - flt(kra["qty_out"])
		status = _calc_status(kra, variance_in, variance_out)

		results.append({
			"item_code": erpnext_code,
			"item_name": kra["item_name"],
			"branch": kra["branch"],
			"kra_qty_in": kra["qty_in"],
			"kra_qty_out": kra["qty_out"],
			"local_qty_in": local["qty_in"],
			"local_qty_out": local["qty_out"],
			"variance_in": variance_in,
			"variance_out": variance_out,
			"status": status,
		})

	# Items only in ERPNext (not in KRA) — may indicate untransmitted stock
	kra_erpnext_codes = {etims_to_erpnext.get(kra["item_code"], kra["item_code"])
						 for kra in kra_summary.values()}

	for item_code, local in local_summary.items():
		if item_code in kra_erpnext_codes:
			continue  # Already handled above
		if local["qty_in"] == 0 and local["qty_out"] == 0:
			continue

		item_name = frappe.db.get_value("Item", item_code, "item_name") or item_code
		results.append({
			"item_code": item_code,
			"item_name": item_name,
			"branch": "",
			"kra_qty_in": 0,
			"kra_qty_out": 0,
			"local_qty_in": local["qty_in"],
			"local_qty_out": local["qty_out"],
			"variance_in": local["qty_in"],
			"variance_out": local["qty_out"],
			"status": "Not in KRA",
		})

	# Sort: variances first
	results.sort(key=lambda x: (0 if x["status"] != "Matched" else 1, x["item_code"]))
	return results


def _build_item_code_map():
	"""Map eTIMS item codes to ERPNext item codes."""
	items = frappe.get_all("Item", filters={
		"custom_item_code": ["is", "set"],
		"disabled": 0,
	}, fields=["name", "custom_item_code"], limit_page_length=0)

	return {i.custom_item_code: i.name for i in items}


def _get_kra_summary(from_date, to_date, branch=None):
	"""Aggregate KRA stock register entries by item + branch."""
	filters = {"movement_date": ["between", [from_date, to_date]]}
	if branch:
		filters["branch"] = branch

	kra_entries = frappe.get_all("eTIMS Stock Register Entry", filters=filters,
		fields=["item_code", "item_name", "quantity", "movement_type", "branch"],
		limit_page_length=10000)

	summary = {}
	for entry in kra_entries:
		key = (entry.item_code, entry.branch or "")
		if key not in summary:
			summary[key] = {"item_code": entry.item_code, "item_name": entry.item_name,
				"branch": entry.branch, "qty_in": 0, "qty_out": 0}
		# SAR types: 02=Purchase, 04=Transfer In, 06=Material Receipt → IN
		# 11=Sales, 03=Sales Return, 12=Purchase Return, 13=Transfer Out → OUT
		if entry.movement_type in ("02", "04", "06"):
			summary[key]["qty_in"] += flt(entry.quantity)
		elif entry.movement_type in ("11", "03", "12", "13"):
			summary[key]["qty_out"] += flt(entry.quantity)

	return summary


def _get_local_summary(from_date, to_date, branch=None):
	"""Aggregate ERPNext Stock Ledger using SQL — avoids loading all rows."""
	warehouse_filter = ""
	params = {"from_date": from_date, "to_date": to_date}

	if branch:
		# Get warehouses linked to this branch
		warehouses = frappe.get_all("TIS Device Initialization",
			filters={"branch_id": branch, "active": 1},
			fields=["default_sales_warehouse", "default_stores_warehouse"])

		wh_list = set()
		for w in warehouses:
			if w.default_sales_warehouse:
				wh_list.add(w.default_sales_warehouse)
			if w.default_stores_warehouse:
				wh_list.add(w.default_stores_warehouse)

		if wh_list:
			warehouse_filter = "AND sle.warehouse IN %(warehouses)s"
			params["warehouses"] = list(wh_list)

	result = frappe.db.sql(f"""
		SELECT
			sle.item_code,
			SUM(CASE WHEN sle.actual_qty > 0 THEN sle.actual_qty ELSE 0 END) as qty_in,
			SUM(CASE WHEN sle.actual_qty < 0 THEN ABS(sle.actual_qty) ELSE 0 END) as qty_out
		FROM `tabStock Ledger Entry` sle
		WHERE sle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		AND sle.is_cancelled = 0
		{warehouse_filter}
		GROUP BY sle.item_code
	""", params, as_dict=True)

	return {r.item_code: {"qty_in": flt(r.qty_in), "qty_out": flt(r.qty_out)} for r in result}


def _calc_status(kra, variance_in, variance_out):
	"""Determine match status with 1% threshold."""
	if abs(variance_in) <= 0.01 and abs(variance_out) <= 0.01:
		return "Matched"

	threshold_in = max(flt(kra["qty_in"]) * 0.01, 1)
	threshold_out = max(flt(kra["qty_out"]) * 0.01, 1)

	if abs(variance_in) > threshold_in or abs(variance_out) > threshold_out:
		return "Variance"

	return "Matched"
