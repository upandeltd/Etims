# Copyright (c) 2023, Upande Ltd and contributors
# For license information, please see license.txt

import traceback

import frappe
from frappe import _
from frappe.model.document import Document

from kenya_etims_compliance.utils.etims_utils import eTIMS
from kenya_etims_compliance.utils.kra_client import KRAClient


class eTIMSPurchaseInformation(Document):
	@frappe.whitelist()
	def trnsPurchaseSalesReq(self):
		request_datetime = self.last_request_date
		if not request_datetime:
			frappe.throw(_("Set 'From Date and Time' before searching."), frappe.ValidationError)

		date_time_str = frappe.utils.get_datetime(request_datetime).strftime("%Y%m%d%H%M%S")

		payload = {
			"lastReqDt": date_time_str,
		}

		try:
			result = KRAClient().post("selectTrnsPurchaseSalesList", payload)

			if result.get("Error"):
				return {"Error": result.get("Error")}

			if result.get("Empty"):
				return {"Success": "No purchases found for this date range. Try an earlier date."}

			response_result = {"data": result.get("Success")}
			process_purchases(response_result)

			self.last_search_date_and_time = request_datetime
			self.save()

			return {"Success": "Purchase search completed"}

		except (frappe.ValidationError, frappe.DoesNotExistError):
			frappe.log_error(title="eTIMS: Purchase Sales Request failed", message=traceback.format_exc())
			return {"Error": "An error occurred on TIS server!"}


def process_purchases(response_json, register_items=True):
	data = response_json.get("data") or {}

	for invoice in data.get("saleList") or []:
		upsert_purchase_invoice(invoice, register_items=register_items)


def upsert_purchase_invoice(invoice, register_items=False):
	"""Store one KRA ``saleList`` row as an eTIMS Purchase Invoice, items included.

	The per-band totals (taxblAmt/taxRt/taxAmt A-E) and the full ``itemList`` are
	the only place KRA's own tax decomposition is recorded, so they are always
	persisted — reconciliation reads them to compare band by band instead of
	inferring a mismatch from a single total.

	register_items: also create and KRA-register any unknown Item. Only the
	manual search does this; the daily pull must not silently create Items or
	POST to KRA on every tick.

	Returns the eTIMS Purchase Invoice name (existing or newly created).
	"""
	supplier_pin = invoice.get("spplrTin") or ""
	supplier_invoice_number = invoice.get("spplrInvcNo")

	# KRA invoice numbers are per-supplier sequences, so the PIN is half the
	# identity. Matching on the number alone collided across suppliers and
	# silently dropped the second supplier's invoice.
	existing = frappe.db.get_value(
		"eTIMS Purchase Invoice",
		{"supplier_pin": supplier_pin, "supplier_invoice_number": supplier_invoice_number},
		"name",
	)
	if existing:
		return existing

	new_doc = frappe.new_doc("eTIMS Purchase Invoice")
	new_doc.supplier_pin = supplier_pin
	new_doc.supplier_name = invoice.get("spplrNm")
	new_doc.supplier_branch_id = invoice.get("spplrBhfId")
	new_doc.supplier_invoice_number = supplier_invoice_number
	new_doc.receipt_type_code = invoice.get("rcptTyCd")
	new_doc.payment_type_code = invoice.get("pmtTyCd")
	new_doc.validated_date = invoice.get("cfmDt")
	new_doc.sale_date = eTIMS.strp_date_object(invoice.get("salesDt"))
	new_doc.stock_released_date = invoice.get("stockRlsDt")
	new_doc.total_item_count = invoice.get("totItemCnt")
	new_doc.taxable_amount_a = invoice.get("taxblAmtA")
	new_doc.taxable_amount_b = invoice.get("taxblAmtB")
	new_doc.taxable_amount_c = invoice.get("taxblAmtC")
	new_doc.taxable_amount_d = invoice.get("taxblAmtD")
	new_doc.taxable_amount_e = invoice.get("taxblAmtE")
	new_doc.tax_rate_a = invoice.get("taxRtA")
	new_doc.tax_rate_b = invoice.get("taxRtB")
	new_doc.tax_rate_c = invoice.get("taxRtC")
	new_doc.tax_rate_d = invoice.get("taxRtD")
	new_doc.tax_rate_e = invoice.get("taxRtE")
	new_doc.tax_amt_a = invoice.get("taxAmtA")
	new_doc.tax_amt_b = invoice.get("taxAmtB")
	new_doc.tax_amt_c = invoice.get("taxAmtC")
	new_doc.tax_amt_d = invoice.get("taxAmtD")
	new_doc.tax_amt_e = invoice.get("taxAmtE")
	new_doc.total_taxable_amount = invoice.get("totTaxblAmt")
	new_doc.total_tax_amount = invoice.get("totTaxAmt")
	new_doc.total_amount = invoice.get("totAmt")
	new_doc.remark = invoice.get("remark")

	for item_detail in invoice.get("itemList") or []:
		if register_items:
			try:
				eTIMS.map_new_item(item_detail)
			except (frappe.ValidationError, frappe.DoesNotExistError):
				frappe.log_error(
					title="eTIMS: Purchase Item Processing failed", message=traceback.format_exc()
				)
				raise

		new_doc.append("items", assign_purchase_item(item_detail))

	# after_insert reads this to decide whether it's safe to build the
	# ERPNext-side Purchase Invoice: that flow treats item_name as a real
	# Item Code, which is only true when register_items mapped/created the
	# Items above. The daily pull (register_items=False) must still persist
	# the raw KRA row for reconciliation without that side effect.
	new_doc.flags.register_items = register_items
	new_doc.insert(ignore_permissions=True)

	return new_doc.name


def assign_purchase_item(item_detail):
	item_dict = {
		"item_sequence_number": item_detail.get("itemSeq"),
		"item_code": item_detail.get("itemCd"),
		"item_classification_code": item_detail.get("itemClsCd"),
		"item_name": item_detail.get("itemNm"),
		"barcode": item_detail.get("bcd"),
		"packing_unit_code": item_detail.get("pkgUnitCd"),
		"quantity_unit_code": item_detail.get("qtyUnitCd"),
		"package": item_detail.get("pkg"),
		"quantity": item_detail.get("qty"),
		"unit_price": item_detail.get("prc"),
		"supply_amount": item_detail.get("splyAmt"),
		"discount_rate": item_detail.get("dcRt"),
		"discount_amount": item_detail.get("dcAmt"),
		"taxation_type_code": item_detail.get("taxTyCd"),
		"taxable_amount": item_detail.get("taxblAmt"),
		"tax_amount": item_detail.get("taxAmt"),
		"total_amount": item_detail.get("totAmt"),
	}

	return item_dict
