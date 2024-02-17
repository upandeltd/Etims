from datetime  import datetime
    
import frappe

class eTIMS():
    def get_headers():
        branch_id = eTIMS.get_user_branch_id()
        header_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id}, fields=["*"])
        
        if header_docs[0]:
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
        tims_base_url = eTIMS.get_base_url() + '/api/method/kenya_tims_compliance.utils.etims_response.'
        
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