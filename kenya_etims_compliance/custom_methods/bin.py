import frappe
import requests
from frappe import _

from kenya_etims_compliance.utils.etims_utils import eTIMS
from kenya_etims_compliance.utils.kra_client import KRAClient


def on_submit(doc, method):
	# Skip eTIMS stock master update if the current user has no Tax Branch Office configured
	if not eTIMS.get_user_branch_id():
		return

	mod_user_name = eTIMS.get_name_of_user(doc.modified_by)
	reg_user_name = eTIMS.get_name_of_user(doc.owner)

	for item in doc.items:
		if item.get("custom_maintain_stock") == 1:
			try:
				stockMasterSaveReq(item, doc, reg_user_name, mod_user_name)
				# Persist the flag to DB — in-memory child row assignment is not saved by the parent
				frappe.db.set_value(item.doctype, item.name, "custom_stock_master_updated", 1)
				frappe.msgprint(_("Master Stock updated successfully"))
			except (
				frappe.DoesNotExistError,
				requests.ConnectionError,
				requests.Timeout,
				requests.HTTPError,
			) as e:
				frappe.log_error(
					title="eTIMS Stock Master Error",
					message=f"Failed to update stock master for {item.get('item_code')}: {e!s}",
				)
				frappe.msgprint(
					f"Warning: Could not update eTIMS Stock Master for {item.get('item_code')}: {e!s}",
					indicator="orange",
					alert=True,
				)


def resolve_stores_warehouse(tax_branch=None):
	"""Resolve a Stores Warehouse for the current branch, with graceful fallbacks.

	Resolution order:
	  1. Warehouse with warehouse_type=Stores, is_group=0, custom_tax_branch_office=branch
	  2. TIS Device Initialization's `default_stores_warehouse` (if it's a Stores leaf)
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

	# Tier 2: TIS Device's configured default
	if tax_branch:
		devices = frappe.db.get_all(
			"TIS Device Initialization",
			filters={"branch_id": tax_branch, "active": 1},
			fields=["default_stores_warehouse"], limit=1,
		)
		if devices and devices[0].default_stores_warehouse:
			wh_name = devices[0].default_stores_warehouse
			meta = frappe.db.get_value("Warehouse", wh_name, ["warehouse_type", "is_group"], as_dict=True)
			if meta and meta.warehouse_type == "Stores" and not meta.is_group:
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


def get_bin_qty(item_code):
	tax_branch = eTIMS.get_user_branch_id()

	warehouse_name = resolve_stores_warehouse(tax_branch)
	if not warehouse_name:
		frappe.throw(
			_("No Stores warehouse exists in the system. "
			  "Create a Warehouse with Type=Stores (not a group) — and ideally link it to Tax Branch Office '{0}' via the 'Tax Branch Office' field.").format(tax_branch or "(your branch)")
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

	quantity = get_bin_qty(item.get("item_code"))

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
	return {"Error": result.get("Error", "Oops Bad Request!")}
