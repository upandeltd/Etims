import json
import traceback
from datetime import datetime

import frappe
import requests
from frappe import _, scrub
from frappe.utils import flt

from kenya_etims_compliance.utils.etims_utils import eTIMS, get_next_sar_number, get_org_sar_number, get_tax_template_details
from kenya_etims_compliance.utils.permissions import can_modify_doctype
from kenya_etims_compliance.utils.kra_client import KRAClient


@frappe.whitelist()
def searchPurchaseTrnsReq(invoice_no=None, last_req_dt=None):
	"""Search purchase transactions in eTIMS"""
	response = eTIMS.searchTrns(invoice_no, last_req_dt, "purchase")

	for key, value in response.items():
		if key == "Success":
			return {"Success": value}
		else:
			return {"Error": value}


@frappe.whitelist()
def selectPurchaseTrnsInfoReq(invoice_no):
	"""Get purchase transaction details from eTIMS"""
	response = eTIMS.selectTrnsPurchaseInfo(invoice_no)

	for key, value in response.items():
		if key == "Success":
			return {"Success": value}
		else:
			return {"Error": value}


def validate(doc, method):
	"""
	Method validate invoice number before submitting invoice
	"""

	if doc.custom_invoice_number and doc.name:
		doc_exists = frappe.db.exists("Purchase Invoice", {"name": doc.name})

		if doc_exists:
			invoice_numbers = validate_inv_number(doc)
			if doc.custom_invoice_number in invoice_numbers:
				insert_invoice_number(doc, method)


def get_total_discount(doc):
	discount_amount = 0

	if doc.items:
		for item in doc.items:
			if item.get("discount_percentage") and item.get("discount_percentage") > 0:
				total_dsc = (item.get("discount_amount") or 0) * (item.get("qty") or 1)
				discount_amount += total_dsc

	return discount_amount


def add_taxes(doc, method):
	if doc.items:
		for item in doc.items:
			add_taxes_from_tax_template(item, doc, db_insert=True)


def add_taxes_from_tax_template(child_item, parent_doc, db_insert=True):
	add_taxes_from_item_tax_template = frappe.db.get_single_value(
		"Accounts Settings", "add_taxes_from_item_tax_template"
	)

	if child_item.get("item_tax_rate") and add_taxes_from_item_tax_template:
		tax_map = json.loads(child_item.get("item_tax_rate"))
		for tax_type in tax_map:
			tax_rate = flt(tax_map[tax_type])
			taxes = parent_doc.get("taxes") or []
			# add new row for tax head only if missing
			found = any(tax.account_head == tax_type for tax in taxes)
			if not found:
				tax_row = parent_doc.append("taxes", {})
				tax_row.update(
					{
						"description": str(tax_type).split(" - ")[0],
						"charge_type": "On Net Total",
						"account_head": tax_type,
						"rate": tax_rate,
						"category": "Total",
						"included_in_print_rate": 1,
						"add_deduct_tax": "Add",
					}
				)
				if parent_doc.doctype == "Purchase Invoice":
					tax_row.update({"category": "Total", "add_deduct_tax": "Add"})
				if db_insert:
					tax_row.db_insert()


def insert_invoice_number(doc, method):
	"""
	Method sets increment for invoice number and orginal invoice number before submitting invoice
	"""
	if doc.name:
		branch_id = eTIMS.get_user_branch_id()
		# Initialize pur_warehouse before conditional to avoid UnboundLocalError
		pur_warehouse = None
		init_docs = frappe.db.get_all(
			"TIS Device Initialization", filters={"branch_id": branch_id}, fields=["default_stores_warehouse"]
		)
		if init_docs:
			pur_warehouse = init_docs[0].get("default_stores_warehouse")

		last_inv_number = get_last_inv_number(doc, branch_id)

		if doc.items:
			insert_tax_amounts(doc)

		total_vat_amount = fetch_total_vat(doc)
		total_non_vat_amount = fetch_total_non_vat(doc)

		# update_stock decision: respect the user's choice, but auto-disable when
		# enabling it would technically fail, and warn when leaving it off risks
		# KRA stock-register reconciliation.
		user_choice = 1 if doc.get("update_stock") else 0

		has_pr_link = any(it.get("purchase_receipt") for it in (doc.items or []))
		has_stock_item = False
		if doc.items:
			item_codes = [it.item_code for it in doc.items if it.item_code]
			if item_codes:
				stocked = frappe.db.get_all(
					"Item",
					filters={"item_code": ["in", item_codes], "is_stock_item": 1},
					fields=["name"],
					limit=1,
				)
				has_stock_item = bool(stocked)

		new_update_stock = user_choice
		if user_choice == 1 and has_pr_link:
			new_update_stock = 0
			frappe.msgprint(
				_("Auto-disabled 'Update Stock' on this invoice because it links to a Purchase Receipt. "
				  "Stock was already booked by the PR — eTIMS will receive the stock movement from there."),
				title=_("Update Stock disabled"), indicator="orange",
			)
		elif user_choice == 1 and not has_stock_item:
			new_update_stock = 0
			frappe.msgprint(
				_("Auto-disabled 'Update Stock' on this invoice because none of the items are stock items "
				  "(all are services). No stock movement to send."),
				title=_("Update Stock disabled"), indicator="orange",
			)
		elif user_choice == 0 and has_stock_item and not has_pr_link:
			frappe.msgprint(
				_("'Update Stock' is OFF on this invoice but items include stock items. "
				  "KRA's stock register will not receive a stock-in movement, which may cause reconciliation "
				  "mismatches. Either enable Update Stock or send a separate stock movement."),
				title=_("KRA stock reconciliation risk"), indicator="yellow",
			)

		update_dict = {
			"custom_invoice_number": last_inv_number,
			"update_stock": new_update_stock,
			"custom_tax_branch_office": branch_id,
			"custom_total_taxable_amount": total_vat_amount,
			"custom_total_nontaxable_amount": total_non_vat_amount,
		}
		# Only override set_warehouse when we're actually updating stock
		if new_update_stock and pur_warehouse:
			update_dict["set_warehouse"] = pur_warehouse

		frappe.db.set_value("Purchase Invoice", doc.name, update_dict, update_modified=False)

		# Sync in-memory doc fields to match what was written to DB
		doc.custom_invoice_number = last_inv_number
		doc.update_stock = new_update_stock
		doc.custom_tax_branch_office = branch_id
		if new_update_stock and pur_warehouse:
			doc.set_warehouse = pur_warehouse
		doc.custom_total_taxable_amount = total_vat_amount
		doc.custom_total_nontaxable_amount = total_non_vat_amount


def insert_tax_amounts(doc):
	taxable_amounts = get_taxable_amounts(doc)
	for key, value in taxable_amounts.items():
		try:
			if doc.taxes:
				for item in doc.taxes:
					if item.get("custom_code") == key:
						frappe.db.set_value(
							"Purchase Taxes and Charges",
							item.get("name"),
							"custom_total_taxable_amount",
							round(value, 2),
							update_modified=False,
						)
		except (frappe.DoesNotExistError, frappe.DataError) as e:
			frappe.throw(_("Error calculating tax amounts: {0}").format(str(e)))


def get_taxable_amounts(doc):
	taxable_amounts_dict = {}

	try:
		if doc.items:
			for item in doc.items:
				if item.get("custom_tax_code") not in taxable_amounts_dict.keys():
					taxable_amounts_dict[item.get("custom_tax_code")] = 0

				taxable_amounts_dict[item.get("custom_tax_code")] += item.net_amount
	except Exception as e:
		frappe.throw(_("Error getting taxable amounts: {0}").format(str(e)))

	return taxable_amounts_dict


def fetch_total_vat(doc):
	taxable_amount = 0
	if doc.taxes:
		for item in doc.taxes:
			if item.get("base_tax_amount_after_discount_amount"):
				if item.get("base_tax_amount_after_discount_amount") > 0:
					taxable_amount += item.get("custom_total_taxable_amount")
				if item.get("base_tax_amount_after_discount_amount") < 0 and doc.is_return:
					taxable_amount += item.get("custom_total_taxable_amount")

	return taxable_amount


def fetch_total_non_vat(doc):
	taxable_non_vat_amount = 0
	if doc.taxes:
		for item in doc.taxes:
			if item.get("base_tax_amount_after_discount_amount") == 0:
				taxable_non_vat_amount += item.get("custom_total_taxable_amount")

	return taxable_non_vat_amount


def handle_reverse_invoice(doc):
	"""Handle buyer-initiated invoicing for unregistered suppliers.

	Per KRA Reverse Invoicing Guidelines (March 2025).
	"""
	if doc.custom_supplier_vat_registered:
		frappe.throw(_("Cannot issue reverse invoice — supplier is VAT-registered."))

	request_date = doc.posting_date
	date_str = eTIMS.strf_date_object(request_date)
	now_dt = datetime.now()
	date_time_str = now_dt.strftime("%Y%m%d%H%M%S")
	conc_datetime_str = eTIMS.strf_datetime_format(doc.modified)

	payload = {
		"trdInvcNo": doc.name,
		"invcNo": doc.custom_invoice_number,
		"orgInvcNo": 0,
		"custTin": doc.get("custom_supplier_pin") or "",
		"custNm": doc.supplier_name or doc.supplier,
		"salesTyCd": "N",
		"rcptTyCd": "R",
		"pmtTyCd": doc.custom_payment_type_code or "01",
		"salesSttsCd": "02",
		"cfmDt": conc_datetime_str,
		"salesDt": date_str,
		"stockRlsDt": date_time_str,
		"totItemCnt": len(doc.items),
		"totTaxblAmt": abs(doc.custom_total_taxable_amount or 0),
		"totTaxAmt": abs(doc.base_total_taxes_and_charges),
		"totAmt": abs(doc.base_grand_total),
		"prchrAcptcYn": "N",
		"remark": f"Reverse Invoice - {doc.remarks or ''}",
		"regrId": (doc.owner or "")[:20],
		"regrNm": (doc.owner or "")[:20],
		"modrId": (doc.modified_by or "")[:20],
		"modrNm": (doc.modified_by or "")[:20],
		"receipt": {
			"custTin": doc.get("custom_supplier_pin") or "",
			"rcptPbctDt": date_time_str,
			"prchrAcptcYn": "N",
		},
		"itemList": etims_pur_item_list(doc),
	}

	# Add tax breakdown
	for code in ["A", "B", "C", "D", "E"]:
		payload[f"taxblAmt{code}"] = 0
		payload[f"taxRt{code}"] = 0
		payload[f"taxAmt{code}"] = 0

	if doc.taxes:
		for tax_item in doc.taxes:
			code = tax_item.get("custom_code")
			if code and code in ["A", "B", "C", "D", "E"]:
				payload[f"taxblAmt{code}"] = abs(round(tax_item.get("custom_total_taxable_amount", 0), 2))
				payload[f"taxRt{code}"] = abs(get_tax_account_rate(tax_item.get("account_head")) or 0)
				payload[f"taxAmt{code}"] = abs(tax_item.get("base_tax_amount_after_discount_amount", 0))

	result = KRAClient().post(
		"saveTrnsSalesOsdc",
		payload,
		reference_doctype="Purchase Invoice",
		reference_name=doc.name,
	)
	if result.get("Error"):
		frappe.log_error(title="eTIMS Reverse Invoice Error", message=result.get("Error"))
		frappe.throw(_("eTIMS Error: {0}").format(result.get("Error")))
	return result.get("Success")


def trnsPurchaseSaveReq(doc, method):
	# Handle reverse invoicing (buyer-initiated)
	if getattr(doc, "custom_is_reverse_invoice", False):
		result = handle_reverse_invoice(doc)
		if result:
			frappe.msgprint(_("Reverse invoice submitted to eTIMS"))
		return

	supplier_details = get_supplier_details(doc.supplier)

	tax_code_list = []

	request_date_and_time = doc.modified

	conc_datetime_str = eTIMS.strf_datetime_format(request_date_and_time)

	now = datetime.now()
	date_time_str = now.strftime("%Y%m%d%H%M%S")

	request_date = doc.posting_date
	date_str = eTIMS.strf_date_object(request_date)

	count = 0

	for _item in doc.items:
		count += 1

	payload = {
		"invcNo": doc.custom_invoice_number,
		"orgInvcNo": doc.custom_original_invoice_number,
		"spplrTin": supplier_details.get("supp_pin"),
		"spplrBhfId": supplier_details.get("supp_bhid"),
		"spplrNm": doc.supplier,
		"spplrInvcNo": doc.bill_no,
		"regTyCd": doc.custom_registration_type_code,
		"pchsTyCd": doc.custom_purchase_type_code,
		"rcptTyCd": doc.custom_receipt_type_code,
		"pmtTyCd": doc.custom_payment_type_code,
		"pchsSttsCd": doc.custom_purchase_status_code,
		"cfmDt": date_time_str,
		"pchsDt": date_str,
		"totItemCnt": count,
		"totTaxblAmt": abs(doc.custom_total_taxable_amount),
		"totTaxAmt": abs(doc.base_total_taxes_and_charges),
		"totAmt": abs(doc.grand_total),
		"remark": doc.remarks,
		"regrId": doc.owner,
		"regrNm": doc.owner,
		"modrId": doc.modified_by,
		"modrNm": doc.modified_by,
		"itemList": etims_pur_item_list(doc),
	}

	for tax_item in doc.taxes:
		if tax_item.get("custom_code") not in tax_code_list:
			tax_code_list.append(tax_item.get("custom_code"))

		if "A" in tax_code_list:
			if tax_item.custom_code == "A":
				payload["taxblAmtA"] = abs(round((tax_item.get("custom_total_taxable_amount")), 2))
				payload["taxRtA"] = abs(get_tax_account_rate(tax_item.get("account_head")))
				payload["taxAmtA"] = abs(tax_item.get("tax_amount_after_discount_amount"))
		else:
			payload["taxblAmtA"] = 0
			payload["taxRtA"] = 0
			payload["taxAmtA"] = 0

		if "B" in tax_code_list:
			if tax_item.custom_code == "B":
				payload["taxblAmtB"] = abs(round((tax_item.get("custom_total_taxable_amount")), 2))
				payload["taxRtB"] = abs(get_tax_account_rate(tax_item.get("account_head")))
				payload["taxAmtB"] = abs(tax_item.get("tax_amount_after_discount_amount"))
		else:
			payload["taxblAmtB"] = 0
			payload["taxRtB"] = 0
			payload["taxAmtB"] = 0

		if "C" in tax_code_list:
			if tax_item.custom_code == "C":
				payload["taxblAmtC"] = abs(round((tax_item.get("custom_total_taxable_amount")), 2))
				payload["taxRtC"] = abs(get_tax_account_rate(tax_item.get("account_head")))
				payload["taxAmtC"] = abs(tax_item.get("tax_amount_after_discount_amount"))
		else:
			payload["taxblAmtC"] = 0
			payload["taxRtC"] = 0
			payload["taxAmtC"] = 0

		if "D" in tax_code_list:
			if tax_item.custom_code == "D":
				payload["taxblAmtD"] = abs(round((tax_item.get("custom_total_taxable_amount")), 2))
				payload["taxRtD"] = abs(get_tax_account_rate(tax_item.get("account_head")))
				payload["taxAmtD"] = abs(tax_item.get("tax_amount_after_discount_amount"))
		else:
			payload["taxblAmtD"] = 0
			payload["taxRtD"] = 0
			payload["taxAmtD"] = 0

		if "E" in tax_code_list:
			if tax_item.custom_code == "E":
				payload["taxblAmtE"] = abs(round((tax_item.get("custom_total_taxable_amount")), 2))
				payload["taxRtE"] = abs(get_tax_account_rate(tax_item.get("account_head")))
				payload["taxAmtE"] = abs(tax_item.get("tax_amount_after_discount_amount"))
		else:
			payload["taxblAmtE"] = 0
			payload["taxRtE"] = 0
			payload["taxAmtE"] = 0

	if doc.is_return == 1:
		return_status = purchase_return_information(doc)

		if return_status == "partial":
			payload["rfdDt"] = conc_datetime_str
		elif return_status == "full":
			payload["wrhsDt"] = date_time_str
			payload["cnclReqDt"] = conc_datetime_str
			payload["cnclDt"] = conc_datetime_str
		elif return_status == "null":
			frappe.throw(_("Invalid, return amount is greater than original amount!"))

	if doc.custom_update_purchase_in_tims:
		from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
			get_etims_settings,
		)

		settings = get_etims_settings()

		if settings.get("enable_queue", 1):
			from kenya_etims_compliance.custom_methods.queue_processor import enqueue_invoice

			branch_id = None
			try:
				branch_id = KRAClient()._get_user_branch_id()
			except (
				frappe.DoesNotExistError,
				requests.ConnectionError,
				requests.Timeout,
				requests.HTTPError,
			) as e:
				frappe.log_error("eTIMS: Failed to get branch ID", str(e))

			enqueue_invoice(
				doc=doc,
				payload=payload,
				api_endpoint="insert_purchase",
				branch_id=branch_id,
			)
			frappe.msgprint(_("Purchase invoice queued for eTIMS submission"), indicator="blue")
		else:
			# Synchronous fallback (original behavior)
			try:
				client = KRAClient()
				result = client.insert_purchase(payload)

				if "Error" in result:
					frappe.throw(result["Error"])

				stockIOSaveReq(doc, date_str)
				doc.custom_item_updated_in_tims = 1

				frappe.msgprint(_("Purchase invoice synced to eTIMS successfully"))

			except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
				frappe.log_error(title="eTIMS Purchase Invoice Error", message=traceback.format_exc())
				frappe.throw(_("eTIMS Error: {0}").format(e))
	else:
		frappe.logger().debug("eTIMS purchase skipped for %s", doc.name)
		stockIOSaveReq(doc, date_str)
		return


def stockIOSaveReq(doc, date_str):
	taxAmt = 0
	taxblAmt = 0

	client = KRAClient()
	stock_list = etims_stock_item_list(doc)

	for item in doc.items:
		if item.get("custom_maintain_stock") == 1 and item.get("custom_tax_code") in ["B", "E"]:
			taxblAmt += item.get("net_amount")
			taxAmt += item.get("amount") - item.get("net_amount")

	payload = {
		"sarNo": get_next_sar_number(doc, doc.custom_tax_branch_office),
		"orgSarNo": get_org_sar_number(doc),
		"regTyCd": "A",
		"custTin": client.headers.get("tin"),
		"custBhfId": eTIMS.get_user_branch_id(),
		"ocrnDt": date_str,
		"totItemCnt": len(stock_list),
		"totTaxblAmt": abs(round(taxblAmt, 2)),
		"totTaxAmt": abs(round(taxAmt, 2)),
		"totAmt": abs(doc.grand_total),
		"remark": doc.remarks,
		"regrId": doc.owner,
		"regrNm": doc.owner,
		"modrId": doc.modified_by,
		"modrNm": doc.modified_by,
		"itemList": stock_list,
	}

	if doc.is_return == 1:
		return_status = purchase_return_information(doc)

		if return_status == "partial" or return_status == "full":
			payload["sarTyCd"] = "12"

		elif return_status == "null":
			frappe.throw(_("Invalid, return amount is greater than original amount!"))

	else:
		payload["sarTyCd"] = "02"

	if doc.custom_update_purchase_in_tims:
		try:
			result = client.insert_stock_io(payload)

			if "Error" in result:
				frappe.log_error(title="eTIMS Purchase Stock IO Error", message=result["Error"])
				return {"Error": result["Error"]}

			return {"Success": "Stock IO synced successfully"}

		except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
			frappe.log_error(title="eTIMS Purchase Stock IO Error", message=traceback.format_exc())
			return {"Error": f"eTIMS Error: {e!s}"}
	else:
		frappe.logger().debug("eTIMS purchase stock IO skipped for %s", doc.name)
		return


def get_supplier_details(supplier):
	supplier_kra_details = frappe.get_doc("Supplier", supplier)

	supp_dict = {
		"supp_pin": supplier_kra_details.get("custom_supplier_pin"),
		"supp_bhid": supplier_kra_details.get("custom_branch_id"),
	}

	return supp_dict


def get_last_inv_number(doc, branch_id):

	cur_number = 0
	last_inv_no = 0

	settings_docs = frappe.db.get_all(
		"TIS Device Initialization", filters={"branch_id": branch_id}, fields=["last_purchase_invoice_number"]
	)

	if settings_docs:
		last_inv_no = settings_docs[0].get("last_purchase_invoice_number")

	try:
		last_inv = frappe.db.get_all(
			doc.doctype,
			filters={"name": ["!=", doc.name], "custom_tax_branch_office": branch_id},
			fields=["custom_invoice_number"],
			order_by="custom_invoice_number desc",
			page_length=1,
		)

		if last_inv and last_inv[0].get("custom_invoice_number"):
			last_inv_no = last_inv[0].get("custom_invoice_number")

		cur_number = (last_inv_no or 0) + 1

	except Exception as e:
		frappe.log_error("eTIMS: Invoice number calculation error", str(e))
		cur_number = (last_inv_no or 0) + 1

	return cur_number


def get_original_invoice_number(doc):
	org_invoice_no = 0

	if doc.amended_from:
		org_invoice = frappe.get_all(
			"Purchase Invoice", filters={"name": doc.amended_from}, fields=["custom_invoice_number"]
		)
		if org_invoice:
			org_invoice_no = org_invoice[0].get("custom_invoice_number")

	return org_invoice_no


def validate_inv_number(doc):
	invoice_numbers = []
	invoice_number_list = frappe.db.get_all(
		"Purchase Invoice", fields=["custom_invoice_number", "name"], order_by="custom_invoice_number desc"
	)

	if invoice_number_list:
		for invoice_no in invoice_number_list:
			if not invoice_no.get("name") == doc.name:
				if invoice_no.get("custom_invoice_number") not in invoice_numbers:
					invoice_numbers.append(invoice_no.get("custom_invoice_number"))

	return invoice_numbers


def etims_pur_item_list(doc):
	pur_item_list = []
	for item in doc.items:
		item_tax_details = get_tax_template_details(item.get("item_code"))
		item_detail = frappe.db.get_all(
			"Item",
			filters={"disabled": 0, "item_code": item.get("item_code")},
			fields=[
				"custom_item_code",
				"custom_item_classification_code",
				"custom_item_name",
				"custom_packaging_unit_code",
				"custom_quantity_unit_code",
			],
		)

		if not item_detail:
			frappe.throw(f"Item {item.get('item_code')} not found or is disabled")

		barcode = eTIMS.get_item_barcode(item.item_code, item.uom)

		item_etims_data = {
			"itemSeq": item.get("idx"),
			"itemCd": item_detail[0].get("custom_item_code"),
			"itemClsCd": item_detail[0].get("custom_item_classification_code"),
			"itemNm": item_detail[0].get("custom_item_name"),
			"bcd": barcode if barcode else "",
			# "spplrItemClsCd":null,
			# "spplrItemCd":null,
			# "spplrItemNm": item.item_code,
			"pkgUnitCd": item_detail[0].get("custom_packaging_unit_code"),
			"pkg": abs(item.get("qty")),
			"qtyUnitCd": item_detail[0].get("custom_quantity_unit_code"),
			"qty": abs(item.get("qty")),
			"prc": abs(item.get("rate")),
			"splyAmt": abs(item.get("amount")),
			"dcRt": abs(item.get("discount_percentage")),
			"dcAmt": abs(item.get("discount_amount")),
			"taxTyCd": item_tax_details,
			"taxblAmt": abs(round(item.get("net_amount"), 2)),
			"taxAmt": abs(round((item.get("amount") - item.get("net_amount")), 2)),
			"totAmt": abs(item.get("amount")),
			"totDcAmt": abs(item.get("discount_amount")),
			# "itemExprDt":null
		}
		if item_etims_data not in pur_item_list:
			pur_item_list.append(item_etims_data)

	return pur_item_list


def etims_stock_item_list(doc):
	stock_item_list = []
	for item in doc.items:
		if item.custom_maintain_stock:
			item_tax_details = get_tax_template_details(item.get("item_code"))
			item_detail = frappe.db.get_all(
				"Item",
				filters={"disabled": 0, "item_code": item.get("item_code")},
				fields=[
					"custom_item_code",
					"custom_item_classification_code",
					"custom_item_name",
					"custom_packaging_unit_code",
					"custom_quantity_unit_code",
				],
			)

			barcode = eTIMS.get_item_barcode(item.item_code, item.uom)

			item_etims_data = {
				"itemSeq": item.get("idx"),
				"itemCd": item_detail[0].get("custom_item_code"),
				"itemClsCd": item_detail[0].get("custom_item_classification_code"),
				"itemNm": item_detail[0].get("custom_item_name"),
				"bcd": barcode if barcode else "",
				"pkgUnitCd": item_detail[0].get("custom_packaging_unit_code"),
				"pkg": abs(item.get("qty")),
				"qtyUnitCd": item_detail[0].get("custom_quantity_unit_code"),
				"qty": abs(item.get("qty")),
				"prc": abs(item.get("rate")),
				"splyAmt": abs(item.get("amount")),
				"dcRt": abs(item.get("discount_percentage")),
				"dcAmt": abs(item.get("discount_amount")),
				"taxTyCd": item_tax_details,
				"taxblAmt": abs(round(item.get("net_amount"), 2)),
				"taxAmt": abs(round((item.get("amount") - item.get("net_amount")), 2)),
				"totAmt": abs(item.get("amount")),
				"totDcAmt": abs(round((item.get("discount_amount") * item.get("qty")), 2)),
			}
			if item_etims_data not in stock_item_list:
				stock_item_list.append(item_etims_data)

	return stock_item_list




def get_tax_account_rate(account_head):
	tax_acc_docs = frappe.db.get_all("Account", filters={"name": account_head}, fields=["tax_rate"])

	if tax_acc_docs:
		tax_rate = tax_acc_docs[0].get("tax_rate")

		return tax_rate


def purchase_return_information(doc):
	diff_amount = 0
	return_status = ""

	if doc.is_return:
		if doc.return_against:
			return_amount = doc.grand_total
			return_against = frappe.get_doc("Purchase Invoice", doc.return_against)
			prev_return_amount = return_against.grand_total

			diff_amount = prev_return_amount + return_amount

		if diff_amount > 0:
			return_status = "partial"
		elif diff_amount == 0:
			return_status = "full"
		elif diff_amount < 0:
			return_status = "null"

	return return_status


# =============================================================================
# Invoice Verification Module - Phase 1: Invoice Checker API Integration
# =============================================================================


@frappe.whitelist()
def verify_supplier_invoice(docname):
	"""Verify supplier invoice before allowing payment

	This function is called from the Purchase Invoice form when the user
	clicks the "Verify Invoice with KRA" button. It verifies the invoice
	with the KRA eTIMS system and updates the verification status.

	Args:
	    docname: Purchase Invoice name/ID

	Returns:
	    {
	        "verified": True/False,
	        "message": "...",
	        "details": {...}  # if verified
	    }
	"""
	if not can_modify_doctype("Purchase Invoice", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	try:
		doc = frappe.get_doc("Purchase Invoice", docname)

		# Skip if already verified
		if doc.get("custom_invoice_verified"):
			return {
				"verified": True,
				"message": "Invoice already verified with KRA",
				"verification_date": doc.get("custom_verification_date"),
				"qr_code": doc.get("custom_qr_code"),
			}

		# Get supplier details
		supplier_pin = frappe.db.get_value("Supplier", doc.supplier, "custom_supplier_pin")

		if not supplier_pin:
			return {
				"verified": False,
				"warning": "Supplier PIN not set. Cannot verify invoice.",
				"message": "Please set the Tax PIN for this supplier in the Supplier master.",
			}

		# Get invoice details for verification
		invoice_no = doc.bill_no or doc.name
		cu_invoice_no = doc.get("custom_supplier_cu_invoice_no") or None
		invoice_date = doc.bill_date or doc.posting_date
		total_amount = doc.grand_total

		if not invoice_no and not cu_invoice_no:
			return {
				"verified": False,
				"warning": "No invoice identifier",
				"message": "Set either 'Supplier Invoice No' or 'Supplier CU Invoice No' before verifying.",
			}

		# Fast path: check the locally-pulled Register Entries first (no KRA round-trip)
		# Tries trader invoice no first, then CU invoice no.
		local_match = None
		if frappe.db.exists("DocType", "eTIMS Purchase Register Entry"):
			if invoice_no:
				local_match = frappe.db.get_value(
					"eTIMS Purchase Register Entry",
					{"supplier_pin": supplier_pin, "kra_invoice_number": invoice_no},
					["name", "total_amount", "invoice_date", "tax_amount"],
					as_dict=True,
				)
			if not local_match and cu_invoice_no:
				local_match = frappe.db.get_value(
					"eTIMS Purchase Register Entry",
					{"supplier_pin": supplier_pin, "kra_invoice_number": cu_invoice_no},
					["name", "total_amount", "invoice_date", "tax_amount"],
					as_dict=True,
				)

		if local_match:
			variance = abs((local_match.get("total_amount") or 0) - (total_amount or 0))
			result = {
				"Success": {
					"spplrTin": supplier_pin,
					"spplrInvcNo": invoice_no,
					"cuInvcNo": cu_invoice_no,
					"totAmt": local_match.get("total_amount"),
					"totTaxAmt": local_match.get("tax_amount"),
					"salesDt": local_match.get("invoice_date"),
					"_source": "local_register",
					"_variance": variance if variance > 0.01 else 0,
				}
			}
		else:
			# Fall back to live KRA lookup — matches on EITHER trader inv or CU inv
			result = eTIMS.invoiceCheckerReq(
				invoice_no=invoice_no,
				supplier_pin=supplier_pin,
				invoice_date=invoice_date,
				total_amount=total_amount,
				cu_invoice_no=cu_invoice_no,
			)

		if "Success" in result:
			# Extract verification details
			invoice_details = result["Success"]

			# Update invoice with verification status
			frappe.db.set_value(
				"Purchase Invoice",
				doc.name,
				{
					"custom_invoice_verified": 1,
					"custom_verification_date": frappe.utils.now(),
					"custom_qr_code": invoice_details.get("qrCode", ""),
					"custom_kra_invoice_number": invoice_details.get("invcNo", ""),
					"custom_supplier_pin_verified": supplier_pin,
				},
				update_modified=False,
			)

			# Log successful verification
			eTIMS.log_errors(
				f"Invoice Verified: {invoice_no}",
				f"Successfully verified with KRA eTIMS. Amount: {total_amount}",
			)

			return {
				"verified": True,
				"message": "Invoice verified successfully with KRA eTIMS",
				"details": invoice_details,
				"qr_code": invoice_details.get("qrCode", ""),
				"verification_date": frappe.utils.now(),
			}
		else:
			error_msg = result.get("Error", "Unknown error")
			# Log failed verification
			eTIMS.log_errors(
				f"Invoice Verification Failed: {invoice_no}", f"Supplier: {doc.supplier}, Error: {error_msg}"
			)

			return {
				"verified": False,
				"error": error_msg,
				"message": f"Invoice could not be verified with KRA: {error_msg}. "
				f"Please check the invoice details and contact the supplier if necessary.",
			}

	except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
		eTIMS.log_errors("Invoice Verification Exception", str(e))
		return {
			"verified": False,
			"error": str(e),
			"message": f"An error occurred during verification: {e!s}",
		}


def auto_verify_invoice(doc, method):
	"""Automatically verify invoice when created (if configured)

	This is called as a hook when a Purchase Invoice is submitted.
	It checks if auto-verification is enabled and the supplier is
	registered in eTIMS, then automatically verifies the invoice.

	To use this, add to hooks.py:
	"Purchase Invoice": {
	    "on_submit": "kenya_etims_compliance.custom_methods.purchase_invoice.auto_verify_invoice"
	}
	"""
	from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
		get_etims_settings,
	)

	settings = get_etims_settings()

	# Check if auto-verification is enabled
	if not settings.get("auto_verify_invoices", 0):
		return

	# Check if supplier allows auto-verification
	supplier = frappe.get_doc("Supplier", doc.supplier)
	if not supplier.get("custom_auto_verify_invoices", 0):
		return

	# Check if supplier is registered in eTIMS
	if not supplier.get("custom_registered_in_etims", 0):
		return

	# Proceed with automatic verification
	result = verify_supplier_invoice(doc.name)

	if result.get("verified"):
		frappe.msgprint(_("Invoice automatically verified with KRA eTIMS"))
	else:
		# Log but don't block submission
		eTIMS.log_errors(f"Auto-verification failed for {doc.name}", result.get("error", "Unknown error"))


@frappe.whitelist()
def get_supplier_invoice_status(supplier):
	"""Get verification status of all invoices for a supplier

	Useful for:
	- Supplier performance dashboards
	- Compliance reporting
	- Audit trails

	Args:
	    supplier: Supplier name/ID

	Returns:
	    {
	        "supplier": "...",
	        "total_invoices": n,
	        "verified_invoices": m,
	        "unverified_invoices": k,
	        "verification_rate": "xx%"
	    }
	"""
	if not can_modify_doctype("Purchase Invoice", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	try:
		total_invoices = frappe.db.count("Purchase Invoice", filters={"supplier": supplier, "docstatus": 1})

		verified_invoices = frappe.db.count(
			"Purchase Invoice", filters={"supplier": supplier, "docstatus": 1, "custom_invoice_verified": 1}
		)

		unverified_invoices = total_invoices - verified_invoices
		verification_rate = (verified_invoices / total_invoices * 100) if total_invoices > 0 else 0

		return {
			"supplier": supplier,
			"total_invoices": total_invoices,
			"verified_invoices": verified_invoices,
			"unverified_invoices": unverified_invoices,
			"verification_rate": f"{verification_rate:.1f}%",
		}

	except frappe.DataError as e:
		return {
			"error": str(e),
			"supplier": supplier,
			"total_invoices": 0,
			"verified_invoices": 0,
			"unverified_invoices": 0,
			"verification_rate": "N/A",
		}


@frappe.whitelist()
def mark_invoice_as_manually_verified(docname, reason):
	"""Manually mark an invoice as verified (with override reason)

	This should only be used in exceptional circumstances where:
	- Supplier is not eTIMS registered
	- KRA API is temporarily unavailable
	- Small value purchases below threshold

	Args:
	    docname: Purchase Invoice name
	    reason: Reason for manual verification override

	Returns:
	    {"success": True/False, "message": "..."}
	"""
	if not can_modify_doctype("Purchase Invoice", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	try:
		doc = frappe.get_doc("Purchase Invoice", docname)

		# Check if already verified
		if doc.get("custom_invoice_verified"):
			return {"success": False, "message": "Invoice is already verified"}

		# Update invoice as manually verified
		frappe.db.set_value(
			"Purchase Invoice",
			doc.name,
			{
				"custom_invoice_verified": 1,
				"custom_verification_date": frappe.utils.now(),
				"custom_qr_code": f"MANUAL_VERIFICATION: {reason}",
				"custom_kra_invoice_number": "MANUAL_OVERRIDE",
				"custom_verification_override_reason": reason,
			},
			update_modified=False,
		)

		# Log the manual override
		eTIMS.log_errors(
			f"Manual Verification Override: {docname}", f"Reason: {reason}, User: {frappe.session.user}"
		)

		return {"success": True, "message": "Invoice marked as manually verified"}

	except (frappe.DoesNotExistError, frappe.DataError) as e:
		return {"success": False, "message": f"Error: {e!s}"}
