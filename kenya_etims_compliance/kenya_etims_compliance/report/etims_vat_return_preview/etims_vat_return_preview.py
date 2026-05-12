import frappe
from frappe import _
from frappe.utils import add_months, flt, getdate


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	summary = get_summary(data)
	return columns, data, None, chart, summary


def get_columns():
	return [
		{"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 180},
		{"fieldname": "tax_code", "label": _("Tax Code"), "fieldtype": "Data", "width": 80},
		{"fieldname": "taxable_amount", "label": _("Taxable Amount"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "tax_rate", "label": _("Rate %"), "fieldtype": "Percent", "width": 80},
		{"fieldname": "tax_amount", "label": _("Tax Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "count", "label": _("Invoices"), "fieldtype": "Int", "width": 80},
	]


def get_data(filters):
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	company = filters.get("company")

	if not from_date or not to_date:
		return []

	data = []
	company_filter = {"company": company} if company else {}

	# OUTPUT VAT — Sales Invoices transmitted to eTIMS
	si_filters = {
		"docstatus": 1,
		"posting_date": ["between", [from_date, to_date]],
		"custom_update_invoice_in_tims": 1,
		**company_filter,
	}
	sales_invoices = frappe.get_all(
		"Sales Invoice",
		filters=si_filters,
		fields=["name", "base_grand_total", "base_total_taxes_and_charges", "custom_update_sales_to_etims"],
		limit_page_length=0,
	)

	si_transmitted = [s for s in sales_invoices if s.custom_update_sales_to_etims]
	si_pending = [s for s in sales_invoices if not s.custom_update_sales_to_etims]

	output_taxable = sum(
		flt(s.base_grand_total) - flt(s.base_total_taxes_and_charges) for s in si_transmitted
	)
	output_tax = sum(flt(s.base_total_taxes_and_charges) for s in si_transmitted)

	data.append(
		{
			"category": "OUTPUT VAT (Sales)",
			"tax_code": "",
			"taxable_amount": output_taxable,
			"tax_rate": 16,
			"tax_amount": output_tax,
			"status": "Transmitted" if not si_pending else f"{len(si_pending)} pending",
			"count": len(si_transmitted),
		}
	)

	# INPUT VAT — Purchase Invoices
	pi_filters = {
		"docstatus": 1,
		"posting_date": ["between", [from_date, to_date]],
		**company_filter,
	}
	purchase_invoices = frappe.get_all(
		"Purchase Invoice",
		filters=pi_filters,
		fields=[
			"name",
			"base_grand_total",
			"base_total_taxes_and_charges",
			"custom_kra_match_status",
			"custom_update_purchase_in_tims",
		],
		limit_page_length=0,
	)

	pi_matched = [p for p in purchase_invoices if p.custom_kra_match_status == "Matched"]
	pi_unmatched = [p for p in purchase_invoices if p.custom_kra_match_status != "Matched"]

	supported_input_taxable = sum(
		flt(p.base_grand_total) - flt(p.base_total_taxes_and_charges) for p in pi_matched
	)
	supported_input_tax = sum(flt(p.base_total_taxes_and_charges) for p in pi_matched)

	at_risk_taxable = sum(flt(p.base_grand_total) - flt(p.base_total_taxes_and_charges) for p in pi_unmatched)
	at_risk_tax = sum(flt(p.base_total_taxes_and_charges) for p in pi_unmatched)

	data.append(
		{
			"category": "INPUT VAT (Supported)",
			"tax_code": "",
			"taxable_amount": supported_input_taxable,
			"tax_rate": 16,
			"tax_amount": supported_input_tax,
			"status": "KRA Matched",
			"count": len(pi_matched),
		}
	)

	data.append(
		{
			"category": "INPUT VAT (At Risk)",
			"tax_code": "",
			"taxable_amount": at_risk_taxable,
			"tax_rate": 16,
			"tax_amount": at_risk_tax,
			"status": "Not matched — may be rejected",
			"count": len(pi_unmatched),
		}
	)

	# NET VAT
	net_vat = output_tax - supported_input_tax
	data.append(
		{
			"category": "NET VAT PAYABLE",
			"tax_code": "",
			"taxable_amount": output_taxable - supported_input_taxable,
			"tax_rate": "",
			"tax_amount": net_vat,
			"status": "Due by 20th",
			"count": "",
		}
	)

	return data


def get_summary(data):
	output_row = next((d for d in data if d["category"] == "OUTPUT VAT (Sales)"), {})
	supported_row = next((d for d in data if d["category"] == "INPUT VAT (Supported)"), {})
	at_risk_row = next((d for d in data if d["category"] == "INPUT VAT (At Risk)"), {})
	net_row = next((d for d in data if d["category"] == "NET VAT PAYABLE"), {})

	return [
		{"value": output_row.get("tax_amount", 0), "label": _("Output VAT"), "datatype": "Currency"},
		{
			"value": supported_row.get("tax_amount", 0),
			"label": _("Supported Input VAT"),
			"datatype": "Currency",
			"indicator": "green",
		},
		{
			"value": at_risk_row.get("tax_amount", 0),
			"label": _("At-Risk Input VAT"),
			"datatype": "Currency",
			"indicator": "red",
		},
		{
			"value": net_row.get("tax_amount", 0),
			"label": _("Net VAT Payable"),
			"datatype": "Currency",
			"indicator": "blue",
		},
	]


def get_chart(data):
	output = next((d for d in data if d["category"] == "OUTPUT VAT (Sales)"), {})
	supported = next((d for d in data if d["category"] == "INPUT VAT (Supported)"), {})
	at_risk = next((d for d in data if d["category"] == "INPUT VAT (At Risk)"), {})

	return {
		"data": {
			"labels": [_("Output VAT"), _("Supported Input"), _("At-Risk Input")],
			"datasets": [
				{
					"values": [
						output.get("tax_amount", 0),
						supported.get("tax_amount", 0),
						at_risk.get("tax_amount", 0),
					]
				}
			],
		},
		"type": "bar",
		"colors": ["#3498db", "#2ecc71", "#e74c3c"],
	}
