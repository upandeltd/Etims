# Copyright (c) 2023, Upande Ltd and contributors
# For license information, please see license.txt

import requests, traceback

import frappe
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS


class eTIMSItemInformation(Document):
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
            # print(response_json)
            process_item_cls_info(response_json)
   
            self.last_search_date_and_time = request_datetime
            self.save()
            return {"Success":response_json.get("resultMsg")}

        except:
            eTIMS.log_errors("Item Classification Search", traceback.format_exc())
            return {"Error":"Oops Bad Request!"}	
        # self.item_classification_data = response_result
        
    
    # @frappe.whitelist()
    # def itemSaveReq(self):
    #     headers = eTIMS.get_headers()
    #     etims_item_list = get_tims_items()

    #     for item in etims_item_list:
    #         try:
    #             response = requests.request(
    #                 "POST",
    #                 eTIMS.tims_base_url() + 'saveItem', json = item, headers=headers)
        
    #             response_json = response.json()
    #             print(response_json)
    #             if not response_json.get("resultCd") == '000':
    #                 return {"Error":response_json.get("resultMsg")}
    #             # print(response_json)
    #             etim_item_save(item.get("itemCd"))
    #             # self.view_itemcls_search_response = eTIMS.get_base_url() + "/app/etims-item-classification"
        
    #             return {"Success":response_json.get("resultMsg")}

    #         except:
    #             return "Bad Request!"	

      
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
                    # self.save()
            self.item_last_search_date_and_time = request_datetime
            self.save()
            return {"Success":response_json.get("resultMsg")}

        except:
            eTIMS.log_errors("Item Search", traceback.format_exc())

            return {"Error":"Oops Bad Request!"}	

def process_item_cls_info(response):
    data = response.get("data")
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
    code_info_docs = frappe.db.get_all("eTIMS Item Classification",filters = {"item_class_code": item_code})
    
    if code_info_docs:
        cdcls_exists = True
    
    return cdcls_exists

# def get_tims_items():
#     item_tims_info_list = []
#     item_list = frappe.db.get_all("Item", filters={"disabled": 0, "custom_registered_in_tims":0}, fields=["*"])
    
#     if item_list:
#         for item in item_list:
#             payload = {
#                         "itemCd":item.get("custom_item_code"),
#                         "itemClsCd":item.get("custom_item_classification_code"),
#                         "itemClsNm":item.get("custom_item_classification_name"),
#                         "itemTyCd":item.get("custom_item_type_code"),
#                         "itemNm":item.get("custom_item_name"),
#                         "itemStdNm":item.get("custom_item_standard_name"),
#                         "orgnNatCd":item.get("custom_origin_place_code_nation"),
#                         "pkgUnitCd":item.get("custom_packaging_unit_code"),
#                         "qtyUnitCd":item.get("custom_quantity_unit_code"),
#                         "taxTyCd":item.get("custom_taxation_type_code"),
#                         "btchNo":item.get("custom_batch_number"),
#                         "bcd":item.get("custom_barcode"),
#                         "dftPrc":item.get("custom_default_unit_price"),
#                         "grpPrcL1":item.get("custom_group1_unit_price"),
#                         "grpPrcL2":item.get("custom_group2_unit_price"),
#                         "grpPrcL3": item.get("custom_group3_unit_price"),
#                         "grpPrcL4":item.get("custom_group4_unit_price"),
#                         "grpPrcL5":item.get("custom_group5_unit_price"),
#                         "addInfo":item.get("custom_additional_information"),
#                         "sftyQty":item.get("custom_safety_quantity"),
#                         "isrcAplcbYn":item.get("custom_insurance_appicableyn"),
#                         "useYn":item.get("custom_used__unused"),
#                         "regrId":item.get("custom_registration_id"),
#                         "regrNm":item.get("custom_registration_name"), 
#                         "modrId":item.get("custom_modifier_id"), 
#                         "modrNm":item.get("custom_modifier_name")
#                     }
#             if not payload in item_tims_info_list:
#                 item_tims_info_list.append(payload)
                
                
#     return item_tims_info_list
        
# def etim_item_save(tims_item_code):
#     item_list = frappe.db.get_all("Item", filters={"disabled": 0, "custom_item_code": tims_item_code}, fields=["name", "custom_registered_in_tims"])
    
#     if len(item_list) == 1:
#         item_name = item_list[0].get("name")
#         frappe.db.set_value('Item', item_name, 'custom_registered_in_tims', 1, update_modified=True)
    
#     return True

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
  