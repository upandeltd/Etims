import requests
from datetime import datetime

import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS
def validate(doc, method):
    '''
    Method validate invoice number before submitting invoice
    '''
    if doc.custom_invoice_number and doc.name:
        doc_exists = frappe.db.exists("Purchase Invoice", {"name": doc.name})

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
        
        frappe.db.set_value('Purchase Invoice', doc.name, 'custom_invoice_number', last_inv_number, update_modified=True)
        insert_tax_amounts(doc)
        total_vat_amount = fetch_total_vat(doc)
        total_non_vat_amount = fetch_total_non_vat(doc)
        
        frappe.db.set_value('Purchase Invoice', doc.name,
                            { 
                                "custom_total_taxable_amount": total_vat_amount,
                                "custom_total_nontaxable_amount": total_non_vat_amount
                            },
                            update_modified=True)
        
        doc.reload()
    
def insert_tax_amounts(doc):
    taxable_amounts = get_taxable_amounts(doc)
    for key, value in taxable_amounts.items():
        try:
            if doc.taxes:
                for item in doc.taxes:
                    if item.get("custom_code") == key:
                        frappe.db.set_value('Purchase Taxes and Charges', item.get("name"), 'custom_total_taxable_amount', round(value, 2), update_modified=True)
        except:
            frappe.throw(Exception)

def get_taxable_amounts(doc):
    taxable_amounts_dict = {}
    
    try:
        if doc.items:
            for item in doc.items:
                if not item.get("custom_tax_code") in taxable_amounts_dict.keys():
                    taxable_amounts_dict[item.get("custom_tax_code")] = 0
                
                taxable_amounts_dict[item.get("custom_tax_code")] += item.net_amount
    except:
        frappe.throw(Exception)
        
    return taxable_amounts_dict

def fetch_total_vat(doc):
    taxable_amount = 0
    if doc.taxes:
        for item in doc.taxes:
            if item.get("base_tax_amount_after_discount_amount") > 0:
                taxable_amount += item.get("custom_total_taxable_amount")
                
    return taxable_amount
    
def fetch_total_non_vat(doc):
    taxable_non_vat_amount = 0
    if doc.taxes:
        for item in doc.taxes:
            if item.get("base_tax_amount_after_discount_amount") == 0:
                taxable_non_vat_amount += item.get("custom_total_taxable_amount")
                
    return taxable_non_vat_amount

@frappe.whitelist()
def trnsPurchaseSaveReq(doc, method):
    headers = eTIMS.get_headers()
    supplier_details = get_supplier_details(doc.supplier)
    
    tax_code_list = []
    
    headers = eTIMS.get_headers()
    
    request_date_and_time = doc.creation
   
    conc_datetime_str = eTIMS.strf_datetime_format(request_date_and_time)
       
    now = datetime.now()
    date_time_str = now.strftime("%Y%m%d%H%M%S")
    
    request_date = doc.posting_date
    date_str = eTIMS.strf_date_object(request_date)
	
    count = 0
    
    for item in doc.items:
        count += 1
        
    payload ={
        "invcNo": doc.custom_invoice_number,
        "orgInvcNo": doc.custom_original_invoice_number,
        "spplrTin":supplier_details.get("supp_pin"),
        "spplrBhfId":supplier_details.get("supp_bhid"),
        "spplrNm":doc.supplier,
        "spplrInvcNo":doc.bill_no,
        "regTyCd": doc.custom_registration_type_code,
        "pchsTyCd": doc.custom_purchase_type_code,
        "rcptTyCd": doc.custom_receipt_type_code,
        "pmtTyCd": doc.custom_payment_type_code,
        "pchsSttsCd": doc.custom_purchase_status_code,
        "cfmDt": date_time_str,
        "pchsDt": date_str,
        "totItemCnt": count,
        "totTaxblAmt":doc.custom_total_taxable_amount,
        "totTaxAmt":doc.base_total_taxes_and_charges,
        "totAmt":doc.grand_total,
        "remark": doc.remarks,
        "regrId": doc.owner,
        "regrNm": doc.owner,
        "modrId": doc.modified_by,
        "modrNm": doc.modified_by,
        "itemList":etims_sale_item_list(doc)
    }
    
    for tax_item in doc.taxes:
        if not tax_item.get("custom_code") in tax_code_list:
            tax_code_list.append(tax_item.get("custom_code")) 
        
        if "A" in tax_code_list:
            if tax_item.custom_code == "A":
                payload["taxblAmtA"] = round((tax_item.get("custom_total_taxable_amount") + tax_item.get("tax_amount_after_discount_amount")), 2)
                payload["taxRtA"] =  get_tax_account_rate(tax_item.get("account_head"))
                payload["taxAmtA"] = tax_item.get("tax_amount_after_discount_amount")
        else:
            payload["taxblAmtA"] = 0
            payload["taxRtA"] =  0
            payload["taxAmtA"] = 0
        
        if "B" in tax_code_list:
            if tax_item.custom_code == "B":
                payload["taxblAmtB"] = round((tax_item.get("custom_total_taxable_amount") + tax_item.get("tax_amount_after_discount_amount")), 2)
                payload["taxRtB"] =  get_tax_account_rate(tax_item.get("account_head"))
                payload["taxAmtB"] = tax_item.get("tax_amount_after_discount_amount")
        else:
            payload["taxblAmtB"] = 0
            payload["taxRtB"] =  0
            payload["taxAmtB"] = 0
            
        if "C" in tax_code_list:
            if tax_item.custom_code == "C":
                payload["taxblAmtC"] = round((tax_item.get("custom_total_taxable_amount") + tax_item.get("tax_amount_after_discount_amount")), 2)
                payload["taxRtC"] =  get_tax_account_rate(tax_item.get("account_head"))
                payload["taxAmtC"] = tax_item.get("tax_amount_after_discount_amount")
        else:
            payload["taxblAmtC"] = 0
            payload["taxRtC"] =  0
            payload["taxAmtC"] = 0
            
        if "D" in tax_code_list:
            if tax_item.custom_code == "D":
                payload["taxblAmtD"] = round((tax_item.get("custom_total_taxable_amount") + tax_item.get("tax_amount_after_discount_amount")), 2)
                payload["taxRtD"] =  get_tax_account_rate(tax_item.get("account_head"))
                payload["taxAmtD"] = tax_item.get("tax_amount_after_discount_amount")
        else:
            payload["taxblAmtD"] = 0
            payload["taxRtD"] =  0
            payload["taxAmtD"] = 0
            
        if "E" in tax_code_list:
            if tax_item.custom_code == "E":
                payload["taxblAmtE"] = round((tax_item.get("custom_total_taxable_amount") + tax_item.get("tax_amount_after_discount_amount")), 2)
                payload["taxRtE"] =  get_tax_account_rate(tax_item.get("account_head"))
                payload["taxAmtE"] = tax_item.get("tax_amount_after_discount_amount")
        else:
            payload["taxblAmtE"] = 0
            payload["taxRtE"] =  0
            payload["taxAmtE"] = 0
            
    if doc.custom_original_invoice_number:
        payload["wrhsDt"] = date_time_str
        payload["cnclReqDt"] = conc_datetime_str
        payload["cnclDt"] = conc_datetime_str
        
    if doc.is_return:
        payload["rfdDt"] = conc_datetime_str

    if doc.custom_update_purchase_in_tims:
        try:
            response = requests.request(
                    "POST", 
                    eTIMS.tims_base_url() + 'insertTrnsPurchase', 
                    json = payload, 
                    headers=headers
                )
            response_json = response.json()

            if not response_json.get("resultCd") == '000':
                return {"Error":response_json.get("resultMsg")}
            
            stockIOSaveReq(doc, date_str, count)
            doc.custom_item_updated_in_tims = 1
            
            frappe.msgprint(response_json.get("resultMsg"))

        except:
            frappe.throw("Error")
    else:
        print(payload)
        stockIOSaveReq(doc, date_str, count)
        return

def stockIOSaveReq(doc, date_str, item_count):
    headers = eTIMS.get_headers()
    payload = {
        "sarNo": get_etims_sar_no(doc),
        "orgSarNo": get_org_etims_sar_no(doc),
        "regTyCd":"A",
        "custTin": headers.get("tin"),
        # "custNm":null,
        "custBhfId": eTIMS.get_user_branch_id(),
        "ocrnDt": date_str,
        "totItemCnt": item_count,
        "totTaxblAmt": doc.custom_total_taxable_amount,
        "totTaxAmt": doc.base_total_taxes_and_charges,
        "totAmt": doc.grand_total,
        "remark": doc.remarks,
        "regrId": doc.owner,
        "regrNm": doc.owner,
        "modrId": doc.modified_by,
        "modrNm": doc.modified_by,
        "itemList": etims_sale_item_list(doc)
        }
    
    if doc.custom_original_invoice_number != 0 or doc.is_return == 1: 
        payload["sarTyCd"] = "12"
    elif doc.custom_import_purchase == 1:
        payload["sarTyCd"] = "01"
    else:
        payload["sarTyCd"] = "02"
    
    if doc.custom_update_purchase_in_tims:
        try:
            response = requests.request(
                        "POST", 
                        eTIMS.tims_base_url() + 'insertStockIO',
                        json = payload, 
                        headers=headers
                    )
        
            response_json = response.json()
            # print(response_json)
            if not response_json.get("resultCd") == '000':
                return {"Error":response_json.get("resultMsg")}
                    
            return {"Success": response_json.get("resultMsg")}

        except:
                return {"Error":"Oops Bad Request!"}
    
    else:
        print(payload)
        return
        
def get_etims_sar_no(doc):
    etims_sar_no = 1
    try:
        etims_sar_docs = frappe.get_last_doc("eTIMS Stock Release Number")
        
        new_sar_no = etims_sar_docs.get("sr_number") + 1
        
        new_doc = frappe.new_doc("eTIMS Stock Release Number") 
        new_doc.reference_type = "Purchase Invoice"
        new_doc.reference = doc.name
        new_doc.sr_number = new_sar_no
        new_doc.orginal_sr_number = get_org_etims_sar_no(doc)
        new_doc.insert()
        frappe.db.commit()

        return new_sar_no
    except:
        new_doc = frappe.new_doc("eTIMS Stock Release Number") 
        new_doc.reference_type = "Purchase Invoice"
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

def get_supplier_details(supplier):
    supplier_kra_details = frappe.get_doc("Supplier", supplier)
    
    supp_dict = {
        "supp_pin": supplier_kra_details.get("custom_supplier_pin"),
        "supp_bhid": supplier_kra_details.get("custom_branch_id")
    }
    
    return supp_dict
    
def get_last_inv_number(doc):
    last_invoice_no_doc = frappe.get_doc("TIS Settings")
    invoice_number = 0
    last_inv_no = last_invoice_no_doc.get("last_purchase_invoice_number")
    
    try:
        last_inv = frappe.db.get_all("Purchase Invoice",
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
   
    
def get_original_invoice_number(doc):
    org_invoice_no = 0
    
    if doc.amended_from:
        org_invoice = frappe.get_all("Purchase Invoice", filters={"name":doc.amended_from}, fields = ["custom_invoice_number"])

        org_invoice_no = org_invoice[0].get("custom_invoice_number")
    
    else:
        return org_invoice_no
    

def validate_inv_number(doc):
    invoice_numbers = []
    invoice_number_list = frappe.db.get_all("Purchase Invoice", fields = ["custom_invoice_number", "name"], order_by='custom_invoice_number desc')
    
    if invoice_number_list:
        for invoice_no in invoice_number_list:
            if not invoice_no.get("name") == doc.name:
                if not invoice_no.get("custom_invoice_number") in invoice_numbers:
                    invoice_numbers.append(invoice_no.get("custom_invoice_number"))
                
    return invoice_numbers

def etims_sale_item_list(doc):
    sales_item_list = []
    for item in doc.items:
        item_tax_details = get_tax_template_details(item.get("item_code"))
        item_detail = frappe.db.get_all("Item", filters={"disabled": 0, "item_code": item.get("item_code")}, fields = ["*"])
        item_tax_amount = format(item.get("amount") * (eTIMS.get_default_tax_rate_b()/100), ".2f")
        
        barcode = eTIMS.get_item_barcode(item.item_code, item.uom)
        
        item_etims_data = {
                    "itemSeq": item.get("idx"),
					"itemCd": item_detail[0].get("custom_item_code"),
					"itemClsCd": item_detail[0].get("custom_item_classification_code"),
					"itemNm": item_detail[0].get("custom_item_name"),
                    "bcd": barcode,
                    # "spplrItemClsCd":null,
                    # "spplrItemCd":null,
                    # "spplrItemNm": item.item_code,
                    "pkgUnitCd": item_detail[0].get("custom_packaging_unit_code"),
					"pkg":item.get("qty"),
					"qtyUnitCd": item_detail[0].get("custom_quantity_unit_code"),
					"qty": item.get("qty"),
					"prc": item.get("rate"),
					"splyAmt": item.get("amount"),
					"dcRt": item.get("discount_percentage"),
					"dcAmt": item.get("discount_amount"),
                    "taxTyCd": item_tax_details,
					"taxblAmt": item.get("amount"),
					"taxAmt": round((item.get("amount") - item.get("net_amount")), 2),
					"totAmt": item.get("amount"),
                    "totDcAmt": item.get("discount_amount")
                    # "itemExprDt":null
				}
        if not item_etims_data in sales_item_list:
            sales_item_list.append(item_etims_data)
            
    return sales_item_list

def get_tax_template_details(item_code):
    item_doc = frappe.get_doc("Item", item_code)
    if item_doc:
        if item_doc.taxes:
            for tax_item in item_doc.taxes:
                tax_code = frappe.get_doc("Item Tax Template", tax_item.get("item_tax_template"))
                
                if tax_code:
                    return tax_code.get("custom_code")
    else:
        return "D"
    
def get_tax_account_rate(account_head):
    tax_acc_docs = frappe.db.get_all("Account", filters={"name": account_head}, fields=["tax_rate"])
    
    if tax_acc_docs:
        tax_rate = tax_acc_docs[0].get("tax_rate")
        
        return tax_rate