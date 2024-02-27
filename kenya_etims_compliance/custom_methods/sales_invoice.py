import requests
from datetime import datetime, timedelta, time

import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS

def validate(doc, method):
    '''
    Method validate invoice number before submitting invoice
    '''
    if doc.custom_invoice_number and doc.name:
        doc_exists = frappe.db.exists("Sales Invoice", {"name": doc.name})

        if doc_exists:
            invoice_numbers = validate_inv_number(doc)
        
            if doc.custom_invoice_number in invoice_numbers:
                insert_invoice_number(doc, method)
    
    
def insert_invoice_number(doc,method):
    '''
    Method sets increment for invoice number and orginal invoice number before submitting invoice
    '''
    if doc.name:
        last_inv_number = get_last_inv_number(doc)
        
        frappe.db.set_value('Sales Invoice', doc.name, 'custom_invoice_number', last_inv_number, update_modified=True)
        
        doc.reload()

def trnsSalesSaveWrReq(doc, method):
    '''
    Method that collects sales information and updates it to tims server
    '''
    headers = eTIMS.get_headers()
    
    request_date = doc.posting_date
    request_time = doc.posting_time
   
    date_str = eTIMS.strf_date_object(request_date)
    time_str = eTIMS.strf_time(request_time)
    
    conc_datetime_str = date_str + time_str
   
    date_str = eTIMS.strf_date_object(request_date)
    
    now = datetime.now()
    date_time_str = now.strftime("%Y%m%d%H%M%S")
	
    count = 0
    for item in doc.items:
        count += 1
  
    payload = {
        "trdInvcNo": doc.name,
        "invcNo": doc.custom_invoice_number,
        "orgInvcNo": doc.custom_original_invoice_number,
        "custTin": doc.custom_pin,
        "custNm": doc.customer,
        "salesTyCd": doc.custom_sales_type_code,
        "rcptTyCd": doc.custom_receipt_type_code,
        "pmtTyCd": doc.custom_payment_type_code,
        "salesSttsCd": doc.custom_invoice_status_code,
        "cfmDt": conc_datetime_str,
        "salesDt": date_str,
        "stockRlsDt": date_time_str,
        "totItemCnt": count,
        "totTaxblAmt":doc.grand_total,
        "totTaxAmt":doc.base_total_taxes_and_charges,
        "totAmt":doc.grand_total,
        "prchrAcptcYn":"N",
        "remark": doc.remarks,
        "regrId": doc.owner,
        "regrNm": doc.owner,
        "modrId": doc.modified_by,
        "modrNm": doc.modified_by,
        "receipt":{
            "custTin": doc.custom_pin,
            # "custMblNo":null,
            "rcptPbctDt": date_time_str,
            # "trdeNm":null,
            # "adrs":null,
            # "topMsg":null,
            # "btmMsg":null,
            "prchrAcptcYn":"N"
            },
        "itemList": etims_sale_item_list(doc)
    }
    
    for tax_item in doc.taxes:
        if tax_item.custom_code == "A":
            if not tax_item.get("tax_amount_after_discount_amount") > 0:
                payload["taxblAmtA"] = 0
                payload["taxRtA"] =  tax_item.get("rate")
                payload["taxAmtA"] = tax_item.get("tax_amount_after_discount_amount")
            else:
                payload["taxblAmtA"] = tax_item.get("base_total")
                payload["taxRtA"] =  tax_item.get("rate")
                payload["taxAmtA"] = tax_item.get("tax_amount_after_discount_amount")
          
        if tax_item.custom_code == "B":
            if not tax_item.get("tax_amount_after_discount_amount") > 0:
                payload["taxblAmtB"] = 0
                payload["taxRtB"] =  tax_item.get("rate")
                payload["taxAmtB"] = tax_item.get("tax_amount_after_discount_amount")
            else:
                payload["taxblAmtB"] = tax_item.get("base_total")
                payload["taxRtB"] =  tax_item.get("rate")
                payload["taxAmtB"] = tax_item.get("tax_amount_after_discount_amount")
        
        if tax_item.custom_code == "C":
            if not tax_item.get("tax_amount_after_discount_amount") > 0:
                payload["taxblAmtC"] = 0
                payload["taxRtC"] =  tax_item.get("rate")
                payload["taxAmtC"] = tax_item.get("tax_amount_after_discount_amount")
            else:
                payload["taxblAmtC"] = tax_item.get("base_total")
                payload["taxRtC"] =  tax_item.get("rate")
                payload["taxAmtC"] = tax_item.get("tax_amount_after_discount_amount")
          
        if tax_item.custom_code == "D":
            if not tax_item.get("tax_amount_after_discount_amount") > 0:
                payload["taxblAmtD"] = 0
                payload["taxRtD"] =  tax_item.get("rate")
                payload["taxAmtD"] = tax_item.get("tax_amount_after_discount_amount")
            else:
                payload["taxblAmtD"] = tax_item.get("base_total")
                payload["taxRtD"] =  tax_item.get("rate")
                payload["taxAmtD"] = tax_item.get("tax_amount_after_discount_amount")
            
        if tax_item.custom_code == "E":
            if not tax_item.get("tax_amount_after_discount_amount") > 0:
                payload["taxblAmtE"] = 0
                payload["taxRtE"] =  tax_item.get("rate")
                payload["taxAmtE"] = tax_item.get("tax_amount_after_discount_amount")
            else:
                payload["taxblAmtE"] = tax_item.get("base_total")
                payload["taxRtE"] =  tax_item.get("rate")
                payload["taxAmtE"] = tax_item.get("tax_amount_after_discount_amount")
            
    if int(doc.custom_original_invoice_number) > 0:
        payload["cnclReqDt"] = conc_datetime_str
        payload["cnclDt"] = conc_datetime_str
        payload["rfdDt"] = date_time_str
        payload["rfdRsnCd"] = doc.custom_credit_note_reason_code
    
    if doc.custom_update_invoice_in_tims:
        try:
            response = requests.request(
                "POST", 
                eTIMS.tims_base_url() + 'saveTrnsSalesOsdc', 
                json = payload, 
                headers=headers)
            response_json = response.json()

            if not response_json.get("resultCd") == '000':
                return {"Error":response_json.get("resultMsg")}
            
            data = response_json.get("data")
            control_unit_date_time = eTIMS.strp_datetime_object(data.get("sdcDateTime"))
            doc.custom_current_receipt_number = data.get("curRcptNo")
            doc.custom_total_receipt_number = data.get("totRcptNo")
            doc.custom_internal_data = data.get("intrlData")
            doc.custom_receipt_signature = data.get("rcptSign")
            doc.custom_control_unit_date_time = control_unit_date_time
                
            stockIOSaveReq(doc, date_str, count)
            doc.custom_update_sales_to_etims = 1
            
            return {"Success": response_json.get("resultMsg")}

        except:
                return {"Error":"Oops Bad Request!"}
    else:
        print(payload)
        stockIOSaveReq(doc, date_str, count)
        return
        
def stockIOSaveReq(doc, date_str, item_count):
    # sar_no, org_sar_no = get_etims_sar_no(doc)
    
    headers = eTIMS.get_headers()
    payload = {
        "sarNo": get_etims_sar_no(doc),
        "orgSarNo": get_org_etims_sar_no(doc),
        "regTyCd": "A",
        "custTin": doc.custom_pin,
        "custNm": doc.customer,
        "custBhfId": doc.tax_id,
        "ocrnDt": date_str,
        "totItemCnt": item_count,
        "totTaxblAmt": doc.grand_total,
        "totTaxAmt": doc.base_total_taxes_and_charges,
        "totAmt": doc.grand_total,
        "remark": doc.remarks,
        "regrId": doc.owner,
        "regrNm": doc.owner,
        "modrId": doc.modified_by,
        "modrNm": doc.modified_by,
        "itemList": etims_sale_item_list(doc)
        }
    
    if doc.custom_original_invoice_number != 0: 
        payload["sarTyCd"] = "3"
    
    else:
        payload["sarTyCd"] = "11"

    if doc.custom_update_invoice_in_tims:
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
        new_doc.reference_type = "Sales Invoice"
        new_doc.reference = doc.name
        new_doc.sr_number = new_sar_no
        new_doc.orginal_sr_number = get_org_etims_sar_no(doc)
        new_doc.insert()
        frappe.db.commit()

        return new_sar_no
    except:
        new_doc = frappe.new_doc("eTIMS Stock Release Number") 
        new_doc.reference_type = "Sales Invoice"
        new_doc.reference = doc.name
        new_doc.sr_number = etims_sar_no 
        new_doc.orginal_sr_number = get_org_etims_sar_no(doc)
        new_doc.insert()
        frappe.db.commit()

        return etims_sar_no
    
def get_org_etims_sar_no(doc):
    org_etims_sar_no = 0
    
    if doc.custom_original_invoice_number:
        prev_doc  = frappe.db.get_all("eTIMS Stock Release Number", filters={"reference": doc.amended_from}, fields=["sr_number"])
        
        org_etims_sar_no = prev_doc[0].get("sr_number")
    
        return org_etims_sar_no
    else:

        return org_etims_sar_no
    
def get_customer_details(customer):
    customer_kra_details = frappe.get_doc("Customer", customer)
    
    cust_dict = {
        "cust_pin": customer_kra_details.get("custom_customer_pin"),
        "cust_name": customer_kra_details.get("custom_customer_name")
    }
    
    return cust_dict
    
def get_last_inv_number(doc):
    last_invoice_no_doc = frappe.get_doc("TIS Settings")
    invoice_number = 0
    last_inv_no = last_invoice_no_doc.get("last_sales_invoice_number")
    
    try:
        last_inv = frappe.db.get_all("Sales Invoice",
                                        filters = {'name': ['!=', doc.name]},
                                        fields=['custom_invoice_number'],
                                        order_by='custom_invoice_number desc',
                                        page_length = 1
                                    )
        
        if last_inv[0]:
            # print(last_inv)
            last_inv_no = last_inv[0].get("custom_invoice_number")
            
        invoice_number = last_inv_no + 1
        
    except:
        invoice_number = last_inv_no + 1
    
    return invoice_number
   
    
# def get_original_invoice_number(doc):
#     org_invoice_no = 0
    
#     if doc.amended_from:
#         org_invoice = frappe.get_all("Sales Invoice", filters={"name":doc.amended_from}, fields = ["custom_invoice_number"])

#         org_invoice_no = org_invoice[0].get("custom_invoice_number")
        
#         return org_invoice_no
#     else:
       
#         return org_invoice_no


def validate_inv_number(doc):
    invoice_numbers = []
    invoice_number_list = frappe.db.get_all("Sales Invoice", fields = ["custom_invoice_number", "name"], order_by='custom_invoice_number desc')
    
    if invoice_number_list:
        for invoice_no in invoice_number_list:
            if not invoice_no.get("name") == doc.name:
                if not invoice_no.get("custom_invoice_number") in invoice_numbers:
                    invoice_numbers.append(invoice_no.get("custom_invoice_number"))
                
    return invoice_numbers

def etims_sale_item_list(doc):
    sales_item_list = []
    for item in doc.items:
        item_tax_code = get_tax_template_details(item.get("item_tax_template"))
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
					"prc": item.get("rate"),
					"splyAmt": item.get("amount"),
					"dcRt": item.get("discount_percentage"),
					"dcAmt": item.get("discount_amount"),
					# "isrccCd":null,
					# "isrccNm":null,
					# "isrcRt":null,
					# "isrcAmt":null,
                    "totDcAmt": item.get("discount_amount"),
					"taxTyCd": item_tax_code,
					"taxblAmt": item.get("amount"),
					"taxAmt": round((item.get("amount") - item.get("net_amount")), 2),
					"totAmt": item.get("amount")
				}

        if not item_etims_data in sales_item_list:
            sales_item_list.append(item_etims_data)
            
    return sales_item_list

def get_tax_template_details(template_name):
    tax_doc = frappe.get_doc("Item Tax Template", template_name)
    if tax_doc:
      
        tax_code =  tax_doc.custom_code
    
        return tax_code
    else:
        return "D"