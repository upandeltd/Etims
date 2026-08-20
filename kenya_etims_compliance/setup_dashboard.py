"""Create Number Cards and Dashboard Charts referenced by the eTIMS workspace.

Wired into `after_migrate` (hooks.py) so the workspace's number_card/chart blocks
have backing documents. Idempotently REPAIRS each card/chart on every run
(drop-then-recreate), so a card that failed once is recovered on the next
migrate. Defensive — a single failed insert is logged and skipped so it can
never abort `bench migrate`.

Two hard requirements learned from rendering these on a live v15 bench:
  1. Card/chart `name`s MUST match the `number_card_name` / `chart_name` refs in
     kenya_etims_compliance/workspace/etims_compliance/etims_compliance.json, and
     a Number Card's name derives from its `label` (so label == the ref).
  2. `filters_json` for Document-type cards and Count charts MUST be a LIST of
     [doctype, field, operator, value] conditions, NOT a dict. A dict becomes a
     frappe._dict whose `.append` is None, crashing dashboard_chart.get() with
     "'NoneType' object is not callable".
"""

import frappe


def create_number_cards():
	cards = [
		{
			"name": "eTIMS Sales Today",
			"label": "eTIMS Sales Today",
			"document_type": "Sales Invoice",
			"function": "Count",
			"filters_json": '[["Sales Invoice","docstatus","=",1],["Sales Invoice","posting_date","=",Today]]',
			"color": "#10b981",
		},
		{
			"name": "eTIMS Sales This Month",
			"label": "eTIMS Sales This Month",
			"document_type": "Sales Invoice",
			"function": "Count",
			"filters_json": '[["Sales Invoice","docstatus","=",1],["Sales Invoice","posting_date","between",[This Month]]]',
			"color": "#3b82f6",
		},
		{
			"name": "eTIMS Pending Queue",
			"label": "eTIMS Pending Queue",
			"document_type": "eTIMS Invoice Queue",
			"function": "Count",
			"filters_json": '[["eTIMS Invoice Queue","status","in",["Queued","Processing"]]]',
			"color": "#f59e0b",
		},
		{
			"name": "eTIMS Failed Today",
			"label": "eTIMS Failed Today",
			"document_type": "eTIMS Invoice Queue",
			"function": "Count",
			"filters_json": '[["eTIMS Invoice Queue","status","=","Failed"],["eTIMS Invoice Queue","modified","Today"]]',
			"color": "#ef4444",
		},
		{
			"name": "eTIMS Purchase Today",
			"label": "eTIMS Purchase Today",
			"document_type": "Purchase Invoice",
			"function": "Count",
			"filters_json": '[["Purchase Invoice","docstatus","=",1],["Purchase Invoice","posting_date","=",Today]]',
			"color": "#8b5cf6",
		},
		{
			"name": "eTIMS Purchase This Month",
			"label": "eTIMS Purchase This Month",
			"document_type": "Purchase Invoice",
			"function": "Count",
			"filters_json": '[["Purchase Invoice","docstatus","=",1],["Purchase Invoice","posting_date","between",[This Month]]]',
			"color": "#06b6d4",
		},
		# --- Enhanced dashboard cards ---
		{
			"name": "eTIMS Sales Amount Today",
			"label": "eTIMS Sales Amount Today",
			"document_type": "Sales Invoice",
			"function": "Sum",
			"filters_json": '[["Sales Invoice","docstatus","=",1],["Sales Invoice","posting_date","=",Today]]',
			"color": "#10b981",
		},
		{
			"name": "eTIMS Sales Amount Month",
			"label": "eTIMS Sales Amount Month",
			"document_type": "Sales Invoice",
			"function": "Sum",
			"filters_json": '[["Sales Invoice","docstatus","=",1],["Sales Invoice","posting_date","between",[This Month]]]',
			"color": "#10b981",
		},
		{
			"name": "eTIMS Stock Entries Today",
			"label": "eTIMS Stock Entries Today",
			"document_type": "Stock Entry",
			"function": "Count",
			"filters_json": '[["Stock Entry","docstatus","=",1],["Stock Entry","posting_date","=",Today]]',
			"color": "#f97316",
		},
		{
			"name": "eTIMS Suppliers Verified",
			"label": "eTIMS Suppliers Verified",
			"document_type": "Supplier",
			"function": "Count",
			"filters_json": '[["Supplier","custom_kra_pin_verified","=",1]]',
			"color": "#22c55e",
		},
		{
			"name": "eTIMS Suppliers Unverified",
			"label": "eTIMS Suppliers Unverified",
			"document_type": "Supplier",
			"function": "Count",
			"filters_json": '[["Supplier","custom_kra_pin_verified","=",0]]',
			"color": "#eab308",
		},
		{
			"name": "eTIMS Days To Filing",
			"label": "eTIMS Days To Filing",
			"type": "Custom",
			"document_type": "eTIMS Settings",
			"function": "kenya_etims_compliance.custom_methods.dashboard.get_days_to_filing_deadline",
			"color": "#7c3aed",
		},
	]

	for c in cards:
		# Idempotent repair: always drop + recreate. A card/chart that failed once
		# would otherwise freeze on disk forever (skip-if-exists never repaired it).
		if frappe.db.exists("Number Card", c["name"]):
			frappe.delete_doc("Number Card", c["name"], ignore_permissions=True, force=True)
		try:
			doc_data = {
				"doctype": "Number Card",
				"name": c["name"],
				"label": c["label"],
				"type": c.get("type", "Document Type"),
				"filters_json": c.get("filters_json", "[]"),
				"color": c.get("color"),
				"show_percentage_stats": c.get("show_percentage_stats", 0),
				"stats_time_interval": c.get("stats_time_interval", "Daily"),
				"is_public": 1,
			}
			if c.get("type", "Document Type") == "Document Type":
				doc_data["document_type"] = c["document_type"]
				doc_data["function"] = c["function"]
			elif c.get("type") == "Custom":
				doc_data["method"] = c["function"]
				if c.get("document_type"):
					doc_data["document_type"] = c["document_type"]
			frappe.get_doc(doc_data).insert(ignore_permissions=True)
			frappe.logger().debug(f"Created number card: {c['name']}")
		except Exception:
			# Never abort migrate on a single bad card (e.g. missing field on a bench)
			frappe.log_error(
				title=f"eTIMS: number card create failed: {c['name']}"[:140],
				message=frappe.get_traceback(),
			)


def create_dashboard_charts():
	charts = [
		{
			"name": "eTIMS Monthly Sales Transmission",
			"chart_name": "eTIMS Monthly Sales Transmission",
			"chart_type": "Count",
			"document_type": "Sales Invoice",
			"based_on": "posting_date",
			"type": "Bar",
			"color": "#10b981",
			"timespan": "Last Year",
			"time_interval": "Monthly",
			"filters_json": '[["Sales Invoice","docstatus","=",1],["Sales Invoice","custom_update_invoice_in_tims","=",1]]',
		},
		{
			"name": "eTIMS Monthly Purchase Transmission",
			"chart_name": "eTIMS Monthly Purchase Transmission",
			"chart_type": "Count",
			"document_type": "Purchase Invoice",
			"based_on": "posting_date",
			"type": "Bar",
			"color": "#3b82f6",
			"timespan": "Last Year",
			"time_interval": "Monthly",
			"filters_json": '[["Purchase Invoice","docstatus","=",1],["Purchase Invoice","custom_update_purchase_in_tims","=",1]]',
		},
		{
			"name": "eTIMS Queue Status Breakdown",
			"chart_name": "eTIMS Queue Status Breakdown",
			"chart_type": "Group By",
			"document_type": "eTIMS Invoice Queue",
			"group_by_based_on": "status",
			"type": "Pie",
			"color": "#f59e0b",
			"filters_json": "[]",
		},
		{
			"name": "eTIMS Daily Queue Volume",
			"chart_name": "eTIMS Daily Queue Volume",
			"chart_type": "Count",
			"document_type": "eTIMS Invoice Queue",
			"based_on": "creation",
			"type": "Line",
			"color": "#06b6d4",
			"timespan": "Last Month",
			"time_interval": "Daily",
			"filters_json": "[]",
		},
	]

	for c in charts:
		# Idempotent repair: same drop-then-create pattern as number cards.
		if frappe.db.exists("Dashboard Chart", c["name"]):
			frappe.delete_doc("Dashboard Chart", c["name"], ignore_permissions=True, force=True)
		try:
			doc_data = {
				"doctype": "Dashboard Chart",
				"name": c["name"],
				"chart_name": c["chart_name"],
				"chart_type": c["chart_type"],
				"document_type": c["document_type"],
				"type": c["type"],
				"color": c.get("color"),
				"is_public": 1,
				"filters_json": c.get("filters_json", "[]"),
			}
			if c["chart_type"] == "Count":
				doc_data["based_on"] = c["based_on"]
				doc_data["timespan"] = c.get("timespan", "Last Year")
				doc_data["time_interval"] = c.get("time_interval", "Monthly")
			elif c["chart_type"] == "Group By":
				doc_data["group_by_based_on"] = c["group_by_based_on"]

			frappe.get_doc(doc_data).insert(ignore_permissions=True)
			frappe.logger().debug(f"Created dashboard chart: {c['name']}")
		except Exception:
			frappe.log_error(
				title=f"eTIMS: dashboard chart create failed: {c['name']}"[:140],
				message=frappe.get_traceback(),
			)


def execute():
	"""Entry point wired into after_migrate."""
	create_number_cards()
	create_dashboard_charts()
	frappe.db.commit()
	frappe.logger().info("eTIMS dashboard setup complete")
