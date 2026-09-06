import json
import traceback
from datetime import datetime

import frappe
import requests
from frappe import _, scrub
from frappe.query_builder.functions import Cast_, Max
from frappe.utils import cint, flt

from kenya_etims_compliance.utils.etims_utils import (
	apply_tax_bands,
	eTIMS,
	get_next_sar_number,
	get_org_sar_number,
	get_tax_template_details,
	split_item_tax,
)
from kenya_etims_compliance.utils.permissions import (
	can_modify_doctype,
	is_etims_admin,
	is_etims_manager,
	require,
)
from kenya_etims_compliance.utils.kra_client import KRAClient


@frappe.whitelist()
def searchPurchaseTrnsReq(invoice_no=None, last_req_dt=None):
	"""Search purchase transactions in eTIMS"""
	# Proxies a KRA lookup on the company's credentials, so it must not be
	# reachable by any authenticated session.
	require("Purchase Invoice", "read")

	response = eTIMS.searchTrns(invoice_no, last_req_dt, "purchase")

	for key, value in response.items():
		if key == "Success":
			return {"Success": value}
		else:
			return {"Error": value}


def get_total_discount(doc):
	"""Sum per-line discount across the document (line discount_amount * qty)."""
	discount_amount = 0

	if doc.items:
		for item in doc.items:
			if item.get("discount_percentage") and item.get("discount_percentage") > 0:
				total_dsc = flt(item.get("discount_amount")) * (item.get("qty") or 1)
				discount_amount += total_dsc

	return discount_amount


def validate(doc, method):
	"""
	Method validate invoice number before submitting invoice
	"""
	if doc.custom_update_purchase_in_tims and doc.custom_invoice_number and doc.name:
		doc_exists = frappe.db.exists("Purchase Invoice", {"name": doc.name})

		if doc_exists:
			invoice_numbers = validate_inv_number(doc)
			if doc.custom_invoice_number in invoice_numbers:
				# Free-text supplier invoice references (e.g. "KRACU0200133329/26")
				# live in the same column; colliding them silently with an
				# eTIMS-assigned number would destroy a legacy reference.
				frappe.throw(
					_(
						"custom_invoice_number '{0}' is already used by another Purchase Invoice. "
						"Clear it (to assign a fresh eTIMS number) or fix the duplicate before submitting."
					).format(doc.custom_invoice_number)
				)

	# Populate orgInvcNo for credit notes (return_against) and amended invoices
	# so KRA treats the submission as a correction, not a fresh sale.
	if doc.custom_update_purchase_in_tims and not doc.custom_original_invoice_number:
		ref = doc.return_against or doc.amended_from
		if ref:
			original = frappe.db.get_value(
				"Purchase Invoice", ref, "custom_invoice_number"
			)
			if original:
				doc.custom_original_invoice_number = original
def on_cancel(doc, method):
	"""on_cancel hook — stop any pending eTIMS submission and warn when a
	signed invoice is cancelled (KRA's API does not expose a purchase-cancel
	endpoint in this app, so the fiscal receipt stays live until the operator
	files a debit note with KRA directly).
	"""
	if not doc.custom_update_purchase_in_tims:
		return

	# Cancel any in-flight queue entries so process_queue_entry's docstatus
	# guard short-circuits before KRA submission.
	if doc.custom_etims_queue_entry:
		frappe.db.set_value(
			"eTIMS Invoice Queue",
			doc.custom_etims_queue_entry,
			{"status": "Cancelled", "last_error": "Source invoice cancelled."},
			update_modified=False,
		)

	if doc.custom_item_updated_in_tims:
		frappe.log_error(
			title=f"eTIMS: cancelled Purchase Invoice already signed to KRA: {doc.name}"[:140],
			message=(
				f"Purchase Invoice {doc.name} was cancelled after being signed to KRA. "
				"The fiscal receipt remains live at KRA. File a debit note with "
				"KRA to reconcile."
			),
		)


	discount_amount = 0

	if doc.items:
		for item in doc.items:
			if item.get("discount_percentage") and item.get("discount_percentage") > 0:
				total_dsc = flt(item.get("discount_amount")) * flt(item.get("qty") or 1)
				discount_amount += total_dsc

def insert_invoice_number(doc, method):
	"""
	Method sets increment for invoice number and orginal invoice number before submitting invoice
	"""
	# Per HIGH review finding: insert_invoice_number rewrites update_stock /
	# set_warehouse / custom_tax_branch_office site-wide — gate it on the
	# eTIMS opt-in so non-eTIMS Purchase Invoices are untouched.
	if not doc.get("custom_update_purchase_in_tims"):
		return
	if doc.name:
		branch_id = eTIMS.get_user_branch_id()
		# Initialize pur_warehouse before conditional to avoid UnboundLocalError
		pur_warehouse = None
		init_docs = frappe.db.get_all(
			"TIS Device Initialization", filters={"branch_id": branch_id}, fields=["default_stores_warehouse"]
		)
		if init_docs:
			pur_warehouse = init_docs[0].get("default_stores_warehouse")

		# Assign the eTIMS invoice number ONCE — re-deriving it on every save lets
		# the stored invcNo drift after transmission. Keep an existing number.
		last_inv_number = doc.custom_invoice_number or get_last_inv_number(doc, branch_id)

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
					taxable_amount += flt(item.get("custom_total_taxable_amount"))
				if item.get("base_tax_amount_after_discount_amount") < 0 and doc.is_return:
					taxable_amount += flt(item.get("custom_total_taxable_amount"))

	return taxable_amount


def fetch_total_non_vat(doc):
	taxable_non_vat_amount = 0
	if doc.taxes:
		for item in doc.taxes:
			if item.get("base_tax_amount_after_discount_amount") == 0:
				taxable_non_vat_amount += flt(item.get("custom_total_taxable_amount"))

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
		"totTaxblAmt": abs(flt(doc.custom_total_taxable_amount)),
		"totTaxAmt": abs(flt(doc.base_total_taxes_and_charges)),
		"totAmt": abs(flt(doc.base_grand_total)),
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

	# KRA tax bands A-E (shared, summed-per-band, null-guarded helper)
	apply_tax_bands(payload, doc.taxes, get_tax_account_rate)

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
	# Handle reverse invoicing (buyer-initiated) — independent of the
	# custom_update_purchase_in_tims gate: reverse invoicing is its own flow.
	if getattr(doc, "custom_is_reverse_invoice", False):
		result = handle_reverse_invoice(doc)
		if result:
			frappe.msgprint(_("Reverse invoice submitted to eTIMS"))
		return

	# Per CRITICAL 4: gate at the top so payload construction never runs on a
	# site that has eTIMS purchase reporting off. abs(None) on
	# custom_total_taxable_amount and etims_pur_item_list's get_doc both crash
	# when this gate sits lower.
	if not doc.custom_update_purchase_in_tims:
		frappe.logger().debug("eTIMS purchase skipped for %s", doc.name)
		return

	# Per HIGH review finding (hook-stage inversion): insert_invoice_number runs
	# at on_update and writes the totals, but frm.savesubmit() collapses edit +
	# submit into one request — so the totals seen by the payload must be
	# recomputed HERE (before_submit), in the same hook, against the in-memory
	# doc that has the freshly-edited amounts.
	insert_tax_amounts(doc)
	doc.custom_total_taxable_amount = flt(fetch_total_vat(doc))
	doc.custom_total_nontaxable_amount = flt(fetch_total_non_vat(doc))

	supplier_details = get_supplier_details(doc.supplier)

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
		"totTaxblAmt": abs(flt(doc.custom_total_taxable_amount)),
		"totTaxAmt": abs(flt(doc.base_total_taxes_and_charges)),
		"totAmt": abs(flt(doc.grand_total)),
		"remark": doc.remarks,
		"regrId": doc.owner,
		"regrNm": doc.owner,
		"modrId": doc.modified_by,
		"modrNm": doc.modified_by,
		"itemList": etims_pur_item_list(doc),
	}

	apply_tax_bands(payload, doc.taxes, get_tax_account_rate)

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


def stockIOSaveReq(doc, date_str):
	# Per CRITICAL 4: gate at the top, matching the sales twin at
	# sales_invoice.stockIOSaveReq:347. Building the payload unconditionally
	# runs etims_stock_item_list (which dereferences item_detail[0] without a
	# guard) and abs(None) on doc.grand_total on every Purchase Invoice save,
	# regardless of the eTIMS opt-in.
	if not doc.custom_update_purchase_in_tims:
		return

	taxAmt = 0
	taxblAmt = 0

	client = KRAClient()
	stock_list = etims_stock_item_list(doc)

	for item in doc.items:
		if item.get("custom_maintain_stock") == 1 and item.get("custom_tax_code") in ["B", "E"]:
			item_taxbl, item_tax = split_item_tax(item.get("amount"), item.get("net_amount"), item.get("item_tax_template"))
			taxblAmt += item_taxbl
			taxAmt += item_tax

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
		"totAmt": abs(flt(doc.grand_total)),
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

	try:
		result = client.insert_stock_io(payload)

		if "Error" in result:
			frappe.log_error(title="eTIMS Purchase Stock IO Error", message=result["Error"])
			return {"Error": result["Error"]}

		return {"Success": "Stock IO synced successfully"}

	except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
		frappe.log_error(title="eTIMS Purchase Stock IO Error", message=traceback.format_exc())
		return {"Error": f"eTIMS Error: {e!s}"}


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

	# Per HIGH review finding: the FOR UPDATE lock is a no-op when branch_id is
	# None or no TIS Device Initialization row matches — silently allocating the
	# same number twice creates duplicate invcNo, which KRA rejects forever.
	if not branch_id:
		frappe.throw(
			_(
				"Cannot allocate an eTIMS purchase invoice number: no Tax Branch Office is "
				"configured for the current user. Set 'Tax Branch Office' on the eTIMS Branch User "
				"and try again."
			)
		)

	# Serialize per-branch number allocation. Lock the branch's device row with
	# FOR UPDATE so two concurrent submits cannot read the same max and assign a
	# DUPLICATE eTIMS invoice number (KRA rejects duplicate invcNo). No commit
	# occurs between this lock and the set_value that writes the number.
	tis_device = frappe.qb.DocType("TIS Device Initialization")
	frappe.qb.from_(tis_device).where(tis_device.branch_id == branch_id).for_update().select(
		tis_device.name
	).run()

	settings_docs = frappe.db.get_all(
		"TIS Device Initialization", filters={"branch_id": branch_id}, fields=["last_purchase_invoice_number"]
	)

	if not settings_docs:
		frappe.throw(
			_(
				"Cannot allocate an eTIMS purchase invoice number: no TIS Device Initialization "
				"row matches branch '{0}'. Create / activate the device and try again."
			).format(branch_id)
		)

	last_inv_no = settings_docs[0].get("last_purchase_invoice_number") or 0

	try:
		# custom_invoice_number is a free-text field on this site (legacy supplier
		# invoice refs like "KRACU0200133329/26" live in the same column as
		# eTIMS-assigned running numbers), so an ORDER BY on the column would sort
		# lexically and pick the wrong row, and non-numeric values can't be
		# incremented. Only numeric-looking values count towards "last number".
		pinv = frappe.qb.DocType("Purchase Invoice")
		result = (
			frappe.qb.from_(pinv)
			.where(
				(pinv.name != doc.name)
				& (pinv.custom_tax_branch_office == branch_id)
				& (pinv.custom_invoice_number.regexp(r"^[0-9]+$"))
			)
			.select(Max(Cast_(pinv.custom_invoice_number, "UNSIGNED")))
		).run()

		if result and result[0][0] is not None:
			last_inv_no = max(last_inv_no or 0, cint(result[0][0]))

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
		taxbl_amt, tax_amt = split_item_tax(item.get("amount"), item.get("net_amount"), item.get("item_tax_template"))

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
			"pkg": abs(flt(item.get("qty"))),
			"qtyUnitCd": item_detail[0].get("custom_quantity_unit_code"),
			"qty": abs(flt(item.get("qty"))),
			"prc": abs(flt(item.get("rate"))),
			"splyAmt": abs(flt(item.get("amount"))),
			"dcRt": abs(flt(item.get("discount_percentage"))),
			"dcAmt": abs(flt(item.get("discount_amount"))),
			"taxTyCd": item_tax_details,
			"taxblAmt": taxbl_amt,
			"taxAmt": tax_amt,
			"totAmt": round(taxbl_amt + tax_amt, 2),
			"totDcAmt": abs(flt(item.get("discount_amount"))),
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

			if not item_detail:
				frappe.throw(f"Item {item.get('item_code')} not found or is disabled")

			taxbl_amt, tax_amt = split_item_tax(item.get("amount"), item.get("net_amount"), item.get("item_tax_template"))
			barcode = eTIMS.get_item_barcode(item.item_code, item.uom)

			item_etims_data = {
				"itemSeq": item.get("idx"),
				"itemCd": item_detail[0].get("custom_item_code"),
				"itemClsCd": item_detail[0].get("custom_item_classification_code"),
				"itemNm": item_detail[0].get("custom_item_name"),
				"bcd": barcode if barcode else "",
				"pkgUnitCd": item_detail[0].get("custom_packaging_unit_code"),
				"pkg": abs(flt(item.get("qty"))),
				"qtyUnitCd": item_detail[0].get("custom_quantity_unit_code"),
				"qty": abs(flt(item.get("qty"))),
				"prc": abs(flt(item.get("rate"))),
				"splyAmt": abs(flt(item.get("amount"))),
				"dcRt": abs(flt(item.get("discount_percentage"))),
				"dcAmt": abs(flt(item.get("discount_amount"))),
				"taxTyCd": item_tax_details,
				"taxblAmt": taxbl_amt,
				"taxAmt": tax_amt,
				"totAmt": round(taxbl_amt + tax_amt, 2),
				"totDcAmt": abs(round((flt(item.get("discount_amount")) * flt(item.get("qty"))), 2)),
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

			# Compare against what's still outstanding, not the original invoice's
			# full total: prior return tranches already reduce that balance. Without
			# this, a second (or later) return that completes a 100% reversal still
			# reads as "partial" against the ORIGINAL total, and the required KRA
			# cancellation tags (cnclReqDt/cnclDt) never fire even though the
			# original is fully credited back.
			prior_returns = flt(
				frappe.db.get_value(
					"Purchase Invoice",
					{
						"is_return": 1,
						"docstatus": 1,
						"return_against": doc.return_against,
						"name": ["!=", doc.name or ""],
					},
					"sum(grand_total)",
				)
			)
			remaining_balance = return_against.grand_total + prior_returns

			diff_amount = remaining_balance + return_amount

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
	require("Purchase Invoice", "write")
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
					# KRA's purchase register keys the supplier's invoice number as
					# `spplrInvcNo` (see etims_utils.searchTrns), and the local
					# fast-path above builds the same key. `invcNo` is the SALES
					# side's field and is absent from both, so this silently stored
					# "" and threw away the audit link on every verification.
					"custom_kra_invoice_number": (
						invoice_details.get("spplrInvcNo") or invoice_details.get("invcNo") or ""
					),
					"custom_supplier_pin_verified": supplier_pin,
				},
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
	require("Purchase Invoice", "read")
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
	# CRITICAL 9 — gate. require() alone lets any user with Frappe write
	# permission through (including a Sales Clerk), but the audit-trail
	# value of a manual override is only real when an Admin/Manager
	# approves it. Narrow the grant here.
	require("Purchase Invoice", "write")
	if not (is_etims_admin() or is_etims_manager()):
		frappe.throw(
			_("Manual verification override requires eTIMS Manager or Administrator role."),
			frappe.PermissionError,
		)

	# Reject empty / oversized reasons before writing. Reason goes into a
	# free-text field that is rendered in the UI, so cap it.
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("An override reason is required for manual verification."))
	if len(reason) > 500:
		reason = reason[:500]

	try:
		doc = frappe.get_doc("Purchase Invoice", docname)

		# CRITICAL 9 — only submitted invoices are eligible for payment
		# eligibility, and the override is what makes them eligible.
		if doc.docstatus != 1:
			frappe.throw(
				_("Manual verification override requires a submitted Purchase Invoice (docstatus=1)."),
				frappe.PermissionError,
			)

		# Check if already verified
		if doc.get("custom_invoice_verified"):
			return {"success": False, "message": "Invoice is already verified"}

		# Update invoice as manually verified.
		# NOTE: do NOT pass update_modified=False — that suppresses the
		# Version row that the audit trail depends on (CRITICAL 9). The
		# Version row also captures the full payload diff including the
		# override reason, which is what makes the override auditable.
		# NOTE: do NOT write the free-text reason into custom_qr_code —
		# that field is rendered unescaped in the purchase_invoice.js
		# Dialog (the Frontend agent owns the render-side escape). The
		# reason lives in custom_verification_override_reason instead.
		frappe.db.set_value(
			"Purchase Invoice",
			doc.name,
			{
				"custom_invoice_verified": 1,
				"custom_verification_date": frappe.utils.now(),
				"custom_kra_invoice_number": "MANUAL_OVERRIDE",
				"custom_verification_override_reason": reason,
			},
		)

		# Log the manual override to Error Logging (visible to eTIMS Auditor).
		eTIMS.log_errors(
			f"Manual Verification Override: {docname}",
			f"Reason: {reason}, User: {frappe.session.user}",
		)

		return {"success": True, "message": "Invoice marked as manually verified"}

	except (frappe.DoesNotExistError, frappe.DataError) as e:
		return {"success": False, "message": f"Error: {e!s}"}
