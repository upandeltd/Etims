import traceback
from datetime import datetime

import frappe
from frappe import _

from kenya_etims_compliance.utils.etims_utils import eTIMS
from kenya_etims_compliance.utils.kra_client import KRAClient
from kenya_etims_compliance.utils.permissions import can_sync_to_etims


# This part describes the components of SaveItem API function (url : /saveItem) and data types for each item.
# This API function is divided into 'Request: Argument' and 'Response: Return Object'.
# The ItemSaveReq is an Argument Object of Request, The ItemSaveRes is a Return Object of Response
def _get_branch_user(system_user):
	"""Resolve a Frappe login to its registered eTIMS Branch User.

	The Frappe login (an item's owner/modifier) is linked via the branch user's
	``system_user`` field; the KRA identifier lives in the separate
	``kra_user_id`` field. Falls back to matching ``user_id`` directly for older
	records that stored the login there. Returns a dict with ``user_name`` and
	``kra_user_id`` for a saved branch user, else None.
	"""
	if not system_user:
		return None
	try:
		# Match the login via system_user (preferred) or user_id (legacy records).
		# Guard the system_user filter for sites where the field isn't migrated yet.
		or_filters = {"user_id": system_user}
		if frappe.get_meta("eTIMS Branch User").has_field("system_user"):
			or_filters["system_user"] = system_user
		rows = frappe.get_all(
			"eTIMS Branch User",
			filters={"saved": 1},
			or_filters=or_filters,
			fields=["user_name", "kra_user_id"],
			limit=1,
		)
		return rows[0] if rows else None
	except Exception:
		return None


def _get_branch_user_name(system_user):
	"""Backwards-compatible wrapper — returns user_name only."""
	result = _get_branch_user(system_user)
	return result.get("user_name") if result else None


@frappe.whitelist()
def validate_items_for_etims(items=None):
	import json

	if isinstance(items, str):
		items = json.loads(items)

	valid = []
	invalid = []

	for item_name in items:
		result = validate_item_for_etims(item_name)
		if result.get("valid"):
			valid.append(item_name)
		else:
			invalid.append({"item": item_name, "errors": result.get("errors", [])})

	return {"valid": valid, "invalid": invalid}


@frappe.whitelist()
def validate_item_for_etims(doc_name):
	item = frappe.get_doc("Item", doc_name)
	errors = []

	# 1. Branch users
	creator = _get_branch_user_name(item.owner)
	modifier = _get_branch_user_name(item.modified_by)
	if not creator:
		errors.append(
			_("Creator '{0}' is not a registered eTIMS Branch User.").format(item.owner)
		)
	if not modifier:
		errors.append(
			_("Modifier '{0}' is not a registered eTIMS Branch User.").format(item.modified_by)
		)

	# 2. Required fields
	if not item.custom_item_classification_code:
		errors.append(_("Item Classification Code is required."))
	if not item.custom_default_packing_unit:
		errors.append(_("Default Packing Unit is required."))
	if not item.custom_default_quantity_unit:
		errors.append(_("Default Quantity Unit is required."))
	if not item.custom_country_of_origin:
		errors.append(_("Country of Origin is required."))
	if not item.custom_default_unit_price:
		errors.append(_("Default Unit Price is required."))
	if not item.taxes:
		errors.append(_("Tax Template is required."))

	# 3. Item code uniqueness
	if item.custom_item_code:
		_duplicate = frappe.db.exists(
			"Item",
			{
				"custom_item_code": item.custom_item_code,
				"name": ["!=", item.name],
			},
		)
		if _duplicate:
			errors.append(
				_("Item code '{0}' is already used by item '{1}'.").format(
					item.custom_item_code, _duplicate
				)
			)

	# 4. Already registered check
	if item.custom_registered_in_tims:
		errors.append(_("Item is already registered in eTIMS."))

	if errors:
		return {"valid": False, "errors": errors}

	return {"valid": True}


@frappe.whitelist()
def itemSaveReq(doc_name):
	if not can_sync_to_etims("Item"):
		frappe.throw(
			_("Permission Denied: you do not have permission to sync to eTIMS."),
			frappe.PermissionError,
		)

	response = eTIMS.itemSaveReq(doc_name)

	for key, value in response.items():
		if key == "Success":
			return {"Success": value}
		else:
			eTIMS.log_errors("Item Registration", value)
			return {"Error": value}


@frappe.whitelist()
def searchItemReq(item_code=None, item_name=None, last_req_dt=None):
	response = eTIMS.searchItem(item_code, item_name, last_req_dt)

	for key, value in response.items():
		if key == "Success":
			return {"Success": value}
		else:
			eTIMS.log_errors("Item Search", value)
			return {"Error": value}


@frappe.whitelist()
def selectItemReq(item_code):
	response = eTIMS.selectItem(item_code)

	for key, value in response.items():
		if key == "Success":
			return {"Success": value}
		else:
			eTIMS.log_errors("Item Details", value)
			return {"Error": value}


@frappe.whitelist()
def importItemUpdateReq(doc_name):
	if not can_sync_to_etims("Item"):
		frappe.throw(
			_("Permission Denied: you do not have permission to sync to eTIMS."),
			frappe.PermissionError,
		)

	frappe.has_permission("Item", "write", doc=doc_name, throw=True)

	import_item = frappe.get_doc("Item", doc_name)

	if import_item.custom_is_import_item == 1:
		declr_date = datetime.strftime(import_item.get("custom_declaration_date"), "%Y%m%d")

		payload = {
			"taskCd": import_item.get("custom_task_code"),
			"dclDe": declr_date,
			"itemSeq": 1,
			"hsCd": import_item.get("custom_hs_code"),
			"itemClsCd": import_item.get("custom_item_classification_code"),
			"itemCd": import_item.get("custom_item_code"),
			"imptItemSttsCd": get_status_code(import_item.get("custom_import_item_status_code")),
			"remark": import_item.get("custom_remark"),
			"modrId": import_item.get("modified_by"),
			"modrNm": import_item.get("modified_by"),
		}
		try:
			result = KRAClient().post("updateImportItem", payload)

			if result.get("Error"):
				return {"Error": result.get("Error")}

			return {"Success": result.get("Success")}

		except Exception:
			eTIMS.log_errors("Import Item Update", traceback.format_exc())
			return {"Error": _("Import item update failed. Please check the error log for details.")}


def get_status_code(code_name):
	if code_name == "Unsent":
		return 1
	elif code_name == "Waiting":
		return 2
	elif code_name == "Approved":
		return 3
	else:
		return 4


def autofill_tims_info(doc, method):
	if doc.custom_update_item_to_tims == 1 and not doc.custom_registered_in_tims == 1:
		# 1. Resolve branch users (strict)
		creator = _get_branch_user(doc.owner)
		modifier = _get_branch_user(doc.modified_by)

		if not creator:
			frappe.throw(
				_("Creator '{0}' is not a registered eTIMS Branch User.").format(doc.owner)
			)

		if not modifier:
			frappe.throw(
				_("Modifier '{0}' is not a registered eTIMS Branch User.").format(doc.modified_by)
			)

		# 2. Required Fields Guard
		missing = []
		if not doc.custom_item_classification_code:
			missing.append(_("Item Classification Code"))
		if not doc.custom_default_packing_unit:
			missing.append(_("Default Packing Unit"))
		if not doc.custom_default_quantity_unit:
			missing.append(_("Default Quantity Unit"))
		if not doc.custom_country_of_origin:
			missing.append(_("Country of Origin"))

		if missing:
			frappe.throw(
				_("The following eTIMS fields are required before registration:<br>{0}").format(
					"<br>".join(f"• {m}" for m in missing)
				)
			)

		# 3. Auto-fill fields
		doc.custom_item_name = doc.item_code
		doc.custom_item_standard_name = doc.item_name
		doc.custom_quantity_unit_code = get_item_qty_unit_codes(doc.custom_default_quantity_unit)
		doc.custom_packaging_unit_code = get_item_pkg_unit_codes(doc.custom_default_packing_unit)
		doc.custom_used__unused = get_item_status(doc)
		doc.custom_item_type_code = get_item_type_code(doc)
		doc.custom_registration_id = creator.get("kra_user_id")
		doc.custom_registration_name = creator.get("user_name")
		doc.custom_modifier_id = modifier.get("kra_user_id")
		doc.custom_modifier_name = modifier.get("user_name")

		if doc.taxes:
			for tax_item in doc.taxes:
				doc.custom_taxation_type_code = get_taxation_type(tax_item.get("item_tax_template"))
		else:
			frappe.throw(_("Tax template for Item is required!"))

		if not doc.custom_default_unit_price:
			doc.custom_default_unit_price = get_item_prices(doc)

		if not doc.custom_item_code:
			doc.custom_item_code = get_item_code(doc)
		else:
			# 4. Duplicate Item Code Check
			_duplicate = frappe.db.exists(
				"Item",
				{
					"custom_item_code": doc.custom_item_code,
					"name": ["!=", doc.name],
				}
			)
			if _duplicate:
				frappe.throw(
					_(
						"Item code '{0}' is already assigned to item '{1}'. "
						"Each item must have a unique eTIMS item code."
					).format(doc.custom_item_code, _duplicate)
				)


def get_item_pkg_unit_codes(pkg_unit):
	try:
		etims_code_doc = frappe.get_doc("eTIMS Packing Unit", pkg_unit)
		if etims_code_doc:
			return etims_code_doc.get("etims_code")
	except Exception as e:
		frappe.log_error("eTIMS: item - item error", str(e))
		return


def get_item_qty_unit_codes(qty_unit):
	try:
		etims_code_doc = frappe.get_doc("eTIMS Quantity Unit", qty_unit)
		if etims_code_doc:
			return etims_code_doc.get("etims_code")
	except Exception as e:
		frappe.log_error("eTIMS: item - item error", str(e))
		return


def get_item_status(doc):
	if not doc.disabled:
		return "Y"
	else:
		return "N"


def get_taxation_type(tax_template):
	tax_list = []
	if tax_template:
		tax_doc = frappe.get_doc("Item Tax Template", tax_template)

		if tax_doc.get("custom_code") not in tax_list:
			tax_list.append(tax_doc.get("custom_code"))

	return tax_list[0]


def get_item_prices(doc):
	if not doc.custom_default_unit_price:
		item_price_doc = frappe.db.get_all(
			"Item Price",
			filters={"item_code": doc.item_code, "selling": 1, "customer": ""},
			fields=["price_list_rate"],
		)

		if item_price_doc:
			return item_price_doc[0].get("price_list_rate")
		else:
			frappe.throw(_("Price list for Item is required!"))


def get_item_type_code(doc):
	item_type_doc = frappe.get_doc("Item Group", doc.item_group)

	if item_type_doc:
		return item_type_doc.get("custom_etims_item_type_code")


def get_country_code(country):
	if not country:
		return None

	if len(country) == 2 and country.isalpha():
		return country.upper()

	try:
		code = frappe.db.get_value("eTIMS Country", country, "code_name")
		if code:
			return code
	except Exception:
		pass

	return country


def get_item_code(doc):
	origin_code = doc.custom_origin_place_code_nation
	if not origin_code and doc.custom_country_of_origin:
		origin_code = get_country_code(doc.custom_country_of_origin)

	if origin_code:
		str_item_code = (
			origin_code
			+ str(get_item_type_code(doc))
			+ get_item_pkg_unit_codes(doc.custom_default_packing_unit)
			+ get_item_qty_unit_codes(doc.custom_default_quantity_unit)
		)

		item_code = str(str_item_code) + create_item_digit_code(doc)

		return item_code


def item_code_increment(doc):
	item_code_list = []
	item_codes_dgt_list = []
	tims_item_codes = frappe.db.get_all(
		"Item", filters={"name": ["!=", doc.name]}, fields=["custom_item_code"]
	)
	if tims_item_codes:
		for item in tims_item_codes:
			if item.get("custom_item_code"):
				if (
					item.get("custom_item_code") not in item_code_list
					and len(item.get("custom_item_code")) > 10
				):
					item_code_list.append(item.get("custom_item_code"))

			for code in item_code_list:
				start = int(len(code) - 7)
				end = len(code)
				code_dgt = code[start:end]

				if code_dgt not in item_codes_dgt_list:
					item_codes_dgt_list.append(code_dgt)

	return item_codes_dgt_list


def create_item_digit_code(doc):
	item_codes = item_code_increment(doc)
	item_code_dgt = "0000001"
	digit_code_list = []

	if len(item_codes) > 0:
		for item in item_codes:
			if item not in digit_code_list:
				digit_code_list.append(int(item))

		largest_no = max(digit_code_list)
		next_dgt = largest_no + 1

		padded_num = str(next_dgt).rjust(7, "0")
		return padded_num

	else:
		return item_code_dgt


def get_bin_qty(item_code):
	bin_docs = frappe.db.get_all("Bin", filters={"item_code": item_code}, fields=["actual_qty"])

	if bin_docs:
		return bin_docs[0].get("actual_qty")
	else:
		return 0