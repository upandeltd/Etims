# Copyright (c) 2025, Upande Ltd and contributors
# For license information, please see license.txt

import requests, segno, json, html  #pyqrcode
from datetime import datetime

import frappe
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS

class eTIMSSalesInvoice(Document):
    def before_insert(self):
        scu = ""
        if self.update_invoice_in_etims:		
            branch_id = eTIMS.get_user_branch_id()
   
            etims_details = get_etims_details(self.company, branch_id, self.owner, self.modified_by)
            last_inv_number = self.get_last_inv_number()
    

            if etims_details:
                scu = etims_details.get("scu")
                self.branch_id = branch_id
                self.sales_control_unit = scu
                self.invoice_number = last_inv_number
                
            if self.is_return:
                self.receipt_type_code = "R"
                self.payment_type_code = "07"
                self.sales_status_code = "05"
        
    def validate(self):
        '''
        Method validate invoice number before submitting invoice
        '''
        if self.invoice_number and self.name:
            doc_exists = frappe.db.exists("Sales Invoice", {"name": self.trader_invoice_number})

            if doc_exists:
                if self.update_invoice_in_etims:
                    invoice_numbers = self.validate_inv_number()
            
                    if self.invoice_number in invoice_numbers:
                        self.insert_invoice_number()
                        
    def insert_invoice_number(self):
        if self.update_invoice_in_etims:		
            last_inv_number = self.get_last_inv_number()
            org_inv_no = self.get_org_etims_sar_no()
           
            self.invoice_number = last_inv_number
            self.original_invoice_number = org_inv_no
        

    def validate_inv_number(self):
        invoice_numbers = []
        invoice_number_list = frappe.db.get_all("eTIMS Sales Invoice", fields = ["invoice_number", "name"], order_by='invoice_number desc')
        
        if invoice_number_list:
            for invoice_no in invoice_number_list:
                if not invoice_no.get("name") == self.name:
                    if not invoice_no.get("invoice_number") in invoice_numbers:
                        invoice_numbers.append(invoice_no.get("invoice_number"))
                    
        return invoice_numbers
        
    # def on_updates(self):
    #     '''
    #     Method sets increment for invoice number and orginal invoice number before submitting invoice
    #     '''
    #     scu = ""
    #     if self.update_invoice_in_etims:		
    #         branch_id = eTIMS.get_user_branch_id()
   
    #         etims_details = get_etims_details(self.company, branch_id, self.owner, self.modified_by)
    #         last_inv_number = self.get_last_inv_number()
    

    #         if etims_details:
    #             scu = etims_details.get("scu")
            
    #         frappe.db.set_value('eTIMS Sales Invoice', self.name, {
    #             "sales_control_unit": scu,
    #             "invoice_number": last_inv_number,
    #             "branch_id": branch_id
    #         }, update_modified=True)
            
    #         self.reload()
            
    # def get_etims_sar_no(doc):
    # 	etims_sar_no = 1
    # 	branch_id = eTIMS.get_user_branch_id()
    # 	try:
    # 		etims_sar_docs = frappe.get_last_doc("eTIMS Stock Release Number", filters={"tax_branch_office": branch_id})
            
    # 		new_sar_no = etims_sar_docs.get("sr_number") + 1
            
    # 		new_doc = frappe.new_doc("eTIMS Stock Release Number") 
    # 		new_doc.reference_type = doc.doctype
    # 		new_doc.reference = doc.name
    # 		new_doc.tax_branch_office = branch_id
    # 		new_doc.sr_number = new_sar_no
    # 		new_doc.orginal_sr_number = get_org_etims_sar_no(doc)
    # 		new_doc.insert()
    # 		frappe.db.commit()

    # 		return new_sar_no
    # 	except:
    # 		new_doc = frappe.new_doc("eTIMS Stock Release Number") 
    # 		new_doc.reference_type = doc.doctype
    # 		new_doc.reference = doc.name
    # 		new_doc.tax_branch_office = branch_id
    # 		new_doc.sr_number = etims_sar_no 
    # 		new_doc.orginal_sr_number = get_org_etims_sar_no(doc)
            
    # 		new_doc.insert()
    # 		frappe.db.commit()

    # 		return etims_sar_no
        
    # def get_org_etims_sar_no(doc):
    # 	org_etims_sar_no = 0
        
    # 	if doc.custom_original_invoice_number:
    # 		prev_doc  = frappe.db.get_all("eTIMS Stock Release Number", filters={"reference": doc.return_against}, fields=["sr_number"])
            
    # 		org_etims_sar_no = prev_doc[0].get("sr_number")
        
    # 		return org_etims_sar_no
    # 	else:

    # 		return org_etims_sar_no
    
    def get_org_etims_sar_no(self):
        org_etims_sar_no = 0
        
        if self.return_against:
            org_inv_no  = frappe.db.get_value("eTIMS Sales Invoice", {"trader_invoice_number": self.return_against}, "invoice_number")
            
            org_etims_sar_no = org_inv_no
        
            return org_etims_sar_no
        else:

            return org_etims_sar_no
    
    def get_last_inv_number(self):
    
        cur_number = 0
        last_inv_no = 0
        
        if self.update_invoice_in_etims:
            branch_id = eTIMS.get_user_branch_id()
            last_inv_no = frappe.db.get_value("Tax Branch Configurations", {"tax_branch_office": branch_id, "company": self.company}, "last_etims_sales_invoice_number")
            
            try:
                last_inv = frappe.db.get_all("eTIMS Sales Invoice",
                                                filters = {'trader_invoice_number': ['!=', self.trader_invoice_number], 'update_invoice_in_etims': 1, "branch_id": self.branch_id},
                                                fields=["invoice_number"],
                                                order_by='invoice_number desc',
                                                page_length = 1
                                            )
                
                if last_inv[0]:
                    # print(last_inv)
                    last_inv_no = last_inv[0].get("invoice_number")
                    
                cur_number = int(last_inv_no) + 1
                
            except:

                cur_number = int(last_inv_no) + 1
        
        return int(cur_number)


    def validate_inv_number(self):
        invoice_numbers = []
        invoice_number_list = frappe.db.get_all("eTIMS Sales Invoice", fields = ["invoice_number", "name"], order_by='invoice_number desc')
        
        if invoice_number_list:
            for invoice_no in invoice_number_list:
                if not invoice_no.get("name") == self.name:
                    if not invoice_no.get("invoice_number") in invoice_numbers:
                        invoice_numbers.append(invoice_no.get("invoice_number"))
                    
        return invoice_numbers
    
    # def on_update(self):
    #     if self.sales_updated_in_etims:
    #         file_name = self.create_qr_code()
                
    #         attachment_url = create_attachment(file_name, self.trader_invoice_number)

    #         self.receipt_qr_code = attachment_url
            
    #         # self.save()
    #         # self.submit()
    #         frappe.db.commit()
    #         # create_sales_receipt(data, doc.name)
            
def create_qr_code(branch_id, receipt_signature): 
        header_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id, "active":1}, fields=["api_mode", "pin"])
    
        if receipt_signature:
            if header_docs:
                settings_doc = header_docs[0]
                
                url = "https://etims-sbx.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data=" + settings_doc.get("pin") + branch_id + receipt_signature
                file_name = receipt_signature + ".png"
                
                file_path = frappe.get_site_path('private', 'files', file_name)
                
                if settings_doc.get("api_mode") == "Production":
                    url = "https://etims.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data=" + settings_doc.get("pin") + branch_id + receipt_signature
                else:
                    url = "https://etims-sbx.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data=" + settings_doc.get("pin") + branch_id + receipt_signature
                    
                
                # print(qrcode)
                try:
                    qrcode = segno.make_qr(url)
                    qrcode.save(file_path, scale=5)
                    
                    return file_name, url
                    
                except:
                    frappe.throw("QR Code Not Generated!")
                    
def create_attachment(file_name, inv_name):
    new_attachment = frappe.new_doc("File")
    new_attachment.file_name = file_name
    new_attachment.file_url = "/private/files/" + file_name
    new_attachment.attached_to_doctype = "eTIMS Sales Invoice"
    new_attachment.attached_to_name = inv_name
    new_attachment.is_private = 1
    
    new_attachment.save()
    frappe.db.commit()
    
    return new_attachment.get("file_url")

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


def writeInvoiceToeTIMS(doc, method):
    if doc.custom_update_invoice_in_tims:
        doc_name = doc.name
        etims_inv_doc_name = frappe.db.exists("eTIMS Sales Invoice", {"trader_invoice_number": doc_name})
        
        if etims_inv_doc_name and not etims_inv_doc_name in ["None", None]:
            data_doc = frappe.get_doc("eTIMS Sales Invoice", etims_inv_doc_name)
            trnsSalesSaveWrReq(data_doc)
        else:
            frappe.throw("Update Invoice In eTIMS is checked, you can't proceed without creating an eTIMS Sales Invoice!")

@frappe.whitelist()
def trnsSalesSaveWrReq(doc):

    '''
    Method that collects sales information and updates it to tims server
    '''
    headers = eTIMS.get_headers() 
                
    payload = {
        "trdInvcNo": doc.get("trader_invoice_number"),
        "invcNo": doc.get("invoice_number"),
        "orgInvcNo": doc.get("original_invoice_number"),
        "custTin": doc.get("customer_tin"),
        "custNm": doc.get("customer_name"),
        "salesTyCd": doc.get("sales_type_code"),
        "rcptTyCd": doc.get("receipt_type_code"),
        "pmtTyCd": doc.get("payment_type_code"),
        "salesSttsCd": doc.get("sales_status_code"),
        "cfmDt": doc.get("confirmation_date"),
        "salesDt": doc.get("sales_date"),
        "stockRlsDt": doc.get("stock_release_date"),
        "totItemCnt": doc.get("total_item_count"),
        "totTaxblAmt": doc.get("total_taxable_amount"),
        "totTaxAmt": doc.get("total_tax_amount"),
        "totAmt": doc.get("total_amount"),
        "taxblAmtA": doc.get("taxable_amount_a"),
        "taxRtA": doc.get("tax_rate_a"),
        "taxAmtA": doc.get("tax_amount_a"),
        "taxblAmtB": doc.get("taxable_amount_b"),
        "taxRtB": doc.get("tax_rate_b"),
        "taxAmtB": doc.get("tax_amount_b"),
        "taxblAmtC": doc.get("taxable_amount_c"),
        "taxRtC": doc.get("tax_rate_c"),
        "taxAmtC": doc.get("tax_amount_c"),
        "taxblAmtD": doc.get("taxable_amount_d"),
        "taxRtD": doc.get("tax_rate_d"),
        "taxAmtD": doc.get("tax_amount_d"),
        "taxblAmtE": doc.get("taxable_amount_e"),
        "taxRtE": doc.get("tax_rate_e"),
        "taxAmtE": doc.get("tax_amount_e"),
        "prchrAcptcYn": doc.get("purchase_accept"),
        "remark":  doc.get("remark"),
        "regrId": doc.get("registration_name"),
        "regrNm": doc.get("registration_name"),
        "modrId": doc.get("modifier_name"),
        "modrNm": doc.get("modifier_name"),
        "receipt":{
            "custTin": doc.get("customer_tin"),
            # "custMblNo":null,
            "rcptPbctDt": doc.get("receipt_publish_date"),
            # "trdeNm":null,
            # "adrs":null,
            # "topMsg":null,
            # "btmMsg":null,
            "prchrAcptcYn": doc.get("purchase_accept")
            },
        "itemList": etims_sale_item_list_sales(doc.get("items"))
    }
 
    if doc.is_return == 1:
        return_status = sales_return_information(doc.get("trader_invoice_number"))
        payload["salesDt"] = frappe.db.get_value("eTIMS Sales Invoice", {"trader_invoice_number": doc.return_against}, "sales_date")
        
        if return_status == "partial":
            payload["rfdDt"] = doc.get("receipt_publish_date")
            payload["rfdRsnCd"] = doc.credit_note_reason_code
        elif return_status == "full":
            payload["cnclReqDt"] = doc.get("confirmation_date")
            payload["cnclDt"] = doc.get("confirmation_date")
            payload["rfdDt"] = doc.get("receipt_publish_date")
            payload["rfdRsnCd"] = doc.credit_note_reason_code
        elif return_status == "null":
            frappe.throw("Invalid, return amount is greater than original amount!")

    try:
        response = requests.request(
            "POST", 
            eTIMS.tims_base_url() + 'saveTrnsSalesOsdc', 
            json = payload, 
            headers=headers)

        response_json = response.json()

        if not response_json.get("resultCd") == '000':
            error_message = str(response_json.get("resultMsg"))

            escaped_message = html.escape(error_message)

            # Throw error with escaped message
            frappe.throw(f"{escaped_message}")
                        
        data = response_json.get("data")

        control_unit_date_time = eTIMS.strp_datetime_object(data.get("sdcDateTime"))
        control_unit_date = eTIMS.strp_date_object(data.get("sdcDateTime")[0:8])
        control_unit_time = eTIMS.strp_time_object(data.get("sdcDateTime")[8:14])
        
        doc.current_receipt_number = data.get("curRcptNo")
        doc.total_receipt_number = data.get("totRcptNo")
        doc.internal_data = data.get("intrlData")
        doc.receipt_signature = data.get("rcptSign")
        doc.control_unit_date_time = control_unit_date_time
        doc.control_unit_date = control_unit_date
        doc.control_unit_time = control_unit_time
        
        
        doc.sales_updated_in_etims = 1
        file_name, url = create_qr_code(headers.get("bhfId"), data.get("rcptSign"))
            
        attachment_url = create_attachment(file_name, doc.name)

        doc.receipt_qr_code = attachment_url
        doc.receipt_url = url
        
        doc.save()
        frappe.db.commit()
                
        ######STOCK######
        # # stockIOSaveReq(doc, date_str)
        
        # doc.submit()
        # print(payload)
        
        frappe.msgprint(f'Invoice {doc.trader_invoice_number} has been submitted to eTIMS 🎉')

    except:
        frappe.throw("Oops Bad Request!")
        
# def stockIOSaveReq(doc, date_str):
#     # sar_no, org_sar_no = get_etims_sar_no(doc)
#     taxAmt = 0
#     taxblAmt = 0
#     if doc.custom_update_invoice_in_tims:
#         headers = eTIMS.get_headers()
#         stock_list = etims_sale_item_list_stock(doc)
#         if len(stock_list):
#             for item in doc.items:
#                 if item.get("custom_maintain_stock") == 1 and item.get("custom_tax_code") in ["B", "E"]:
#                     taxblAmt += item.get("base_net_amount")
#                     taxAmt +=  (item.get("base_amount") - item.get("base_net_amount"))
                    
#                     # if not item.get("")
            
#             payload = {
#                 "sarNo": get_etims_sar_no(doc),
#                 "orgSarNo": get_org_etims_sar_no(doc),
#                 "regTyCd": "A",
#                 "custTin": doc.tax_id,
#                 "custNm": doc.customer,
#                 "custBhfId": "",
#                 "ocrnDt": date_str,
#                 "totItemCnt": len(stock_list),
#                 "totTaxblAmt": abs(round(taxblAmt, 2)),
#                 "totTaxAmt": abs(round(taxAmt, 2)),
#                 "totAmt": abs(doc.base_grand_total),
#                 "remark": doc.remarks,
#                 "regrId": doc.owner,
#                 "regrNm": doc.owner,
#                 "modrId": doc.modified_by,
#                 "modrNm": doc.modified_by,
#                 "itemList": stock_list
#                 }
            
#             if doc.is_return == 1: 
#                 return_status = sales_return_information(doc)
                
#                 if return_status == "partial" or return_status == "full":
#                     payload["sarTyCd"] = "03"
                
#                 elif return_status == "null":
#                     frappe.throw("Invalid, return amount is greater than original amount!")
            
#             else:
#                 payload["sarTyCd"] = "11"

#             if doc.custom_update_invoice_in_tims:
#                 try:
#                     print(payload)
#                     response = requests.request(
#                                 "POST", 
#                                 eTIMS.tims_base_url() + 'insertStockIO',
#                                 json = payload, 
#                                 headers=headers
#                             )
                
#                     response_json = response.json()

#                     if not response_json.get("resultCd") == '000':
#                         # print("*"*80)
#                         # print(response_json.get("resultMsg"))
#                         frappe.throw(response_json.get("resultMsg"))
                            
#                     frappe.msgprint(response_json.get("resultMsg"))

#                 except:
#                     frappe.throw("Oops Bad Request!")
#             else:
#                 return

def etims_sale_item_list_sales(items):
    sales_item_list = []
    for item in items:
        item_etims_data = {
                    "itemSeq": item.get("item_sequence_number"),
                    "itemCd": item.get("etims_item_code"),
                    "itemClsCd": item.get("item_classification_code"),
                    "itemNm": item.get("item_name"),
                    # "bcd":null,
                    "pkgUnitCd": item.get("packaging_unit_code"),
                    "pkg": abs(item.get("package")),
                    "qtyUnitCd": item.get("quantity_unit_code"),
                    "qty": abs(item.get("quantity")),
                    "prc": abs(item.get("unit_price")),
                    "splyAmt": abs(item.get("supply_amount")),
                    "dcRt": abs(item.get("discount_rate")),
                    "dcAmt": abs(item.get("total_discount_amount")),
                    # "isrccCd":null,
                    # "isrccNm":null,
                    # "isrcRt":null,
                    # "isrcAmt":null,
                    "totDcAmt": abs(item.get("total_discount_amount")),
                    "taxTyCd": item.get("tax_type_code"),
                    "taxblAmt": abs(item.get("taxable_amount")),
                    "taxAmt": abs(item.get("tax_amount")),
                    "totAmt": abs(item.get("total_amount")) 
                }

        if not item_etims_data in sales_item_list:
            sales_item_list.append(item_etims_data)
            
    return sales_item_list

@frappe.whitelist()
def update_etims_values():
    if not frappe.form_dict.message:
        frappe.throw("Missing 'message' in request data")

    raw_data = frappe.form_dict.message
    json_data = json.loads(raw_data)
    data_obj = json_data.get("data")
    data = data_obj.get("details")

    doc_exists = frappe.db.exists("eTIMS Sales Invoice", {"trader_invoice_number": data.get("doc_name")})
    
    if doc_exists and not doc_exists in ["None", None]:
        doc = frappe.get_doc("eTIMS Sales Invoice", doc_exists)
        doc.sales_type_code = get_sales_type_code(data.get("stc"))
        doc.payment_type_code = get_payment_type_code(data.get("ptc"))
        doc.sales_status_code = get_sales_status_code(data.get("isc"))
        doc.receipt_type_code = get_rcpt_type_code(data.get("rtc"))
        doc.credit_note_reason_code = get_return_reason_code(data.get("rrc"))
        
        doc.save()
        frappe.db.commit()
    
@frappe.whitelist()
def get_set_options():
    if not frappe.form_dict.message:
        frappe.throw("Missing 'message' in request data")

    raw_data = frappe.form_dict.message
    json_data = json.loads(raw_data)
    data = json_data.get("data")

    if not data or not data.get("doc_name"):
        frappe.throw("Missing Sales Invoice Name!")

    doc_name = data.get("doc_name")

    # Default values
    defaults = {
        "sales_type_code": "N",
        "payment_type_code": "01",
        "sales_status_code": "02",
        "receipt_type_code": "S",
        "credit_note_reason_code": "02"
    }

    # Fetch values from the database
    fetched_value = frappe.db.get_value(
        "eTIMS Sales Invoice",
        {"trader_invoice_number": doc_name},
        ["sales_type_code", "payment_type_code", "sales_status_code", "receipt_type_code", "credit_note_reason_code"]
    )
    
    if not fetched_value or fetched_value in ["None", None]:
        frappe.throw("eTIMS Sales Invoice has not been created yet.")


    # Unpack fetched values and replace defaults only if not None
    keys = ["sales_type_code", "payment_type_code", "sales_status_code", "receipt_type_code", "credit_note_reason_code"]
    for i, key in enumerate(keys):
        if fetched_value[i] is not None:
            defaults[key] = fetched_value[i]

    defaults["sales_type_code"] = get_sales_type_name(defaults.get("sales_type_code"))
    defaults["payment_type_code"] = get_payment_type_name(defaults.get("payment_type_code"))
    defaults["sales_status_code"] = get_sales_status_name(defaults.get("sales_status_code"))
    defaults["receipt_type_code"] = get_rcpt_type_name(defaults.get("receipt_type_code"))
    defaults["credit_note_reason_code"] = get_return_reason_name(defaults.get("credit_note_reason_code"))

    frappe.response.message = defaults
    

def get_sales_type_name(sales_type_code):
    code = ""
    key_value = {
        "N": "Normal",
        "C": "Copy",
        "T": "Training",
        "P": "Profoma"
        }
    for k, v in key_value.items():
        if sales_type_code == k:
            code = v
    return code

def get_rcpt_type_name(rcpt_type_code):
    code = ""
    key_value = {
        "S": "Sale",
        "R": "Credit Note After Sale"
        }
    for k, v in key_value.items():
        if rcpt_type_code == k:
            code = v
    return code

def get_payment_type_name(pymnt_type_code):
    code = ""
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
        if pymnt_type_code == k:
            code = v
    return code

def get_sales_status_name(sales_status_code):
    code = ""
    key_value = {
        "01": "Wait for Approval",
        "02": "Approved",
        "03": "Cancel Request",
        "04": "Cancelled",
        "05": "Credit Note Generated",
        "06": "Transferred"
        }
    for k, v in key_value.items():
        if sales_status_code == k:
            code = v
    return code

def get_return_reason_name(return_code):
    code = ""
    key_value = {
        "01": "Missing Quantity",
        "02": "Missing Data",
        "03": "Damaged",
        "04": "Wasted",
        "05": "Raw Material Shortage",
        "06": "Refund"
        }
    for k, v in key_value.items():
        if return_code == k:
            code = v
    return code

def get_sales_type_code(sales_type):
    code = ""
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
    code = ""
    key_value = {
        "S": "Sale",
        "R": "Credit Note After Sale"
        }
    for k, v in key_value.items():
        if rcpt_type == v:
            code = k
    return code

def get_payment_type_code(pymnt_type):
    code = ""
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
    code = ""
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

def get_return_reason_code(return_type):
    code = ""
    key_value = {
        "01": "Missing Quantity",
        "02": "Missing Data",
        "03": "Damaged",
        "04": "Wasted",
        "05": "Raw Material Shortage",
        "06": "Refund"
        }
    for k, v in key_value.items():
        if return_type == v:
            code = k
    return code

def sales_return_information(doc_name):
    diff_amount = 0
    return_status = ""
    doc = frappe.get_doc("Sales Invoice", doc_name)
    
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