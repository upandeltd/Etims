import requests

import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS

def insert_tax_rate_and_amount(doc, method):
    total_taxable_amount = 0
    total_amount = 0
    main_tax_amount = 0
    
    if doc.items:
        for item in doc.items:
            if item.get("custom_tax_code"):
                account_head_list = frappe.db.get_all("Account", filters={"account_type": "Tax", "custom_tax_code": item.get("custom_tax_code")}, fields=["tax_rate"])
              
                if account_head_list:
                    item.custom_rate = account_head_list[0].get("tax_rate")

                if account_head_list[0].get("tax_rate") > 0:
                    if item.get("basic_amount"):
                        tax_rate = account_head_list[0].get("tax_rate")/100
                        taxable_amount = item.get("basic_amount")/(1+tax_rate)
                        tax_amount = item.get("basic_amount") - taxable_amount
                        
                        item.custom_tax_amount = round(tax_amount, 2)
                        main_tax_amount += tax_amount
                        total_amount += item.get("basic_amount")
                        total_taxable_amount = round((total_amount - main_tax_amount), 2)
                    
        doc.custom_total_tax_amount = round(main_tax_amount, 2)
        doc.custom_total_taxable_amount = total_taxable_amount

def update_stock_to_etims(doc, method):
    item_count = 0
    request_date = doc.posting_date
    request_time = doc.posting_time
    s_warehouse_id = ""
    t_warehouse_id = ""
    
    date_str = eTIMS.strf_date_object(request_date)
    time_str = eTIMS.strf_time(request_time)

    if doc.from_warehouse:
        
        s_warehouse_id = get_warehouse_branch(doc.from_warehouse)
    if doc.to_warehouse:
        
        t_warehouse_id = get_warehouse_branch(doc.to_warehouse)
    
    for item in doc.items:
            item_count += 1
    
    # if doc.custom_send_stock_info_to_tims:
    if doc.stock_entry_type == "Material Receipt":
            # if doc.custom_is_import_item == 1:
            #     stockIOSaveReq(doc, date_str, item_count, "01", t_warehouse_id)
            # else:
                #logic for stock in
        stockIOSaveReq(doc, date_str, item_count, "06", t_warehouse_id)
            
    if doc.stock_entry_type == "Material Transfer":
        is_inter_branch = check_if_interbranch(doc)
        
        if is_inter_branch:
            if doc.custom_update_both_branches:
                stockIOSaveReq(doc, date_str, item_count, "13", t_warehouse_id)
                stockIOSaveReq(doc, date_str, item_count, "04", t_warehouse_id)
            elif doc.custom_update_from_branch_only:
                stockIOSaveReq(doc, date_str, item_count, "13", t_warehouse_id)
            else:
                stockIOSaveReq(doc, date_str, item_count, "04", t_warehouse_id)
        #get warehouse branch if intrbranch is true
        #logic fot transfer within branches
    
        
def stockIOSaveReq(doc, date_str, item_count, sar_type, branch_id):    
    # headers = get_headers(branch_id)
    headers = eTIMS.get_headers()
    payload = {
        "sarNo": get_etims_sar_no(doc),
        "orgSarNo": 0,
        "regTyCd": "A",
        "custTin": headers.get("tin"),
        # "custNm": doc.customer,
        "custBhfId": branch_id,
        "ocrnDt": date_str,
        "totItemCnt": item_count,
        "totTaxblAmt": doc.custom_total_taxable_amount,
        "totTaxAmt": doc.custom_total_tax_amount,
        "totAmt": round(doc.total_incoming_value, 2),
        "remark": doc.remarks,
        "regrId": doc.owner,
        "regrNm": doc.owner,
        "modrId": doc.modified_by,
        "modrNm": doc.modified_by,
        "sarTyCd": sar_type,
        "itemList": etims_stock_item_list(doc)
        }
    
        
    if doc.custom_send_stock_info_to_etims == 1:
        if not doc.custom_updated_in_etims == 1:
            try:
                response = requests.request(
                            "POST", 
                            eTIMS.tims_base_url() + 'insertStockIO',
                            json = payload, 
                            headers=headers
                        )
            
                response_json = response.json()

                if not response_json.get("resultCd") == '000':
                    print(response_json.get("resultMsg"))
                    # eTIMS.log_errors("Stock Entry", response_json.get("resultMsg"))
                    frappe.throw(response_json.get("resultMsg"))
                   
                
                doc.custom_updated_in_etims = 1   
                frappe.msgprint(response_json.get("resultMsg"))

            except:
                
                frappe.throw("Error: Oops Bad Request!")
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
    
    s_warehouse = item.get("from_warehouse")
    t_warehouse = item.get("to_warehouse")
    
    s_warehouse_doc = frappe.get_doc("Warehouse", s_warehouse)
    t_warehouse_doc = frappe.get_doc("Warehouse", t_warehouse)
    
    if s_warehouse_doc.get("custom_tax_branch_office") and t_warehouse_doc.get("custom_tax_branch_office"):
    
        if not s_warehouse_doc.get("custom_tax_branch_office") == t_warehouse_doc.get("custom_tax_branch_office"):
            interbranch_transfer = True
            
    else:
        pass
    
    return interbranch_transfer

def get_warehouse_branch(warehouse_name):
    try:
        warehouse_doc = frappe.get_doc("Warehouse", warehouse_name)
        
        return warehouse_doc.get("custom_tax_branch_office")
    except:
        frappe.throw("No tax branch id")
    
    

def etims_stock_item_list(doc):
    stock_item_list = []
    for item in doc.items:
        item_tax_code = get_tax_template_details(item.get("item_code"))
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
					"prc": round(item.get("basic_rate"), 2),
					"splyAmt": item.get("basic_amount"),
					"dcRt": 0.0,
					"dcAmt": 0.0,
					# "isrccCd":null,
					# "isrccNm":null,
					# "isrcRt":null,
					# "isrcAmt":null,
                    "totDcAmt": 0.0,
					"taxTyCd": item_tax_code,
					"taxblAmt": round((item.get("amount") - item.get("custom_tax_amount")), 2),
					"taxAmt": item.get("custom_tax_amount"),
					"totAmt": round(item.get("amount"), 2)
				}

        if not item_etims_data in stock_item_list:
            stock_item_list.append(item_etims_data)
            
    return stock_item_list

def get_tax_template_details(item_code):
    item_doc = frappe.get_doc("Item", item_code)
    if item_doc:
        for tax_item in item_doc.taxes:
            tax_code = frappe.get_doc("Item Tax Template", tax_item.get("item_tax_template"))
            
            if tax_code:
                return tax_code.get("custom_code")
    else:
        return "D"
    
def get_headers(branch_id):
    header_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id}, fields=["*"])
        
    if header_docs:
        headers = {
            "tin":header_docs[0].get("pin"),
            "bhfId":header_docs[0].get("branch_id"),
            "cmcKey":header_docs[0].get("communication_key"),
        }
        
        return headers