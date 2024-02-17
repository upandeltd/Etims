import requests

import frappe
from kenya_tims_compliance.utils.etims_utils import eTIMS

def update_stock_to_etims(doc, method):
    item_count = 0
    request_date = doc.posting_date
    request_time = doc.posting_time
    
    date_str = eTIMS.strf_date_object(request_date)
    time_str = eTIMS.strf_time(request_time)
    
    for item in doc.items:
            item_count += 1
    
    # if doc.custom_send_stock_info_to_tims:
    if doc.stock_entry_type == "Material Receipt":

            #logic for stock in
            stockIOSaveReq(doc, date_str, item_count, "4")
            
    if doc.stock_entry_type == "Material Transfer":
        is_inter_branch = check_if_interbranch()
        
        if is_inter_branch:
            stockIOSaveReq(doc, date_str, item_count, "13")
        #get warehouse branch if intrbranch is true
        #logic fot transfer within branches
    
        
def stockIOSaveReq(doc, date_str, item_count, sar_type):    
    headers = eTIMS.get_headers()
    payload = {
        "sarNo": get_etims_sar_no(doc),
        "orgSarNo": 0,
        "regTyCd": "A",
        # "custTin": doc.custom_pin,
        # "custNm": doc.customer,
        # "custBhfId":null,
        "ocrnDt": date_str,
        "totItemCnt": item_count,
        "totTaxblAmt": doc.total_incoming_value,
        "totTaxAmt": "doc.base_total_taxes_and_charges",#########################
        "totAmt": doc.total_incoming_value,
        "remark": doc.remarks,
        "regrId": doc.owner,
        "regrNm": doc.owner,
        "modrId": doc.modified_by,
        "modrNm": doc.modified_by,
        "sarTyCd": sar_type,
        "itemList": etims_stock_item_list(doc)
        }
    
        
    if doc.custom_send_stock_info_to_tims == 1:
        if not doc.custom_updated_in_tims == 1:
            try:
                response = requests.request(
                            "POST", 
                            eTIMS.tims_base_url() + 'insertStockIO',
                            json = payload, 
                            headers=headers
                        )
            
                response_json = response.json()

                if not response_json.get("resultCd") == '000':
                    return {"Error":response_json.get("resultMsg")}
                        
                return {"Success": response_json.get("resultMsg")}

            except:
                    return {"Error":"Oops Bad Request!"}
    else:
        print(payload)

def get_etims_sar_no(doc):
    etims_sar_no = 1
    try:
        etims_sar_docs = frappe.get_last_doc("eTIMS Stock Release Number")
        
        new_sar_no = etims_sar_docs.get("sr_number") + 1
        
        new_doc = frappe.new_doc("eTIMS Stock Release Number") 
        new_doc.reference_type = "Stock Entry"
        new_doc.reference = doc.name
        new_doc.sr_number = new_sar_no
        # new_doc.orginal_sr_number = get_org_etims_sar_no(doc)
        new_doc.insert()
        frappe.db.commit()

        return new_sar_no
    except:
        new_doc = frappe.new_doc("eTIMS Stock Release Number") 
        new_doc.reference_type = "Stock Entry"
        new_doc.reference = doc.name
        new_doc.sr_number = etims_sar_no 
        # new_doc.orginal_sr_number = get_org_etims_sar_no(doc)
        new_doc.insert()
        frappe.db.commit()

        return etims_sar_no
    
# def get_org_etims_sar_no(doc):
#     org_etims_sar_no = 0
    
#     if doc.custom_original_invoice_number:
#         prev_doc  = frappe.db.get_all("eTIMS Stock Release Number", filters={"reference": doc.amended_from}, fields=["sr_number"])
        
#         org_etims_sar_no = prev_doc[0].get("sr_number")
    
#         return org_etims_sar_no
#     else:

#         return org_etims_sar_no
    
def check_if_interbranch(item):
    interbranch_transfer = False
    
    s_warehouse = item.get("s_warehouse")
    t_warehouse = item.get("t_warehouse")
    
    s_warehouse_doc = frappe.get_doc("Warehouse", s_warehouse)
    t_warehouse_doc = frappe.get_doc("Warehouse", t_warehouse)
    
    if s_warehouse_doc.get("custom_tax_branch_office") and t_warehouse_doc.get("custom_tax_branch_office"):
    
        if not s_warehouse_doc.get("custom_tax_branch_office") == t_warehouse_doc.get("custom_tax_branch_office"):
            interbranch_transfer = True
            
    else:
        pass
    
    return interbranch_transfer

def etims_stock_item_list(doc):
    stock_item_list = []
    for item in doc.items:
        item_tax_details = get_tax_template_details(item.get("item_code")) ####################################
        item_detail = frappe.db.get_all("Item", filters={"disabled": 0, "item_code": item.get("item_code")}, fields = ["*"])
        item_etims_data = {
					"itemSeq": item.get("idx"),
					"itemCd": item_detail[0].get("custom_item_code"),
					"itemClsCd": item_detail[0].get("custom_item_classification_code"),
					"itemNm": item_detail[0].get("custom_item_name"),
					# "bcd":null,
					"pkgUnitCd": item_detail[0].get("custom_packaging_unit_code"),
					"pkg": item.get("qty"),
					"qtyUnitCd": item_detail[0].get("custom_quantity_unit_code"),
					"qty": item.get("qty"),
					"prc": item.get("basic_rate"),
					"splyAmt": item.get("basic_amount"),
					"dcRt": 0.0,
					"dcAmt": 0.0,
					# "isrccCd":null,
					# "isrccNm":null,
					# "isrcRt":null,
					# "isrcAmt":null,
                    "totDcAmt": 0.0,
					# "taxTyCd": item_tax_details.get("tax_code"),
					# "taxblAmt": item.get("basic_amount"),###############################
					# "taxAmt": round((item.get("amount") - item.get("net_amount")), 2),###############################
					# "totAmt": item.get("amount")###############################
				}

        if not item_etims_data in stock_item_list:
            stock_item_list.append(item_etims_data)
            
    return stock_item_list

def get_tax_template_details(template_name):
    tax_temp_list = []
    tax_doc = frappe.get_doc("Item Tax Template", template_name)
    if tax_doc:
        for tax_item in tax_doc.taxes:
            tax_details = {
                "rate": tax_item.tax_rate,
                "tax_code": tax_item.custom_code,
                "tax_name": tax_item.custom_code_name
            }

            if not tax_details in tax_temp_list:
                tax_temp_list.append(tax_details)
    
        return tax_temp_list[0]
    else:
        return "D"