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
		{
			"fieldname": "supplier",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 200,
		},
		{"fieldname": "supplier_pin", "label": _("PIN"), "fieldtype": "Data", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "score", "label": _("Score"), "fieldtype": "Int", "width": 80},
		{"fieldname": "pin_verified", "label": _("PIN Verified"), "fieldtype": "Check", "width": 100},
		{
			"fieldname": "transmission_rate",
			"label": _("Transmission %"),
			"fieldtype": "Percent",
			"width": 120,
		},
		{"fieldname": "open_invoices", "label": _("Open PIs"), "fieldtype": "Int", "width": 80},
		{"fieldname": "total_exposure", "label": _("Exposure (KES)"), "fieldtype": "Currency", "width": 140},
	]


def get_data(filters):
	supplier_filters = {
		"disabled": 0,
		"custom_supplier_pin": ["is", "set"],
	}
	if filters.get("status"):
		supplier_filters["custom_etims_compliance_status"] = filters["status"]

	suppliers = frappe.get_all(
		"Supplier",
		filters=supplier_filters,
		fields=[
			"name",
			"custom_supplier_pin",
			"custom_etims_compliance_status",
			"custom_etims_compliance_score",
			"custom_kra_pin_verified",
			"custom_etims_transmission_rate",
		],
		order_by="custom_etims_compliance_score asc",
		limit_page_length=0,
	)

	data = []
	for s in suppliers:
		# Count unmatched PIs = exposure
		unmatched_pis = frappe.get_all(
			"Purchase Invoice",
			filters={
				"supplier": s.name,
				"docstatus": 1,
				"custom_kra_match_status": ["not in", ["Matched", ""]],
			},
			fields=["base_grand_total"],
			limit_page_length=0,
		)

		exposure = sum(flt(p.base_grand_total) for p in unmatched_pis)

		data.append(
			{
				"supplier": s.name,
				"supplier_pin": s.custom_supplier_pin,
				"status": s.custom_etims_compliance_status or "Unknown",
				"score": s.custom_etims_compliance_score or 0,
				"pin_verified": s.custom_kra_pin_verified,
				"transmission_rate": s.custom_etims_transmission_rate or 0,
				"open_invoices": len(unmatched_pis),
				"total_exposure": exposure,
			}
		)

	return data


def get_summary(data):
	total = len(data)
	compliant = len([d for d in data if d["status"] == "Compliant"])
	at_risk = len([d for d in data if d["status"] == "At Risk"])
	non_compliant = len([d for d in data if d["status"] == "Non-Compliant"])
	total_exposure = sum(d["total_exposure"] for d in data)

	return [
		{"value": total, "label": _("Total Suppliers"), "datatype": "Int"},
		{"value": compliant, "label": _("Compliant"), "datatype": "Int", "indicator": "green"},
		{"value": at_risk, "label": _("At Risk"), "datatype": "Int", "indicator": "orange"},
		{"value": non_compliant, "label": _("Non-Compliant"), "datatype": "Int", "indicator": "red"},
		{"value": total_exposure, "label": _("Total Exposure"), "datatype": "Currency", "indicator": "red"},
	]


def get_chart(data):
	compliant = len([d for d in data if d["status"] == "Compliant"])
	at_risk = len([d for d in data if d["status"] == "At Risk"])
	non_compliant = len([d for d in data if d["status"] == "Non-Compliant"])
	unknown = len([d for d in data if d["status"] == "Unknown"])

	return {
		"data": {
			"labels": [_("Compliant"), _("At Risk"), _("Non-Compliant"), _("Unknown")],
			"datasets": [{"values": [compliant, at_risk, non_compliant, unknown]}],
		},
		"type": "donut",
		"colors": ["#2ecc71", "#f39c12", "#e74c3c", "#95a5a6"],
	}
