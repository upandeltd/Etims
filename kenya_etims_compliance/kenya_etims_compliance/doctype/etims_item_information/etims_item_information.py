# Copyright (c) 2023, Upande Ltd and contributors
# For license information, please see license.txt

import traceback

import frappe
from frappe import _
from frappe.model.document import Document

from kenya_etims_compliance.utils.etims_utils import (
	ensure_item_classification,
	eTIMS,
	get_country_of_origin,
	get_item_tax_template,
	get_item_type,
	get_packing_and_quantity_unit,
)
from kenya_etims_compliance.utils.kra_client import KRAClient
from kenya_etims_compliance.utils.permissions import can_sync_to_etims


class eTIMSItemInformation(Document):
	# This part describes the item API function (url : /selectItemClsList) of product classification and data types for each item.
	# API functions are dividedinto'Request:Argument' and 'Response:Return Object'.
	# The ItemClsSearchReq is an Argument Object of Request, The ItemClsSearchRes is a ReturnObject ofResponse.
	@frappe.whitelist()
	def itemClsSearchReq(self):
		if not can_sync_to_etims(self.doctype):
			frappe.throw(
				_("Permission Denied: you do not have permission to sync to eTIMS."),
				frappe.PermissionError,
			)

		request_datetime = self.search_datetime
		if not request_datetime:
			frappe.throw(_("Set 'Search Date and Time' before searching."), frappe.ValidationError)

		date_time_str = frappe.utils.get_datetime(request_datetime).strftime("%Y%m%d%H%M%S")

		client = KRAClient()
		payload = {
			"bhfId": client.branch_id or "",
			"lastReqDt": date_time_str,
		}

		try:
			result = client.post("selectItemClsList", payload)

			if result.get("Error"):
				return {"Error": result.get("Error")}

			response_result = {"data": result.get("Success")}
			frappe.enqueue(process_item_cls_info, queue="long", response_result=response_result)

			self.last_search_date_and_time = request_datetime
			self.save()
			return {"Success": "Item classification search completed"}

		except (frappe.ValidationError, frappe.DoesNotExistError):
			frappe.log_error(title="eTIMS: Item Classification Search failed", message=traceback.format_exc())
			return {"Error": "Oops Bad Request!"}

	# This part describes the components of SelectItemList API function (url : /selectItemList) and data types for each item.
	# This API function is divided into 'Request:Argument' and 'Response: Return Object'.
	# The ItemSearchReq is an Argument Object of Request, The ItemSearchRes is a Return Object of Response
	@frappe.whitelist()
	def itemSearchReq(self):
		if not can_sync_to_etims(self.doctype):
			frappe.throw(
				_("Permission Denied: you do not have permission to sync to eTIMS."),
				frappe.PermissionError,
			)

		request_datetime = self.item_request_datetime
		if not request_datetime:
			frappe.throw(_("Set 'Item Request Date and Time' before searching."), frappe.ValidationError)

		date_time_str = frappe.utils.get_datetime(request_datetime).strftime("%Y%m%d%H%M%S")

		payload = {
			"lastReqDt": date_time_str,
		}

		try:
			result = KRAClient().post("selectItemList", payload)

			if result.get("Error"):
				return {"Error": result.get("Error")}

			response_result = {"data": result.get("Success")}
			item_list = process_registered_items(response_result)
			for item in item_list:
				item_exists = check_if_item_exists(item.get("item_code"))
				if not item_exists:
					self.append("registered_items", item)
			self.item_last_search_date_and_time = request_datetime
			self.save()
			return {"Success": "Item search completed"}

		except (frappe.ValidationError, frappe.DoesNotExistError):
			frappe.log_error(title="eTIMS: Item Search failed", message=traceback.format_exc())
			return {"Error": "Oops Bad Request!"}

	@frappe.whitelist()
	def itemSaveComposition(self):
		if not can_sync_to_etims(self.doctype):
			frappe.throw(
				_("Permission Denied: you do not have permission to sync to eTIMS."),
				frappe.PermissionError,
			)

		if not self.bom_items:
			frappe.throw(_("No BOM items to register!"))

		if not self.item:
			frappe.throw(_("Item name is mandatory!"))

		item_doc = frappe.get_doc("Item", self.item)

		for item in self.bom_items:
			if not item.get("saved_in_etims") == 1:
				payload = {
					"itemCd": self.etims_item_code or item_doc.get("custom_item_code"),
					"cpstItemCd": item.get("etims_item_code"),
					"cpstQty": item.get("quantity"),
					"regrNm": item.owner,
					"regrId": item.owner,
				}
				try:
					result = KRAClient().post("saveItemComposition", payload)

					if result.get("Error"):
						return {"Error": result.get("Error")}

					item.saved_in_etims = 1
					self.save()
					self.itemSaveComposition()
					return {"Success": "Item composition saved"}

				except (frappe.ValidationError, frappe.DoesNotExistError):
					frappe.log_error(
						title="eTIMS: Item Save Composition failed", message=traceback.format_exc()
					)
					return {"Error": "Oops Bad Request!"}

	@frappe.whitelist()
	def consolidate_item_bom(self):
		if not can_sync_to_etims(self.doctype):
			frappe.throw(
				_("Permission Denied: you do not have permission to sync to eTIMS."),
				frappe.PermissionError,
			)

		try:
			if not self.item:
				frappe.throw(_("No Item Selected!"))

			item_bom = check_if_item_has_bom(self.item)
			bom_item_list = get_exploded_items(item_bom)

			for item in bom_item_list:
				check_bom_item_exists = check_if_bom_item_exists(item.get("etims_item_code"), item_bom)
				if not check_bom_item_exists:
					self.append(
						"bom_items",
						{
							"item_name": item.get("item_name"),
							"etims_item_code": item.get("etims_item_code"),
							"quantity": item.get("qty"),
							"stock_uom": item.get("uom"),
							"parent_bom": item.get("bom"),
						},
					)
					self.save()
		except (frappe.DoesNotExistError, frappe.ValidationError) as e:
			frappe.log_error(title="eTIMS: Consolidate Item BOM failed", message=str(e))
			frappe.throw(_("Something went wrong!"))


def process_item_cls_info(response_result):
	data = response_result.get("data")
	if data.get("itemClsList"):
		for item in data.get("itemClsList"):
			code_exists = check_if_doc_exists(item.get("itemClsCd"))
			if not code_exists:
				new_doc = frappe.new_doc("eTIMS Item Classification")
				new_doc.item_class_code = item.get("itemClsCd")
				new_doc.item_class_name = item.get("itemClsNm")
				new_doc.item_class_level = item.get("itemClsLvl")
				new_doc.taxation_type_code = item.get("taxTyCd")
				new_doc.is_major_target = item.get("mjrTgYn")
				new_doc.usedunused = item.get("useYn")
				new_doc.insert()

	else:
		frappe.throw(_("No code data found for this period please try an earlier date"))


def check_if_doc_exists(item_code):
	cdcls_exists = False
	code_info_docs = frappe.db.get_all(
		"eTIMS Item Classification", filters={"item_class_code": item_code}, fields=["name"]
	)

	if code_info_docs:
		cdcls_exists = True

	return cdcls_exists


def process_registered_items(response_result):
	item_list = []
	data = response_result.get("data")

	if data.get("itemList"):
		for item in data.get("itemList"):
			create_new_item_doctype(item)
			data = {
				"pin": item.get("tin"),
				"item_classification_code": item.get("itemClsCd"),
				"item_code": item.get("itemCd"),
				"item_type_code": item.get("itemTyCd"),
				"item_name": item.get("itemNm"),
				"item_standard_name": item.get("itemStdNm"),
				"origin_place_code_nation": item.get("orgnNatCd"),
				"packing_unit_code": item.get("pkgUnitCd"),
				"quantity_unit_code": item.get("qtyUnitCd"),
				"taxation_type_code": item.get("taxTyCd"),
				"batch_number": item.get("btchNo"),
				"regist_branch_office_id": item.get("regBhfId"),
				"barcode": item.get("bcd"),
				"default_unit_price": item.get("dftPrc"),
				"group1_unit_price": item.get("grpPrcL1"),
				"group2_unit_price": item.get("grpPrcL2"),
				"group3_unit_price": item.get("grpPrcL3"),
				"group4_unit_price": item.get("grpPrcL4"),
				"group5_unit_price": item.get("grpPrcL5"),
				"add_information": item.get("addInfo"),
				"safety_quantity": item.get("sftyQty"),
				"insurance_appicable_yn": item.get("isrcAplcbYn"),
				"kra_modify_yn_item_classification_code": item.get("rraModYn"),
				"usedunused": item.get("useYn"),
			}

			if data not in item_list:
				item_list.append(data)

	return item_list


def check_if_item_exists(item_code):
	item_exists = False
	etims_items = frappe.db.get_all("eTIMS Registered Items", filters={"item_code": item_code})

	if etims_items:
		item_exists = True

	return item_exists


def check_if_bom_item_exists(etims_item_code, parent_bom):
	item_exists = False
	etims_items = frappe.db.get_all(
		"eTIMS BOM Item", filters={"etims_item_code": etims_item_code, "parent_bom": parent_bom}
	)

	if etims_items:
		item_exists = True

	return item_exists


def check_if_item_has_bom(item_code):
	"""method to check if item has bom

	Args:
	    item_name (str): item name
	"""
	try:
		valid_bom = frappe.get_all(
			"BOM", filters={"item": item_code, "is_active": 1, "is_default": 1, "docstatus": 1}
		)
		if len(valid_bom) > 0:
			return valid_bom[0].get("name")
		else:
			frappe.throw("BOM for {} is not defined".format(item_code))
	except (frappe.DoesNotExistError, frappe.ValidationError) as e:
		frappe.log_error(title="eTIMS: Check Item BOM failed", message=str(e))
		frappe.throw("BOM for {} is not defined".format(item_code))


def get_exploded_items(bom_name):
	bom_details_list = []
	bom_doc = frappe.get_doc("BOM", bom_name)
	for item in bom_doc.exploded_items:
		item_doc = frappe.get_doc("Item", item.item_code)
		if not item_doc.get("custom_item_code"):
			frappe.throw("Item {} has no eTIMS item code.".format(item_doc.item_code))

		if not item_doc.get("custom_registered_in_tims"):
			frappe.throw("Item {} not registered to eTIMS.".format(item_doc.item_code))

		etims_item_code = item_doc.get("custom_item_code")

		bom_item_details = {
			"item_name": item.item_code,
			"etims_item_code": etims_item_code,
			"qty": item.get("stock_qty"),
			"uom": item.get("stock_uom"),
			"bom": bom_name,
		}

		if bom_item_details not in bom_details_list:
			bom_details_list.append(bom_item_details)

	return bom_details_list


def create_new_item_doctype(item):
	current_user = frappe.session.user
	item_exists = check_if_item_exits(item.get("itemNm"))

	if not item_exists:
		pkgUnitNm, qtyUnitNm = get_packing_and_quantity_unit(item.get("pkgUnitCd"), item.get("qtyUnitCd"))
		nat_of_origin = get_country_of_origin(item.get("itemCd"))

		new_item_doc = frappe.new_doc("Item")
		new_item_doc.item_code = item.get("itemNm")
		new_item_doc.custom_item_code = item.get("itemCd")
		new_item_doc.custom_item_name = item.get("itemNm")
		new_item_doc.item_group = get_item_type(item.get("itemCd"))
		new_item_doc.stock_uom = "Nos"
		new_item_doc.custom_country_of_origin = nat_of_origin
		new_item_doc.custom_item_classification_code = ensure_item_classification(item.get("itemClsCd"))
		new_item_doc.custom_packaging_unit_code = item.get("pkgUnitCd")
		new_item_doc.custom_quantity_unit_code = item.get("qtyUnitCd")
		new_item_doc.custom_default_unit_price = item.get("dftPrc")
		new_item_doc.custom_default_packing_unit = pkgUnitNm
		new_item_doc.custom_default_quantity_unit = qtyUnitNm
		new_item_doc.custom_used__unused = "Y"
		new_item_doc.custom_taxation_type_code = item.get("taxTyCd")
		new_item_doc.custom_registration_id = current_user
		new_item_doc.custom_modifier_id = current_user
		new_item_doc.custom_registered_in_tims = 1

		if item.get("taxTyCd"):
			tax_template = get_item_tax_template(item.get("taxTyCd"))
			new_item_doc.append("taxes", {"item_tax_template": tax_template})

		new_item_doc.insert()

		create_selling_price(item.get("itemNm"), item.get("dftPrc"))

		new_item_doc.save()


def create_selling_price(item_code, prc):
	prc_list = frappe.db.get_all(
		"Item Price", filters={"item_code": item_code, "selling": 1}, fields=["name"]
	)

	if not prc_list:
		new_item_prc = frappe.new_doc("Item Price")
		new_item_prc.item_code = item_code
		new_item_prc.price_list = "Standard Selling"
		new_item_prc.price_list_rate = prc

		new_item_prc.insert()


def check_if_item_exits(item_code):
	item_exists = frappe.db.exists({"doctype": "Item", "item_code": item_code})

	if item_exists:
		return True
	else:
		return False
