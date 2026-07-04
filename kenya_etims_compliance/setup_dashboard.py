"""Create Number Cards and Dashboard Charts referenced by the eTIMS workspace.

Wired into `after_migrate` (hooks.py) so the workspace's number_card/chart blocks
have backing documents. Idempotent (skips existing) and defensive — a single
failed insert is logged and skipped so it can never abort `bench migrate`.

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
			"name": "Sales Transmitted",
			"label": "Sales Transmitted",
			"document_type": "Sales Invoice",
			"function": "Count",
			"filters_json": '[["Sales Invoice","docstatus","=",1],["Sales Invoice","custom_update_sales_to_etims","=",1]]',
			"color": "#2ecc71",
			"show_percentage_stats": 1,
			"stats_time_interval": "Monthly",
		},
		{
			"name": "Sales Pending",
			"label": "Sales Pending",
			"document_type": "Sales Invoice",
			"function": "Count",
			"filters_json": '[["Sales Invoice","docstatus","=",1],["Sales Invoice","custom_update_invoice_in_tims","=",1],["Sales Invoice","custom_update_sales_to_etims","=",0]]',
			"color": "#f39c12",
			"show_percentage_stats": 1,
			"stats_time_interval": "Monthly",
		},
		{
			"name": "Purchases Matched",
			"label": "Purchases Matched",
			"document_type": "Purchase Invoice",
			"function": "Count",
			"filters_json": '[["Purchase Invoice","docstatus","=",1],["Purchase Invoice","custom_kra_match_status","=","Matched"]]',
			"color": "#2ecc71",
			"show_percentage_stats": 1,
			"stats_time_interval": "Monthly",
		},
		{
			"name": "Queue Pending",
			"label": "Queue Pending",
			"document_type": "eTIMS Invoice Queue",
			"function": "Count",
			"filters_json": '[["eTIMS Invoice Queue","status","in",["Queued","Failed"]]]',
			"color": "#e74c3c",
		},
		{
			"name": "Suppliers Verified",
			"label": "Suppliers Verified",
			"document_type": "Supplier",
			"function": "Count",
			"filters_json": '[["Supplier","disabled","=",0],["Supplier","custom_kra_pin_verified","=",1]]',
			"color": "#3498db",
		},
		{
			# Number Card derives its name from `label`, so label MUST equal the
			# workspace's number_card_name reference ("Errors This Month").
			"name": "Errors This Month",
			"label": "Errors This Month",
			"document_type": "Error Logging",
			"function": "Count",
			"filters_json": "[]",
			"color": "#e74c3c",
			"show_percentage_stats": 1,
			"stats_time_interval": "Monthly",
		},
		# --- Enhanced dashboard cards ---
		{
			"name": "Queue Failed",
			"label": "Queue Failed",
			"document_type": "eTIMS Invoice Queue",
			"function": "Count",
			"filters_json": '[["eTIMS Invoice Queue","status","=","Failed"]]',
			"color": "#dc3545",
		},
		{
			"name": "Purchases Unmatched",
			"label": "Purchases Unmatched",
			"document_type": "Purchase Invoice",
			"function": "Count",
			"filters_json": '[["Purchase Invoice","docstatus","=",1],["Purchase Invoice","custom_kra_match_status","not in",["Matched",""]]]',
			"color": "#e67e22",
		},
		{
			"name": "Sales Success Rate",
			"label": "Sales Success Rate (%)",
			"type": "Custom",
			"document_type": "Sales Invoice",
			"function": "kenya_etims_compliance.custom_methods.dashboard.get_sales_success_rate",
			"color": "#16a34a",
		},
		{
			"name": "Input VAT at Risk",
			"label": "Input VAT at Risk",
			"type": "Custom",
			"document_type": "Purchase Invoice",
			"function": "kenya_etims_compliance.custom_methods.dashboard.get_input_vat_at_risk",
			"color": "#dc2626",
		},
		{
			"name": "Compliance Score",
			"label": "Compliance Score",
			"type": "Custom",
			"document_type": "eTIMS Compliance Score",
			"function": "kenya_etims_compliance.custom_methods.dashboard.get_compliance_score",
			"color": "#2563eb",
		},
		{
			"name": "Days to Filing Deadline",
			"label": "Days to Filing Deadline",
			"type": "Custom",
			"document_type": "eTIMS Settings",
			"function": "kenya_etims_compliance.custom_methods.dashboard.get_days_to_filing_deadline",
			"color": "#7c3aed",
		},
	]

	for c in cards:
		if frappe.db.exists("Number Card", c["name"]):
			continue
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
			"filters_json": '[["Sales Invoice","custom_update_invoice_in_tims","=",1],["Sales Invoice","docstatus","=",1]]',
			"timespan": "Last Year",
			"time_interval": "Monthly",
			"type": "Bar",
			"color": "#2ecc71",
		},
		{
			"name": "eTIMS Purchase Transmission",
			"chart_name": "eTIMS Purchase Transmission",
			"chart_type": "Count",
			"document_type": "Purchase Invoice",
			"based_on": "posting_date",
			"filters_json": '[["Purchase Invoice","custom_update_purchase_in_tims","=",1],["Purchase Invoice","docstatus","=",1]]',
			"timespan": "Last Year",
			"time_interval": "Monthly",
			"type": "Bar",
			"color": "#3498db",
		},
		{
			"name": "eTIMS Errors Trend",
			"chart_name": "eTIMS Errors Trend",
			"chart_type": "Count",
			"document_type": "Error Logging",
			# Error Logging has no Date/Datetime field, so trend on the standard
			# `creation` timestamp (always present and valid as a chart based_on).
			"based_on": "creation",
			"filters_json": "[]",
			"timespan": "Last Year",
			"time_interval": "Monthly",
			"type": "Line",
			"color": "#e74c3c",
		},
		# --- Enhanced dashboard charts ---
		{
			"name": "eTIMS Queue Status",
			"chart_name": "eTIMS Queue Status",
			"chart_type": "Group By",
			"document_type": "eTIMS Invoice Queue",
			"group_by_based_on": "status",
			"filters_json": "[]",
			"type": "Donut",
			"color": "#2490ef",
		},
		{
			"name": "eTIMS Purchase Match Status",
			"chart_name": "eTIMS Purchase Match Status",
			"chart_type": "Group By",
			"document_type": "Purchase Invoice",
			"group_by_based_on": "custom_kra_match_status",
			"filters_json": '[["Purchase Invoice","docstatus","=",1],["Purchase Invoice","custom_update_purchase_in_tims","=",1]]',
			"type": "Donut",
			"color": "#f39c12",
		},
		{
			"name": "eTIMS Sales Transmission Status",
			"chart_name": "eTIMS Sales Transmission Status",
			"chart_type": "Group By",
			"document_type": "Sales Invoice",
			"group_by_based_on": "custom_update_sales_to_etims",
			"filters_json": '[["Sales Invoice","docstatus","=",1],["Sales Invoice","custom_update_invoice_in_tims","=",1]]',
			"type": "Donut",
			"color": "#2ecc71",
		},
	]

	for c in charts:
		if frappe.db.exists("Dashboard Chart", c["name"]):
			continue
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
