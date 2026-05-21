import traceback  # pyqrcode
from datetime import datetime, time, timedelta

import frappe
import requests
import segno
from frappe import _

from kenya_etims_compliance.custom_methods.queue_processor import enqueue_invoice
from kenya_etims_compliance.custom_methods.receipt_labels import get_receipt_label
from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
	get_etims_settings,
)
from kenya_etims_compliance.utils.etims_utils import eTIMS, get_next_sar_number, get_org_sar_number
from kenya_etims_compliance.utils.kra_client import KRAClient


@frappe.whitelist()
def searchSalesTrnsReq(invoice_no=None, last_req_dt=None):
	"""Search sales transactions in eTIMS"""
	response = eTIMS.searchTrns(invoice_no, last_req_dt, "sales")

	for key, value in response.items():
		if key == "Success":
			return {"Success": value}
		else:
			return {"Error": value}


@frappe.whitelist()
def selectSalesTrnsInfoReq(invoice_no):
	"""Get sales transaction details from eTIMS"""
	response = eTIMS.selectTrnsSalesInfo(invoice_no)

	for key, value in response.items():
		if key == "Success":
			return {"Success": value}
		else:
			return {"Error": value}


def show_etims_queued_message(doc, method):
	"""on_submit hook — show the "queued" msgprint only if submit actually succeeded.

	Runs after ERPNext's submit logic (incl. GL posting and fiscal year check).
	If anything in the submit chain failed earlier, this hook never runs and
	the misleading "queued" message is never shown.
	"""
	if frappe.flags.get("_etims_show_queued_msg"):
		frappe.msgprint(_("Sales invoice queued for eTIMS submission"), indicator="blue")
		frappe.flags._etims_show_queued_msg = False


def validate(doc, method):
	"""
	Method validate invoice number before submitting invoice
	"""
	# Auto-enable eTIMS signing from POS Profile (server-side fallback)
	if doc.pos_profile and not doc.custom_update_invoice_in_tims:
		enable_etims = frappe.db.get_value("POS Profile", doc.pos_profile, "custom_enable_etims_signing")
		if enable_etims:
			doc.custom_update_invoice_in_tims = 1

	if doc.custom_invoice_number and doc.name:
		doc_exists = frappe.db.exists("Sales Invoice", {"name": doc.name})

		if doc_exists:
			if doc.custom_update_invoice_in_tims:
				invoice_numbers = validate_inv_number(doc)

				if doc.custom_invoice_number in invoice_numbers:
					insert_invoice_number(doc, method)


def insert_invoice_number(doc, method):
	"""
	Method sets increment for invoice number and orginal invoice number before submitting invoice
	"""
	if not doc.items:
		frappe.throw(_("Sales Invoice must have at least one item to submit to eTIMS"))

	scu = ""
	sales_warehouse = ""
	item_count = 0
	if doc.name and doc.custom_update_invoice_in_tims:
		branch_id = eTIMS.get_user_branch_id()
		init_docs = frappe.db.get_all(
			"TIS Device Initialization",
			filters={"branch_id": branch_id},
			fields=["sales_control_unit_id", "default_sales_warehouse"],
		)

		if init_docs:
			scu = init_docs[0].get("sales_control_unit_id")
			sales_warehouse = init_docs[0].get("default_sales_warehouse")

		if doc.items:
			item_count = len(doc.items)
			insert_tax_amounts(doc)

		total_discount_amount = get_total_discount(doc)

		total_vat_amount = fetch_total_vat(doc)
		total_non_vat_amount = fetch_total_non_vat(doc)

		last_inv_number = get_last_inv_number(doc, branch_id)

		frappe.db.set_value(
			"Sales Invoice",
			doc.name,
			{
				"custom_invoice_number": last_inv_number,
				"custom_sales_control_unit": scu,
				"update_stock": 1,
				"set_warehouse": sales_warehouse,
				"custom_tax_branch_office": branch_id,
				"custom_total_taxable_amount": total_vat_amount,
				"custom_total_nontaxable_amount": total_non_vat_amount,
				"custom_item_count": item_count,
				"custom_total_discount_amount": total_discount_amount,
				"custom_total_before_discount": total_discount_amount + doc.base_grand_total,
			},
			update_modified=False,
		)

		# Sync in-memory doc fields to match what was written to DB
		doc.custom_invoice_number = last_inv_number
		doc.custom_sales_control_unit = scu
		doc.update_stock = 1
		doc.set_warehouse = sales_warehouse
		doc.custom_tax_branch_office = branch_id
		doc.custom_total_taxable_amount = total_vat_amount
		doc.custom_total_nontaxable_amount = total_non_vat_amount
		doc.custom_item_count = item_count
		doc.custom_total_discount_amount = total_discount_amount
		doc.custom_total_before_discount = total_discount_amount + doc.base_grand_total


def insert_tax_amounts(doc):
	if doc.items:
		taxable_amounts = get_taxable_amounts(doc)
		for key, value in taxable_amounts.items():
			try:
				if doc.taxes:
					for item in doc.taxes:
						if item.get("custom_code") == key:
							tax_templates = frappe.db.get_all(
								"Item Tax Template", filters={"custom_code": key}, fields=["custom_code_name"]
							)

							if len(tax_templates):
								frappe.db.set_value(
									"Sales Taxes and Charges",
									item.get("name"),
									{
										"custom_total_taxable_amount": round(value, 2),
										"custom_code_name": tax_templates[0].get("custom_code_name"),
									},
									update_modified=False,
								)
								# Sync in-memory child row to match DB write
								item.custom_total_taxable_amount = round(value, 2)
								item.custom_code_name = tax_templates[0].get("custom_code_name")
			except (frappe.DoesNotExistError, frappe.DataError) as e:
				frappe.throw(_("Error calculating tax amounts: {0}").format(str(e)))


def get_total_discount(doc):
	discount_amount = 0

	if doc.items:
		for item in doc.items:
			if item.get("discount_percentage") > 0:
				total_dsc = item.get("custom_discount_amount_kes") * item.get("qty")
				discount_amount += total_dsc

	return discount_amount


def get_taxable_amounts(doc):
	taxable_amounts_dict = {}

	try:
		if doc.items:
			for item in doc.items:
				if item.get("custom_tax_code") not in taxable_amounts_dict.keys():
					taxable_amounts_dict[item.get("custom_tax_code")] = 0

				taxable_amounts_dict[item.get("custom_tax_code")] += item.base_net_amount
	except Exception as e:
		frappe.throw(_("Error getting taxable amounts: {0}").format(str(e)))

	return taxable_amounts_dict


def fetch_total_vat(doc):
	taxable_amount = 0
	if doc.taxes:
		for item in doc.taxes:
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


def trnsSalesSaveWrReq(doc, method):
	"""
	Method that collects sales information and updates it to tims server.
	Called during before_submit — assigns invoice number first, then sends to eTIMS.
	"""
	if doc.custom_update_invoice_in_tims:
		tax_code_list = []

		request_date_and_time = doc.modified

		conc_datetime_str = eTIMS.strf_datetime_format(request_date_and_time)

		now = datetime.now()
		date_time_str = now.strftime("%Y%m%d%H%M%S")

		request_date = doc.posting_date
		date_str = eTIMS.strf_date_object(request_date)

		count = doc.custom_item_count or len(doc.items) or 0
		if count < 1:
			frappe.throw(_("Sales Invoice must have at least one item to submit to eTIMS"))

		payload = {
			"trdInvcNo": doc.name,
			"invcNo": doc.custom_invoice_number,
			"orgInvcNo": doc.custom_original_invoice_number,
			"custTin": doc.tax_id,
			"custNm": doc.customer,
			"salesTyCd": doc.custom_sales_type_code,
			"rcptTyCd": doc.custom_receipt_type_code,
			"pmtTyCd": doc.custom_payment_type_code,
			"salesSttsCd": doc.custom_invoice_status_code,
			"cfmDt": conc_datetime_str,
			"salesDt": date_str,
			"stockRlsDt": date_time_str,
			"totItemCnt": count,
			"totTaxblAmt": abs(doc.custom_total_taxable_amount),
			"totTaxAmt": abs(doc.base_total_taxes_and_charges),
			"totAmt": abs(doc.base_grand_total),
			"prchrAcptcYn": "N",
			"remark": doc.remarks,
			"regrId": (doc.owner or "")[:20],
			"regrNm": (doc.owner or "")[:20],
			"modrId": (doc.modified_by or "")[:20],
			"modrNm": (doc.modified_by or "")[:20],
			"receipt": {
				"custTin": doc.tax_id,
				# "custMblNo":null,
				"rcptPbctDt": date_time_str,
				# "trdeNm":null,
				# "adrs":null,
				# "topMsg":null,
				# "btmMsg":null,
				"prchrAcptcYn": "N",
			},
			"itemList": etims_sale_item_list_sales(doc),
		}

		for tax_item in doc.taxes:
			if tax_item.get("custom_code") not in tax_code_list:
				tax_code_list.append(tax_item.get("custom_code"))

			if "A" in tax_code_list:
				if tax_item.custom_code == "A":
					payload["taxblAmtA"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
					payload["taxRtA"] = abs(get_tax_account_rate(tax_item.get("account_head")))
					payload["taxAmtA"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
			else:
				payload["taxblAmtA"] = 0
				payload["taxRtA"] = 0
				payload["taxAmtA"] = 0

			if "B" in tax_code_list:
				if tax_item.custom_code == "B":
					payload["taxblAmtB"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
					payload["taxRtB"] = abs(get_tax_account_rate(tax_item.get("account_head")))
					payload["taxAmtB"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
			else:
				payload["taxblAmtB"] = 0
				payload["taxRtB"] = 0
				payload["taxAmtB"] = 0

			if "C" in tax_code_list:
				if tax_item.custom_code == "C":
					payload["taxblAmtC"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
					payload["taxRtC"] = abs(get_tax_account_rate(tax_item.get("account_head")))
					payload["taxAmtC"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
			else:
				payload["taxblAmtC"] = 0
				payload["taxRtC"] = 0
				payload["taxAmtC"] = 0

			if "D" in tax_code_list:
				if tax_item.custom_code == "D":
					payload["taxblAmtD"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
					payload["taxRtD"] = abs(get_tax_account_rate(tax_item.get("account_head")))
					payload["taxAmtD"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
			else:
				payload["taxblAmtD"] = 0
				payload["taxRtD"] = 0
				payload["taxAmtD"] = 0

			if "E" in tax_code_list:
				if tax_item.custom_code == "E":
					payload["taxblAmtE"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
					payload["taxRtE"] = abs(get_tax_account_rate(tax_item.get("account_head")))
					payload["taxAmtE"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
			else:
				payload["taxblAmtE"] = 0
				payload["taxRtE"] = 0
				payload["taxAmtE"] = 0

		if doc.is_return == 1:
			return_status = sales_return_information(doc)

			if return_status == "partial":
				payload["rfdDt"] = date_time_str
				payload["rfdRsnCd"] = doc.custom_credit_note_reason_code
			elif return_status == "full":
				payload["cnclReqDt"] = conc_datetime_str
				payload["cnclDt"] = conc_datetime_str
				payload["rfdDt"] = date_time_str
				payload["rfdRsnCd"] = doc.custom_credit_note_reason_code
			elif return_status == "null":
				frappe.throw(_("Invalid, return amount is greater than original amount!"))

	if doc.custom_update_invoice_in_tims:
		settings = get_etims_settings()

		# Training mode (Spec 4.1.3): set receipt type to "T"
		if settings.get("training_mode"):
			payload["rcptTyCd"] = "T"

		# Set receipt label (Spec 4.3)
		receipt_label = get_receipt_label(doc)
		frappe.db.set_value(
			"Sales Invoice", doc.name, "custom_receipt_label", receipt_label, update_modified=False
		)

		if settings.get("enable_queue", 1):
			branch_id = None
			try:
				branch_id = KRAClient()._get_user_branch_id()
			except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
				frappe.log_error("eTIMS: Failed to get branch ID", str(e))

			enqueue_invoice(
				doc=doc,
				payload=payload,
				api_endpoint="save_sales",
				branch_id=branch_id,
			)
			# Defer the msgprint until after the submit transaction commits.
			# If submit later fails (e.g., fiscal year missing), the queue insert
			# rolls back and this message must NOT appear.
			frappe.flags._etims_show_queued_msg = True
		else:
			# Synchronous fallback (original behavior)
			try:
				client = KRAClient()
				result = client.save_sales(payload)

				if "Error" in result:
					frappe.throw(result["Error"])

				data = result["Success"]
				control_unit_date_time = eTIMS.strp_datetime_object(data.get("sdcDateTime"))
				control_unit_date = eTIMS.strp_date_object(data.get("sdcDateTime")[0:8])
				control_unit_time = eTIMS.strp_time_object(data.get("sdcDateTime")[8:14])

				doc.custom_current_receipt_number = data.get("curRcptNo")
				doc.custom_total_receipt_number = data.get("totRcptNo")
				doc.custom_internal_data = data.get("intrlData")
				doc.custom_receipt_signature = data.get("rcptSign")
				doc.custom_control_unit_date_time = control_unit_date_time
				doc.custom_control_unit_date = control_unit_date
				doc.custom_control_unit_time = control_unit_time

				file_name, qr_url = create_qr_code(
					client.headers.get("tin"), client.headers.get("bhfId"), data.get("rcptSign")
				)
				attachment_url = create_attachment(file_name, doc.name)

				doc.custom_receipt_qr_code = attachment_url
				doc.custom_receipt_qr_url = qr_url

				create_sales_receipt(data, doc.name)
				stockIOSaveReq(doc, date_str)
				doc.custom_update_sales_to_etims = 1

				frappe.msgprint(_("Sales invoice synced to eTIMS successfully"))

			except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
				frappe.log_error(title="eTIMS Sales Invoice Error", message=traceback.format_exc())
				frappe.throw(_("eTIMS Error: {0}").format(e))
	else:
		return


def stockIOSaveReq(doc, date_str):
	taxAmt = 0
	taxblAmt = 0
	if doc.custom_update_invoice_in_tims:
		stock_list = etims_sale_item_list_stock(doc)
		if len(stock_list):
			for item in doc.items:
				if item.get("custom_maintain_stock") == 1 and item.get("custom_tax_code") in ["B", "E"]:
					taxblAmt += item.get("base_net_amount")
					taxAmt += item.get("base_amount") - item.get("base_net_amount")

			payload = {
				"sarNo": get_next_sar_number(doc, doc.custom_tax_branch_office),
				"orgSarNo": get_org_sar_number(doc),
				"regTyCd": "A",
				"custTin": doc.tax_id,
				"custNm": doc.customer,
				"custBhfId": "",
				"ocrnDt": date_str,
				"totItemCnt": len(stock_list),
				"totTaxblAmt": abs(round(taxblAmt, 2)),
				"totTaxAmt": abs(round(taxAmt, 2)),
				"totAmt": abs(doc.base_grand_total),
				"remark": doc.remarks,
				"regrId": (doc.owner or "")[:20],
				"regrNm": (doc.owner or "")[:20],
				"modrId": (doc.modified_by or "")[:20],
				"modrNm": (doc.modified_by or "")[:20],
				"itemList": stock_list,
			}

			if doc.is_return == 1:
				return_status = sales_return_information(doc)

				if return_status == "partial" or return_status == "full":
					payload["sarTyCd"] = "03"

				elif return_status == "null":
					frappe.throw(_("Invalid, return amount is greater than original amount!"))

			else:
				payload["sarTyCd"] = "11"

			if doc.custom_update_invoice_in_tims:
				try:
					frappe.logger().debug("Stock IO payload: {0}".format(payload))
					client = KRAClient()
					result = client.insert_stock_io(payload)

					if "Error" in result:
						frappe.throw(result["Error"])

					frappe.msgprint(_("Stock IO synced to eTIMS successfully"))

				except requests.Timeout:
					frappe.log_error(
						title="eTIMS Stock IO Timeout", message=f"Stock IO for {doc.name} timed out"
					)
					frappe.throw(_("eTIMS stock I/O timed out."))
				except requests.ConnectionError:
					frappe.log_error(title="eTIMS Stock IO Connection Error", message=traceback.format_exc())
					frappe.throw(_("Cannot connect to eTIMS for stock I/O."))
				except (requests.HTTPError, frappe.ValidationError) as e:
					frappe.log_error(title="eTIMS Stock IO Error", message=traceback.format_exc())
					frappe.throw(_("eTIMS Stock IO Error: {0}").format(e))
			else:
				return


def get_customer_details(customer):
	customer_kra_details = frappe.get_doc("Customer", customer)

	cust_dict = {
		"cust_pin": customer_kra_details.get("custom_customer_pin"),
		"cust_name": customer_kra_details.get("custom_customer_name"),
	}

	return cust_dict


def get_last_inv_number(doc, branch_id):

	cur_number = 0
	last_inv_no = 0

	if doc.custom_update_invoice_in_tims:
		settings_docs = frappe.db.get_all(
			"TIS Device Initialization", filters={"branch_id": branch_id}, fields=["*"]
		)

		if settings_docs:
			last_inv_no = settings_docs[0].get("last_sales_invoice_number")

		try:
			last_inv = frappe.db.get_all(
				doc.doctype,
				filters={
					"name": ["!=", doc.name],
					"custom_update_invoice_in_tims": 1,
					"custom_tax_branch_office": branch_id,
				},
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


def validate_inv_number(doc):
	invoice_numbers = []
	invoice_number_list = frappe.db.get_all(
		"Sales Invoice", fields=["custom_invoice_number", "name"], order_by="custom_invoice_number desc"
	)

	if invoice_number_list:
		for invoice_no in invoice_number_list:
			if not invoice_no.get("name") == doc.name:
				if invoice_no.get("custom_invoice_number") not in invoice_numbers:
					invoice_numbers.append(invoice_no.get("custom_invoice_number"))

	return invoice_numbers


def etims_sale_item_list_sales(doc):
	sales_item_list = []
	for item in doc.items:
		item_tax_code = get_tax_template_details(item.get("item_tax_template"))
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
			"pkg": abs(item.get("qty")),
			"qtyUnitCd": item_detail[0].get("custom_quantity_unit_code"),
			"qty": abs(item.get("qty")),
			"prc": abs(item.get("base_rate")),
			"splyAmt": abs(item.get("base_amount")),
			"dcRt": abs(item.get("discount_percentage")),
			"dcAmt": abs(round((item.get("custom_discount_amount_kes") * item.get("qty")), 2)),
			# "isrccCd":null,
			# "isrccNm":null,
			# "isrcRt":null,
			# "isrcAmt":null,
			"totDcAmt": abs(round((item.get("custom_discount_amount_kes") * item.get("qty")), 2)),
			"taxTyCd": item_tax_code,
			"taxblAmt": abs(round(item.get("base_net_amount"), 2)),
			"taxAmt": abs(round((item.get("base_amount") - item.get("base_net_amount")), 2)),
			"totAmt": abs(item.get("base_amount")),
		}

		if item_etims_data not in sales_item_list:
			sales_item_list.append(item_etims_data)

	return sales_item_list


def etims_sale_item_list_stock(doc):
	stock_item_list = []
	for item in doc.items:
		if item.custom_maintain_stock:
			item_tax_code = get_tax_template_details(item.get("item_tax_template"))
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
				"pkgUnitCd": item_detail[0].get("custom_packaging_unit_code"),
				"pkg": item.get("qty"),
				"qtyUnitCd": item_detail[0].get("custom_quantity_unit_code"),
				"qty": abs(item.get("qty")),
				"prc": abs(item.get("base_rate")),
				"splyAmt": abs(item.get("base_amount")),
				"dcRt": abs(item.get("discount_percentage")),
				"dcAmt": abs(round((item.get("custom_discount_amount_kes") * item.get("qty")), 2)),
				"totDcAmt": abs(round((item.get("custom_discount_amount_kes") * item.get("qty")), 2)),
				"taxTyCd": item_tax_code,
				"taxblAmt": abs(round(item.get("base_net_amount"), 2)),
				"taxAmt": abs(round((item.get("base_amount") - item.get("base_net_amount")), 2)),
				"totAmt": abs(item.get("base_amount")),
			}

			if item_etims_data not in stock_item_list:
				stock_item_list.append(item_etims_data)

	return stock_item_list


def get_tax_template_details(template_name):
	tax_doc = frappe.get_doc("Item Tax Template", template_name)
	if tax_doc:
		tax_code = tax_doc.custom_code

		return tax_code
	else:
		return "D"


def get_tax_account_rate(account_head):
	tax_acc_docs = frappe.db.get_all("Account", filters={"name": account_head}, fields=["tax_rate"])

	if tax_acc_docs:
		tax_rate = tax_acc_docs[0].get("tax_rate")

		return tax_rate


def create_sales_receipt(data, doc_name):
	control_unit_date_time = eTIMS.strp_datetime_object(data.get("sdcDateTime"))

	new_rcpt_doc = frappe.new_doc("eTIMS Sales Receipt")
	new_rcpt_doc.receipt_number = data.get("curRcptNo")
	new_rcpt_doc.total_receipt_number = data.get("totRcptNo")
	new_rcpt_doc.internal_data = data.get("intrlData")
	new_rcpt_doc.receipt_signature = data.get("rcptSign")
	new_rcpt_doc.control_unit_date_time = control_unit_date_time
	new_rcpt_doc.reference = doc_name

	new_rcpt_doc.insert()


def create_qr_code(pin, branch_id, rcpt_signature):
	header_docs = frappe.db.get_all(
		"TIS Device Initialization", filters={"branch_id": branch_id, "active": 1}, fields=["api_mode"]
	)

	if rcpt_signature:
		if header_docs:
			settings_doc = header_docs[0]

			url = (
				"https://etims-sbx.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data="
				+ pin
				+ branch_id
				+ rcpt_signature
			)
			file_name = rcpt_signature + ".png"

			file_path = frappe.get_site_path("private", "files", file_name)

			if settings_doc.get("api_mode") == "Production":
				url = (
					"https://etims.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data="
					+ pin
					+ branch_id
					+ rcpt_signature
				)
			else:
				url = (
					"https://etims-sbx.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data="
					+ pin
					+ branch_id
					+ rcpt_signature
				)

			# print(qrcode)
			try:
				qrcode = segno.make_qr(url)
				qrcode.save(file_path, scale=5)

				return file_name, url

			except Exception as e:
				frappe.log_error("eTIMS: QR code generation failed", str(e))
				frappe.throw(_("QR Code Not Generated: {0}").format(e))


def create_attachment(file_name, inv_name):
	new_attachment = frappe.new_doc("File")
	new_attachment.file_name = file_name
	new_attachment.file_url = "/private/files/" + file_name
	new_attachment.attached_to_doctype = "Sales Invoice"
	new_attachment.attached_to_name = inv_name
	new_attachment.is_private = 1

	new_attachment.save()

	return new_attachment.get("file_url")


def sales_return_information(doc):
	diff_amount = 0
	return_status = ""

	if doc.is_return:
		if doc.return_against:
			return_amount = doc.grand_total
			return_against = frappe.get_doc("Sales Invoice", doc.return_against)
			prev_return_amount = return_against.grand_total

			diff_amount = prev_return_amount + return_amount

		if diff_amount > 0:
			return_status = "partial"
		elif diff_amount == 0:
			return_status = "full"
		elif diff_amount < 0:
			return_status = "null"

	return return_status
