# Copyright (c) 2023, Upande Ltd and contributors
# For license information, please see license.txt

import requests, traceback

import frappe
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS


class eTIMSItemInformation(Document):
    #This part describes the item API function (url : /selectItemClsList) of product classification and data types for each item. 
    # API functions are dividedinto'Request:Argument' and 'Response:Return Object'. 
    # The ItemClsSearchReq is an Argument Object of Request, The ItemClsSearchRes is a ReturnObject ofResponse.
    @frappe.whitelist()
    def itemClsSearchReq(self):
        request_datetime = self.search_datetime
        date_time_str = eTIMS.strf_datetime_object(request_datetime)
        
        headers = eTIMS.get_headers()

        payload = {
                "bhfId": headers.get("bhfId"),
                "lastReqDt" : date_time_str, 
        }
  
        try:
            response = requests.request(
                "POST",
                eTIMS.tims_base_url() + 'selectItemClsList',
                json = payload,
                headers=headers
            )
    
            response_json = response.json()
        
            if not response_json.get("resultCd") == '000':
                return {"Error":response_json.get("resultMsg")}
            
            frappe.enqueue(process_item_cls_info, queue='long', response_result = response_json)
   
            self.last_search_date_and_time = request_datetime
            self.save()
            return {"Success":response_json.get("resultMsg")}

        except:
            eTIMS.log_errors("Item Classification Search", traceback.format_exc())
            return {"Error":"Oops Bad Request!"}	        
    
    # This part describes the components of SelectItemList API function (url : /selectItemList) and data types for each item. 
    # This API function is divided into 'Request:Argument' and 'Response: Return Object'. 
    # The ItemSearchReq is an Argument Object of Request, The ItemSearchRes is a Return Object of Response
    @frappe.whitelist()
    def itemSearchReq(self):
        request_datetime = self.item_request_datetime
        date_time_str = eTIMS.strf_datetime_object(request_datetime)
        
        headers = eTIMS.get_headers()

        payload = {
                "lastReqDt" : date_time_str, 
        }
      

        try:
            response = requests.request(
                "POST", 
                eTIMS.tims_base_url() + 'selectItemList', 
                json = payload, 
                headers=headers
            )
    
            response_json = response.json()
        
            if not response_json.get("resultCd") == '000':
                return {"Error":response_json.get("resultMsg")}

            item_list = process_registered_items(response_json)
            for item in item_list:
                item_exists = check_if_item_exists(item.get("item_code"))
                if not item_exists == True:
                    self.append("registered_items", item)
                
            self.item_last_search_date_and_time = request_datetime
            self.save()
            return {"Success":response_json.get("resultMsg")}

        except:
            eTIMS.log_errors("Item Search", traceback.format_exc())

            return {"Error":"Oops Bad Request!"}	

def process_item_cls_info(response_result):
    data = response_result.get("data")
    if data.get("itemClsList"):
        for item in data.get("itemClsList"):
            code_exists = check_if_doc_exists(item.get("itemClsCd"))
            if not code_exists == True:
                new_doc = frappe.new_doc("eTIMS Item Classification")
                new_doc.item_class_code = item.get("itemClsCd")
                new_doc.item_class_name = item.get("itemClsNm")
                new_doc.item_class_level = item.get("itemClsLvl")
                new_doc.taxation_type_code = item.get("taxTyCd")
                new_doc.is_major_target = item.get("mjrTgYn")
                new_doc.usedunused = item.get("useYn")
                new_doc.insert()
                
                frappe.db.commit()
    else:
        frappe.throw("No code data found for this period please try an earlier date")
        
def check_if_doc_exists(item_code):
    cdcls_exists = False
    code_info_docs = frappe.db.get_all("eTIMS Item Classification",filters = {"item_class_code": item_code}, fields=["name"])
    
    if code_info_docs:
        cdcls_exists = True
    
    return cdcls_exists

def process_registered_items(response_result):
    item_list = []
    data = response_result.get("data")
   
    if data.get("itemList"):
        for item in data.get("itemList"):
            data = {
                "pin": item.get("tin"),
                "item_classification_code": item.get("itemClsCd"),
                "item_code": item.get("itemCd"),
                "item_type_code": item.get("itemTyCd"),
                "item_name": item.get("itemNm"),
                "item_standard_name": item.get("itemStdNm"),
                "origin_place_code_nation": item.get("orgnNatCd"),
                "packing_unit_code": item.get("pkgUnitCd"),
                "quantity_unit_code": item.get("qtyUnitCd"),
                "taxation_type_code": item.get("taxTyCd"),
                "batch_number": item.get("btchNo"),
                "regist_branch_office_id": item.get("regBhfId"),
                "barcode": item.get("bcd"),
                "default_unit_price": item.get("dftPrc"),
                "group1_unit_price": item.get("grpPrcL1"),
                "group2_unit_price": item.get("grpPrcL2"),
                "group3_unit_price": item.get("grpPrcL3"),
                "group4_unit_price": item.get("grpPrcL4"),
                "group5_unit_price": item.get("grpPrcL5"),
                "add_information": item.get("addInfo"),
                "safety_quantity": item.get("sftyQty"),
                "insurance_appicable_yn": item.get("isrcAplcbYn"),
                "kra_modify_yn_item_classification_code": item.get("rraModYn"),
                "usedunused": item.get("useYn")
            }
            
            if not data in item_list:
                item_list.append(data)
                
    return item_list
        
def check_if_item_exists(item_code):
    item_exists = False
    etims_items = frappe.db.get_all("eTIMS Registered Items",filters = {"item_code": item_code})
    
    if etims_items:
        item_exists = True
    
    return item_exists
  