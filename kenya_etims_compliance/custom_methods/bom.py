import requests, traceback

import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS
@frappe.whitelist()
def itemSaveComposition(doc_name):
    bom_item_list = get_bom_items(doc_name)
    doc = frappe.get_doc("BOM", doc_name)
    
    for payload in bom_item_list:
        post_item_compostion(payload, doc)
    check_if_all_items_sent(doc)
        
                
def get_bom_items(doc_name):
    payload_list = []
    
    doc = frappe.get_doc("BOM", doc_name)
    
    if not doc.exploded_items:
        frappe.throw("No exploded items to register!")
    
    if not doc.custom_etims_item_code:
        frappe.throw("eTIMS item code is missing!")   
    
    if doc.is_default ==1 and doc.is_active ==1:        
        for item in doc.items:
            if not item.get("custom_etims_item_code"):
                frappe.throw("Item {} missing etims item code.".format(item.get("item_code")))
                
            if not item.get("custom_updated_in_etims") == 1:
                payload = {
                    "itemCd" : doc.get("custom_etims_item_code"),
                    "cpstItemCd": item.get("custom_etims_item_code"),
                    "cpstQty": item.get("qty"),
                    "regrNm" : item.owner,
                    "regrId" : item.owner
                }
                
                if not payload in payload_list:
                    payload_list.append(payload)
        
    return payload_list

def post_item_compostion(item_payload, doc):
    headers = eTIMS.get_headers()
    
    for item in doc.items:
        if item.get("custom_etims_item_code") == item_payload.get("cpstItemCd"):
            try:
                response = requests.request(
                    "POST",
                    eTIMS.tims_base_url() + 'saveItemComposition', 
                    json = item_payload, 
                    headers=headers
                )

                response_json = response.json()

                if not response_json.get("resultCd") == '000':
                    
                    frappe.throw(response_json.get("resultMsg"))
                
                item.custom_updated_in_etims = 1
                doc.save()
                frappe.msgprint(response_json.get("resultMsg"))

            except:
                eTIMS.log_errors("Item Save Composition", traceback.format_exc())
                frappe.throw("Oops Bad Request!")
            
def check_if_all_items_sent(doc):
    check_count = 0
    item_count = 0
    for item in doc.items:
        item_count += 1
        if item.get("custom_updated_in_etims") == 1:
            check_count += 1
            
    if check_count == item_count:
        doc.custom_updated_to_etims = 1
        doc.save()
        return True
    else:
        return False
            
        
    