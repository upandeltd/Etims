import requests
import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS

def on_submit(doc, method):
    if doc.custom_send_stock_info_to_etims: #*******Change condition
        try: 
            t_warehouse_id = doc.custom_target_tax_branch_office
            s_warehouse_id = doc.custom_source_tax_branch_office

            if doc.stock_entry_type == "Material Receipt":
                if t_warehouse_id:
                    etims_details = get_etims_details(doc.company, t_warehouse_id, doc.owner, doc.modified_by)
                    for item in doc.items:
                        stockMasterSaveReq(item, doc, etims_details.get("creator"), etims_details.get("modifier"), t_warehouse_id, doc.to_warehouse)
                        item.custom_stock_master_updated = 1
                                    
                        frappe.msgprint("Master Stock updated successfully")

                else:
                    frappe.throw("Missing Value For Warehouse Id")
                    
            elif doc.stock_entry_type == "Material Transfer":
                if t_warehouse_id and s_warehouse_id:
                    etims_details = get_etims_details(doc.company, t_warehouse_id, doc.owner, doc.modified_by)

                    for item in doc.items:
                        stockMasterSaveReq(item, doc, etims_details.get("creator"), etims_details.get("modifier"), s_warehouse_id, doc.from_warehouse)
                        stockMasterSaveReq(item, doc, etims_details.get("creator"), etims_details.get("modifier"), t_warehouse_id, doc.to_warehouse)
                        item.custom_stock_master_updated = 1
                                    
                        frappe.msgprint("Master Stock updated successfully")

                else:
                    frappe.throw("Missing Value For Warehouse Id")
        except:
            frappe.throw("Error saving Master Stock")        
    
def get_bin_qty(item_code, store_warehouse):
        quantity = 0
            
        bin_docs = frappe.db.get_all("Bin", filters={"item_code":item_code, "warehouse": store_warehouse}, fields=["actual_qty"])

        if bin_docs:
            quantity = bin_docs[0].get("actual_qty")
        
        return quantity
        
def stockMasterSaveReq(item, doc, regName, modName, branch_id, warehosue):
    item_code = frappe.db.get_value('Item', item.get("item_code"), 'custom_etims_item_code')
    
    quantity = get_bin_qty(item.get("item_code"), warehosue)
    
    payload = {
        "itemCd": item_code,
        "rsdQty": quantity, 
        "regrId": regName,
        "regrNm": regName,
        "modrId": modName,
        "modrNm": modName,
    }
    save_stock_master(doc, payload, branch_id)
    
def save_stock_master(doc, payload, branch_id):
    if doc.custom_send_stock_info_to_etims:
        headers = get_headers(branch_id, doc.company)
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
        
def get_headers(branch_id, company):
    header_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id, "active":1, "company": company}, fields=["pin", "branch_id", "communication_key"])

    if header_docs:
        headers = {
            "tin":header_docs[0].get("pin"),
            "bhfId":header_docs[0].get("branch_id"),
            "cmcKey":header_docs[0].get("communication_key"),
        }
        
        return headers
    

def get_etims_details(company, branch_id, owner, modified_by):
    query = """
        SELECT 
            tbc.update_stock_selling AS update_stock
        FROM
            `tabTIS Device Initialization` AS tdi
        LEFT JOIN
            `tabTax Branch Configurations` AS tbc
        ON
            tbc.tis_device_initialization = tdi.name
        WHERE 
            tdi.company = %s
        AND
            tdi.branch_id = %s
        AND
            tdi.active = 1
    """

    results = frappe.db.sql(query, (company, branch_id), as_dict=True)
    
    if results:
        creator = frappe.db.get_value("eTIMS Branch User", {"system_user": owner, "saved": 1}, "user_name")
        modifier = frappe.db.get_value("eTIMS Branch User", {"system_user": modified_by, "saved": 1}, "user_name")

        if not creator:
            frappe.throw("Sales Invoice Creater Not Registered As Branch Operator")
        
        if not modifier:
            frappe.throw("Sales Invoice Modifier Not Registered As Branch Operator")
            
        results[0]["creator"] = creator
        results[0]["modifier"] = modifier
        
    return results[0]