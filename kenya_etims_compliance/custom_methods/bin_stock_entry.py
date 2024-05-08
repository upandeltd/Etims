import requests
import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS

def on_submit(doc, method):
    if not doc.custom_send_stock_info_to_etims: #*******Change condition
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
                                    
                        frappe.msgprint("Master Stock updated successfully")

                else:
                    frappe.throw("Missing Value For Warehouse Id")
                    
            elif doc.stock_entry_type == "Material Transfer":
                if t_warehouse_id and s_warehouse_id:
                    for item in doc.items:
                        stockMasterSaveReq(item, doc, reg_user_name, mod_user_name, s_warehouse_id)
                        stockMasterSaveReq(item, doc, reg_user_name, mod_user_name, t_warehouse_id)
                        item.custom_stock_master_updated = 1
                                    
                        frappe.msgprint("Master Stock updated successfully")

                else:
                    frappe.throw("Missing Value For Warehouse Id")
        except:
            frappe.throw("Error saving Master Stock")        
    
def get_bin_qty(item_code, branch_id):
        store_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": branch_id}, fields=["warehouse_name", "name"])
            
        bin_docs = frappe.db.get_all("Bin", filters={"item_code":item_code, "warehouse": store_warehouse[0].get("name")}, fields=["actual_qty"])

        if bin_docs:

            return bin_docs[0].get("actual_qty")
    
def stockMasterSaveReq(item, doc, regName, modName, branch_id):
    item_code = frappe.db.get_value('Item', item.get("item_code"), 'custom_item_code')
    
    quantity = get_bin_qty(item.get("item_code"), branch_id)
    
    payload = {
        "itemCd": item_code,
        "rsdQty": quantity, 
        "regrId": doc.owner, 
        "regrNm": regName, 
        "modrId": doc.modified_by, 
        "modrNm": modName
    }
    save_stock_master(doc, payload, branch_id)
    
def save_stock_master(doc, payload, branch_id):
    if doc.custom_send_stock_info_to_etims:
        headers = get_headers(branch_id)
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
    
    else:
        print("**Stock Master - Stock***")
        print(payload)
        
def get_headers(branch_id):
    header_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id, "active":1}, fields=["pin", "branch_id", "communication_key"])

    if header_docs:
        headers = {
            "tin":header_docs[0].get("pin"),
            "bhfId":header_docs[0].get("branch_id"),
            "cmcKey":header_docs[0].get("communication_key"),
        }
        
        return headers