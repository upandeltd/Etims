import requests
import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS

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
                item.custom_stock_master_updated = 1
                frappe.msgprint("Master Stock updated successfully")
            except Exception as e:
                frappe.log_error(
                    title="eTIMS Stock Master Error",
                    message=f"Failed to update stock master for {item.get('item_code')}: {str(e)}"
                )
                frappe.msgprint(
                    f"Warning: Could not update eTIMS Stock Master for {item.get('item_code')}: {str(e)}",
                    indicator="orange",
                    alert=True
                )        
    
def get_bin_qty(item_code):
        tax_branch = eTIMS.get_user_branch_id()

        store_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": tax_branch}, fields=["warehouse_name", "name"])

        if not store_warehouse:
            frappe.throw(f"No Stores warehouse found for tax branch: {tax_branch}")
            
        bin_docs = frappe.db.get_all("Bin", filters={"item_code":item_code, "warehouse": store_warehouse[0].get("name")}, fields=["actual_qty"])

        if bin_docs:
            return bin_docs[0].get("actual_qty")

        return 0
    
def stockMasterSaveReq(item, doc, regName, modName):
    item_code = frappe.db.get_value('Item', item.get("item_code"), 'custom_item_code')
    
    quantity = get_bin_qty(item.get("item_code"))
    
    payload = {
        "itemCd": item_code,
        "rsdQty": quantity, 
        "regrId": doc.owner, 
        "regrNm": regName, 
        "modrId": doc.modified_by, 
        "modrNm": modName
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
    headers = eTIMS.get_headers()
    try:
        response = requests.request(
            "POST",
            eTIMS.tims_base_url() + 'saveStockMaster',
            json = payload,
            headers=headers,
            timeout=30
        )
        
        response_json = response.json()
        if not response_json.get("resultCd") == '000':
        
            return {"Oops!":response_json.get("resultMsg")}
        
        return {"Success":response_json.get("resultMsg")}

    except Exception:
        return {"Error":"Oops Bad Request!"}