import traceback  # pyqrcode
from datetime import datetime, time, timedelta

import frappe

from kenya_etims_compliance.utils.permissions import (
	is_etims_admin,
	is_etims_manager,
	require,
	validate_branch_access,
)
import requests
import segno
from frappe import _
from frappe.utils import flt

from kenya_etims_compliance.custom_methods.queue_processor import enqueue_invoice
from kenya_etims_compliance.custom_methods.receipt_labels import get_receipt_label
from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
	get_etims_settings,
)
from kenya_etims_compliance.utils.etims_utils import (
	KRA_TAX_BANDS,
	NON_VAT_CODE,
	_resolve_band_code,
	apply_tax_bands,
	eTIMS,
	get_next_sar_number,
	get_org_sar_number,
	split_item_tax,
)
from kenya_etims_compliance.utils.kra_client import KRAClient


def _guard_kra_sales_lookup(invoice_no):
	"""Gate the two KRA sales-lookup proxies.

	``require("Sales Invoice", "read")`` alone is company-wide: in a
	multi-branch setup any cashier could read another branch's KRA fiscal
	status. Scope it:

	* named invoice that exists locally -> enforce that branch on the caller
	* named invoice with no local record, or a bare date sweep -> the result
	  spans the whole company, so restrict it to managers/admins
	"""
	require("Sales Invoice", "read")

	local = None
	if invoice_no:
		local = frappe.db.get_value(
			"Sales Invoice",
			{"custom_invoice_number": invoice_no},
			["name", "custom_tax_branch_office"],
			as_dict=True,
		) or frappe.db.get_value(
			"Sales Invoice",
			{"name": invoice_no},
			["name", "custom_tax_branch_office"],
			as_dict=True,
		)

	if local:
		validate_branch_access(local)
		return

	if not (
		is_etims_admin()
		or is_etims_manager()
		or "System Manager" in frappe.get_roles()
		or frappe.session.user == "Administrator"
	):
		frappe.throw(
			_(
				"Permission Denied: a company-wide KRA lookup requires the "
				"eTIMS Manager or eTIMS Administrator role."
			),
			frappe.PermissionError,
		)


@frappe.whitelist()
def searchSalesTrnsReq(invoice_no=None, last_req_dt=None):
	"""Search sales transactions in eTIMS"""
	# Proxies a KRA lookup on the company's credentials, so it must not be
	# reachable by any authenticated session, nor leak another branch's
	# fiscal status.
	_guard_kra_sales_lookup(invoice_no)

	response = eTIMS.searchTrns(invoice_no, last_req_dt, "sales")

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
def on_cancel(doc, method):
	"""on_cancel hook — stop any pending eTIMS submission and warn when a
	signed invoice is cancelled (KRA's API does not expose a sales-cancel
	endpoint in this app, so the fiscal receipt stays live until the operator
	files a credit note / refund with KRA directly).
	"""
	if not doc.custom_update_invoice_in_tims:
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

	if doc.custom_update_sales_to_etims:
		frappe.log_error(
			title=f"eTIMS: cancelled Sales Invoice already signed to KRA: {doc.name}"[:140],
			message=(
				f"Sales Invoice {doc.name} was cancelled after being signed to KRA. "
				"The fiscal receipt remains live at KRA. File a credit note / refund "
				"with KRA to reconcile."
			),
		)

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
					# Collision safety net: clear the number so the assign-once
					# guard in insert_invoice_number reallocates a fresh one.
					doc.custom_invoice_number = None
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

		# Assign the eTIMS invoice number ONCE. Re-deriving it on every save lets
		# the stored invcNo drift after transmission (the post-success doc.save()
		# re-fires on_update). Keep an already-assigned number; only allocate a
		# new one when none exists. Tax amounts/totals below still recompute.
		last_inv_number = doc.custom_invoice_number or get_last_inv_number(doc, branch_id)

		# update_stock decision: respect the user's choice, auto-disable when
		# enabling it would technically fail, warn when leaving it off risks
		# KRA stock-register reconciliation.
		user_choice = 1 if doc.get("update_stock") else 0

		has_dn_link = any(it.get("delivery_note") or it.get("dn_detail") for it in (doc.items or []))
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
		if user_choice == 1 and has_dn_link:
			new_update_stock = 0
			frappe.msgprint(
				_("Auto-disabled 'Update Stock' on this invoice because it links to a Delivery Note. "
				  "Stock was already booked by the DN — eTIMS will receive the stock movement from there."),
				title=_("Update Stock disabled"), indicator="orange",
			)
		elif user_choice == 1 and not has_stock_item:
			new_update_stock = 0
			frappe.msgprint(
				_("Auto-disabled 'Update Stock' on this invoice because none of the items are stock items "
				  "(all are services). No stock movement to send."),
				title=_("Update Stock disabled"), indicator="orange",
			)
		elif user_choice == 0 and has_stock_item and not has_dn_link:
			frappe.msgprint(
				_("'Update Stock' is OFF on this invoice but items include stock items. "
				  "KRA's stock register will not receive a stock-out movement, which may cause reconciliation "
				  "mismatches. Either enable Update Stock or send a separate stock movement."),
				title=_("KRA stock reconciliation risk"), indicator="yellow",
			)

		update_dict = {
			"custom_invoice_number": last_inv_number,
			"custom_sales_control_unit": scu,
			"update_stock": new_update_stock,
			"custom_tax_branch_office": branch_id,
			"custom_total_taxable_amount": total_vat_amount,
			"custom_total_nontaxable_amount": total_non_vat_amount,
			"custom_item_count": item_count,
			"custom_total_discount_amount": total_discount_amount,
			"custom_total_before_discount": total_discount_amount + doc.base_grand_total,
		}
		if new_update_stock and sales_warehouse:
			update_dict["set_warehouse"] = sales_warehouse

		frappe.db.set_value("Sales Invoice", doc.name, update_dict, update_modified=False)

		# Sync in-memory doc fields to match what was written to DB
		doc.custom_invoice_number = last_inv_number
		doc.custom_sales_control_unit = scu
		doc.update_stock = new_update_stock
		if new_update_stock and sales_warehouse:
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
						row_code = _resolve_band_code(item)
						if row_code == key:
							tax_templates = frappe.db.get_all(
								"Item Tax Template", filters={"custom_code": key}, fields=["custom_code_name"]
							)

							if len(tax_templates):
								frappe.db.set_value(
									"Sales Taxes and Charges",
									item.get("name"),
									{
										"custom_code": row_code,
										"custom_total_taxable_amount": round(value, 2),
										"custom_code_name": tax_templates[0].get("custom_code_name"),
									},
									update_modified=False,
								)
								# Sync in-memory child row to match DB write
								item.custom_code = row_code
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


def _payload_consistency_problems(payload):
	"""Ways the assembled KRA payload contradicts itself.

	The header totals, the A-E band breakdown and the item lines are each
	assembled from a different source, so a half-configured site can produce a
	payload where they disagree. Every check below compares the payload
	against itself -- no site configuration is assumed.
	"""
	problems = []
	items = payload.get("itemList") or []

	line_taxbl = round(sum(flt(li.get("taxblAmt")) for li in items), 2)
	line_tax = round(sum(flt(li.get("taxAmt")) for li in items), 2)
	head_taxbl = flt(payload.get("totTaxblAmt"))
	head_tax = flt(payload.get("totTaxAmt"))

	if abs(head_taxbl - line_taxbl) > 0.05:
		problems.append(
			_("Header taxable amount {0} does not match the {1} on the item lines.").format(
				head_taxbl, line_taxbl
			)
		)
	if abs(head_tax - line_tax) > 0.05:
		problems.append(
			_("Header tax amount {0} does not match the {1} on the item lines.").format(head_tax, line_tax)
		)

	band_taxbl = round(sum(flt(payload.get(f"taxblAmt{code}")) for code in KRA_TAX_BANDS), 2)
	band_tax = round(sum(flt(payload.get(f"taxAmt{code}")) for code in KRA_TAX_BANDS), 2)
	if abs(band_taxbl - line_taxbl) > 0.05 or abs(band_tax - line_tax) > 0.05:
		problems.append(
			_(
				"Tax bands A-E total {0} taxable / {1} tax but the item lines total {2} / {3}. "
				"Set the KRA code on the Sales Taxes and Charges rows."
			).format(band_taxbl, band_tax, line_taxbl, line_tax)
		)

	if flt(payload.get("totItemCnt")) != len(items):
		problems.append(
			_("Item count {0} does not match the {1} lines actually sent.").format(
				payload.get("totItemCnt"), len(items)
			)
		)

	return problems


def trnsSalesSaveWrReq(doc, method):
	"""
	Method that collects sales information and updates it to tims server.
	Called during before_submit — assigns invoice number first, then sends to eTIMS.
	"""
	if doc.custom_update_invoice_in_tims:
		# An invoice whose items are not yet registered with KRA cannot be
		# declared honestly (see kra_transmission_problems). Blocking the
		# submit would stop the till; transmitting anyway would file a false
		# return. So park it: the sale completes, the invoice is flagged
		# Failed with the exact reason, and the retry paths pick it up once
		# the item masters are fixed.
		problems = kra_transmission_problems(doc)
		if problems:
			reason = "\n".join(problems)
			doc.custom_etims_queue_status = "Failed"
			frappe.log_error(
				title=f"eTIMS: {doc.name} held back from KRA",
				message=reason,
			)
			frappe.msgprint(
				_("This sale was NOT sent to KRA:<br>{0}").format("<br>".join(problems)),
				title=_("eTIMS transmission held"),
				indicator="red",
			)
			return

		# Per HIGH review finding (hook-stage inversion): insert_invoice_number
		# runs at on_update and writes the totals, but frm.savesubmit() collapses
		# edit + submit into one request — so the totals seen by
		# build_sales_payload (before_submit) must be recomputed HERE, in the
		# same hook, against the in-memory doc that has the freshly-edited
		# amounts. Otherwise totTaxblAmt reads a stale value while totAmt is
		# fresh and the fiscal receipt ends up internally inconsistent.
		insert_tax_amounts(doc)
		total_vat = flt(fetch_total_vat(doc))
		total_non_vat = flt(fetch_total_non_vat(doc))
		doc.custom_total_taxable_amount = total_vat
		doc.custom_total_nontaxable_amount = total_non_vat

		# Build the KRA payload via the shared builder (it also applies the tax
		# bands, return fields, training-mode override and receipt label).
		payload = build_sales_payload(doc)

		# The header totals and the A-E bands are assembled from different
		# sources than the item lines (Sales Taxes and Charges `custom_code`
		# vs Item Tax Template `custom_code`), so a half-configured site
		# produced a payload that contradicted itself -- totTaxAmt 1.38
		# against totTaxblAmt 0, with every band at zero. KRA accepts that;
		# the return is then simply wrong. Hold it back the same way.
		payload_problems = _payload_consistency_problems(payload)
		if payload_problems:
			reason = "\n".join(payload_problems)
			doc.custom_etims_queue_status = "Failed"
			frappe.log_error(
				title=f"eTIMS: {doc.name} payload inconsistent, held back",
				message=reason,
			)
			frappe.msgprint(
				_("This sale was NOT sent to KRA:<br>{0}").format("<br>".join(payload_problems)),
				title=_("eTIMS transmission held"),
				indicator="red",
			)
			return

		settings = get_etims_settings()

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
				stockIOSaveReq(doc, eTIMS.strf_date_object(doc.posting_date))
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
					item_taxbl, item_tax = split_item_tax(
						item.get("base_amount"), item.get("base_net_amount"), item.get("item_tax_template")
					)
					taxblAmt += item_taxbl
					taxAmt += item_tax

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
		# Per HIGH review finding: the FOR UPDATE lock is a no-op when branch_id
		# is None or no TIS Device Initialization row matches — silently
		# allocating the same number twice creates duplicate invcNo, which KRA
		# rejects forever. Throw a clear configuration error instead.
		if not branch_id:
			frappe.throw(
				_(
					"Cannot allocate an eTIMS sales invoice number: no Tax Branch Office is "
					"configured for the current user. Set 'Tax Branch Office' on the eTIMS Branch User "
					"and try again."
				)
			)

		# Serialize per-branch number allocation. Lock the branch's device row
		# with FOR UPDATE so two concurrent submits cannot read the same max and
		# assign a DUPLICATE eTIMS invoice number (KRA rejects duplicate invcNo).
		# The lock is held until the allocating transaction commits — and there
		# is NO intermediate commit between here and the set_value that writes
		# the number — so the next allocator always sees the committed number.
		tis_device = frappe.qb.DocType("TIS Device Initialization")
		frappe.qb.from_(tis_device).where(tis_device.branch_id == branch_id).for_update().select(
			tis_device.name
		).run()

		settings_docs = frappe.db.get_all(
			"TIS Device Initialization", filters={"branch_id": branch_id}, fields=["*"]
		)

		if not settings_docs:
			frappe.throw(
				_(
					"Cannot allocate an eTIMS sales invoice number: no TIS Device Initialization "
					"row matches branch '{0}'. Create / activate the device and try again."
				).format(branch_id)
			)

		last_inv_no = settings_docs[0].get("last_sales_invoice_number") or 0

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
				last_inv_no = max(last_inv_no or 0, last_inv[0].get("custom_invoice_number"))

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


def _kra_line_problems(item, item_tax_code, row):
	"""Reasons this invoice line cannot be honestly declared to KRA.

	A payload that declares one thing and charges another is a false return,
	not a rejected one -- KRA accepts it and the books are then wrong. Two ways
	that used to happen silently:

	  * ``get_tax_template_details`` falls back to "D" (non-VAT) whenever the
	    Item Tax Template carries no ``custom_code``, so a line taxed at 16%
	    was transmitted as exempt.
	  * ``custom_item_code`` / ``custom_item_classification_code`` stay unset
	    until the eTIMS code-sync and item-registration steps have run, so
	    lines went out with null KRA identifiers.

	Returns a list of human-readable problems; empty means the line is safe to
	transmit.
	"""
	problems = []

	if row["taxAmt"] > 0 and item_tax_code == NON_VAT_CODE:
		problems.append(
			_(
				"Item {0} charges tax of {1} but its Item Tax Template {2} maps to KRA tax type "
				"'{3}' (non-VAT). Set the KRA tax band on the Item Tax Template."
			).format(
				item.get("item_code"),
				row["taxAmt"],
				item.get("item_tax_template") or _("(none)"),
				NON_VAT_CODE,
			)
		)

	missing = [
		label
		for label, value in (
			(_("KRA item code"), row["itemCd"]),
			(_("item classification code"), row["itemClsCd"]),
			(_("packaging unit code"), row["pkgUnitCd"]),
			(_("quantity unit code"), row["qtyUnitCd"]),
		)
		if not value
	]
	if missing:
		problems.append(
			_("Item {0} is missing its {1}. Register the item with KRA first.").format(
				item.get("item_code"), ", ".join(missing)
			)
		)

	return problems


def kra_transmission_problems(doc):
	"""Every reason ``doc`` cannot be honestly transmitted to KRA, across all lines."""
	problems = []
	for item in doc.items:
		item_tax_code = get_tax_template_details(item.get("item_tax_template"))
		detail = frappe.db.get_all(
			"Item",
			filters={"disabled": 0, "item_code": item.get("item_code")},
			fields=[
				"custom_item_code",
				"custom_item_classification_code",
				"custom_packaging_unit_code",
				"custom_quantity_unit_code",
			],
		)
		if not detail:
			problems.append(_("Item {0} not found or is disabled").format(item.get("item_code")))
			continue
		row = {
			"itemCd": detail[0].get("custom_item_code"),
			"itemClsCd": detail[0].get("custom_item_classification_code"),
			"pkgUnitCd": detail[0].get("custom_packaging_unit_code"),
			"qtyUnitCd": detail[0].get("custom_quantity_unit_code"),
			"taxAmt": split_item_tax(item.get("base_amount"), item.get("base_net_amount"), item.get("item_tax_template"))[1],
		}
		problems.extend(_kra_line_problems(item, item_tax_code, row))
	return problems


def etims_sale_item_list_sales(doc):
	merged_items = {}
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

		item_cd = item_detail[0].get("custom_item_code")
		# custom_discount_amount_kes is a custom column: init_valid_columns leaves
		# it None when absent and, unlike ERPNext's own fields, nothing
		# repopulates it during validate. flt() keeps the multiply from crashing.
		dc_amt = abs(round((flt(item.get("custom_discount_amount_kes")) * flt(item.get("qty"))), 2))
		taxbl_amt, tax_amt = split_item_tax(
			item.get("base_amount"), item.get("base_net_amount"), item.get("item_tax_template")
		)
		row = {
			"itemCd": item_cd,
			"itemClsCd": item_detail[0].get("custom_item_classification_code"),
			"itemNm": item_detail[0].get("custom_item_name"),
			# "bcd":null,
			"pkgUnitCd": item_detail[0].get("custom_packaging_unit_code"),
			"pkg": abs(item.get("qty")),
			"qtyUnitCd": item_detail[0].get("custom_quantity_unit_code"),
			"qty": abs(item.get("qty")),
			"splyAmt": abs(item.get("base_amount")),
			"dcAmt": dc_amt,
			# "isrccCd":null,
			# "isrccNm":null,
			# "isrcRt":null,
			# "isrcAmt":null,
			"totDcAmt": dc_amt,
			"taxTyCd": item_tax_code,
			"taxblAmt": taxbl_amt,
			"taxAmt": tax_amt,
			"totAmt": round(taxbl_amt + tax_amt, 2),
		}

		problems = _kra_line_problems(item, item_tax_code, row)
		if problems:
			frappe.throw(
				"<br>".join(problems),
				title=_("eTIMS: invoice cannot be transmitted"),
			)

		# KRA validates itemCd as a per-transaction key: the same item code split
		# across multiple ERPNext rows (e.g. a return crediting several original
		# sale lines, or a rate override mid-invoice) must collapse into ONE
		# itemList entry with summed quantities/amounts, or KRA rejects the
		# payload ("Supply/Taxable amount is incorrect for item X", "item code X
		# appears more than once"). Only merge rows that also share a tax type -
		# a genuine tax-code split on the same item must stay separate.
		key = (item_cd, item_tax_code)
		if key in merged_items:
			existing = merged_items[key]
			for field in ("pkg", "qty", "splyAmt", "dcAmt", "totDcAmt", "taxblAmt", "taxAmt", "totAmt"):
				existing[field] = round(existing[field] + row[field], 2)
		else:
			merged_items[key] = row

	sales_item_list = []
	for idx, row in enumerate(merged_items.values(), start=1):
		row["itemSeq"] = idx
		row["prc"] = round(row["splyAmt"] / row["qty"], 2) if row["qty"] else 0
		row["dcRt"] = round((row["dcAmt"] / row["splyAmt"]) * 100, 2) if row["splyAmt"] else 0
		sales_item_list.append(row)

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
			taxbl_amt, tax_amt = split_item_tax(
				item.get("base_amount"), item.get("base_net_amount"), item.get("item_tax_template")
			)
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
				"dcAmt": abs(round((flt(item.get("custom_discount_amount_kes")) * flt(item.get("qty"))), 2)),
				"totDcAmt": abs(round((flt(item.get("custom_discount_amount_kes")) * flt(item.get("qty"))), 2)),
				"taxTyCd": item_tax_code,
				"taxblAmt": taxbl_amt,
				"taxAmt": tax_amt,
				"totAmt": round(taxbl_amt + tax_amt, 2),
			}

			if item_etims_data not in stock_item_list:
				stock_item_list.append(item_etims_data)

def get_tax_template_details(template_name):
	if not template_name:
		return "D"
	tax_code = frappe.db.get_value("Item Tax Template", template_name, "custom_code")
	return tax_code or "D"


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
	"""Build the KRA receipt-verification URL and a QR PNG for it.

	Always returns a ``(file_name, url)`` tuple so callers can unpack safely:
	  * ``(file_name, url)`` — URL built and PNG saved.
	  * ``(None, url)``       — URL built but the PNG could not be saved (the
	                            thermal receipt still renders the QR from the URL
	                            via ``escpos_qr``; only the A4 image attachment
	                            is skipped).
	  * ``(None, None)``      — no receipt signature or no active device, so no
	                            verifiable URL can be built.

	This function MUST NOT raise: it runs inside the eTIMS post-success handler
	*after* the queue status is committed "Sent". A raised exception there would
	abort the document save and silently drop the receipt signature and control
	unit data — a compliance defect, not just a missing QR.
	"""
	if not rcpt_signature:
		return None, None

	header_docs = frappe.db.get_all(
		"TIS Device Initialization", filters={"branch_id": branch_id, "active": 1}, fields=["api_mode"]
	)
	if not header_docs:
		return None, None

	host = (
		"https://etims.kra.go.ke"
		if header_docs[0].get("api_mode") == "Production"
		else "https://etims-sbx.kra.go.ke"
	)
	url = f"{host}/common/link/etims/receipt/indexEtimsReceiptData?Data={pin}{branch_id}{rcpt_signature}"

	file_name = rcpt_signature + ".png"
	file_path = frappe.get_site_path("private", "files", file_name)
	try:
		segno.make_qr(url).save(file_path, scale=5)
	except Exception:
		# Keep the URL (thermal QR still works); only the PNG attachment is lost.
		frappe.log_error("eTIMS: QR code PNG generation failed", frappe.get_traceback())
		return None, url

	return file_name, url


def create_attachment(file_name, inv_name):
	if not file_name:
		return None
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

			# Compare against what's still outstanding, not the original invoice's
			# full total: prior return tranches already reduce that balance. Without
			# this, a second (or later) return that completes a 100% reversal still
			# reads as "partial" against the ORIGINAL total, and the required KRA
			# cancellation tags (cnclReqDt/cnclDt) never fire even though the
			# original is fully credited back.
			prior_returns = flt(
				frappe.db.sql(
					"""
					select sum(grand_total) from `tabSales Invoice`
					where is_return=1 and docstatus=1
					and return_against=%(return_against)s and name != %(name)s
					""",
					{"return_against": doc.return_against, "name": doc.name or ""},
				)[0][0]
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


# ---------------------------------------------------------------------------
# Manual signing of an already-submitted invoice
#
# Closes the gap where an invoice submitted with eTIMS signing disabled had no
# built-in way to be signed afterwards. These functions are ADDITIVE — they do
# not touch the working `before_submit` (trnsSalesSaveWrReq) path. The actual
# transmission reuses the queue (enqueue_invoice -> process_queue_entry ->
# _handle_sales_invoice_success), which already writes fiscal fields to a
# submitted (docstatus=1) document safely.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# VAT obligation enforcement
# ---------------------------------------------------------------------------
# A company with no VAT obligation (eTIMS Settings -> VAT Obligation =
# "Not Registered") must never report VAT it is not registered to collect.
# Two layers keep the booked invoice and the KRA payload consistent:
#   1. enforce_vat_obligation (before_validate) removes the VAT-bearing Sales
#      Taxes and Charges rows *before* ERPNext computes taxes, so no VAT is
#      charged on the actual invoice. VAT lives in the tax rows (re-mapping the
#      item tax template does NOT remove it — set_missing_values regenerates the
#      per-item map), so the rows are the reliable lever. With VAT-inclusive
#      pricing the gross total is preserved; with exclusive pricing the add-on
#      VAT is dropped.
#   2. _normalize_payload_non_vat (inside build_sales_payload) forces the KRA
#      payload into a clean band-D structure, so a stray VAT band/line can
#      never be transmitted.
# ---------------------------------------------------------------------------


def enforce_vat_obligation(doc, method):
	"""before_validate: strip VAT from eTIMS-bound invoices for non-VAT companies.

	Removes every VAT-bearing tax row (rate > 0) before tax calculation, so
	ERPNext recomputes the invoice with no VAT charged. Idempotent: an invoice
	that already carries no rated tax row is left untouched.
	"""
	# Cheap in-memory checks first; only read settings for eTIMS-bound invoices.
	if not doc.get("custom_update_invoice_in_tims") or not doc.get("taxes"):
		return
	if get_etims_settings().get("vat_obligation") != "Not Registered":
		return

	vat_rows = [t for t in doc.taxes if flt(t.get("rate")) > 0]
	if not vat_rows:
		return

	doc.set("taxes", [t for t in doc.taxes if flt(t.get("rate")) <= 0])

	frappe.msgprint(
		_(
			"VAT Obligation is 'Not Registered': removed {0} VAT charge row(s) so no VAT "
			"is charged or transmitted to KRA. With VAT-inclusive pricing the total is "
			"unchanged; with VAT-exclusive pricing the VAT is dropped.<br>Accounts: {1}"
		).format(len(vat_rows), ", ".join(t.account_head for t in vat_rows)),
		title=_("VAT removed (Non-VAT company)"),
		indicator="orange",
	)


def _normalize_payload_non_vat(payload):
	"""Force a clean Non-VAT (D) structure on a KRA sales payload.

	Folds the whole supply into band D at 0% and forces every line's taxTyCd to D
	with zero tax — the transmission-boundary guarantee that complements the
	before_validate conversion, so no stray VAT band/line can reach KRA.
	"""
	items = payload.get("itemList") or []
	band_total = abs(round(sum(flt(li.get("taxblAmt")) for li in items), 2))

	for code in KRA_TAX_BANDS:
		payload[f"taxblAmt{code}"] = 0
		payload[f"taxAmt{code}"] = 0
		payload[f"taxRt{code}"] = 0
	payload[f"taxblAmt{NON_VAT_CODE}"] = band_total
	payload["totTaxblAmt"] = band_total
	payload["totTaxAmt"] = 0

	for li in items:
		li["taxTyCd"] = NON_VAT_CODE
		li["taxAmt"] = 0

	return payload


def build_sales_payload(doc):
	"""Build the KRA save_sales payload for a Sales Invoice.

	A standalone copy of the payload assembly used by trnsSalesSaveWrReq, so the
	manual-sign path can run outside before_submit without altering the working
	submit path. The A-E tax bands are aggregated per code (one pass, no
	order dependence).
	"""
	conc_datetime_str = eTIMS.strf_datetime_format(doc.modified)
	date_time_str = datetime.now().strftime("%Y%m%d%H%M%S")
	date_str = eTIMS.strf_date_object(doc.posting_date)
	count = doc.custom_item_count or len(doc.items) or 0
	if count < 1:
		frappe.throw(_("Sales Invoice must have at least one item to submit to eTIMS"))

	item_list = etims_sale_item_list_sales(doc)

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
		"totItemCnt": len(item_list),
		"totTaxblAmt": abs((doc.custom_total_taxable_amount or 0) + (doc.custom_total_nontaxable_amount or 0)),
		"totTaxAmt": abs(doc.base_total_taxes_and_charges or 0),
		"totAmt": abs(doc.base_grand_total or 0),
		"prchrAcptcYn": "N",
		"remark": doc.remarks,
		"regrId": (doc.owner or "")[:20],
		"regrNm": (doc.owner or "")[:20],
		"modrId": (doc.modified_by or "")[:20],
		"modrNm": (doc.modified_by or "")[:20],
		"receipt": {
			"custTin": doc.tax_id,
			"rcptPbctDt": date_time_str,
			"prchrAcptcYn": "N",
		},
		"itemList": item_list,
	}

	# KRA tax bands A-E (shared, summed-per-band, null-guarded helper)
	apply_tax_bands(payload, doc.taxes, get_tax_account_rate)

	# Non-VAT company: force a clean band-D payload and assert no VAT survives.
	if get_etims_settings().get("vat_obligation") == "Not Registered":
		_normalize_payload_non_vat(payload)

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

	settings = get_etims_settings()
	if settings.get("training_mode"):
		payload["rcptTyCd"] = "T"

	frappe.db.set_value(
		"Sales Invoice", doc.name, "custom_receipt_label", get_receipt_label(doc), update_modified=False
	)

	return payload


def prepare_etims_resign(doc):
	"""Populate the eTIMS number and tax-band fields that were skipped because
	the invoice was submitted with signing off.

	Surgical: assigns the invoice number (if missing) and recomputes the tax
	amounts/totals only. It deliberately does NOT replay the update_stock /
	set_warehouse logic that insert_invoice_number runs at save time — the stock
	ledger entries were already committed at submit and must not be re-derived.

	Caller must set ``doc.custom_update_invoice_in_tims = 1`` first (the number
	helpers are gated on that flag).
	"""
	branch_id = eTIMS.get_user_branch_id()

	if not doc.custom_invoice_number:
		scu = ""
		init_docs = frappe.db.get_all(
			"TIS Device Initialization",
			filters={"branch_id": branch_id},
			fields=["sales_control_unit_id"],
		)
		if init_docs:
			scu = init_docs[0].get("sales_control_unit_id")

		last_inv_number = get_last_inv_number(doc, branch_id)
		frappe.db.set_value(
			"Sales Invoice",
			doc.name,
			{
				"custom_invoice_number": last_inv_number,
				"custom_sales_control_unit": scu,
				"custom_tax_branch_office": branch_id,
			},
			update_modified=False,
		)
		doc.custom_invoice_number = last_inv_number
		doc.custom_sales_control_unit = scu
		doc.custom_tax_branch_office = branch_id

	# Recompute tax-band amounts on the tax rows and the document totals
	insert_tax_amounts(doc)
	total_vat_amount = fetch_total_vat(doc)
	total_non_vat_amount = fetch_total_non_vat(doc)
	total_discount_amount = get_total_discount(doc)
	frappe.db.set_value(
		"Sales Invoice",
		doc.name,
		{
			"custom_total_taxable_amount": total_vat_amount,
			"custom_total_nontaxable_amount": total_non_vat_amount,
			"custom_total_discount_amount": total_discount_amount,
		},
		update_modified=False,
	)
	doc.custom_total_taxable_amount = total_vat_amount
	doc.custom_total_nontaxable_amount = total_non_vat_amount
	doc.custom_total_discount_amount = total_discount_amount


@frappe.whitelist()
def sign_submitted_invoice(invoice_name):
	"""Sign a SUBMITTED Sales Invoice that was originally submitted with eTIMS
	signing disabled (so no queue entry was ever created).

	Late-signing caveat: this assigns a fresh eTIMS invoice number and records
	the sale in eTIMS *now* (current submission window) while ERPNext still holds
	it in its original posting period. If that period's VAT return is already
	filed, prefer a credit note / reissue instead of signing late.
	"""
	doc = frappe.get_doc("Sales Invoice", invoice_name)
	frappe.has_permission("Sales Invoice", "submit", doc=doc, throw=True)

	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted invoice can be signed to eTIMS."))
	if doc.custom_update_sales_to_etims:
		frappe.throw(_("This invoice has already been signed to eTIMS."))
	if doc.custom_etims_queue_status in ("Queued", "Processing"):
		frappe.throw(
			_("This invoice is already queued for eTIMS ({0}).").format(doc.custom_etims_queue_status)
		)
	if not doc.items:
		frappe.throw(_("This invoice has no items to send to eTIMS."))

	# Enable signing, then backfill the number + tax fields skipped at submit
	doc.custom_update_invoice_in_tims = 1
	frappe.db.set_value(
		"Sales Invoice", doc.name, "custom_update_invoice_in_tims", 1, update_modified=False
	)
	prepare_etims_resign(doc)

	payload = build_sales_payload(doc)

	# Safety net: never enqueue a malformed payload for a taxed sale
	if not payload.get("invcNo"):
		frappe.throw(
			_("Could not assign an eTIMS invoice number. Check TIS Device Initialization for your branch.")
		)
	bands = [payload.get(f"taxblAmt{c}") or 0 for c in ("A", "B", "C", "D", "E")]
	if abs(doc.base_grand_total or 0) > 0 and not any(bands):
		frappe.throw(
			_(
				"This invoice has no eTIMS tax breakdown — its items are missing Item Tax "
				"Templates or KRA tax codes. Amend the invoice with proper eTIMS tax setup "
				"before signing."
			)
		)

	branch_id = None
	try:
		branch_id = KRAClient()._get_user_branch_id()
	except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
		frappe.log_error("eTIMS: Failed to get branch ID for manual sign", str(e))

	queue_name = enqueue_invoice(
		doc=doc, payload=payload, api_endpoint="save_sales", branch_id=branch_id
	)
	return {"status": "queued", "queue_entry": queue_name, "invoice_number": payload.get("invcNo")}
