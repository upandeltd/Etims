from datetime import datetime

import frappe
from frappe import _

from kenya_etims_compliance.utils.kra_client import KRAClient


class eTIMS:
	@staticmethod
	def get_headers():
		branch_id = eTIMS.get_user_branch_id()
		if not branch_id:
			# Fallback for single-branch setups
			devices = frappe.db.get_all(
				"TIS Device Initialization", filters={"active": 1}, fields=["branch_id"], limit=2
			)
			if len(devices) == 1:
				branch_id = devices[0].get("branch_id")
		if not branch_id:
			return None
		header_docs = frappe.db.get_all(
			"TIS Device Initialization",
			filters={"branch_id": branch_id, "active": 1},
			fields=["pin", "branch_id", "communication_key"],
		)

		if header_docs:
			return {
				"tin": header_docs[0].get("pin"),
				"bhfId": header_docs[0].get("branch_id"),
				"cmcKey": header_docs[0].get("communication_key"),
			}

	@staticmethod
	def get_base_url():
		base_url = frappe.utils.get_url()

		return base_url

	@staticmethod
	def strf_datetime_object(datetime_data):
		datetime_object = datetime.strptime(datetime_data, "%Y-%m-%d %H:%M:%S")
		date_time_str = datetime_object.strftime("%Y%m%d%H%M%S")

		return date_time_str

	@staticmethod
	def strf_datetime_format(datetime_data):
		date_time_str = ""
		if isinstance(datetime_data, str):
			try:
				datetime_object = datetime.strptime(datetime_data, "%Y-%m-%d %H:%M:%S.%f")
				date_time_str = datetime_object.strftime("%Y%m%d%H%M%S")

			except ValueError as e:
				frappe.log_error(title="eTIMS: Datetime format error", message=str(e))
				datetime_object = datetime.strptime(datetime_data, "%Y-%m-%d %H:%M:%S")
				date_time_str = datetime_object.strftime("%Y%m%d%H%M%S")

		else:
			date_time_str = datetime_data.strftime("%Y%m%d%H%M%S")

		return date_time_str

	@staticmethod
	def strf_date_object(date_data):
		"""Format a date as YYYYMMDD. Accepts date, datetime, or 'YYYY-MM-DD' string."""
		if date_data is None:
			return ""
		# Already a date or datetime object
		if hasattr(date_data, "strftime"):
			return date_data.strftime("%Y%m%d")
		# Otherwise, assume string
		try:
			date_object = datetime.strptime(str(date_data), "%Y-%m-%d")
			return date_object.strftime("%Y%m%d")
		except ValueError as e:
			frappe.log_error(title="eTIMS: Date format error", message=str(e))
			return ""

	@staticmethod
	def strf_time(time_data):
		time_str = ""
		try:
			time_object = datetime.strptime(time_data, "%H:%M:%S")
			time_str = time_object.strftime("%H%M%S")
		except ValueError as e:
			frappe.log_error(title="eTIMS: Time format error", message=str(e))
			time_object = datetime.strptime(time_data, "%H:%M:%S.%f")
			time_str = time_object.strftime("%H%M%S")

		return time_str

	@staticmethod
	def get_response_data(response):
		if response.get("message"):
			return response.get("message")
		else:
			return response

	@staticmethod
	def tims_base_url():
		"""Get TIS base URL from settings"""
		from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
			get_api_url,
		)

		branch_id = eTIMS.get_user_branch_id()
		settings_docs = frappe.db.get_all(
			"TIS Device Initialization", filters={"branch_id": branch_id, "active": 1}, fields=["*"]
		)

		if settings_docs:
			api_mode = settings_docs[0].api_mode
			return get_api_url(api_mode)

		# Fallback: use default sandbox URL when no active device found
		return get_api_url("Sandbox")

	@staticmethod
	def verify_supplier_pin(supplier_pin):
		"""Verify supplier PIN via KRA selectCustomer endpoint."""
		if not supplier_pin or len(supplier_pin) != 10:
			return {"Error": "Invalid PIN format"}
		client = KRAClient()
		return client.post("selectCustomer", {"custmTin": supplier_pin})

	@staticmethod
	def strp_datetime_object(date_time_str):
		datetime_object = datetime.strptime(date_time_str, "%Y%m%d%H%M%S")

		return datetime_object

	@staticmethod
	def strp_date_object(date_str):
		date_object = datetime.strptime(date_str, "%Y%m%d")

		return date_object.date()

	@staticmethod
	def strp_time_object(time_str):
		time_object = datetime.strptime(time_str, "%H%M%S")

		return time_object.time()

	@staticmethod
	def get_item_barcode(item_code, uom):
		item_barcodes = frappe.db.get_all(
			"Item Barcode", filters={"parent": item_code, "uom": uom}, fields=["barcode"]
		)

		if item_barcodes:
			return item_barcodes[0].get("barcode")

	@staticmethod
	def log_errors(title, description):
		"""Log errors using frappe.log_error (transaction-safe).

		frappe.log_error writes to the Error Log doctype which is committed
		independently of the current transaction — safe to call inside
		before_submit and other hooks. The old frappe.new_doc('Error Logging').insert()
		pattern is unsafe inside transactions.
		"""
		try:
			frappe.log_error(title=str(title)[:140], message=str(description))
		except Exception:
			pass  # Never let logging break the main operation

	@staticmethod
	def handle_api_response(response_json):
		"""Handle API response with proper error code mapping"""
		result_cd = response_json.get("resultCd")
		result_msg = response_json.get("resultMsg", "Unknown error")

		if result_cd == "000":
			return {"Success": response_json.get("data")}
		elif result_cd == "400":
			error_msg = f"Bad Request: {result_msg}"
			eTIMS.log_errors("API Error (400)", error_msg)
			return {"Error": error_msg}
		elif result_cd == "401":
			error_msg = f"Unauthorized: {result_msg}"
			eTIMS.log_errors("API Error (401)", error_msg)
			return {"Error": error_msg}
		elif result_cd == "500":
			error_msg = f"Server Error: {result_msg}"
			eTIMS.log_errors("API Error (500)", error_msg)
			return {"Error": error_msg}
		else:
			return {"Error": f"Error {result_cd}: {result_msg}"}

	@staticmethod
	def get_etims_sar_no(doc):
		etims_sar_no = 1
		try:
			etims_sar_docs = frappe.get_last_doc(
				"eTIMS Stock Release Number", filters={"tax_branch_office": doc.custom_tax_branch_office}
			)

			new_sar_no = etims_sar_docs.get("sr_number") + 1

			new_doc = frappe.new_doc("eTIMS Stock Release Number")
			new_doc.reference_type = doc.doctype
			new_doc.reference = doc.name
			new_doc.tax_branch_office = doc.custom_tax_branch_office
			new_doc.sr_number = new_sar_no
			new_doc.orginal_sr_number = eTIMS.get_org_etims_sar_no(doc)
			new_doc.insert()

			return new_sar_no
		except (frappe.DoesNotExistError, frappe.ValidationError) as e:
			frappe.log_error(title="eTIMS: SAR number generation failed", message=str(e))
			new_doc = frappe.new_doc("eTIMS Stock Release Number")
			new_doc.reference_type = doc.doctype
			new_doc.reference = doc.name
			new_doc.tax_branch_office = doc.custom_tax_branch_office
			new_doc.sr_number = etims_sar_no
			new_doc.orginal_sr_number = eTIMS.get_org_etims_sar_no(doc)

			new_doc.insert()

			return etims_sar_no

	@staticmethod
	def get_org_etims_sar_no(doc):
		org_etims_sar_no = 0

		if doc.custom_original_invoice_number:
			prev_doc = frappe.db.get_all(
				"eTIMS Stock Release Number", filters={"reference": doc.return_against}, fields=["sr_number"]
			)

			org_etims_sar_no = prev_doc[0].get("sr_number")

			return org_etims_sar_no
		else:
			return org_etims_sar_no

	# def get_last_inv_number(doc, last_set_no, last_no):
	#     branch_id = eTIMS.get_user_branch_id()
	#     cur_number = 0
	#     last_inv_no = 0
	#     # no_list = []
	#     settings_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id}, fields=["*"])
	#     # invs_nos = frappe.db.get_all(doc.doctype,
	#     #                                 filters = {'name': ['!=', doc.name], "custom_tax_branch_office": branch_id},
	#     #                                 fields=[last_no]
	#     #                             )
	#     # for inv_no in invs_nos:
	#     #     if not inv_no.get(last_no) in no_list:
	#     #         no_list.append(inv_no.get(last_no))

	#     if settings_docs:
	#         # last_inv_no = settings_docs[0].get("last_sales_invoice_number")

	#         last_inv_no = settings_docs[0].get(last_set_no)

	#     try:
	#         last_inv = frappe.db.get_all(doc.doctype,
	#                                         filters = {'name': ['!=', doc.name], "custom_tax_branch_office": branch_id},
	#                                         fields=[last_no],
	#                                         order_by='{} desc'.format(last_no),
	#                                         page_length = 1
	#                                     )

	#         if last_inv[0]:
	#             # print(last_inv)
	#             last_inv_no = last_inv[0].get(last_no)

	#         cur_number = last_inv_no + 1

	#     except Exception as e:
	#         cur_number = last_inv_no + 1

	#     return cur_number

	# def get_last_sr_number():
	#     etims_sar_no = 0
	#     branch_id = eTIMS.get_user_branch_id()
	#     settings_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id}, fields=["last_stock_release_number"])

	#     if settings_docs:
	#         etims_sar_no = settings_docs[0].get("last_stock_release_number")

	#     try:
	#         etims_sar_docs = frappe.get_last_doc("eTIMS Stock Release Number", filters={"tax_branch_office": branch_id})

	#         etims_sar_no = etims_sar_docs.get("sr_number") + 1

	#     except Exception as e:
	#         etims_sar_no += 1

	#     return etims_sar_no

	@staticmethod
	def get_user_branch_id():
		current_user = frappe.session.user

		tax_branch_perms = frappe.db.get_all(
			"User Permission",
			filters={"user": current_user, "allow": "Tax Branch Office", "is_default": 1},
			fields=["for_value"],
		)

		if tax_branch_perms:
			return tax_branch_perms[0].get("for_value")

		# Fallback for single-branch setups: use the only active TIS Device
		devices = frappe.db.get_all(
			"TIS Device Initialization", filters={"active": 1}, fields=["branch_id"], limit=2
		)
		if len(devices) == 1:
			return devices[0].get("branch_id")
		return None

	@staticmethod
	def itemSaveReq(doc_name):
		item = frappe.get_doc("Item", doc_name)

		if not item.get("custom_item_classification_code"):
			frappe.throw(_("Missing Item Classification Code!"))

		# Resolve origin place code if needed
		origin_code = item.get("custom_origin_place_code_nation")
		if not origin_code and item.get("custom_country_of_origin"):
			from kenya_etims_compliance.custom_methods.item import get_country_code

			origin_code = get_country_code(item.get("custom_country_of_origin"))

		# Auto-fill identity fields from item.owner / modified_by when blank,
		# and item name fields from item_code / item_name as a sensible default
		regr_id = item.get("custom_registration_id") or item.owner
		regr_nm = item.get("custom_registration_name") or item.owner
		modr_id = item.get("custom_modifier_id") or item.modified_by
		modr_nm = item.get("custom_modifier_name") or item.modified_by
		item_nm = item.get("custom_item_name") or item.item_code
		item_std_nm = item.get("custom_item_standard_name") or item.item_name or item.item_code
		item_cls_nm = item.get("custom_item_classification_name") or item.get("custom_item_classification_code")
		# Valid KRA Item Type codes: 1=Raw Material, 2=Finished Product, 3=Service
		_raw_ty = item.get("custom_item_type_code")
		item_ty_cd = _raw_ty if _raw_ty in ("1", "2", "3") else "2"

		payload = {
			"itemCd": item.get("custom_item_code"),
			"itemClsCd": item.get("custom_item_classification_code"),
			"itemClsNm": item_cls_nm,
			"itemTyCd": item_ty_cd,
			"itemNm": item_nm,
			"itemStdNm": item_std_nm,
			"orgnNatCd": origin_code,
			"pkgUnitCd": item.get("custom_packaging_unit_code"),
			"qtyUnitCd": item.get("custom_quantity_unit_code"),
			"taxTyCd": item.get("custom_taxation_type_code"),
			"btchNo": item.get("custom_batch_number") or "",
			"bcd": item.get("custom_barcode") or "",
			"dftPrc": item.get("custom_default_unit_price") or 0,
			"grpPrcL1": item.get("custom_group1_unit_price") or 0,
			"grpPrcL2": item.get("custom_group2_unit_price") or 0,
			"grpPrcL3": item.get("custom_group3_unit_price") or 0,
			"grpPrcL4": item.get("custom_group4_unit_price") or 0,
			"grpPrcL5": item.get("custom_group5_unit_price") or 0,
			"addInfo": item.get("custom_additional_information") or "",
			"sftyQty": item.get("custom_safety_quantity") or 0,
			"isrcAplcbYn": item.get("custom_insurance_appicableyn") or "N",
			"useYn": item.get("custom_used__unused") or "Y",
			"regrId": regr_id,
			"regrNm": regr_nm,
			"modrId": modr_id,
			"modrNm": modr_nm,
		}

		# Pre-flight validation — name the missing fields BEFORE sending to KRA
		required_labels = {
			"itemCd": "Item Code (custom_item_code)",
			"itemClsCd": "Item Classification Code (custom_item_classification_code)",
			"itemTyCd": "Item Type Code (custom_item_type_code)",
			"itemNm": "Item Name (custom_item_name / item_code)",
			"orgnNatCd": "Origin Nation Code (set Country of Origin)",
			"pkgUnitCd": "Packaging Unit Code (set Default Packing Unit)",
			"qtyUnitCd": "Quantity Unit Code (set Default Quantity Unit)",
			"taxTyCd": "Taxation Type Code (set tax template)",
			"regrId": "Registration ID (item.owner)",
			"regrNm": "Registration Name",
			"modrId": "Modifier ID (item.modified_by)",
			"modrNm": "Modifier Name",
		}
		missing = [label for key, label in required_labels.items() if not payload.get(key)]
		if missing:
			frappe.throw(
				_("Cannot register item — the following fields are empty:<br>{0}").format(
					"<br>".join(f"• {m}" for m in missing)
				)
			)

		client = KRAClient()
		result = client.save_item(payload)

		if "Success" in result:
			item.custom_registered_in_tims = 1
			item.save()
			return {"Success": "Item registered successfully"}

		# On error, log the payload so the failing code field can be identified
		import json as _json
		frappe.log_error(
			title=f"eTIMS saveItem failed for {doc_name}"[:140],
			message=f"Error: {result.get('Error')}\n\nPayload sent to KRA:\n{_json.dumps(payload, indent=2, default=str)}",
		)
		return result

	@staticmethod
	def map_new_item(item):
		item_exists = check_if_item_exits(item.get("itemNm"))

		if not item_exists:
			# create item if not exists
			create_new_item_doctype(item)

		else:
			pass

	@staticmethod
	def get_name_of_user(user):
		user_full_name = frappe.db.get_value("User", user, "full_name")

		return user_full_name

	# Search Endpoints - Phase 1.2

	@staticmethod
	def searchItem(item_code=None, item_name=None, last_req_dt=None):
		"""Search items in eTIMS (Section 7.13)"""
		payload = {}
		if item_code:
			payload["itemCd"] = item_code
		if item_name:
			payload["itemNm"] = item_name
		if last_req_dt:
			payload["lastReqDt"] = eTIMS.strf_datetime_format(last_req_dt)

		client = KRAClient()
		return client.search_item(payload)

	@staticmethod
	def searchStockMove(sar_no=None, last_req_dt=None):
		"""Search stock movements in eTIMS (Section 7.15)"""
		payload = {}
		if sar_no:
			payload["sarNo"] = sar_no
		if last_req_dt:
			payload["lastReqDt"] = eTIMS.strf_datetime_format(last_req_dt)

		client = KRAClient()
		return client.search_stock_move(payload)

	@staticmethod
	def searchTrns(invoice_no=None, last_req_dt=None, trns_type=None):
		"""Search transactions in eTIMS (Section 7.14/7.20).

		KRA only provides LIST endpoints (date-range) — there is no per-invoice
		lookup. We fetch the list and filter for invoice_no client-side.

		trns_type: 'sales' or 'purchase'
		"""
		if trns_type == "sales":
			endpoint = "selectTrnsSalesList"
		elif trns_type == "purchase":
			endpoint = "selectTrnsPurchaseList"
		else:
			return {"Error": "Invalid transaction type. Use 'sales' or 'purchase'"}

		# KRA requires lastReqDt. Default to last 30 days — querying further back
		# can return thousands of transactions and time out.
		from frappe.utils import add_days, now_datetime
		if last_req_dt:
			default_dt = eTIMS.strf_datetime_format(last_req_dt)
		else:
			default_dt = add_days(now_datetime(), -30).strftime("%Y%m%d%H%M%S")
		payload = {"lastReqDt": default_dt}

		client = KRAClient()
		result = client.search_trns(endpoint, payload)

		# If the user asked for a specific invoice, filter the list down to it
		if invoice_no and "Success" in result:
			data = result.get("Success") or {}
			list_key = "salesList" if trns_type == "sales" else "purchaseList"
			items = data.get(list_key) or data.get("saleList") or []
			match = [it for it in items if str(it.get("invcNo")) == str(invoice_no)]
			if not match:
				return {"Error": f"No {trns_type} transaction found for invoice {invoice_no}"}
			return {"Success": match[0] if len(match) == 1 else match}

		return result

	# Stock Release Number Management - Phase 2.1

	@staticmethod
	def stockReleaseNoSaveReq(sar_no, org_sar_no=0, sar_type=None):
		"""Save stock release number to eTIMS (Section 7.16)

		Args:
		    sar_no: Stock release number
		    org_sar_no: Original stock release number (default: 0)
		    sar_type: SAR type code (default: from settings, typically '11')
		"""
		client = KRAClient()

		if sar_type is None:
			sar_type = client.settings.get("default_sar_type_sales", "11")

		payload = {"sarNo": sar_no, "orgSarNo": org_sar_no, "sarTyCd": sar_type}

		return client.stock_release_no_save(payload)

	@staticmethod
	def searchStockReleaseNo(sar_no=None, last_req_dt=None):
		"""Search stock release numbers in eTIMS (Section 7.17)"""
		payload = {}
		if sar_no:
			payload["sarNo"] = sar_no
		if last_req_dt:
			payload["lastReqDt"] = eTIMS.strf_datetime_format(last_req_dt)

		client = KRAClient()
		return client.search_stock_release_no(payload)

	@staticmethod
	def selectStockReleaseNoList(last_req_dt=None):
		"""Get stock release number list from eTIMS (Section 7.18)"""
		payload = {}
		if last_req_dt:
			payload["lastReqDt"] = eTIMS.strf_datetime_format(last_req_dt)

		client = KRAClient()
		return client.select_stock_release_no_list(payload)

	# Detail Query Endpoints - Phase 3.1

	@staticmethod
	def selectItem(item_code):
		"""Get item details from eTIMS (Section 7.9)"""
		client = KRAClient()
		return client.select_item({"itemCd": item_code})

	@staticmethod
	def selectTrnsSalesInfo(invoice_no):
		"""Get sales transaction details from eTIMS (Section 7.21)"""
		client = KRAClient()
		return client.select_trns_sales_info({"invcNo": invoice_no})

	@staticmethod
	def selectTrnsPurchaseInfo(invoice_no):
		"""Get purchase transaction details from eTIMS (Section 7.21)"""
		client = KRAClient()
		return client.select_trns_purchase_info({"invcNo": invoice_no})

	# Medium Priority Features - Phase 4

	@staticmethod
	def selectNoticeInfo(notice_no):
		"""Get notice details from eTIMS (Section 7.23)"""
		client = KRAClient()
		return client.select_notice_info({"ntcNo": notice_no})

	@staticmethod
	def selectOrgUsrInfo():
		"""Get organization/user info from eTIMS (Section 7.5)"""
		client = KRAClient()
		return client.select_org_usr_info()

	# Invoice Verification - Phase 1: Invoice Checker API Integration

	@staticmethod
	def invoiceCheckerReq(invoice_no, supplier_pin, invoice_date, total_amount, cu_invoice_no=None):
		"""Check invoice validity via KRA Invoice Checker API.

		Matches on EITHER trader invoice no OR CU invoice no (supplier CU ID + sequence)
		— whichever is provided. If both match, that's a strong verification.

		Args:
		    invoice_no: Supplier trader invoice number (e.g., 'INV-2026-473')
		    supplier_pin: Supplier Tax PIN
		    invoice_date: Invoice date (YYYY-MM-DD or datetime object)
		    total_amount: Total invoice amount (float/decimal)
		    cu_invoice_no: Optional 'KRACU.../<seq>' from supplier receipt

		Returns:
		    {"Success": {... + _matched_by: 'trader_inv'|'cu_inv'|'both'}} or {"Error": "..."}
		"""
		from frappe.utils import add_days, getdate
		try:
			anchor = getdate(invoice_date)
			lookback_dt = add_days(anchor, -90).strftime("%Y%m%d000000")
		except Exception:
			lookback_dt = "20260101000000"

		client = KRAClient()
		list_result = client.post("selectTrnsPurchaseSalesList", {"lastReqDt": lookback_dt})

		if list_result.get("Error"):
			return list_result
		if list_result.get("Empty"):
			return {"Error": f"KRA returned no purchases since {lookback_dt[:8]}. Invoice not found."}

		data = list_result.get("Success") or {}
		records = data.get("saleList") or data.get("purchaseList") or []

		# Parse CU invoice no — two possible formats:
		#   eTIMS:        '<CU_ID>/<sequence>'  e.g. 'KRACU0400003494/5'  → match spplrSdcId + sdcRcptNo
		#   TIMS device:  '<long_numeric>'      e.g. '0091665530000157477' → match as-is against receipt no
		cu_id, cu_seq, cu_raw = None, None, None
		if cu_invoice_no:
			cu_raw = str(cu_invoice_no).strip()
			if "/" in cu_raw:
				parts = cu_raw.split("/", 1)
				cu_id = parts[0].strip().upper()
				cu_seq = parts[1].strip()

		invoice_no_str = str(invoice_no or "").strip()
		pin_str = str(supplier_pin or "").strip().upper()

		def _trader_match(r):
			if not invoice_no_str:
				return False
			if str(r.get("spplrInvcNo") or "").strip() != invoice_no_str:
				return False
			return not pin_str or str(r.get("spplrTin") or "").strip().upper() == pin_str

		def _cu_match(r):
			# eTIMS format: needs both CU_ID and sequence to match
			if cu_id and cu_seq:
				r_cu_id = str(r.get("spplrSdcId") or r.get("bcncSdcId") or "").strip().upper()
				r_cu_seq = str(r.get("sdcRcptNo") or r.get("totSdcRcptNo") or "").strip()
				if r_cu_id == cu_id and r_cu_seq == cu_seq:
					return True
			# TIMS device format: long numeric — try every receipt-like field
			if cu_raw and "/" not in cu_raw:
				candidates = [
					str(r.get("sdcRcptNo") or "").strip(),
					str(r.get("totSdcRcptNo") or "").strip(),
					str(r.get("spplrInvcNo") or "").strip(),
					str(r.get("rcptNo") or "").strip(),
					str(r.get("intrlData") or "").strip(),
				]
				if cu_raw in candidates:
					return True
			return False

		matches = []
		for r in records:
			t, c = _trader_match(r), _cu_match(r)
			if t or c:
				r["_matched_by"] = "both" if t and c else ("trader_inv" if t else "cu_inv")
				matches.append(r)

		if not matches:
			id_parts = []
			if invoice_no_str:
				id_parts.append(f"trader invoice {invoice_no_str}")
			if cu_id:
				id_parts.append(f"CU invoice {cu_id}/{cu_seq}")
			id_str = " or ".join(id_parts) if id_parts else "any identifier"
			return {
				"Error": f"Invoice not found in KRA's records since {lookback_dt[:8]} "
				f"(searched by {id_str}, supplier {pin_str or '-'}). "
				f"The supplier may not have submitted this invoice to eTIMS yet."
			}

		match = matches[0]

		# Variance check on total amount
		try:
			kra_total = float(match.get("totAmt") or 0)
			our_total = float(total_amount or 0)
			variance = abs(kra_total - our_total)
			if variance > 0.01:
				match["_variance"] = variance
				match["_our_amount"] = our_total
				match["_kra_amount"] = kra_total
		except (TypeError, ValueError):
			pass

		return {"Success": match}


def check_if_item_exits(item_code):
	item_exists = frappe.db.exists("Item", {"item_code": item_code})

	if item_exists:
		return True
	else:
		return False


def get_tax_template_details(item_code):
	"""Return the eTIMS tax code for an item, falling back to 'D' (exempt)."""
	tax_rows = frappe.db.get_all(
		"Item Tax",
		filters={"parent": item_code},
		fields=["item_tax_template"],
	)
	for row in tax_rows:
		template = row.get("item_tax_template")
		if not template:
			continue
		code = frappe.db.get_value("Item Tax Template", template, "custom_code")
		if code:
			return code
	return "D"


def create_new_item_doctype(item):
	current_user = frappe.session.user

	pkgUnitNm, qtyUnitNm = get_packing_and_quantity_unit(item.get("pkgUnitCd"), item.get("qtyUnitCd"))
	nat_of_origin = get_country_of_origin(item.get("itemCd"))

	new_item_doc = frappe.new_doc("Item")
	new_item_doc.item_code = item.get("itemNm")
	new_item_doc.custom_item_name = item.get("itemNm")
	new_item_doc.item_group = get_item_type(item.get("itemCd"))
	new_item_doc.stock_uom = "Nos"
	new_item_doc.valuation_rate = item.get("prc")
	new_item_doc.custom_country_of_origin = nat_of_origin
	new_item_doc.custom_item_classification_code = item.get("itemClsCd")
	new_item_doc.custom_packaging_unit_code = item.get("pkgUnitCd")
	new_item_doc.custom_quantity_unit_code = item.get("qtyUnitCd")
	new_item_doc.custom_default_packing_unit = pkgUnitNm
	new_item_doc.custom_default_quantity_unit = qtyUnitNm
	new_item_doc.custom_default_unit_price = item.get("prc")
	new_item_doc.custom_used__unused = "Y"
	new_item_doc.custom_taxation_type_code = item.get("taxTyCd")
	new_item_doc.custom_registration_id = current_user

	new_item_doc.custom_modifier_id = current_user

	if item.get("taxTyCd"):
		tax_template = get_item_tax_template(item.get("taxTyCd"))
		new_item_doc.append("taxes", {"item_tax_template": tax_template})

	new_item_doc.custom_update_item_to_tims = 1
	new_item_doc.insert()

	eTIMS.itemSaveReq(new_item_doc.name)


def get_packing_and_quantity_unit(pkgUnitCd, qtyUnitCd):
	packing_unit_name = "Non-Exterior Packaging Unit"
	quantity_unit_name = "Gross"

	packing_unit = frappe.db.get_all(
		"eTIMS Packing Unit", filters={"etims_code": pkgUnitCd}, fields=["etims_code_name"]
	)
	quantity_unit = frappe.db.get_all(
		"eTIMS Quantity Unit", filters={"etims_code": qtyUnitCd}, fields=["etims_code_name"]
	)

	if packing_unit:
		packing_unit_name = packing_unit[0].get("etims_code_name")

	if quantity_unit:
		quantity_unit_name = quantity_unit[0].get("etims_code_name")

	return packing_unit_name, quantity_unit_name


def get_country_of_origin(item_code):
	nat_code = item_code[:2]

	try:
		etims_country_list = frappe.db.get_all(
			"eTIMS Country", filters={"code_name": nat_code}, fields=["country_name", "code_name"]
		)

		if etims_country_list:
			country_name = etims_country_list[0].get("country_name")

			return country_name
	except frappe.ValidationError as e:
		frappe.log_error(title="eTIMS: Country lookup failed", message=str(e))

	return "Kenya"


def get_item_type(item_code):
	item_type_code = item_code[2:3]

	item_group = "All Item Groups"

	if item_type_code == "1":
		item_group = "Raw Material"
	elif item_type_code == "2":
		item_group = "Products"
	elif item_type_code == "3":
		item_group = "Services"

	return item_group


def get_item_tax_template(tax_type_code):
	item_tax_doc = frappe.db.get_all(
		"Item Tax Template", filters={"custom_code": tax_type_code}, fields=["name"]
	)

	if item_tax_doc:
		return item_tax_doc[0].get("name")


def get_next_sar_number(doc, branch_id):
	"""Get next SAR number with database locking to prevent duplicates.

	Uses SELECT ... FOR UPDATE to lock rows. MUST be called BEFORE the
	KRA API call (during payload construction) to minimize lock hold time.
	Lock is released when the enclosing transaction commits.
	"""
	last_sar = frappe.db.sql(
		"""
        SELECT sr_number FROM `tabeTIMS Stock Release Number`
        WHERE tax_branch_office = %s
        ORDER BY sr_number DESC
        LIMIT 1
        FOR UPDATE
    """,
		(branch_id,),
		as_dict=True,
	)

	next_number = (last_sar[0].sr_number + 1) if last_sar else 1

	new_doc = frappe.new_doc("eTIMS Stock Release Number")
	new_doc.reference_type = doc.doctype
	new_doc.reference = doc.name
	new_doc.tax_branch_office = branch_id
	new_doc.sr_number = next_number
	new_doc.orginal_sr_number = get_org_sar_number(doc)
	new_doc.insert()

	return next_number


def get_org_sar_number(doc):
	"""Get original SAR number for returns/amendments."""
	if not doc.get("custom_original_invoice_number"):
		return 0

	prev = frappe.db.get_all(
		"eTIMS Stock Release Number",
		filters={"reference": doc.return_against},
		fields=["sr_number"],
		page_length=1,
	)
	return prev[0].sr_number if prev else 0


def apply_tax_bands(payload, taxes, rate_func):
	"""Aggregate KRA tax bands A-E into ``payload`` from a document's tax rows.

	Single source of truth for the band breakdown (previously duplicated across
	the sales/purchase submit paths). Key correctness rules:
	  * taxblAmt/taxAmt are SUMMED per band (a document may legitimately have
	    more than one tax row mapping to the same KRA code) — never overwritten.
	  * Every value is null-guarded so a missing field cannot raise.
	  * taxAmt uses ``base_tax_amount_after_discount_amount`` (company/KES amount,
	    which is what KRA expects).
	  * taxRt is the band's % rate (same for every row of a band) so it is set.

	``rate_func(account_head)`` returns the account's tax rate.
	"""
	for code in ("A", "B", "C", "D", "E"):
		payload[f"taxblAmt{code}"] = 0
		payload[f"taxRt{code}"] = 0
		payload[f"taxAmt{code}"] = 0

	for tax in (taxes or []):
		code = tax.get("custom_code")
		if code in ("A", "B", "C", "D", "E"):
			payload[f"taxblAmt{code}"] += abs(round(tax.get("custom_total_taxable_amount") or 0, 2))
			payload[f"taxAmt{code}"] += abs(tax.get("base_tax_amount_after_discount_amount") or 0)
			payload[f"taxRt{code}"] = abs(rate_func(tax.get("account_head")) or 0)

	return payload
