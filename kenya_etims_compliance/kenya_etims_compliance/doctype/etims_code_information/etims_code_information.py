# Copyright (c) 2023, Upande Ltd and contributors
# For license information, please see license.txt

from datetime import datetime
import requests, traceback

import frappe
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS


class eTIMSCodeInformation(Document):
    # Get standard codes and data including;
    # item classification code for managing item, location code, and package, weight code, PIN list and notice from KRA to update codes in ERP
    @frappe.whitelist()
    def codeSearchReq(self):
        request_datetime = self.code_request_datetime
        date_time_str = eTIMS.strf_datetime_object(request_datetime)

        headers = eTIMS.get_headers()

        payload = {
            "lastReqDt": date_time_str,
        }

        try:
            response = requests.request(
                "POST",
                eTIMS.tims_base_url() + "selectCodeList",
                json=payload,
                headers=headers,
            )
            response_json = response.json()

            if not response_json.get("resultCd") == "000":
                return {"Error": response_json.get("resultMsg")}

            process_code_information(response_json)
            create_quantity_units(response_json)
            create_packing_units(response_json)
            create_country_code(response_json)

            self.last_search_date_and_time = request_datetime

            return {"Success": response_json.get("resultMsg")}

        except:
            eTIMS.log_errors("Code Search", traceback.format_exc())
            return {"Error":"Oops Bad Request!"}

    #This part describes the Customer API function (url : /selectCustomer) and 
    # data types for each item. The Customer means the taxpayer. 
    # API functions are dividedinto 'Request:Argument' and 'Response:Return Object'. 
    # The CustSearchReq is an Argument Object of Request, The CustSearchRes is a ReturnObjectofResponse. 
    # Based on the ‘custmTin ‘, the server provides customer information registered to the provided PIN
    @frappe.whitelist()
    def custSearchReq(self):
        #empty customer details records first
        self.set("customer_details", [])
        self.save()
        
        headers = eTIMS.get_headers()

        payload = {
            "custmTin": self.customer_tin
            }

        try:
            response = requests.request(
                "POST",
                eTIMS.tims_base_url() + "selectCustomer",
                json=payload,
                headers=headers,
            )
            
            response_data = response.json()
            response_json = eTIMS.get_response_data(response_data)
            

            if not response_json.get("resultCd") == "000":
                return {"Error": response_json.get("resultMsg")}
            
            data = response_json.get("data")
            if data:
                for cust in data.get("custList"):
                    cust_exists = check_customer_exists(cust.get("tin"))
                    
                    self.create_erp_customer(cust.get("taxprNm"), cust.get("tin"))
                    
                    if not cust_exists == True:
                        self.create_customer(cust)

            return {"Success": response_json.get("resultMsg")}

        except:
            eTIMS.log_errors("Customer Search", traceback.format_exc())
            return {"Error":"Oops Bad Request!"}
    
    #This part describes the components of Notice API function(url : /selectNoticeList) and data types for each item. 
    # This API function is divided into 'Request:Argument' and 'Response: Return Object'. 
    # The NoticeSearchReq is an Argument Object of Request, The NoticeSearchRes is a Return ObjectofResponse
    @frappe.whitelist()
    def noticeSearchReq(self):
        #empty notice records first
        self.set("notices", [])
        self.save()
        
        request_datetime = self.notice_date_and_time
        date_time_str = eTIMS.strf_datetime_object(request_datetime)

        headers = eTIMS.get_headers()

        payload = {
            "lastReqDt": date_time_str,
        }

        try:
            response = requests.request(
                "POST",
                eTIMS.tims_base_url() + "selectNoticeList",
                json=payload,
                headers=headers,
            )

            response_json = response.json()

            if not response_json.get("resultCd") == "000":
                return {"Error": response_json.get("resultMsg")}

            notice_list = process_notices(response_json)
            self.last_request_date = request_datetime
            
            for notice in notice_list:
                create_notice_record(notice)
                notice_exists = check_if_notice_exists(notice.get("notice_number"))
                if not notice_exists == True:
                    self.append("notices", notice)

                    self.save()
            return {"Success": response_json.get("resultMsg")}

        except:
            eTIMS.log_errors("Notice Search", traceback.format_exc())
            return {"Error":"Oops Bad Request!"}

    def create_customer(self, customer):
        customer_dict = {
            "taxpayer_pin": customer.get("tin"),
            "taxpayer_name": customer.get("taxprNm"),
            "taxpayer_status_code": customer.get("taxprSttsCd"),
            "county_name": customer.get("prvncNm"),
            "sub_county_name": customer.get("dstrtNm"),
            "tax_locality_name": customer.get("sctrNm"),
            "location_description": customer.get("locDesc"),
        }

        self.append("customer_details", customer_dict)
        self.save()
        return True
    
    def create_erp_customer(self, customer_name, pin):
        customer_exists = frappe.db.exists("Customer", {"customer_name": customer_name})
        
        if not customer_exists:
            new_customer = frappe.new_doc("Customer")
            new_customer.customer_name = customer_name
            new_customer.custom_customer_pin = pin
            new_customer.custom_used_yn = "Y"
            new_customer.custom_customer_name = customer_name
            new_customer.customer_type = "Company"
            new_customer.customer_group = "Individual"
        
            new_customer.insert()
            frappe.db.commit()
        


######################################### Methods ##################################################
#process the code data from the CodeSearchReq
def process_code_information(response_result):
    """function that get's the responce of CodeSearchReq as a dict for processing

    Args:
        response_result (_dict_): result from CodeSearchReq
    """
    data = response_result.get("data")
    if data.get("clsList"):
        for item in data.get("clsList"):
            code_exists = check_if_doc_exists(
                "eTIMS Code Classification", "code_class", item.get("cdCls")
            )
            if not code_exists == True:
                new_doc = frappe.new_doc("eTIMS Code Classification")
                new_doc.code_class = item.get("cdCls")
                new_doc.code_class_name = item.get("cdClsNm")
                new_doc.code_description = item.get("cdClsDesc")
                new_doc.user_define_code_1 = item.get("userDfnNm1")
                new_doc.user_define_code_2 = item.get("userDfnNm2")
                new_doc.user_define_code_3 = item.get("userDfnNm3")
                new_doc.use_yes_or_no = item.get("useYn")
                new_doc.insert()

                for code_detail in item.get("dtlList"):
                    code_dict = assign_code_dict(code_detail)
                    new_doc.append("items", code_dict)

                new_doc.save()

                frappe.db.commit()
    else:
        frappe.throw("No code data found for this period please try an earlier date!")


def check_customer_exists(cust_pin):
    cust_exists = False
    cust_items = frappe.db.get_all("eTIMS Customer", filters={"taxpayer_pin": cust_pin})

    if cust_items:
        cust_exists = True

    return cust_exists


def process_notices(response_result):
    """function to process notices from api

    Args:
        response_result (_dict_): dict of notices

    Returns:
        _list_: list of notices
    """
    notice_list = []
    data = response_result.get("data")

    if data.get("noticeList"):
        for item in data.get("noticeList"):
            data = {
                "notice_number": item.get("noticeNo"),
                "title": item.get("title"),
                "contents": item.get("cont"),
                "detail_url": item.get("dtlUrl"),
                "registration_name": item.get("regrNm"),
                "registration_date_and_time": item.get("regDt"),
            }

            if not data in notice_list:
                notice_list.append(data)
    return notice_list


def assign_code_dict(code_detail):
    code_dict = {
        "code": code_detail.get("cd"),
        "code_name": code_detail.get("cdNm"),
        "code_description": code_detail.get("cdDesc"),
        "sort_order": code_detail.get("srtOrd"),
        "user_define_code_1": code_detail.get("userDfnCd1"),
        "user_define_code_2": code_detail.get("userDfnCd2"),
        "user_define_code_3": code_detail.get("userDfnCd3"),
        "use_yes_or_no": code_detail.get("useYn"),
    }

    return code_dict


def create_packing_units(response_result):
    data = response_result.get("data")
    if data.get("clsList"):
        for item in data.get("clsList"):
            if item.get("cdClsNm") == "Packing Unit":
                for code_item in item.get("dtlList"):
                    code_exists = check_if_doc_exists(
                        "eTIMS Packing Unit", "etims_code_name", code_item.get("cdNm")
                    )
                    if not code_exists == True:
                        new_doc = frappe.new_doc("eTIMS Packing Unit")
                        new_doc.etims_code = code_item.get("cd")
                        new_doc.etims_code_name = code_item.get("cdNm")
                        new_doc.code_description = code_item.get("cdDesc")
                        new_doc.sort_order = code_item.get("srtOrd")
                        new_doc.user_define_code_1 = code_item.get("userDfnCd1")
                        new_doc.user_define_code_2 = code_item.get("userDfnCd2")
                        new_doc.user_define_code_3 = code_item.get("userDfnCd3")
                        new_doc.use_yes_or_no = code_item.get("useYn")
                        new_doc.insert()

                        frappe.db.commit()

def create_quantity_units(response_result):
    data = response_result.get("data")
    if data.get("clsList"):
        for item in data.get("clsList"):
            if item.get("cdClsNm") == "Quantity Unit":
                for code_item in item.get("dtlList"):
                    code_exists = check_if_doc_exists(
                        "eTIMS Quantity Unit", "etims_code_name", code_item.get("cdNm")
                    )
                    if not code_exists == True:
                        new_doc = frappe.new_doc("eTIMS Quantity Unit")
                        new_doc.etims_code = code_item.get("cd")
                        new_doc.etims_code_name = code_item.get("cdNm")
                        new_doc.code_description = code_item.get("cdDesc")
                        new_doc.sort_order = code_item.get("srtOrd")
                        new_doc.user_define_code_1 = code_item.get("userDfnCd1")
                        new_doc.user_define_code_2 = code_item.get("userDfnCd2")
                        new_doc.user_define_code_3 = code_item.get("userDfnCd3")
                        new_doc.use_yes_or_no = code_item.get("useYn")
                        new_doc.insert()

                        frappe.db.commit()
#method to create etims country codes and contry names, to keep consistency                    
def create_country_code(response_result):
    data = response_result.get("data")
    if data.get("clsList"):
        for item in data.get("clsList"):
            if item.get("cdClsNm") == "Country":
                for code_item in item.get("dtlList"):
                    code_exists = check_if_doc_exists(
                        "eTIMS Country", "code_name", code_item.get("cd")
                    )
                    if not code_exists == True:
                        new_doc = frappe.new_doc("eTIMS Country")
                        new_doc.country_name = code_item.get("cdNm")
                        new_doc.code_name = code_item.get("cd")
                       
                        new_doc.insert()

                        frappe.db.commit()
                        
                        
def check_if_doc_exists(doc, doc_filter, doc_value):
    cdcls_exists = False
    code_info_docs = frappe.db.get_all(doc, filters={doc_filter: doc_value})

    if code_info_docs:
        cdcls_exists = True

    return cdcls_exists


def check_if_notice_exists(notice_no):
    notice_exists = False
    notice_items = frappe.db.get_all(
        "eTIMS Notice Item", filters={"notice_number": notice_no}
    )

    if notice_items:
        notice_exists = True

    return notice_exists

def create_notice_record(notice):
    notice_rec_exists = frappe.db.exists("eTIMS Notice", {"notice_number": notice.get("notice_number")})

    if not notice_rec_exists:
        new_notice_record = frappe.new_doc("eTIMS Notice")
        new_notice_record.notice_number = notice.get("notice_number")
        new_notice_record.title = notice.get("title")
        new_notice_record.contents = notice.get("contents")
        new_notice_record.detail_url = notice.get("detail_url")
        new_notice_record.registration_name = notice.get("registration_name")
        new_notice_record.registration_date_and_time = notice.get("registration_date_and_time")
        
        new_notice_record.insert()
    if notice_rec_exists:
        notice_doc = frappe.get_doc("eTIMS Notice", notice_rec_exists)
        notice_doc.title = notice.get("title")
        notice_doc.contents = notice.get("contents")
        notice_doc.detail_url = notice.get("detail_url")
        notice_doc.registration_name = notice.get("registration_name")
        notice_doc.registration_date_and_time = notice.get("registration_date_and_time")
        
        notice_doc.save()
        
    frappe.db.commit()