import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	summary = get_summary(data)
	return columns, data, None, chart, summary


def get_columns():
	return [
		{"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link",
		 "options": "Item", "width": 150},
		{"fieldname": "item_name", "label": _("Item"), "fieldtype": "Data", "width": 180},
		{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Link",
		 "options": "Tax Branch Office", "width": 80},
		{"fieldname": "kra_qty_in", "label": _("KRA In"), "fieldtype": "Float", "width": 90},
		{"fieldname": "kra_qty_out", "label": _("KRA Out"), "fieldtype": "Float", "width": 90},
		{"fieldname": "local_qty_in", "label": _("Local In"), "fieldtype": "Float", "width": 90},
		{"fieldname": "local_qty_out", "label": _("Local Out"), "fieldtype": "Float", "width": 90},
		{"fieldname": "variance_in", "label": _("Var In"), "fieldtype": "Float", "width": 80},
		{"fieldname": "variance_out", "label": _("Var Out"), "fieldtype": "Float", "width": 80},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
	]


def get_data(filters):
	from kenya_etims_compliance.custom_methods.stock_reconciliation_etims import run_stock_reconciliation

	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	branch = filters.get("branch")

	if not from_date or not to_date:
		return []

	data = run_stock_reconciliation(from_date, to_date, branch)

	# Apply status filter if set
	status_filter = filters.get("status")
	if status_filter:
		data = [d for d in data if d.get("status") == status_filter]

	return data


def get_summary(data):
	total = len(data)
	matched = len([d for d in data if d.get("status") == "Matched"])
	variance = len([d for d in data if d.get("status") == "Variance"])
	not_in_kra = len([d for d in data if d.get("status") == "Not in KRA"])
	total_var_in = sum(abs(flt(d.get("variance_in"))) for d in data if d.get("status") != "Matched")
	total_var_out = sum(abs(flt(d.get("variance_out"))) for d in data if d.get("status") != "Matched")

	return [
		{"value": total, "label": _("Total Items"), "datatype": "Int"},
		{"value": matched, "label": _("Matched"), "datatype": "Int", "indicator": "green"},
		{"value": variance, "label": _("Variance"), "datatype": "Int", "indicator": "orange"},
		{"value": not_in_kra, "label": _("Not in KRA"), "datatype": "Int", "indicator": "red"},
		{"value": total_var_in, "label": _("Total Var In"), "datatype": "Float", "indicator": "red"},
		{"value": total_var_out, "label": _("Total Var Out"), "datatype": "Float", "indicator": "red"},
	]


def get_chart(data):
	matched = len([d for d in data if d.get("status") == "Matched"])
	variance = len([d for d in data if d.get("status") == "Variance"])
	not_in_kra = len([d for d in data if d.get("status") == "Not in KRA"])

	return {
		"data": {
			"labels": [_("Matched"), _("Variance"), _("Not in KRA")],
			"datasets": [{"values": [matched, variance, not_in_kra]}],
		},
		"type": "donut",
		"colors": ["#2ecc71", "#f39c12", "#e74c3c"],
	}
