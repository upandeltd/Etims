# Copyright (c) 2023, Upande Ltd and contributors
# For license information, please see license.txt

from datetime  import datetime
import requests, traceback

import frappe
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS


class eTIMSImportItemInformation(Document):
    @frappe.whitelist()
    def importItemSearchReq(self):
        request_datetime = self.data_from_datetime
        date_time_str = eTIMS.strf_datetime_object(request_datetime)
        
        headers = eTIMS.get_headers()

        payload = {
                "lastReqDt" : date_time_str, 
        }

        try:
            response = requests.request(
                "POST", 
                eTIMS.tims_base_url() + 'selectImportItemList', 
                json = payload, 
                headers=headers
            )
            response_data = response.json()
            response_json = eTIMS.get_response_data(response_data)
   
            if not response_json.get("resultCd") == '000':
                return {"Error":response_json.get("resultMsg")}

            item_list = process_item_information(response_json)
            self.last_search_date_and_time = request_datetime
               
            
            for item in item_list:
                item_exists = check_import_item_exits(item.get("task_code"))
    
                if item_exists == False:
                    map_import_item(item)
                    self.save()
                else:
                    update_import_item_entry(item, item_exists)
            
                
            return {"Success": response_json.get("resultMsg")}

        except:
            eTIMS.log_errors("Search Import Item", traceback.format_exc())
            return {"Error":"Oops Bad Request!"}
    
#  pkgUnitCd': 'KGM', 'qty': 14, 'qtyUnitCd': 'KGM', 'totWt': 140, 'netWt': 14, 'spplrNm': 'SEITZ GMGH', 'agntNm': 'SCHENKER LIMITED', 'invcFcurAmt': 11817.5, 'invcFcurCd': 'EUR', 'invcFcurExcrt': 135.73}, {'taskCd': '20230209004633', 'dclDe': '01022023', 'itemSeq': 1, 'dclNo': '23NBOIM401167364', 'hsCd': '63079000', 'itemNm': 'N; LIFTING BELTS 2t x 4m,3t x4m,5t x 4m,2t x 1m; L; 1; 1; 1; ', 'imptItemsttsCd': '2', 'orgnNatCd': 'DE', 'exptNatCd': 'DE', 'pkg': 17, 'pkgUnitCd': 'KGM', 'qty': 14, 'qtyUnitCd': 'KGM', 'totWt': 140, 'netWt': 14, 'spplrNm': 'SEITZ GMGH', 'agntNm': 'SCHENKER LIMITED', 'invcFcurAmt': 11817.5, 'invcFcurCd': 'EUR', 'invcFcurExcrt': 135.73}, {'taskCd': '20230209004634', 'dclDe': '01022023', 'itemSeq': 1, 'dclNo': '23NBOIM401167364', 'hsCd': '63079000', 'itemNm': 'N; LIFTING BELTS 2t x 4m,3t x4m,5t x 4m,2t x 1m; L; 1; 1; 1; ', 'imptItemsttsCd': '2', 'orgnNatCd': 'DE', 'exptNatCd': 'DE', 'pkg': 17, 'pkgUnitCd': 'KGM', 'qty': 14, 'qtyUnitCd': 'KGM', 'totWt': 140, 'netWt': 14, 'spplrNm': 'SEITZ GMGH'
######################################### Methods ################################
def process_item_information(response_result):
    item_list = []
    data = response_result.get("data")

    if data.get("itemList"):
        for item in data.get("itemList"):
            data = {
                "task_code": item.get("taskCd"),
                "declaration_date": item.get("dclDe"),
                "item_sequence": item.get("itemSeq"),
                "declaration_number": item.get("dclNo"),
                "hs_code": item.get("hsCd"),
                "item_name": item.get("itemNm"),
                "import_item_status_code": item.get("imptItemsttsCd"),
                "origin_nation_code": item.get("orgnNatCd"),
                "export_nation_code": item.get("exptNatCd"),
                "package": item.get("pkg"),
                "packaging_unit_code": item.get("pkgUnitCd"),
                "quantity": item.get("qty"),
                "quantity_unit_code": item.get("qtyUnitCd"),
                "gross_weight": item.get("totWt"),
                "net_weight": item.get("netWt"),
                "supplier_name": item.get("spplrNm"),
                "agent_name": item.get("agntNm"),
                "invoice_foreign_currency_amount": item.get("invcFcurAmt"),
                "invoice_foreign_currency": item.get("invcFcurCd"),
                "invoice_foreign_currency_crt": item.get("invcFcurExcrt")
            }

            if not data in item_list:
                item_list.append(data)
    return item_list

def check_import_item_exits(task_code):
    item_exists = False
    import_item = frappe.db.get_all("eTIMS Import Item", filters={"task_code": task_code}, fields=["task_code"])

    if import_item:
        item_exists =import_item[0].get("task_code")

    return item_exists

def create_import_item_entry(item):
    # Create a new document of the eTIMS Import Item doctype
    new_import_item_doc = frappe.new_doc("eTIMS Import Item")
    
    # Get a list of valid field names in the doctype
    valid_fields = [field.fieldname for field in new_import_item_doc.meta.fields]
    
    # Iterate through the item dictionary
    for key, value in item.items():
        
        # Check if the key exists as a field in the doctype
        if key in valid_fields:
            # Set the value of the field in the new document
            new_import_item_doc.set(key, value)
    
    # Save the document
    new_import_item_doc.insert()

def update_import_item_entry(item, item_name):
    # Create a new document of the eTIMS Import Item doctype
    new_import_item_doc = frappe.get_doc("eTIMS Import Item", item_name)
    
    # Get a list of valid field names in the doctype
    valid_fields = [field.fieldname for field in new_import_item_doc.meta.fields]
    
    # Iterate through the item dictionary
    for key, value in item.items():
        
        # Check if the key exists as a field in the doctype
        if key in valid_fields:
            # Set the value of the field in the new document
            new_import_item_doc.set(key, value)
    
    # Save the document
    new_import_item_doc.save()

def map_import_item(item):
    item_exists = check_if_item_exits(item.get("item_name"))
    item_price_ksh = 0
    
    try:
        item_price_ksh = (item.get("invoice_foreign_currency_amount")/item.get("quantity"))*item.get("invoice_foreign_currency_crt")
    except:
        item_price_ksh = 0
        
    
    if item_exists == False:
        # create item if not exists
        create_import_item_doctype(item, item_price_ksh)
        
        # create stock entry for receipt and update stock
    else:
        update_import_item_doctype(item, item_price_ksh)
        

def check_if_item_exits(item_code):
    item_exists = frappe.db.exists({"doctype": "Item", "item_code": item_code})
    
    if item_exists:
        
        return True
    else:
        return False

def create_import_item_doctype(item, item_price_ksh):
    date_str = item.get("declaration_date")
    date_obj = datetime.strptime(date_str, "%d%m%Y").date()
    
    new_item_doc = frappe.new_doc("Item")
    new_item_doc.item_code = item.get("item_name")
    new_item_doc.item_group = "All Item Groups"
    new_item_doc.stock_uom = "Nos"
    new_item_doc.custom_is_import_item = 1
    new_item_doc.valuation_rate = item_price_ksh
    new_item_doc.custom_task_code = item.get("task_code")
    new_item_doc.custom_declaration_date = date_obj
    new_item_doc.custom_hs_code = item.get("hs_code")
    new_item_doc.custom_remark = item.get("remark")
    new_item_doc.custom_country_of_origin = get_etims_country(item.get("origin_nation_code"))
    
    if item.get("import_item_status_code") == "1":
        new_item_doc.custom_import_item_status_code = "Unsent"
    
    elif item.get("import_item_status_code") == "2":
        new_item_doc.custom_import_item_status_code = "Waiting"
        
    elif item.get("import_item_status_code") == "3":
        new_item_doc.custom_import_item_status_code = "Approved"
        
    elif item.get("import_item_status_code") == "4":
        new_item_doc.custom_import_item_status_code = "Cancelled"
    
    new_item_doc.insert()
    create_import_item_entry(item)
    create_or_update_price_list(item.get("item_name"), item_price_ksh)

def update_import_item_doctype(item, item_price_ksh):
    date_str = item.get("declaration_date")
    date_obj = datetime.strptime(date_str, "%d%m%Y").date()
    
    new_item_doc = frappe.get_doc("Item", item.get("item_name"))
    
    new_item_doc.custom_is_import_item = 1
    new_item_doc.valuation_rate = item_price_ksh
    new_item_doc.custom_task_code = item.get("task_code")
    new_item_doc.custom_declaration_date = date_obj
    new_item_doc.custom_hs_code = item.get("hs_code")
    new_item_doc.custom_remark = item.get("remark")
    new_item_doc.custom_country_of_origin = get_etims_country(item.get("origin_nation_code"))
    
    if item.get("import_item_status_code") == "1":
        new_item_doc.custom_import_item_status_code = "Unsent"
    
    elif item.get("import_item_status_code") == "2":
        new_item_doc.custom_import_item_status_code = "Waiting"
        
    elif item.get("import_item_status_code") == "3":
        new_item_doc.custom_import_item_status_code = "Approved"
        
    elif item.get("import_item_status_code") == "4":
        new_item_doc.custom_import_item_status_code = "Cancelled"
    
    new_item_doc.save()
    create_import_item_entry(item)
    create_or_update_price_list(item.get("item_name"), item_price_ksh)  
    
    frappe.db.commit()  

def get_etims_country(country_code):
    country_code_list = frappe.db.get_all("eTIMS Country", filters={"code_name": country_code}, fields=["country_name"])
    
    if country_code_list:
        country_name = country_code_list[0].get("country_name")
        
        return country_name
    
def create_or_update_price_list(item_code, item_price):
    buying_price_list_exists = frappe.db.exists("Item Price", {"item_code": item_code, "price_list": "Standard Buying"})
    
    if not buying_price_list_exists:
        new_buy_price = frappe.new_doc("Item Price")
        new_buy_price.item_code = item_code
        new_buy_price.price_list = "Standard Buying"
        new_buy_price.price_list_rate = item_price
        
        new_buy_price.insert()
    else:
        price_list = frappe.get_doc("Item Price", buying_price_list_exists)
        price_list.price_list_rate = item_price
        
        price_list.save()
        
    frappe.db.commit()