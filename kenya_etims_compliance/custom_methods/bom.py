import traceback

import frappe
import requests
from frappe import _

from kenya_etims_compliance.utils.etims_utils import eTIMS
from kenya_etims_compliance.utils.kra_client import KRAClient
from kenya_etims_compliance.utils.permissions import require


@frappe.whitelist()
def itemSaveComposition(doc_name):
	# HIGH — gate FIRST. The original code did `frappe.get_doc("BOM", doc_name)`
	# and POSTed each item composition to KRA before any permission check.
	# That means a denied caller still triggered an outbound disclosure.
	require("BOM", "write")

	bom_item_list = get_bom_items(doc_name)
	doc = frappe.get_doc("BOM", doc_name)
	for payload in bom_item_list:
		post_item_compostion(payload, doc)
	check_if_all_items_sent(doc)


def get_bom_items(doc_name):
	payload_list = []

	doc = frappe.get_doc("BOM", doc_name)

	if not doc.custom_etims_item_code:
		frappe.throw(_("eTIMS item code is missing!"))

	if doc.is_default == 1 and doc.is_active == 1:
		for item in doc.items:
			if not item.get("custom_etims_item_code"):
				frappe.throw("Item {} missing etims item code.".format(item.get("item_code")))

			if not item.get("custom_updated_in_etims") == 1:
				payload = {
					"itemCd": doc.get("custom_etims_item_code"),
					"cpstItemCd": item.get("custom_etims_item_code"),
					"cpstQty": item.get("qty"),
					"regrNm": item.owner,
					"regrId": item.owner,
				}

				if payload not in payload_list:
					payload_list.append(payload)

	return payload_list


def post_item_compostion(item_payload, doc):
	for item in doc.items:
		if item.get("custom_etims_item_code") == item_payload.get("cpstItemCd"):
			try:
				result = KRAClient().post("saveItemComposition", item_payload)

				if result.get("Error"):
					frappe.throw(result.get("Error"))

				item.custom_updated_in_etims = 1
				doc.save()
				frappe.msgprint(result.get("Success") or "Item composition saved successfully.")

			except frappe.exceptions.ValidationError:
				raise
			except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
				eTIMS.log_errors("Item Save Composition", traceback.format_exc())
				frappe.throw(_("eTIMS Item Composition Error: {0}").format(e))


def check_if_all_items_sent(doc):
	check_count = 0
	item_count = 0
	for item in doc.items:
		item_count += 1
		if item.get("custom_updated_in_etims") == 1:
			check_count += 1

	if check_count == item_count:
		doc.custom_updated_to_etims = 1
		doc.save()
		return True
	else:
		return False
