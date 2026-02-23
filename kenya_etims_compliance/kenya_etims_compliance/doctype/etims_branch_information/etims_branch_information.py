# Copyright (c) 2023, Upande Ltd and contributors
# For license information, please see license.txt

import requests, traceback

import frappe
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS

class eTIMSBranchInformation(Document):
    @frappe.whitelist()
    def bhfSearchReq(self):
        self.set("branch_details_tab", [])
        self.save()
        
        request_datetime = self.data_from_datetime
        date_time_str = eTIMS.strf_datetime_object(request_datetime)
        
        headers = eTIMS.get_headers()

        payload = {
                "tin": self.tin,
                "lastReqDt" : date_time_str
        }

    
        try:
            response = requests.request(
                "POST", 
                eTIMS.tims_base_url() + 'selectBhfList', 
                json = payload, 
                headers=headers
            )
            response_json = response.json()
   
            if not response_json.get("resultCd") == '000':
                return {"Error":response_json.get("resultMsg")}

            item_list = process_branch_information(response_json)
   
            for item in item_list:
                branch_info_exists = check_if_branch_info_exists(item.get("pin"), item.get("branch_office_id"))
                if not branch_info_exists == True:
                    self.append("branch_details_tab", item)
                    self.save()

            return {"Success":response_json.get("resultMsg")}

        except:
            eTIMS.log_errors("Branch Information", traceback.format_exc())
            return {"Error":"Oops Bad Request!"}
    
 
def process_branch_information(response_result):
    item_list = []
    data = response_result.get("data")
    
    for item in data.get("bhfList"):
        item_dict = {
            "pin": item.get("tin"),
            "branch_office_id": item.get("bhfId"),
            "branch_office_name": item.get("bhfNm"),
            "branch_status_code": item.get("bhfSttsCd"),
            "county_name": item.get("prvncNm"),
            "sub_county_name": item.get("dstrtNm"),
            "tax_locality_name": item.get("sctrNm"),
            "location_description": item.get("locDesc"),
            "manager_name": item.get("mgrNm"),
            "manager_contact": item.get("mgrTelNo"),
            "manager_email": item.get("mgrEmail"),
            "head_office_yesno": item.get("hqYn")
        }
        
        if item_dict not in item_list:
            item_list.append(item_dict)
            
    return item_list

def check_if_branch_info_exists(pin,branch_id):
    branch_info_exists = False
    branch_info_items = frappe.db.get_all("eTIMS Branch Item",filters = {"pin": pin, "branch_office_id":branch_id})
    
    if branch_info_items:
        branch_info_exists = True
    
    return branch_info_exists



def get_tims_customer():
    item_tims_info_list = []
    item_list = frappe.db.get_all("Customer", filters={"disabled": 0, "custom_is_registered":0}, fields=["*"])
    
    if item_list:
        for item in item_list:
            payload = {
                        "custNo": item.get("custom_customer_number"),
                        "custTin": item.get("custom_customer_pin"),
                        "custNm": item.get("custom_customer_name"),
                        "adrs": item.get("custom_address"),
                        "telNo": item.get("custom_contact"),
                        "email": item.get("custom_email"),
                        "faxNo": item.get("custom_fax_number"),
                        "useYn": item.get("custom_used_yn"),
                        "remark": item.get("custom_remark"),
                        "regrId": item.get("custom_registration_id"), 
                        "regrNm": item.get("custom_registration_name"), 
                        "modrId": item.get("custom_modifier_id"), 
                        "modrNm": item.get("custom_modifier_name")
                    }
            if not payload in item_tims_info_list:
                item_tims_info_list.append(payload)
    
    else:
        frappe.throw("No Unregistered Customer Found!")
                
                
    return item_tims_info_list
