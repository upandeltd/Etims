import requests
import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS
from frappe.exceptions import ValidationError

def on_submit(doc, method):
    if doc.custom_update_invoice_in_tims:
        branch_id = eTIMS.get_user_branch_id()
        etims_details = get_etims_details(doc.company, branch_id, doc.owner, doc.modified_by)
        mod_user_name = etims_details.get("modifier")
        reg_user_name = etims_details.get("creator")
        
        try: 
            for item in doc.items:
                if item.get("custom_maintain_stock") == 1:
                    stockMasterSaveReq(item, doc, reg_user_name, mod_user_name, doc.set_warehouse)
                    item.custom_stock_master_updated = 1
                                
                    frappe.msgprint("Master Stock updated successfully")
        except:
            frappe.throw("Error saving Master Stock")        
    
def get_bin_qty(item_code, store_warehouse):
    quantity = 0
        
    bin_docs = frappe.db.get_all("Bin", filters={"item_code":item_code, "warehouse": store_warehouse}, fields=["actual_qty"])

    if bin_docs:
        quantity = bin_docs[0].get("actual_qty")
    
    return quantity

def stockMasterSaveReq(item, doc, regName, modName, warehouse):
    item_code = frappe.db.get_value('Item', item.get("item_code"), 'custom_etims_item_code')
    
    quantity = get_bin_qty(item.get("item_code"), warehouse)
    
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

    except ValidationError as e:
        frappe.throw(str(e))
    
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