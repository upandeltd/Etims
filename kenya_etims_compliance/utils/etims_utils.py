from datetime  import datetime
import requests

    
import frappe

class eTIMS():
    def get_headers():
        branch_id = eTIMS.get_user_branch_id()
        header_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id}, fields=["*"])
        
        if header_docs:
            headers = {
                "tin":header_docs[0].get("pin"),
                "bhfId":header_docs[0].get("branch_id"),
                "cmcKey":header_docs[0].get("communication_key"),
            }
            
            return headers
        
    def get_base_url():
        base_url = frappe.utils.get_url()
        
        return base_url
    
    def strf_datetime_object(datetime_data):
        datetime_object = datetime.strptime(datetime_data, '%Y-%m-%d %H:%M:%S')
        date_time_str = datetime_object.strftime("%Y%m%d%H%M%S")
        
        return date_time_str
    
    def strf_date_object(date_data):
        date_object = datetime.strptime(date_data, '%Y-%m-%d')
        date_str = date_object.strftime("%Y%m%d")
        
        return date_str
    
    def strf_date(date_data):
        date_str = date_data.strftime("%Y%m%d")
        
        return date_str
    
    def strf_time_object(time_data):
        time_object = datetime.strptime(time_data, '%H:%M:%S.%f')
        time_str = time_object.strftime("%H%M%S")
        
        return time_str
    
    def strf_time(time_data):
        time_str = ""
        try:
            time_object = datetime.strptime(time_data, '%H:%M:%S')
            time_str = time_object.strftime("%H%M%S")
        except:
            time_object = datetime.strptime(time_data, '%H:%M:%S.%f')
            time_str = time_object.strftime("%H%M%S")
   
        return time_str
    
    def get_response_data(response):    
        if response.get("message"):
            return response.get("message")
        else:
            return response
    
    def tims_base_url():
        settings_doc = frappe.get_doc("TIS Settings", "TIS Settings")
        tims_base_url = eTIMS.get_base_url() + '/api/method/kenya_etims_compliance.utils.etims_response.'
        
        if settings_doc.is_production == 1:
            tims_base_url = 'https://etims-api.kra.go.ke/etims-api/'
        elif settings_doc.is_sandbox == 1:
            tims_base_url = 'https://etims-api-sbx.kra.go.ke/etims-api/'
        return tims_base_url
    
    def get_default_tax_rate_a():
        tax_rate =0
        settings_doc = frappe.get_doc("TIS Settings")
        if settings_doc.vat_tax_rate_a:
            tax_rate = settings_doc.vat_tax_rate_a
            
        return tax_rate
    
    def get_default_tax_rate_b():
        tax_rate =0
        settings_doc = frappe.get_doc("TIS Settings")
        if settings_doc.vat_tax_rate_b:
            tax_rate = settings_doc.vat_tax_rate_b
            
        return tax_rate
        
    def get_default_tax_rate_c():
        tax_rate =0
        settings_doc = frappe.get_doc("TIS Settings")
        if settings_doc.vat_tax_rate_c:
            tax_rate = settings_doc.vat_tax_rate_c
            
        return tax_rate
    
    def get_default_tax_rate_d():
        tax_rate =0
        settings_doc = frappe.get_doc("TIS Settings")
        if settings_doc.vat_tax_rate_d:
            tax_rate = settings_doc.vat_tax_rate_d
            
        return tax_rate
    
    def get_default_tax_rate_e():
        tax_rate =0
        settings_doc = frappe.get_doc("TIS Settings")
        if settings_doc.vat_tax_rate_e:
            tax_rate = settings_doc.vat_tax_rate_e
            
        return tax_rate
        
    def strp_datetime_object(date_time_str):
        datetime_object = datetime.strptime(date_time_str, '%Y%m%d%H%M%S')
        
        return datetime_object
    
    def strp_date_object(date_str):
        date_object = datetime.strptime(date_str, '%Y%m%d')
        
        return date_object.date()
    
    def get_item_barcode(item_code, uom):
        item_barcodes = frappe.db.get_all("Item Barcode", filters={"parent": item_code, "uom": uom}, fields=["barcode"])
        
        if item_barcodes:
            
            return item_barcodes[0].get("barcode")
        
    def log_errors(title, description):
        new_doc = frappe.new_doc("Error Logging")
        new_doc.title = title
        new_doc.description = description
        
        new_doc.insert()
        
    def get_user_branch_id():
        current_user = frappe.session.user
        
        if "TIS Admin" not in frappe.get_roles(current_user):
            
            tax_branch_perms = frappe.db.get_all("User Permission", filters={"user":current_user, "allow": "Tax Branch Office"}, fields =["for_value"])
            
            if tax_branch_perms:
                tax_branch_id_current_user = tax_branch_perms[0].get("for_value")
                
                return  tax_branch_id_current_user
        
        if "TIS Admin" in frappe.get_roles(current_user):
            
            return "00"
        
    def itemSaveReq(doc_name):
        headers = eTIMS.get_headers()
        
        item = frappe.get_doc("Item", doc_name)
        
        if item.get("custom_item_classification_code"):
        
            payload = {
                "itemCd":item.get("custom_item_code"),
                "itemClsCd":item.get("custom_item_classification_code"),
                "itemClsNm":item.get("custom_item_classification_name"),
                "itemTyCd":item.get("custom_item_type_code"),
                "itemNm":item.get("custom_item_name"),
                "itemStdNm":item.get("custom_item_standard_name"),
                "orgnNatCd":item.get("custom_origin_place_code_nation"),
                "pkgUnitCd":item.get("custom_packaging_unit_code"),
                "qtyUnitCd":item.get("custom_quantity_unit_code"),
                "taxTyCd":item.get("custom_taxation_type_code"),
                "btchNo":item.get("custom_batch_number"),
                "bcd":item.get("custom_barcode"),
                "dftPrc":item.get("custom_default_unit_price"),
                "grpPrcL1":item.get("custom_group1_unit_price"),
                "grpPrcL2":item.get("custom_group2_unit_price"),
                "grpPrcL3": item.get("custom_group3_unit_price"),
                "grpPrcL4":item.get("custom_group4_unit_price"),
                "grpPrcL5":item.get("custom_group5_unit_price"),
                "addInfo":item.get("custom_additional_information"),
                "sftyQty":item.get("custom_safety_quantity"),
                "isrcAplcbYn":item.get("custom_insurance_appicableyn"),
                "useYn":item.get("custom_used__unused"),
                "regrId":item.get("custom_registration_id"),
                "regrNm":item.get("custom_registration_name"), 
                "modrId":item.get("custom_modifier_id"), 
                "modrNm":item.get("custom_modifier_name")
            }
            
            try:
                response = requests.request(
                    "POST", 
                    eTIMS.tims_base_url() + 'saveItem', 
                    json = payload,
                    headers=headers
                )

                response_json = response.json()
                
                if not response_json.get("resultCd") == '000':
                    
                    return {"Error":response_json.get("resultMsg")}
                
                item.custom_registered_in_tims = 1
                item.save()

                return {"Success":response_json.get("resultMsg")}

            except:
                
                return {"Error":"Oops Bad Request!"}
        else:
            frappe.throw("Missing Item Classification Code!")
    
        
    def map_new_item(item):
        item_exists = check_if_item_exits(item.get("itemNm"))
    
        if item_exists == False:
            # create item if not exists
            create_new_item_doctype(item)
            
            # create stock entry for receipt and update stock
        else:
            #check if item is update
            
            # create stock entry for receipt and update stock
            pass

def check_if_item_exits(item_code):
    item_exists = frappe.db.exists({"doctype": "Item", "item_code": item_code})
    
    if item_exists:
        
        return True
    else:
        return False

def create_new_item_doctype(item):
    current_user = frappe.session.user
    
    pkgUnitNm, qtyUnitNm = get_packing_and_quantity_unit(item.get("pkgUnitCd"), item.get("qtyUnitCd"))
    nat_of_origin = get_country_of_origin(item.get("itemCd"))
    
    new_item_doc = frappe.new_doc("Item")
    new_item_doc.item_code = item.get("itemNm")
    new_item_doc.custom_item_name = item.get("itemNm")
    new_item_doc.item_group = get_item_type(item.get("itemCd"))
    new_item_doc.stock_uom = "Nos"
    new_item_doc.valuation_rate = item.get("prc")
    new_item_doc.custom_country_of_origin = nat_of_origin
    new_item_doc.custom_item_classification_code = item.get("itemClsCd")
    new_item_doc.custom_packaging_unit_code = item.get("pkgUnitCd")
    new_item_doc.custom_quantity_unit_code = item.get("qtyUnitCd")
    new_item_doc.custom_default_packing_unit = pkgUnitNm
    new_item_doc.custom_default_quantity_unit = qtyUnitNm
    new_item_doc.custom_default_unit_price = item.get("prc")
    new_item_doc.custom_used__unused = "Y"
    new_item_doc.custom_taxation_type_code = item.get("taxTyCd")
    new_item_doc.custom_registration_id = current_user
    new_item_doc.custom_registration_name =current_user
    new_item_doc.custom_modifier_name = current_user
    new_item_doc.custom_modifier_id = current_user
    
    if item.get("taxTyCd"):
        tax_template = get_item_tax_template(item.get("taxTyCd"))
        new_item_doc.append("taxes",{
            "item_tax_template": tax_template
        })
        
    
    new_item_doc.insert()
    new_item_doc.custom_update_item_to_tims = 1
    
    new_item_doc.save()
    # frappe.db.commit()
    print("*"*90)
    print(new_item_doc.name)
    eTIMS.itemSaveReq(new_item_doc.name)

def get_packing_and_quantity_unit(pkgUnitCd, qtyUnitCd):
    packing_unit_name = "Non-Exterior Packaging Unit"
    quantity_unit_name = "Gross"
    
    packing_unit = frappe.db.get_all("eTIMS Packing Unit", filters={"etims_code": pkgUnitCd}, fields=["etims_code_name"])
    quantity_unit = frappe.db.get_all("eTIMS Quantity Unit", filters={"etims_code": qtyUnitCd}, fields=["etims_code_name"])
    
    if packing_unit:
        packing_unit_name = packing_unit[0].get("etims_code_name")
        
    if quantity_unit:
        quantity_unit_name = quantity_unit[0].get("etims_code_name")
        
    return packing_unit_name, quantity_unit_name
    
def get_country_of_origin(item_code):    
    nat_code = item_code[:2]
    
    try:
        etims_country_list = frappe.db.get_all("eTIMS Country", filters={"code_name": nat_code}, fields=["country_name", "code_name"])
        
        if etims_country_list:
            country_name = etims_country_list[0].get("country_name")
                        
            return country_name
    except:
        return "KE", "Kenya"
    
def get_item_type(item_code):
    item_type_code = item_code[2:3]

    item_group = "All Item Groups"
    
    if item_type_code == "1":
        item_group = "Raw Material"
    elif item_type_code == "2":
        item_group = "Products"
    elif item_type_code == "3":
        item_group = "Services"
    
    return item_group

def get_item_tax_template(tax_type_code):
    item_tax_doc = frappe.db.get_all("Item Tax Template", filters={"custom_code": tax_type_code}, fields=["name"])
    
    if item_tax_doc:
        
        return  item_tax_doc[0].get("name")
    
