import requests, segno, json  #pyqrcode
from datetime import datetime, timedelta, time

import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS


def validate(doc, method):
    '''
    Validation meethod
    '''
    if doc.name:
        doc_exists = frappe.db.exists("Sales Invoice", {"name": doc.name})

        if doc_exists:
            insert_tax_details(doc, method)
    
def insert_tax_details(doc,method):
    '''
    Method sets tax details e.g taxable amounts
    '''
    if doc.name and doc.custom_update_invoice_in_tims:                
        if doc.items:
            insert_tax_amounts(doc)
                
def insert_tax_amounts(doc):
    if doc.items:
        taxable_amounts = get_taxable_amounts(doc)
        for key, value in taxable_amounts.items():
            try:
                if doc.taxes:
                    for item in doc.taxes:
                        if item.get("custom_code") == key:
                            tax_templates = frappe.db.get_all("Item Tax Template", filters={"custom_code": key}, fields=["custom_code_name"])
                            
                            if len(tax_templates):
                                frappe.db.set_value('Sales Taxes and Charges', 
                                                    item.get("name"),
                                                    {
                                                        'custom_total_taxable_amount': round(value, 2),
                                                        'custom_code_name': tax_templates[0].get("custom_code_name")
                                                    }, update_modified=True)
                                
                                frappe.db.commit()
                                doc.reload()
            except:
                frappe.throw(Exception)
            
def get_total_discount(doc):
    discount_amount = 0
    
    if doc.items:
        for item in doc.items:
            if item.get("discount_percentage") > 0:
                total_dsc = item.get("custom_discount_amount_kes") * item.get("qty")
                discount_amount +=  total_dsc 
                
    return discount_amount

def get_taxable_amounts(doc):
    taxable_amounts_dict = {}
    
    try:
        if doc.items:
            for item in doc.items:
                if not item.get("custom_tax_code") in taxable_amounts_dict.keys():
                    taxable_amounts_dict[item.get("custom_tax_code")] = 0
                
                taxable_amounts_dict[item.get("custom_tax_code")] += item.base_net_amount
    except:
        frappe.throw(Exception)
        
    return taxable_amounts_dict      

def fetch_total_vat(doc):
    taxable_amount = 0
    if doc.taxes:
        for item in doc.taxes:
            if item.get("base_tax_amount_after_discount_amount") > 0:
                taxable_amount += item.get("custom_total_taxable_amount")
            if item.get("base_tax_amount_after_discount_amount") < 0 and doc.is_return:
                taxable_amount += item.get("custom_total_taxable_amount")
                
    return taxable_amount
    
def fetch_total_non_vat(doc):
    taxable_non_vat_amount = 0
    if doc.taxes:
        for item in doc.taxes:
            if item.get("base_tax_amount_after_discount_amount") == 0:
                taxable_non_vat_amount += item.get("custom_total_taxable_amount")
                
    return taxable_non_vat_amount

def get_sales_type_code(sales_type):
    code = "P"
    key_value = {
        "N": "Normal",
        "C": "Copy",
        "T": "Training",
        "P": "Profoma"
        }
    for k, v in key_value.items():
        if sales_type == v:
            code = k
    return code

def get_rcpt_type_code(rcpt_type):
    code = "S"
    key_value = {
        "S": "Sale",
        "R": "Credit Note After Sale"
        }
    for k, v in key_value.items():
        if rcpt_type == v:
            code = k
    return code

def get_payment_type_code(pymnt_type):
    code = "01"
    key_value = {
        "01": "Cash",
        "02": "Credit",
        "03": "Cash/Credit",
        "04": "Bank Check",
        "05": "Debit&Credit Card",
        "06": "Mobile-Money",
        "07": "Other"
        }
    for k, v in key_value.items():
        if pymnt_type == v:
            code = k
    return code

def get_sales_status_code(sales_status):
    code = "02"
    key_value = {
        "01": "Wait for Approval",
        "02": "Approved",
        "03": "Cancel Request",
        "04": "Cancelled",
        "05": "Credit Note Generated",
        "06": "Transferred"
        }
    for k, v in key_value.items():
        if sales_status == v:
            code = k
    return code

@frappe.whitelist()
def create_etims_sinv():

    '''
    Method that collects sales information and updates it to tims server
    '''
    if not frappe.form_dict.message:
        frappe.throw("Missing 'message' in request data")

    raw_data = frappe.form_dict.message
    json_data = json.loads(raw_data)
    data_obj = json_data.get("data")
    doc_name = data_obj.get("doc_name")
    
    doc = frappe.get_doc("Sales Invoice", doc_name)
    count = 0
    
    if doc.custom_update_invoice_in_tims:
        tax_code_list = []
        branch_id = eTIMS.get_user_branch_id()
        
        etims_details = get_etims_details(doc.company, branch_id, doc.owner, doc.modified_by)
                
        request_date_and_time = doc.modified
    
        conc_datetime_str = eTIMS.strf_datetime_format(request_date_and_time)
        
        now = datetime.now()
        date_time_str = now.strftime("%Y%m%d%H%M%S")
        
        request_date = doc.posting_date
        date_str = eTIMS.strf_date_object(request_date)
            
        count = len(doc.items)
                    
        payload = {
            "trdInvcNo": doc.name,
            "custTin": doc.tax_id,
            "custNm": doc.customer,
            "cfmDt": conc_datetime_str,
            "salesDt": date_str,
            "stockRlsDt": conc_datetime_str,
            "totItemCnt": count,
            "totDscAmt": abs(round(get_total_discount(doc), 2)),
            "totExDsc": abs(round((get_total_discount(doc) + doc.base_grand_total), 2)),
            "totNonTaxAmt": abs(round(fetch_total_non_vat(doc), 2)),
            "totTaxblAmt": abs(fetch_total_vat(doc)),
            "totTaxAmt": abs(doc.base_total_taxes_and_charges),
            "totAmt": abs(doc.base_grand_total),
            "prchrAcptcYn":"N",
            "remark": doc.remarks,
            "regrNm": etims_details.get("creator"),
            "modrNm": etims_details.get("modifier"),
            "receipt":{
                "rcptPbctDt": date_time_str
                },
            "itemList": etims_sale_item_list_sales(doc)
        }
        
        for tax_item in doc.taxes:
            if not tax_item.get("custom_code") in tax_code_list:
                tax_code_list.append(tax_item.get("custom_code")) 
            
            if "A" in tax_code_list:
                if tax_item.custom_code == "A":
                    payload["taxblAmtA"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
                    payload["taxRtA"] =  abs(get_tax_account_rate(tax_item.get("account_head")))
                    payload["taxAmtA"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
            else:
                payload["taxblAmtA"] = 0
                payload["taxRtA"] =  0
                payload["taxAmtA"] = 0
            
            if "B" in tax_code_list:
                if tax_item.custom_code == "B":
                    payload["taxblAmtB"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
                    payload["taxRtB"] =  abs(get_tax_account_rate(tax_item.get("account_head")))
                    payload["taxAmtB"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
            else:
                payload["taxblAmtB"] = 0
                payload["taxRtB"] =  0
                payload["taxAmtB"] = 0
                
            if "C" in tax_code_list:
                if tax_item.custom_code == "C":
                    payload["taxblAmtC"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
                    payload["taxRtC"] =  abs(get_tax_account_rate(tax_item.get("account_head")))
                    payload["taxAmtC"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
            else:
                payload["taxblAmtC"] = 0
                payload["taxRtC"] =  0
                payload["taxAmtC"] = 0
                
            if "D" in tax_code_list:
                if tax_item.custom_code == "D":
                    payload["taxblAmtD"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
                    payload["taxRtD"] =  abs(get_tax_account_rate(tax_item.get("account_head")))
                    payload["taxAmtD"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
            else:
                payload["taxblAmtD"] = 0
                payload["taxRtD"] =  0
                payload["taxAmtD"] = 0
                
            if "E" in tax_code_list:
                if tax_item.custom_code == "E":
                    payload["taxblAmtE"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
                    payload["taxRtE"] =  abs(get_tax_account_rate(tax_item.get("account_head")))
                    payload["taxAmtE"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
            else:
                payload["taxblAmtE"] = 0
                payload["taxRtE"] =  0
                payload["taxAmtE"] = 0
                    
        
        if doc.is_return == 1:
            return_status = sales_return_information(doc)
    
            if return_status == "partial":
                payload["rfdDt"] = date_time_str
                payload["rfdRsnCd"] = doc.custom_credit_note_reason_code
            elif return_status == "full":
                payload["cnclReqDt"] = conc_datetime_str
                payload["cnclDt"] = conc_datetime_str
                payload["rfdDt"] = date_time_str
                payload["rfdRsnCd"] = doc.custom_credit_note_reason_code
            elif return_status == "null":
                frappe.throw("Invalid, return amount is greater than original amount!")
    
    if doc.custom_update_invoice_in_tims:
        try:
            create_etims_sales_invoice(payload)
            
        except:
            frappe.throw("Oops Bad Request!")
    else:
        return
        
def stockIOSaveReq(doc, date_str):
    taxAmt = 0
    taxblAmt = 0
    if doc.custom_update_invoice_in_tims:
        headers = eTIMS.get_headers()
        stock_list = etims_sale_item_list_stock(doc)
        if len(stock_list):
            for item in doc.items:
                if item.get("custom_maintain_stock") == 1 and item.get("custom_tax_code") in ["B", "E"]:
                    taxblAmt += item.get("base_net_amount")
                    taxAmt +=  (item.get("base_amount") - item.get("base_net_amount"))
                                
            payload = {
                "sarNo": get_etims_sar_no(doc),
                "orgSarNo": get_org_etims_sar_no(doc),
                "regTyCd": "A",
                "custTin": doc.tax_id,
                "custNm": doc.customer,
                "custBhfId": "",
                "ocrnDt": date_str,
                "totItemCnt": len(stock_list),
                "totTaxAmt": abs(round(taxAmt, 2)),
                "totAmt": abs(doc.base_grand_total),
                "remark": doc.remarks,
                "regrId": doc.owner,
                "regrNm": doc.owner,
                "modrId": doc.modified_by,
                "modrNm": doc.modified_by,
                "itemList": stock_list
                }
            
            if doc.is_return == 1: 
                return_status = sales_return_information(doc)
                
                if return_status == "partial" or return_status == "full":
                    payload["sarTyCd"] = "03"
                
                elif return_status == "null":
                    frappe.throw("Invalid, return amount is greater than original amount!")
            
            else:
                payload["sarTyCd"] = "11"

            if doc.custom_update_invoice_in_tims:
                try:
                    print(payload)
                    response = requests.request(
                                "POST", 
                                eTIMS.tims_base_url() + 'insertStockIO',
                                json = payload, 
                                headers=headers
                            )
                
                    response_json = response.json()

                    if not response_json.get("resultCd") == '000':
                        # print("*"*80)
                        # print(response_json.get("resultMsg"))
                        frappe.throw(response_json.get("resultMsg"))
                            
                    frappe.msgprint(response_json.get("resultMsg"))

                except:
                    frappe.throw("Oops Bad Request!")
            else:
                return

def get_etims_sar_no(doc):
    etims_sar_no = 1
    branch_id = eTIMS.get_user_branch_id()
    try:
        etims_sar_docs = frappe.get_last_doc("eTIMS Stock Release Number", filters={"tax_branch_office": branch_id})
        
        new_sar_no = etims_sar_docs.get("sr_number") + 1
        
        new_doc = frappe.new_doc("eTIMS Stock Release Number") 
        new_doc.reference_type = doc.doctype
        new_doc.reference = doc.name
        new_doc.tax_branch_office = branch_id
        new_doc.sr_number = new_sar_no
        new_doc.orginal_sr_number = get_org_etims_sar_no(doc)
        new_doc.insert()
        frappe.db.commit()

        return new_sar_no
    except:
        new_doc = frappe.new_doc("eTIMS Stock Release Number") 
        new_doc.reference_type = doc.doctype
        new_doc.reference = doc.name
        new_doc.tax_branch_office = branch_id
        new_doc.sr_number = etims_sar_no 
        new_doc.orginal_sr_number = get_org_etims_sar_no(doc)
        
        new_doc.insert()
        frappe.db.commit()

        return etims_sar_no
    
def get_org_etims_sar_no(doc):
    org_etims_sar_no = 0
    
    if doc.custom_original_invoice_number:
        prev_doc  = frappe.db.get_all("eTIMS Stock Release Number", filters={"reference": doc.return_against}, fields=["sr_number"])
        
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
    
    
def etims_sale_item_list_sales(doc):
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
					"pkg": abs(item.get("qty")),
					"qtyUnitCd": item_detail[0].get("custom_quantity_unit_code"),
					"qty": abs(item.get("qty")),
					"prc": abs(item.get("base_rate")),
					"splyAmt": abs(item.get("base_amount")),
					"dcRt": abs(item.get("discount_percentage")),
					"dcAmt": abs(round((item.get("custom_discount_amount_kes") * item.get("qty")), 2)),
					# "isrccCd":null,
					# "isrccNm":null,
					# "isrcRt":null,
					# "isrcAmt":null,
                    "totDcAmt": abs(round((item.get("custom_discount_amount_kes") * item.get("qty")), 2)),
					"taxTyCd": item_tax_code,
					"taxblAmt": abs(round(item.get("base_net_amount"), 2)),
					"taxAmt": abs(round((item.get("base_amount") - item.get("base_net_amount")), 2)),
					"totAmt": abs(item.get("base_amount")) 
				}

        if not item_etims_data in sales_item_list:
            sales_item_list.append(item_etims_data)
            
    return sales_item_list

def etims_sale_item_list_stock(doc):
    stock_item_list = []
    for item in doc.items:
        if item.custom_maintain_stock:
            item_tax_code = get_tax_template_details(item.get("item_tax_template"))
            item_detail = frappe.db.get_all("Item", filters={"disabled": 0, "item_code": item.get("item_code")}, fields = ["*"])
            item_etims_data = {
                        "itemSeq": item.get("idx"),
                        "itemCd": item_detail[0].get("custom_item_code"),
                        "itemClsCd": item_detail[0].get("custom_item_classification_code"),
                        "itemNm": item_detail[0].get("custom_item_name"),
                        "pkgUnitCd": item_detail[0].get("custom_packaging_unit_code"),
                        "pkg": item.get("qty"),
                        "qtyUnitCd": item_detail[0].get("custom_quantity_unit_code"),
                        "qty": abs(item.get("qty")),
                        "prc": abs(item.get("base_rate")),
                        "splyAmt": abs(item.get("base_amount")),
                        "dcRt": abs(item.get("discount_percentage")),
                        "dcAmt": abs(round((item.get("custom_discount_amount_kes") * item.get("qty")), 2)),
                        "totDcAmt": abs(round((item.get("custom_discount_amount_kes") * item.get("qty")), 2)),
                        "taxTyCd": item_tax_code,
                        "taxblAmt": abs(round(item.get("base_net_amount"), 2)),
                        "taxAmt": abs(round((item.get("base_amount") - item.get("base_net_amount")), 2)),
                        "totAmt": abs(item.get("base_amount"))
                    }

            if not item_etims_data in stock_item_list:
                stock_item_list.append(item_etims_data)
                
    return stock_item_list

def get_tax_template_details(template_name):
    tax_doc = frappe.get_doc("Item Tax Template", template_name)
    if tax_doc:
      
        tax_code =  tax_doc.custom_code
    
        return tax_code
    else:
        return "D"

def get_tax_account_rate(account_head):
    tax_acc_docs = frappe.db.get_all("Account", filters={"name": account_head}, fields=["tax_rate"])
    
    if tax_acc_docs:
        tax_rate = tax_acc_docs[0].get("tax_rate")
        
        return tax_rate
    
def create_sales_receipt(data, doc_name):
    control_unit_date_time = eTIMS.strp_datetime_object(data.get("sdcDateTime"))
    
    new_rcpt_doc = frappe.new_doc("eTIMS Sales Receipt")
    new_rcpt_doc.receipt_number = data.get("curRcptNo")
    new_rcpt_doc.total_receipt_number = data.get("totRcptNo")
    new_rcpt_doc.internal_data = data.get("intrlData")
    new_rcpt_doc.receipt_signature = data.get("rcptSign")
    new_rcpt_doc.control_unit_date_time = control_unit_date_time
    new_rcpt_doc.reference = doc_name
   
    new_rcpt_doc.insert()
    
    frappe.db.commit()
    
# def create_qr_codedd(pin, branch_id, rcpt_signature):
#     header_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id, "active":1}, fields=["api_mode"])

#     if rcpt_signature:
#         if header_docs:
#             settings_doc = header_docs[0]
            
#             url = "https://etims-sbx.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data=" + pin+ branch_id + rcpt_signature
#             file_name = rcpt_signature + ".png"
            
#             file_path = frappe.get_site_path('private', 'files', file_name)
            
#             if settings_doc.get("api_mode") == "Production":
#                 url = "https://etims.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data=" + pin+ branch_id + rcpt_signature
#             else:
#                 url = "https://etims-sbx.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data=" + pin+ branch_id + rcpt_signature
                
#             try:
#                 big_code = pyqrcode.create(url, error='L', version=27, mode='binary')
#                 big_code.png(file_path, scale=10, module_color=[0, 0, 0, 128], background=[255, 255, 255])
#                 # big_code.show()
                
#                 return file_name
                
#             except:
#                 frappe.throw("QR Code Not Generated!")

def create_qr_code(pin, branch_id, rcpt_signature):     
    header_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id, "active":1}, fields=["api_mode"])

    if rcpt_signature:
        if header_docs:
            settings_doc = header_docs[0]
            
            url = "https://etims-sbx.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data=" + pin+ branch_id + rcpt_signature
            file_name = rcpt_signature + ".png"
            
            file_path = frappe.get_site_path('private', 'files', file_name)
            
            if settings_doc.get("api_mode") == "Production":
                url = "https://etims.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data=" + pin+ branch_id + rcpt_signature
            else:
                url = "https://etims-sbx.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data=" + pin+ branch_id + rcpt_signature
                
            
            # print(qrcode)
            try:
                qrcode = segno.make_qr(url)
                qrcode.save(file_path, scale=5)
                
                return file_name
                
            except:
                frappe.throw("QR Code Not Generated!")
            
    
def create_attachment(file_name, inv_name):
    new_attachment = frappe.new_doc("File")
    new_attachment.file_name = file_name
    new_attachment.file_url = "/private/files/" + file_name
    new_attachment.attached_to_doctype = "Sales Invoice"
    new_attachment.attached_to_name = inv_name
    new_attachment.is_private = 1
    
    new_attachment.save()
    frappe.db.commit()
    
    return new_attachment.get("file_url")

def sales_return_information(doc):
    diff_amount = 0
    return_status = ""
    
    if doc.is_return:
        if doc.return_against:
            return_amount = doc.grand_total
            return_against = frappe.get_doc("Sales Invoice", doc.return_against)
            prev_return_amount = return_against.grand_total
            
            diff_amount = prev_return_amount + return_amount
            
        if diff_amount > 0:
            return_status = "partial"
        elif diff_amount == 0:
            return_status = "full"
        elif diff_amount < 0:
            return_status = "null"
        
    return return_status


def get_etims_details(company, branch_id, owner, modified_by):
    query = """
        SELECT 
            tdi.sales_control_unit_id AS scu,
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

def create_etims_sales_invoice(payload):
    doc_exists = frappe.db.exists("eTIMS Sales Invoice", {"trader_invoice_number": payload.get("trdInvcNo")})

    if not doc_exists:
        new_doc = frappe.new_doc("eTIMS Sales Invoice")
        new_doc.trader_invoice_number = payload.get("trdInvcNo")
        new_doc.customer_tin = payload.get("custTin")
        new_doc.customer_name = payload.get("custNm")
        new_doc.sales_date = payload.get("salesDt")
        new_doc.confirmation_date = payload.get("cfmDt")
        new_doc.stock_release_date = payload.get("stockRlsDt")
        new_doc.total_item_count = payload.get("totItemCnt")
        new_doc.total_discount_amount = payload.get("totDscAmt")
        new_doc.total_before_discount = payload.get("totExDsc")
        new_doc.total_taxable_amount = payload.get("totTaxblAmt")
        new_doc.total_non_taxable_amount = payload.get("totNonTaxAmt")
        new_doc.total_tax_amount = payload.get("totTaxAmt")
        new_doc.total_amount = payload.get("totAmt")
        new_doc.purchase_accept = payload.get("prchrAcptcYn")
        new_doc.remark = payload.get("remark")
        new_doc.registration_name = payload.get("regrNm")
        new_doc.modifier_name = payload.get("modrNm")
        new_doc.receipt_publish_date = payload.get("receipt")["rcptPbctDt"]
        new_doc.taxable_amount_a = payload.get("taxblAmtA")
        new_doc.taxable_amount_b = payload.get("taxblAmtB")
        new_doc.taxable_amount_c = payload.get("taxblAmtC")
        new_doc.taxable_amount_d = payload.get("taxblAmtD")
        new_doc.taxable_amount_e = payload.get("taxblAmtE")
        new_doc.tax_rate_a = payload.get("taxRtA")
        new_doc.tax_rate_b = payload.get("taxRtB")
        new_doc.tax_rate_c = payload.get("taxRtC")
        new_doc.tax_rate_d = payload.get("taxRtD")
        new_doc.tax_rate_e = payload.get("taxRtE")
        new_doc.tax_amount_a = payload.get("taxAmtA")
        new_doc.tax_amount_b = payload.get("taxAmtB")
        new_doc.tax_amount_c = payload.get("taxAmtC")
        new_doc.tax_amount_d = payload.get("taxAmtD")
        new_doc.tax_amount_e = payload.get("taxAmtE")
        
        for item in payload.get("itemList"):
            new_doc.append("items", {
                "item_sequence_number": item.get("itemSeq") ,
                "etims_item_code": item.get("itemCd") ,
                "item_classification_code": item.get("itemClsCd") ,
                "item_name": item.get("itemNm") ,
                "packaging_unit_code": item.get("pkgUnitCd") ,
                "quantity_unit_code": item.get("qtyUnitCd") ,
                "package": item.get("pkg") ,
                "quantity": item.get("qty") ,
                "unit_price": item.get("prc") ,
                "supply_amount": item.get("splyAmt") ,
                "discount_rate": item.get("dcRt") ,
                "total_discount_amount": item.get("dcAmt") ,
                "tax_type_code": item.get("taxTyCd") ,
                "taxable_amount": item.get("taxblAmt") ,
                "tax_amount": item.get("taxAmt") ,
                "total_amount": item.get("totAmt")
            })
            
        new_doc.insert()
        frappe.db.commit()
    # else:
    #     if not doc_exists in ["None", None]:
    #         etims_sinv = frappe.get_doc("eTIMS Sales Invoice", doc_exists)
    #         etims_sinv.trader_invoice_number = payload.get("trdInvcNo")
    #         etims_sinv.customer_tin = payload.get("custTin")
    #         etims_sinv.customer_name = payload.get("custNm")
    #         etims_sinv.sales_date = payload.get("salesDt")
    #         etims_sinv.confirmation_date = payload.get("cfmDt")
    #         etims_sinv.stock_release_date = payload.get("stockRlsDt")
    #         etims_sinv.total_item_count = payload.get("totItemCnt")
    #         etims_sinv.total_taxable_amount = payload.get("totTaxblAmt")
    #         etims_sinv.total_tax_amount = payload.get("totTaxAmt")
    #         etims_sinv.total_amount = payload.get("totAmt")
    #         etims_sinv.purchase_accept = payload.get("prchrAcptcYn")
    #         etims_sinv.remark = payload.get("remark")
    #         etims_sinv.registration_name = payload.get("regrNm")
    #         etims_sinv.modifier_name = payload.get("modrNm")
    #         etims_sinv.receipt_publish_date = payload.get("receipt")["rcptPbctDt"]
    #         etims_sinv.taxable_amount_a = payload.get("taxblAmtA")
    #         etims_sinv.taxable_amount_b = payload.get("taxblAmtB")
    #         etims_sinv.taxable_amount_c = payload.get("taxblAmtC")
    #         etims_sinv.taxable_amount_d = payload.get("taxblAmtD")
    #         etims_sinv.taxable_amount_e = payload.get("taxblAmtE")
    #         etims_sinv.tax_rate_a = payload.get("taxRtA")
    #         etims_sinv.tax_rate_b = payload.get("taxRtB")
    #         etims_sinv.tax_rate_c = payload.get("taxRtC")
    #         etims_sinv.tax_rate_d = payload.get("taxRtD")
    #         etims_sinv.tax_rate_e = payload.get("taxRtE")
    #         etims_sinv.tax_amount_a = payload.get("taxAmtA")
    #         etims_sinv.tax_amount_b = payload.get("taxAmtB")
    #         etims_sinv.tax_amount_c = payload.get("taxAmtC")
    #         etims_sinv.tax_amount_d = payload.get("taxAmtD")
    #         etims_sinv.tax_amount_e = payload.get("taxAmtE")
            
    #         etims_sinv.save()
    #         frappe.db.commit()