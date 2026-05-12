import traceback
from datetime import datetime

import frappe
import requests
from frappe import _

from kenya_etims_compliance.utils.etims_utils import eTIMS, get_next_sar_number
from kenya_etims_compliance.utils.kra_client import KRAClient


@frappe.whitelist()
def searchStockMoveReq(sar_no=None, last_req_dt=None):
	"""Search stock movements in eTIMS"""
	response = eTIMS.searchStockMove(sar_no, last_req_dt)

	for key, value in response.items():
		if key == "Success":
			return {"Success": value}
		else:
			return {"Error": value}


def insert_tax_rate_and_amount(doc, method):
	total_taxable_amount = 0
	total_amount = 0
	main_tax_amount = 0

	if doc.items:
		for item in doc.items:
			if item.get("custom_tax_code"):
				account_head_list = frappe.db.get_all(
					"Account",
					filters={"account_type": "Tax", "custom_tax_code": item.get("custom_tax_code")},
					fields=["tax_rate"],
				)

				if account_head_list:
					item.custom_rate = account_head_list[0].get("tax_rate")

				if account_head_list[0].get("tax_rate") > 0:
					if item.get("basic_amount"):
						tax_rate = account_head_list[0].get("tax_rate") / 100
						taxable_amount = item.get("basic_amount") / (1 + tax_rate)
						tax_amount = item.get("basic_amount") - taxable_amount

						item.custom_tax_amount = round(tax_amount, 2)
						main_tax_amount += tax_amount
						total_amount += item.get("basic_amount")
						total_taxable_amount = round((total_amount - main_tax_amount), 2)

		doc.custom_total_tax_amount = round(main_tax_amount, 2)
		doc.custom_total_taxable_amount = total_taxable_amount


def update_stock_to_etims(doc, method):
	if not doc.custom_send_stock_info_to_etims:
		return

	from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
		get_etims_settings,
	)

	settings = get_etims_settings()
	use_queue = settings.get("enable_queue", 1)

	item_count = len(doc.items) if doc.items else 0
	date_str = eTIMS.strf_date_object(doc.posting_date)

	if not use_queue:
		# Synchronous fallback (original behavior)
		if doc.stock_entry_type == "Material Receipt":
			sar_type = "01" if doc.custom_is_import_stock == 1 else "06"
			stockIOSaveReq(doc, date_str, item_count, sar_type, doc.custom_target_tax_branch_office)
		elif doc.stock_entry_type == "Material Transfer":
			is_inter_branch = check_if_interbranch(doc)
			if is_inter_branch and doc.custom_update_both_branches:
				stockIOSaveReq(doc, date_str, item_count, "13", doc.custom_source_tax_branch_office)
				stockIOSaveReq(doc, date_str, item_count, "04", doc.custom_target_tax_branch_office)
		return

	from kenya_etims_compliance.custom_methods.queue_processor import enqueue_invoice

	if doc.stock_entry_type == "Material Receipt":
		branch_id = doc.custom_target_tax_branch_office
		if not branch_id:
			return

		sar_type = "01" if doc.custom_is_import_stock == 1 else "06"
		payload = _build_stock_io_payload(doc, branch_id, sar_type)
		if payload:
			enqueue_invoice(doc=doc, payload=payload, api_endpoint="insert_stock_io", branch_id=branch_id)

	elif doc.stock_entry_type == "Material Transfer":
		is_inter_branch = check_if_interbranch(doc)

		if is_inter_branch and doc.custom_update_both_branches:
			source_branch = doc.custom_source_tax_branch_office
			target_branch = doc.custom_target_tax_branch_office

			# Source branch (transfer out)
			payload_out = _build_stock_io_payload(doc, source_branch, "13")
			if payload_out:
				enqueue_invoice(
					doc=doc, payload=payload_out, api_endpoint="insert_stock_io", branch_id=source_branch
				)

			# Target branch (transfer in)
			payload_in = _build_stock_io_payload(doc, target_branch, "04")
			if payload_in:
				enqueue_invoice(
					doc=doc, payload=payload_in, api_endpoint="insert_stock_io", branch_id=target_branch
				)


def _build_stock_io_payload(doc, branch_id, sar_type):
	"""Build stock IO payload without calling the API. Returns dict or None."""
	item_count = len(doc.items) if doc.items else 0
	if item_count == 0:
		return None

	request_date = doc.posting_date
	date_str = eTIMS.strf_date_object(request_date)

	return {
		"sarNo": get_next_sar_number(doc, branch_id),
		"orgSarNo": 0,
		"regTyCd": "A",
		"custBhfId": "01",
		"ocrnDt": date_str,
		"totItemCnt": item_count,
		"totTaxblAmt": doc.custom_total_taxable_amount,
		"totTaxAmt": doc.custom_total_tax_amount,
		"totAmt": round(doc.total_incoming_value, 2),
		"remark": doc.remarks if doc.remarks else "",
		"regrId": doc.owner,
		"regrNm": doc.owner,
		"modrId": doc.modified_by,
		"modrNm": doc.modified_by,
		"sarTyCd": sar_type,
		"itemList": etims_stock_item_list(doc),
	}


def stockIOSaveReq(doc, date_str, item_count, sar_type, branch_id):
	client = KRAClient(branch_id=branch_id)

	payload = {
		"sarNo": get_next_sar_number(doc, branch_id),
		"orgSarNo": 0,
		"regTyCd": "A",
		"custBhfId": "01",
		"ocrnDt": date_str,
		"totItemCnt": item_count,
		"totTaxblAmt": doc.custom_total_taxable_amount,
		"totTaxAmt": doc.custom_total_tax_amount,
		"totAmt": round(doc.total_incoming_value, 2),
		"remark": doc.remarks if doc.remarks else "",
		"regrId": doc.owner,
		"regrNm": doc.owner,
		"modrId": doc.modified_by,
		"modrNm": doc.modified_by,
		"sarTyCd": sar_type,
		"itemList": etims_stock_item_list(doc),
	}

	if doc.custom_send_stock_info_to_etims == 1:
		try:
			result = client.insert_stock_io(payload)

			if "Error" in result:
				frappe.logger().debug("Stock entry error: {0}".format(result["Error"]))
				frappe.throw(result["Error"])

			doc.custom_updated_in_etims = 1
			frappe.msgprint(_("Stock entry synced to eTIMS successfully"))

		except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
			frappe.log_error(title="eTIMS Stock Entry Error", message=traceback.format_exc())
			frappe.throw(f"eTIMS Stock Entry Error: {e!s}")
	else:
		frappe.logger().debug("eTIMS stock IO not sent for branch %s", branch_id)


def check_if_interbranch(item):
	interbranch_transfer = False

	s_warehouse = item.get("from_warehouse")
	t_warehouse = item.get("to_warehouse")

	s_warehouse_doc = frappe.get_doc("Warehouse", s_warehouse)
	t_warehouse_doc = frappe.get_doc("Warehouse", t_warehouse)

	if s_warehouse_doc.get("custom_tax_branch_office") and t_warehouse_doc.get("custom_tax_branch_office"):
		if not s_warehouse_doc.get("custom_tax_branch_office") == t_warehouse_doc.get(
			"custom_tax_branch_office"
		):
			interbranch_transfer = True

	else:
		pass

	return interbranch_transfer


def get_warehouse_branch(warehouse_name):
	try:
		warehouse_doc = frappe.get_doc("Warehouse", warehouse_name)

		return warehouse_doc.get("custom_tax_branch_office")
	except frappe.DoesNotExistError as e:
		frappe.log_error("eTIMS: Stock error", str(e))
		frappe.throw(_("No tax branch id"))


def etims_stock_item_list(doc):
	stock_item_list = []
	for item in doc.items:
		item_tax_code = get_tax_template_details(item.get("item_code"))
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
		item_etims_data = {
			"itemSeq": item.get("idx"),
			"itemCd": item_detail[0].get("custom_item_code"),
			"itemClsCd": item_detail[0].get("custom_item_classification_code"),
			"itemNm": item_detail[0].get("custom_item_name"),
			# "bcd":null,
			"pkgUnitCd": item_detail[0].get("custom_packaging_unit_code"),
			"pkg": item.get("qty"),
			"qtyUnitCd": item_detail[0].get("custom_quantity_unit_code"),
			"qty": item.get("qty"),
			"prc": round(item.get("basic_rate"), 2),
			"splyAmt": item.get("basic_amount"),
			"dcRt": 0.0,
			"dcAmt": 0.0,
			"totDcAmt": 0.0,
			"taxTyCd": item_tax_code,
			"taxblAmt": round((item.get("amount") - (item.get("custom_tax_amount") or 0)), 2),
			"taxAmt": item.get("custom_tax_amount") or 0,
			"totAmt": round(item.get("amount"), 2),
		}

		if item_etims_data not in stock_item_list:
			stock_item_list.append(item_etims_data)

	return stock_item_list


def get_tax_template_details(item_code):
	item_doc = frappe.get_doc("Item", item_code)
	if item_doc:
		for tax_item in item_doc.taxes:
			tax_code = frappe.get_doc("Item Tax Template", tax_item.get("item_tax_template"))

			if tax_code:
				return tax_code.get("custom_code")
	else:
		return "D"
