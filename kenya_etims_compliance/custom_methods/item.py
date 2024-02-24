import requests, re
from datetime import datetime

import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS
    
@frappe.whitelist()
def itemSaveReq(doc_name):
    eTIMS.itemSaveReq(doc_name)
    

@frappe.whitelist()
def itemSaveComposition(doc_name):
    headers = eTIMS.get_headers()
    
    item = frappe.get_doc("Item", doc_name)
    payload = {
        "itemCd" : item.get("custom_item_code"),
        "cpstItemCd": item.get("custom_item_code"),
        "cpstQty": get_bin_qty(item.get("item_code")),
        "regrNm" : item.owner,
        "regrId" : item.owner
	}

    try:
        response = requests.request(
            "POST",
            eTIMS.tims_base_url() + 'saveItemComposition', 
            json = payload, 
            headers=headers
        )

        response_json = response.json()

        if not response_json.get("resultCd") == '000':
            return {"Error":response_json.get("resultMsg")}
        
        item.custom_composition_saved_in_tims = 1
        item.save()
        return {"Success":response_json.get("resultMsg")}

    except:
        return {"Error":"Oops Bad Request!"}	


@frappe.whitelist()
def importItemUpdateReq(doc_name):
    headers = eTIMS.get_headers()
    import_item = frappe.get_doc("Item", doc_name)
    
    if import_item.custom_is_import_item == 1:
        declr_date = datetime.strftime(import_item.get("custom_declaration_date"), "%Y%m%d")
        
        payload = {
            "taskCd": import_item.get("custom_task_code"),
            "dclDe": declr_date,
            "itemSeq": 1,
            "hsCd": import_item.get("custom_hs_code"),
            "itemClsCd": import_item.get("custom_item_classification_code"),
            "itemCd": import_item.get("custom_item_code"),
            "imptItemSttsCd": get_status_code(import_item.get("custom_import_item_status_code")),
            "remark": import_item.get("custom_remark"),
            "modrId": import_item.get("modified_by"),
            "modrNm": import_item.get("modified_by")
        }
        try:
            
            response = requests.request(
                "POST", 
                eTIMS.tims_base_url() + 'updateImportItem', 
                json = payload, 
                headers=headers
            )
            response_json = response.json()

            if not response_json.get("resultCd") == '000':
                return {"Error":response_json.get("resultMsg")}

            return {"Success":response_json.get("resultMsg")}

        except:
            return {"Error":"Oops Bad Request!"}	       	
    
def get_status_code(code_name):    
    if code_name == "Unsent":
        return 1
    elif code_name == "Waiting":
        return 2
    elif code_name == "Approved":
        return 3
    else:
        return 4
                
def autofill_tims_info(doc, method):
    '''
    Method autofills tims info for item
    '''
    if doc.custom_update_item_to_tims == 1:
        doc.custom_item_name = doc.item_code
        doc.custom_item_standard_name = doc.item_name
        doc.custom_quantity_unit_code = get_item_qty_unit_codes(doc.custom_default_quantity_unit)
        doc.custom_packaging_unit_code = get_item_pkg_unit_codes(doc.custom_default_packing_unit)
        doc.custom_used__unused = get_item_status(doc)
        # doc.custom_group1_unit_price = get_item_prices(doc)
        # doc.custom_group2_unit_price = get_item_prices(doc)
        # doc.custom_group3_unit_price = get_item_prices(doc)
        # doc.custom_group4_unit_price = get_item_prices(doc)
        doc.custom_item_type_code = get_item_type_code(doc)
        doc.custom_registration_id = doc.owner
        doc.custom_registration_name = doc.owner
        doc.custom_modifier_id = doc.modified_by
        doc.custom_modifier_name = doc.modified_by

        if doc.taxes:
            for tax_item in doc.taxes:
                doc.custom_taxation_type_code = get_taxation_type(tax_item.get("item_tax_template"))
        else:
            frappe.throw("Tax template for Item is required!")
        
        if not doc.custom_default_unit_price:
            doc.custom_default_unit_price = get_item_prices(doc)
        
        if not doc.custom_item_code:
            doc.custom_item_code = get_item_code(doc)


        
def get_item_pkg_unit_codes(pkg_unit):
    try:
        etims_code_doc = frappe.get_doc("eTIMS Packing Unit", pkg_unit)
        if etims_code_doc:
            return etims_code_doc.get("etims_code")
    except:
        return


def get_item_qty_unit_codes(qty_unit):
    try:
        etims_code_doc = frappe.get_doc("eTIMS Quantity Unit", qty_unit)
        if etims_code_doc:
            return etims_code_doc.get("etims_code")
    except:
        return       
    
def get_item_status(doc):
    if not doc.disabled:
        return "Y"
    else:
        return "N"
    
def get_taxation_type(tax_template):
    tax_list = []
    if tax_template:
        tax_doc = frappe.get_doc("Item Tax Template", tax_template)

        if not tax_doc.get("custom_code") in tax_list:
            tax_list.append(tax_doc.get("custom_code"))
                
    return tax_list[0]

def get_item_prices(doc):
    if not doc.custom_default_unit_price:
        item_price_doc = frappe.db.get_all("Item Price", filters={"item_code": doc.item_code, "selling":1, "customer": ""}, fields=["price_list_rate"])
        
        if item_price_doc:
            
            return item_price_doc[0].get("price_list_rate")
        else:
            frappe.throw("Price list for Item is required!")
    
def get_item_type_code(doc):
    item_type_doc = frappe.get_doc("Item Group", doc.item_group)
    
    if item_type_doc:
        return item_type_doc.get("custom_etims_item_type_code")
    
def get_item_code(doc):
    if doc.custom_origin_place_code_nation:
        str_item_code = doc.custom_origin_place_code_nation + str(get_item_type_code(doc)) + get_item_pkg_unit_codes(doc.custom_default_packing_unit) + get_item_qty_unit_codes(doc.custom_default_quantity_unit)
    
        item_code = str(str_item_code) + create_item_digit_code(doc)
    
        return item_code
    
def item_code_increment(doc):
    item_code_list = []
    item_codes_dgt_list = []
    tims_item_codes = frappe.db.get_all("Item",
                                        filters = {'name': ['!=', doc.name]},
                                        fields=['custom_item_code']
                                    )
    if tims_item_codes:
        for item in tims_item_codes:
            if  item.get("custom_item_code"):
                if not item.get("custom_item_code") in item_code_list and len(item.get("custom_item_code")) > 10:
                    item_code_list.append(item.get("custom_item_code"))

            for code in item_code_list:
                start = int(len(code) - 7)
                end = len(code)
                code_dgt = code[start: end]
                
                if not code_dgt in item_codes_dgt_list:
                    item_codes_dgt_list.append(code_dgt)
                    
    return item_codes_dgt_list

def create_item_digit_code(doc):
    item_codes = item_code_increment(doc)
    item_code_dgt = "0000001"
    digit_code_list = []
    
    if len(item_codes) > 0:
        for item in item_codes:
            if not item in digit_code_list:
                digit_code_list.append(int(item))
                
        largest_no = max(digit_code_list)
        next_dgt = largest_no + 1
        
        padded_num = str(next_dgt).rjust(7, '0')
        return padded_num
    
    else:
        return item_code_dgt

def get_bin_qty(item_code):
    bin_docs = frappe.db.get_all("Bin", filters={"item_code":item_code}, fields=["actual_qty"])
    
    if bin_docs:

        return bin_docs[0].get("actual_qty")
    else:
        return 0