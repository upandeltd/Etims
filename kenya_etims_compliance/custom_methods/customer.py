import requests

import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS

@frappe.whitelist()
def bhfCustSaveReq(doc_name):
    headers = eTIMS.get_headers()
    item = frappe.get_doc("Customer", doc_name)

    customer = {
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
 
    try:
        response = requests.request(
            "POST", 
            eTIMS.tims_base_url() + 'saveBhfCustomer', 
            json = customer, 
            headers=headers
        )

        response_json = response.json()

        if not response_json.get("resultCd") == '000':
            return {"Error":response_json.get("resultMsg")}

        item.custom_is_registered = 1
        item.save()

        return {"Success":response_json.get("resultMsg")}

    except:
        return {"Error":"Oops Bad Request!"}	

