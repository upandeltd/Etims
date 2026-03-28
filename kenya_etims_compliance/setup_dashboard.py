"""One-time script to create Number Cards and Dashboard Charts for eTIMS workspace."""
import frappe


def create_number_cards():
    cards = [
        {
            "name": "eTIMS Sales Transmitted",
            "label": "Sales Transmitted",
            "document_type": "Sales Invoice",
            "function": "Count",
            "filters_json": '{"docstatus": 1, "custom_update_sales_to_etims": 1}',
            "color": "#2ecc71",
            "show_percentage_stats": 1,
            "stats_time_interval": "Monthly",
        },
        {
            "name": "eTIMS Sales Pending",
            "label": "Sales Pending",
            "document_type": "Sales Invoice",
            "function": "Count",
            "filters_json": '{"docstatus": 1, "custom_update_invoice_in_tims": 1, "custom_update_sales_to_etims": 0}',
            "color": "#f39c12",
            "show_percentage_stats": 1,
            "stats_time_interval": "Monthly",
        },
        {
            "name": "eTIMS Purchases Matched",
            "label": "Purchases Matched",
            "document_type": "Purchase Invoice",
            "function": "Count",
            "filters_json": '{"docstatus": 1, "custom_kra_match_status": "Matched"}',
            "color": "#2ecc71",
            "show_percentage_stats": 1,
            "stats_time_interval": "Monthly",
        },
        {
            "name": "eTIMS Queue Pending",
            "label": "Queue Pending",
            "document_type": "eTIMS Invoice Queue",
            "function": "Count",
            "filters_json": '{"status": ["in", ["Queued", "Failed"]]}',
            "color": "#e74c3c",
        },
        {
            "name": "eTIMS Suppliers Verified",
            "label": "Suppliers Verified",
            "document_type": "Supplier",
            "function": "Count",
            "filters_json": '{"disabled": 0, "custom_kra_pin_verified": 1}',
            "color": "#3498db",
        },
        {
            "name": "eTIMS Errors This Month",
            "label": "Errors (This Month)",
            "document_type": "Error Logging",
            "function": "Count",
            "filters_json": "{}",
            "color": "#e74c3c",
            "show_percentage_stats": 1,
            "stats_time_interval": "Monthly",
        },
    ]

    for c in cards:
        if not frappe.db.exists("Number Card", c["name"]):
            frappe.get_doc({
                "doctype": "Number Card",
                "name": c["name"],
                "label": c["label"],
                "document_type": c["document_type"],
                "function": c["function"],
                "filters_json": c["filters_json"],
                "color": c.get("color"),
                "show_percentage_stats": c.get("show_percentage_stats", 0),
                "stats_time_interval": c.get("stats_time_interval", "Daily"),
                "is_public": 1,
                "type": "Document Type",
            }).insert(ignore_permissions=True)
            frappe.logger().debug(f"Created number card: {c['name']}")
        else:
            pass


def create_dashboard_charts():
    charts = [
        {
            "name": "eTIMS Monthly Sales Transmission",
            "chart_name": "eTIMS Monthly Sales Transmission",
            "chart_type": "Count",
            "document_type": "Sales Invoice",
            "based_on": "posting_date",
            "filters_json": '{"custom_update_invoice_in_tims": 1, "docstatus": 1}',
            "timespan": "Last Year",
            "time_interval": "Monthly",
            "type": "Bar",
            "color": "#2ecc71",
        },
        {
            "name": "eTIMS Reconciliation Status",
            "chart_name": "eTIMS Reconciliation Status",
            "chart_type": "Group By",
            "document_type": "eTIMS Purchase Register Entry",
            "group_by_based_on": "match_status",
            "type": "Donut",
            "color": "#3498db",
        },
        {
            "name": "eTIMS Queue Status",
            "chart_name": "eTIMS Queue Status",
            "chart_type": "Group By",
            "document_type": "eTIMS Invoice Queue",
            "group_by_based_on": "status",
            "type": "Donut",
            "color": "#f39c12",
        },
    ]

    for c in charts:
        if not frappe.db.exists("Dashboard Chart", c["name"]):
            doc_data = {
                "doctype": "Dashboard Chart",
                "name": c["name"],
                "chart_name": c["chart_name"],
                "chart_type": c["chart_type"],
                "document_type": c["document_type"],
                "type": c["type"],
                "color": c.get("color"),
                "is_public": 1,
                "filters_json": c.get("filters_json", "{}"),
            }
            if c["chart_type"] == "Count":
                doc_data["based_on"] = c["based_on"]
                doc_data["timespan"] = c.get("timespan", "Last Year")
                doc_data["time_interval"] = c.get("time_interval", "Monthly")
            elif c["chart_type"] == "Group By":
                doc_data["group_by_based_on"] = c["group_by_based_on"]

            frappe.get_doc(doc_data).insert(ignore_permissions=True)
            frappe.logger().debug(f"Created dashboard chart: {c['name']}")
        else:
            pass


def execute():
    create_number_cards()
    create_dashboard_charts()
    frappe.db.commit()
    frappe.logger().info("eTIMS dashboard setup complete")
