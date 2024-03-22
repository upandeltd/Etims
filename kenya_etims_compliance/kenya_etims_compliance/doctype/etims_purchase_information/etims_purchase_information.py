# Copyright (c) 2023, Upande Ltd and contributors
# For license information, please see license.txt

import requests, traceback

import frappe
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS

class eTIMSPurchaseInformation(Document):
    @frappe.whitelist()
    def trnsPurchaseSalesReq(self):
        request_datetime = self.last_request_date
        date_time_str = eTIMS.strf_datetime_object(request_datetime)
        
        headers = eTIMS.get_headers()

        payload = {
                "lastReqDt" :date_time_str, 
        }

        try:
            response = requests.request(
                            "POST", 
                            eTIMS.get_base_url() + '/api/method/kenya_etims_compliance.utils.etims_response.' + 'selectTrnsPurchaseSalesList',
                            json = payload, 
                            headers=headers
                        )
    
            response_data = response.json()
            
            response_json = eTIMS.get_response_data(response_data)
            
            if not response_json.get("resultCd") == '000':
       
                return {"Oops!":response_json.get("resultMsg")}
           
            process_purchases(response_json)
            
            self.last_search_date_and_time = request_datetime
            self.save()
     
            return {"Success":response_json.get("resultMsg")}

        except:
            return {"Oops!":"An error occured on TIS server!"}	
        # self.item_classification_data = response_result
    
def process_purchases(response_json):
    data = response_json.get("data")
    invoices = data.get("saleList")
    
    if invoices:
        for invoice in invoices:
            doc_exists = check_if_doc_exists(
                        "eTIMS Purchase Invoice", "supplier_invoice_number", invoice.get("spplrInvcNo")
                    )
            
            sale_date = eTIMS.strp_date_object(invoice.get("salesDt"))
            
            if not doc_exists == True:
                new_doc = frappe.new_doc("eTIMS Purchase Invoice")
                new_doc.supplier_pin = invoice.get("spplrTin")
                new_doc.supplier_name = invoice.get("spplrNm")
                new_doc.supplier_branch_id = invoice.get("spplrBhfId")
                new_doc.supplier_invoice_number = invoice.get("spplrInvcNo")
                new_doc.receipt_type_code = invoice.get("rcptTyCd")
                new_doc.payment_type_code = invoice.get("pmtTyCd")
                new_doc.validated_date = invoice.get("cfmDt")
                new_doc.sale_date = sale_date
                new_doc.stock_released_date = invoice.get("stockRlsDt")
                new_doc.total_item_count = invoice.get("totItemCnt")
                new_doc.taxable_amount_a = invoice.get("taxblAmtA")
                new_doc.taxable_amount_b = invoice.get("taxblAmtB")
                new_doc.taxable_amount_c = invoice.get("taxblAmtC")
                new_doc.taxable_amount_d = invoice.get("taxblAmtD")
                new_doc.taxable_amount_e = invoice.get("taxblAmtE")
                new_doc.tax_rate_a = invoice.get("taxRtA")
                new_doc.tax_rate_b = invoice.get("taxRtB")
                new_doc.tax_rate_c = invoice.get("taxRtC")
                new_doc.tax_rate_d = invoice.get("taxRtD")
                new_doc.tax_rate_e = invoice.get("taxRtE")
                new_doc.tax_amt_a = invoice.get("taxAmtA")
                new_doc.tax_amt_b = invoice.get("taxAmtB")
                new_doc.tax_amt_c = invoice.get("taxAmtC")
                new_doc.tax_amt_d = invoice.get("taxAmtD")
                new_doc.tax_amt_e = invoice.get("taxAmtE")
                new_doc.total_taxable_amount = invoice.get("totTaxblAmt")
                new_doc.total_tax_amount = invoice.get("totTaxAmt")
                new_doc.total_amount = invoice.get("totAmt")
                new_doc.remark = invoice.get("remark")
                
                # new_doc.save()
                
                for item_detail in invoice.get("itemList"):
                    try:
                        #Method to create new item if not exists and register it to etims
                        eTIMS.map_new_item(item_detail)
                        item_dict = assign_purchase_item(item_detail)
                    
                        new_doc.append("items", item_dict)

                        frappe.db.commit()
                    except:
                        frappe.throw(traceback.format_exc())
                
                new_doc.insert()
     
def check_if_doc_exists(doc, doc_filter, doc_value):
    cdcls_exists = False
    code_info_docs = frappe.db.get_all(doc, filters={doc_filter: doc_value})

    if code_info_docs:
        cdcls_exists = True

    return cdcls_exists


def assign_purchase_item(item_detail):        
    item_dict = {
        "item_sequence_number": item_detail.get("itemSeq"),
        "item_code": item_detail.get("itemCd"),
        "item_classification_code": item_detail.get("itemClsCd"),
        "item_name": item_detail.get("itemNm"),
        "barcode": item_detail.get("bcd"),
        "packing_unit_code": item_detail.get("pkgUnitCd"),
        "quantity_unit_code": item_detail.get("qtyUnitCd"),
        "package": item_detail.get("pkg"),
        "unit_price": item_detail.get("prc"),
        "supply_amount": item_detail.get("splyAmt"),
        "discount_rate": item_detail.get("dcRt"),
        "discount_amount": item_detail.get("dcAmt"),
        "taxation_type_code": item_detail.get("taxTyCd"),
        "taxable_amount": item_detail.get("taxblAmt"),
        "tax_amount": item_detail.get("taxAmt"),
        "total_amount": item_detail.get("totAmt")
    }

    return item_dict

