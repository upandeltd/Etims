import frappe
from kenya_etims_compliance.utils.kra_client import KRAClient

@frappe.whitelist()
def bhfCustSaveReq(doc_name):
    item = frappe.get_doc("Customer", doc_name)

    customer = {
        "custNo": item.get("custom_customer_number"),
        "custTin": item.get("tax_id"),
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
        result = KRAClient().post("saveBhfCustomer", customer)

        if result.get("Error"):
            frappe.logger().debug("Customer registration error: {0}".format(result.get("Error")))
            return {"Error": result.get("Error")}

        item.custom_is_registered = 1
        item.save()

        return {"Success": result.get("Success")}

    except Exception as e:
        frappe.log_error("eTIMS: Customer registration error", str(e))
        return {"Error": "Oops Bad Request!"}	

