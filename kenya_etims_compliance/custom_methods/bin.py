import frappe
import requests
from frappe import _

from kenya_etims_compliance.custom_methods.queue_processor import enqueue_invoice
from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
	get_etims_settings,
)
from kenya_etims_compliance.utils.etims_utils import eTIMS
from kenya_etims_compliance.utils.kra_client import KRAClient


def on_submit(doc, method):
	# Skip eTIMS stock master update if the current user has no Tax Branch Office configured
	if not eTIMS.get_user_branch_id():
		return

	# Same rule as the sales path: an item KRA does not know about cannot be
	# declared. Enqueuing it anyway just buries a guaranteed rejection in the
	# retry loop, so hold the whole document back with the reason recorded.
	from kenya_etims_compliance.custom_methods.sales_invoice import kra_transmission_problems

	problems = kra_transmission_problems(doc)
	if problems:
		frappe.log_error(
			title=f"eTIMS: stock master for {doc.name} held back from KRA",
			message="\n".join(problems),
		)
		return

	# Respect the same enable_queue toggle the invoice path uses. When queueing
	# is enabled, hand the whole per-item loop to the existing queue — never
	# issue sequential blocking KRA calls inside a submit transaction.
	if get_etims_settings().get("enable_queue", 1):
		_enqueue_stock_master(doc)
		return

	mod_user_name = eTIMS.get_name_of_user(doc.modified_by)
	reg_user_name = eTIMS.get_name_of_user(doc.owner)

	succeeded, failed = 0, []
	for item in doc.items:
		if item.get("custom_maintain_stock") == 1:
			try:
				stockMasterSaveReq(item, doc, reg_user_name, mod_user_name)
				# Persist the flag to DB — in-memory child row assignment is not saved by the parent
				frappe.db.set_value(item.doctype, item.name, "custom_stock_master_updated", 1)
				succeeded += 1
			except (
				frappe.DoesNotExistError,
				frappe.ValidationError,
				requests.ConnectionError,
				requests.Timeout,
				requests.HTTPError,
			) as e:
				failed.append((item.get("item_code"), str(e)))
				frappe.log_error(
					title="eTIMS Stock Master Error",
					message=f"Failed to update stock master for {item.get('item_code')}: {e!s}",
				)

	# Single summary message at the end (only if anything was actually processed)
	if succeeded and not failed:
		frappe.msgprint(_("eTIMS Master Stock updated for {0} item(s)").format(succeeded), indicator="green")
	elif succeeded and failed:
		details = "<br>".join(f"  • {code}: {err[:120]}" for code, err in failed)
		frappe.msgprint(
			_("eTIMS Master Stock: {0} succeeded, {1} failed.<br>{2}").format(succeeded, len(failed), details),
			indicator="orange", title=_("Partial eTIMS update"),
		)
	elif failed:
		details = "<br>".join(f"  • {code}: {err[:120]}" for code, err in failed)
		frappe.msgprint(
			_("eTIMS Master Stock update failed for {0} item(s):<br>{1}").format(len(failed), details),
			indicator="red", title=_("eTIMS update failed"),
		)


def _enqueue_stock_master(doc):
	"""Queue every stock-maintained line item for KRA stock-master sync.

	Reuses the existing queue — one entry per item, same retry/circuit-breaker
	path the invoice queues take. The on-success handler in queue_processor
	writes custom_stock_master_updated=1 only when KRA returns Success.
	"""
	branch_id = None
	try:
		branch_id = KRAClient()._get_user_branch_id()
	except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
		frappe.log_error("eTIMS: Failed to get branch ID for stock master queue", str(e))

	mod_user_name = eTIMS.get_name_of_user(doc.modified_by)
	reg_user_name = eTIMS.get_name_of_user(doc.owner)

	count = 0
	for item in doc.items:
		if item.get("custom_maintain_stock") != 1:
			continue
		item_code = frappe.db.get_value("Item", item.get("item_code"), "custom_item_code")
		quantity = get_bin_qty(item.get("item_code"), item.get("warehouse"))
		payload = {
			"itemCd": item_code,
			"rsdQty": quantity,
			"regrId": doc.owner,
			"regrNm": reg_user_name,
			"modrId": doc.modified_by,
			"modrNm": mod_user_name,
		}
		enqueue_invoice(
			doc=doc,
			payload=payload,
			api_endpoint="save_stock_master",
			branch_id=branch_id,
		)
		count += 1

	if count:
		frappe.msgprint(
			_("eTIMS Master Stock update queued for {0} item(s).").format(count),
			indicator="blue",
		)


def resolve_stores_warehouse(tax_branch=None):
	"""Resolve a Stores Warehouse for the current branch, with graceful fallbacks.

	Resolution order:
	  1. Warehouse with warehouse_type=Stores, is_group=0, custom_tax_branch_office=branch
	  2. TIS Device Initialization's `default_stores_warehouse` (any non-group warehouse)
	  3. Any Stores leaf warehouse globally (with a warning to configure properly)
	  4. Fall through → caller throws a configuration-fix message
	"""
	tax_branch = tax_branch or eTIMS.get_user_branch_id()

	# Tier 1: branch-specific match
	if tax_branch:
		wh = frappe.db.get_all(
			"Warehouse",
			filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": tax_branch},
			fields=["name"], limit=1,
		)
		if wh:
			return wh[0].name

	# Tier 2: the branch device's explicitly configured default. An admin who filled
	# this field meant it, so honour it even when the warehouse carries no
	# `warehouse_type` — ERPNext leaves that unset on the stock warehouses it creates
	# for a new company, and ships "Transit" as the only Warehouse Type record.
	if tax_branch:
		devices = frappe.db.get_all(
			"TIS Device Initialization",
			filters={"branch_id": tax_branch, "active": 1},
			fields=["default_stores_warehouse"], limit=1,
		)
		if devices and devices[0].default_stores_warehouse:
			wh_name = devices[0].default_stores_warehouse
			if frappe.db.get_value("Warehouse", wh_name, "is_group") == 0:
				return wh_name

	# Tier 3: any Stores leaf warehouse (with one-time notice per request)
	any_wh = frappe.db.get_all(
		"Warehouse", filters={"warehouse_type": "Stores", "is_group": 0},
		fields=["name"], limit=1,
	)
	if any_wh:
		if not frappe.flags.get("_stores_wh_fallback_warned"):
			frappe.msgprint(
				_("Using fallback Stores warehouse '{0}' — no warehouse is linked to tax branch '{1}'. "
				  "Open Warehouse {0} and set Tax Branch Office to {1} for accurate KRA stock reporting.").format(
					any_wh[0].name, tax_branch or "(none)"
				),
				title=_("Stores warehouse fallback"), indicator="orange",
			)
			frappe.flags._stores_wh_fallback_warned = True
		return any_wh[0].name

	return None


def get_bin_qty(item_code, warehouse=None):
	"""On-hand qty for `item_code`, in the warehouse the stock actually moved in.

	`warehouse` comes from the document row being submitted and is the accurate
	source for KRA's rsdQty on multi-warehouse sites. Branch-level resolution is
	only a fallback for rows that carry no warehouse.
	"""
	warehouse_name = warehouse or resolve_stores_warehouse()
	if not warehouse_name:
		frappe.throw(
			_("No Stores warehouse exists in the system. "
			  "Create a Warehouse with Type=Stores (not a group) — and ideally link it to Tax Branch Office '{0}' via the 'Tax Branch Office' field.").format(
				eTIMS.get_user_branch_id() or "(your branch)"
			)
		)

	bin_docs = frappe.db.get_all(
		"Bin",
		filters={"item_code": item_code, "warehouse": warehouse_name},
		fields=["actual_qty"],
	)

	if bin_docs:
		return bin_docs[0].get("actual_qty")

	return 0


def stockMasterSaveReq(item, doc, regName, modName):
	item_code = frappe.db.get_value("Item", item.get("item_code"), "custom_item_code")

	quantity = get_bin_qty(item.get("item_code"), item.get("warehouse"))

	payload = {
		"itemCd": item_code,
		"rsdQty": quantity,
		"regrId": doc.owner,
		"regrNm": regName,
		"modrId": doc.modified_by,
		"modrNm": modName,
	}

	if doc.doctype == "Sales Invoice":
		if doc.custom_update_invoice_in_tims:
			save_stock_master(payload)
		else:
			frappe.logger().debug("eTIMS stock master update for sales")
	if doc.doctype == "Purchase Invoice":
		if doc.custom_update_purchase_in_tims:
			save_stock_master(payload)
		else:
			frappe.logger().debug("eTIMS stock master update for purchase")


def save_stock_master(payload):
	result = KRAClient().post("saveStockMaster", payload)
	if result.get("Success"):
		return {"Success": result.get("Success")}
	# Per contract C-1: raise on rejection instead of returning a soft error
	# dict — callers expect ValidationError to be catchable per-item.
	frappe.throw(
		_("eTIMS stock master rejected: {0}").format(result.get("Error") or "Oops Bad Request!"),
		frappe.ValidationError,
	)
