import frappe
import requests
from frappe import _

from kenya_etims_compliance.utils.etims_utils import eTIMS
from kenya_etims_compliance.utils.kra_client import KRAClient


def on_submit(doc, method):
	if doc.custom_send_stock_info_to_etims:  # *******Change condition
		mod_user_name = eTIMS.get_name_of_user(doc.modified_by)
		reg_user_name = eTIMS.get_name_of_user(doc.owner)

		try:
			t_warehouse_id = doc.custom_target_tax_branch_office
			s_warehouse_id = doc.custom_source_tax_branch_office

			succeeded, failed, api_calls = 0, [], 0

			if doc.stock_entry_type == "Material Receipt":
				if not t_warehouse_id:
					frappe.throw(_("Missing Value For Warehouse Id"))
				for item in doc.items:
					try:
						stockMasterSaveReq(item, doc, reg_user_name, mod_user_name, t_warehouse_id)
						# Persist the flag to DB — in-memory child row assignment is not saved by the parent
						frappe.db.set_value(item.doctype, item.name, "custom_stock_master_updated", 1)
						succeeded += 1
						api_calls += 1
					except (
						frappe.DoesNotExistError,
						frappe.ValidationError,
						requests.ConnectionError,
						requests.Timeout,
						requests.HTTPError,
					) as e:
						failed.append((item.get("item_code"), str(e)))
						frappe.log_error(
							"eTIMS: Stock master save failed",
							f"Failed for {item.get('item_code')}: {e!s}",
						)

			elif doc.stock_entry_type == "Material Transfer":
				if not (t_warehouse_id and s_warehouse_id):
					frappe.throw(_("Missing Value For Warehouse Id"))
				for item in doc.items:
					try:
						stockMasterSaveReq(item, doc, reg_user_name, mod_user_name, s_warehouse_id)
						stockMasterSaveReq(item, doc, reg_user_name, mod_user_name, t_warehouse_id)
						frappe.db.set_value(item.doctype, item.name, "custom_stock_master_updated", 1)
						succeeded += 1
						api_calls += 2
					except (
						frappe.DoesNotExistError,
						frappe.ValidationError,
						requests.ConnectionError,
						requests.Timeout,
						requests.HTTPError,
					) as e:
						failed.append((item.get("item_code"), str(e)))
						frappe.log_error(
							"eTIMS: Stock master save failed",
							f"Failed for {item.get('item_code')}: {e!s}",
						)

			if succeeded and not failed:
				frappe.msgprint(
					_("eTIMS Master Stock updated for {0} item(s)").format(succeeded), indicator="green",
				)
			elif succeeded and failed:
				details = "<br>".join(f"  • {code}: {err[:120]}" for code, err in failed)
				frappe.msgprint(
					_("eTIMS Master Stock: {0} succeeded, {1} failed.<br>{2}").format(
						succeeded, len(failed), details
					),
					indicator="orange", title=_("Partial eTIMS update"),
				)
			elif failed:
				details = "<br>".join(f"  • {code}: {err[:120]}" for code, err in failed)
				frappe.msgprint(
					_("eTIMS Master Stock update failed for {0} item(s):<br>{1}").format(
						len(failed), details
					),
					indicator="red", title=_("eTIMS update failed"),
				)
		except (
			frappe.DoesNotExistError,
			frappe.ValidationError,
			requests.ConnectionError,
			requests.Timeout,
			requests.HTTPError,
		) as e:
			frappe.log_error("eTIMS: Stock master update failed", str(e))
			frappe.throw(f"Error saving Master Stock: {e!s}")


def get_bin_qty(item_code, branch_id):
	from kenya_etims_compliance.custom_methods.bin import resolve_stores_warehouse

	warehouse_name = resolve_stores_warehouse(branch_id)
	if not warehouse_name:
		return 0

	bin_docs = frappe.db.get_all(
		"Bin",
		filters={"item_code": item_code, "warehouse": warehouse_name},
		fields=["actual_qty"],
	)

	if bin_docs:
		return bin_docs[0].get("actual_qty")

	return 0


def stockMasterSaveReq(item, doc, regName, modName, branch_id):
	item_code = frappe.db.get_value("Item", item.get("item_code"), "custom_item_code")

	quantity = get_bin_qty(item.get("item_code"), branch_id)

	payload = {
		"itemCd": item_code,
		"rsdQty": quantity,
		"regrId": doc.owner,
		"regrNm": regName,
		"modrId": doc.modified_by,
		"modrNm": modName,
	}
	save_stock_master(doc, payload, branch_id)


def save_stock_master(doc, payload, branch_id):
	if doc.custom_send_stock_info_to_etims:
		try:
			result = KRAClient(branch_id=branch_id).post("saveStockMaster", payload)

			if result.get("Success") is not None:
				return {"Success": result.get("Success")}

			# Per contract C-1: raise on rejection so callers can collect
			# per-item failures instead of silently marking as updated.
			frappe.throw(
				_("eTIMS stock master rejected: {0}").format(
					result.get("Error") or "Oops Bad Request!"
				),
				frappe.ValidationError,
			)

		except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
			frappe.log_error("eTIMS: Stock master save failed", str(e))
			return {"Error": f"Stock master error: {e!s}"}

	else:
		frappe.logger().debug("eTIMS stock master update for stock entry")
