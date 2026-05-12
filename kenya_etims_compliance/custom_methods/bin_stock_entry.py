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

			if doc.stock_entry_type == "Material Receipt":
				if t_warehouse_id:
					for item in doc.items:
						stockMasterSaveReq(item, doc, reg_user_name, mod_user_name, t_warehouse_id)
						item.custom_stock_master_updated = 1

						frappe.msgprint(_("Master Stock updated successfully"))

				else:
					frappe.throw(_("Missing Value For Warehouse Id"))

			elif doc.stock_entry_type == "Material Transfer":
				if t_warehouse_id and s_warehouse_id:
					for item in doc.items:
						stockMasterSaveReq(item, doc, reg_user_name, mod_user_name, s_warehouse_id)
						stockMasterSaveReq(item, doc, reg_user_name, mod_user_name, t_warehouse_id)
						item.custom_stock_master_updated = 1

						frappe.msgprint(_("Master Stock updated successfully"))

				else:
					frappe.throw(_("Missing Value For Warehouse Id"))
		except (
			frappe.DoesNotExistError,
			requests.ConnectionError,
			requests.Timeout,
			requests.HTTPError,
		) as e:
			frappe.log_error("eTIMS: Stock master update failed", str(e))
			frappe.throw(f"Error saving Master Stock: {e!s}")


def get_bin_qty(item_code, branch_id):
	store_warehouse = frappe.db.get_all(
		"Warehouse",
		filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": branch_id},
		fields=["warehouse_name", "name"],
	)

	if not store_warehouse:
		return 0

	bin_docs = frappe.db.get_all(
		"Bin",
		filters={"item_code": item_code, "warehouse": store_warehouse[0].get("name")},
		fields=["actual_qty"],
	)

	if bin_docs:
		return bin_docs[0].get("actual_qty")


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

			return {"Error": result.get("Error", "Oops Bad Request!")}

		except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
			frappe.log_error("eTIMS: Stock master save failed", str(e))
			return {"Error": f"Stock master error: {e!s}"}

	else:
		frappe.logger().debug("eTIMS stock master update for stock entry")
