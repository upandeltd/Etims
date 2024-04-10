# Copyright (c) 2023, Upande Ltd and contributors
# For license information, please see license.txt

from datetime  import datetime
import requests, traceback

import frappe
from frappe import enqueue
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS

class eTIMSStockInformation(Document):
    @frappe.whitelist()
    def stockMoveReq(self):
        request_datetime = self.from_date_and_time
        date_time_str = eTIMS.strf_datetime_object(request_datetime)
        
        headers = eTIMS.get_headers()

        payload = {
                "lastReqDt" : date_time_str, 
        }

        try:
            response = requests.request(
                "POST", 
                eTIMS.tims_base_url() + 'selectStockMoveList', 
                # eTIMS.get_base_url() + 'selectStockMoveList',
                json = payload, 
                headers=headers
            )
            
            response_data = response.json()
            
            response_json = eTIMS.get_response_data(response_data)
            print(response_json)
            if not response_json.get("resultCd") == '000':
            
                return {"Oops!":response_json.get("resultMsg")}
            
            create_stock_mvnt_doc(response_json)
            
            self.last_search_date_and_time = request_datetime
            self.save()
            
            return {"Success":response_json.get("resultMsg")}

        except:
            print(traceback.format_exc())
            return {"Error":"Oops Bad Request!"}	
 
    @frappe.whitelist()
    def stockMasterSaveReq(self):
        
        headers = eTIMS.get_headers()
        for item in self.items:
            if not item.get("saved") == 1:
                payload = {
                    "itemCd": item.get("etims_code"),
                    "rsdQty": item.get("quantity"), 
                    "regrId": self.owner, 
                    "regrNm": self.owner, 
                    "modrId": self.modified_by, 
                    "modrNm": self.modified_by
                }
                
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
                    item.saved = 1
                    self.save()
                    self.stockMasterSaveReq()
                    return {"Success":response_json.get("resultMsg")}

                except:
                    return {"Error":"Oops Bad Request!"}	

    @frappe.whitelist()
    def insert_items(self):
        items_to_insert = self.consolidate_stock_bin()
        
        for key, value in items_to_insert.items():
            # check if the key is already added for the etims_code
            qty = get_bin_qty(key)
            
            item_added = False
            for item in self.items:
                if item.item_code == key:
                    item_added = True
                    item.quantity = qty
                    item.etims_code = value
                
            if not item_added:
                self.append("items",
                    {
                        "item_code": key,
                        "etims_code": value,
                        "quantity": qty
                    })

        return {"status": True}

    @frappe.whitelist()
    def consolidate_stock_bin(self):
        item_dict = {}
        items = frappe.db.get_all("Item", filters={"custom_registered_in_tims":1, "disabled":0}, fields = ["item_code", "custom_item_code"])
         
        if items:
            for item in items:
                if not item.get("item_code") in item_dict.keys():
                    item_dict[item.get("item_code")] = ""
     
                item_dict[item.get("item_code")] = item.get("custom_item_code")

        return item_dict
    

def get_bin_qty(item_code):
    tax_branch = eTIMS.get_user_branch_id()

    store_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": tax_branch}, fields=["warehouse_name", "name"])
        
    bin_docs = frappe.db.get_all("Bin", filters={"item_code":item_code, "warehouse": store_warehouse[0].get("name")}, fields=["actual_qty"])

    if bin_docs:

        return bin_docs[0].get("actual_qty")
    
def create_stock_mvnt_doc(response_result):
    data = response_result.get("data")
    if data.get("stockList"):
        for item in data.get("stockList"):
            doc_exists = check_if_doc_exists(
                        "eTIMS Stock Movement", "stored_and_released_number", item.get("sarNo")
                    )
          
            occurence_date = eTIMS.strp_date_object(item.get("ocrnDt"))
            
            if not doc_exists == True:
                new_doc = frappe.new_doc("eTIMS Stock Movement")
                new_doc.customer_tin = item.get("custTin")
                new_doc.customer_branch = item.get("custBhfId")
                new_doc.stored_and_released_number = item.get("sarNo")
                new_doc.occurred_date = occurence_date
                new_doc.total_item_count = item.get("totItemCnt")
                new_doc.total_supply_price = item.get("totTaxblAmt")
                new_doc.total_vat = item.get("totTaxAmt")
                new_doc.total_amount = item.get("totAmt")
                new_doc.remark = item.get("remark")
                
                for item_detail in item.get("itemList"):
                    eTIMS.map_new_item(item_detail)
            
                    if item_detail.get("itemExprDt"):
                        expiry_date = eTIMS.strp_datetime_object(item_detail.get("itemExprDt"))
                    
                        item_dict = assign_stock_mvnt_item(item_detail, expiry_date)
                        new_doc.append("items", item_dict)
                    else:
                        item_dict = assign_stock_mvnt_item_no_date(item_detail)
                        new_doc.append("items", item_dict)

                new_doc.insert()

                # frappe.db.commit()
     
def check_if_doc_exists(doc, doc_filter, doc_value):
    cdcls_exists = False
    code_info_docs = frappe.db.get_all(doc, filters={doc_filter: doc_value})

    if code_info_docs:
        cdcls_exists = True

    return cdcls_exists


def assign_stock_mvnt_item(item_detail, item_expiry_date):        
    item_dict = {
        "item_sequence": item_detail.get("itemSeq"),
        "item_code": item_detail.get("itemCd"),
        "item_class_code": item_detail.get("itemClsCd"),
        "item_name": item_detail.get("itemNm"),
        "barcode": item_detail.get("bcd"),
        "package_unit_code": item_detail.get("pkgUnitCd"),
        "package_quantity": item_detail.get("pkg"),
        "unit_quantity_code": item_detail.get("qtyUnitCd"),
        "unit_quantity": item_detail.get("qty"),
        "item_expired_date": item_expiry_date,
        "unit_price": item_detail.get("prc"),
        "supply_amount": item_detail.get("splyAmt"),
        "discount_rate": item_detail.get("totDcAmt"),
        "taxable_amount": item_detail.get("taxblAmt"),
        "taxation_type_code": item_detail.get("taxTyCd"),
        "tax_amount": item_detail.get("taxAmt"),
        "total_amount": item_detail.get("totAmt")
    }

    return item_dict

def assign_stock_mvnt_item_no_date(item_detail):        
    item_dict = {
        "item_sequence": item_detail.get("itemSeq"),
        "item_code": item_detail.get("itemCd"),
        "item_class_code": item_detail.get("itemClsCd"),
        "item_name": item_detail.get("itemNm"),
        "barcode": item_detail.get("bcd"),
        "package_unit_code": item_detail.get("pkgUnitCd"),
        "package_quantity": item_detail.get("pkg"),
        "unit_quantity_code": item_detail.get("qtyUnitCd"),
        "unit_quantity": item_detail.get("qty"),
        "item_expired_date": item_detail.get("itemExprDt"),
        "unit_price": item_detail.get("prc"),
        "supply_amount": item_detail.get("splyAmt"),
        "discount_rate": item_detail.get("totDcAmt"),
        "taxable_amount": item_detail.get("taxblAmt"),
        "taxation_type_code": item_detail.get("taxTyCd"),
        "tax_amount": item_detail.get("taxAmt"),
        "total_amount": item_detail.get("totAmt")
    }

    return item_dict


    
