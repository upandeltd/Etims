import requests
import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS

def on_submit(doc, method):
    mod_user_name = eTIMS.get_name_of_user(doc.modified_by)
    reg_user_name = eTIMS.get_name_of_user(doc.owner)
    
    try: 
        for item in doc.items:
            if item.get("custom_maintain_stock") == 1:
                stockMasterSaveReq(item, doc, reg_user_name, mod_user_name)
                item.custom_stock_master_updated = 1
                            
                frappe.msgprint("Master Stock updated successfully")
    except:
        frappe.throw("Error saving Master Stock")        
    
def get_bin_qty(item_code):
        tax_branch = eTIMS.get_user_branch_id()

        store_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": tax_branch}, fields=["warehouse_name", "name"])
            
        bin_docs = frappe.db.get_all("Bin", filters={"item_code":item_code, "warehouse": store_warehouse[0].get("name")}, fields=["actual_qty"])

        if bin_docs:

            return bin_docs[0].get("actual_qty")
    
def stockMasterSaveReq(item, doc, regName, modName):
    item_code = frappe.db.get_value('Item', item.get("item_code"), 'custom_item_code')
    
    quantity = get_bin_qty(item.get("item_code"))
    
    print(item.get("item_code"))
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
            print("**Stock Master - Sales***")
            print(payload)
    if doc.doctype == "Purchase Invoice":
        if doc.custom_update_purchase_in_tims:
            save_stock_master(payload)	
        else:
            print("**Stock Master - Pur***")
            print(payload)
        
def save_stock_master(payload):
    headers = eTIMS.get_headers()
    try:
        response = requests.request(
            "POST", 
            eTIMS.tims_base_url() + 'saveStockMaster', 
            json = payload, 
            headers=headers
        )
        
        response_json = response.json()
        if not response_json.get("resultCd") == '000':
        
            return {"Oops!":response_json.get("resultMsg")}
        
        return {"Success":response_json.get("resultMsg")}

    except:
        return {"Error":"Oops Bad Request!"}