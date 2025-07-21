import requests

import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS

def insert_tax_code(doc, method):
    if doc.custom_send_stock_info_to_etims == 1:
        if doc.items:
            for item in doc.items:
                tax_code = frappe.db.get_value("eTIMS Item", {"item": item.get("item_code")}, "taxation_type_code")
                if tax_code:
                    item.custom_tax_code = tax_code
    
    insert_tax_rate_and_amount(doc, method)


def insert_tax_rate_and_amount(doc, method):
    if doc.custom_send_stock_info_to_etims == 1:
        main_tax_amount = total_taxable_amount = 0
        
        if doc.items:
            for item in doc.items:
                if item.get("custom_tax_code"):
                    main_tax_amount, total_taxable_amount = insert_item_tax(item)

                    doc.custom_total_tax_amount = round(main_tax_amount, 2)
                    doc.custom_total_taxable_amount = total_taxable_amount

def insert_item_tax(item):
    total_amount = main_tax_amount = total_taxable_amount = 0
    account_head_list = frappe.db.get_all("Account", filters={"account_type": "Tax", "custom_tax_code": item.get("custom_tax_code")}, fields=["tax_rate"])

    if account_head_list:
        item.custom_rate = account_head_list[0].get("tax_rate")

    if account_head_list[0].get("tax_rate") > 0:
        if item.get("basic_amount"):
            tax_rate = account_head_list[0].get("tax_rate")/100
            taxable_amount = item.get("basic_amount")/(1+tax_rate)
            tax_amount = item.get("basic_amount") - taxable_amount
            
            item.custom_tax_amount = round(tax_amount, 2)
            main_tax_amount += tax_amount
            total_amount += item.get("basic_amount")
            total_taxable_amount = round((total_amount - main_tax_amount), 2)

    return main_tax_amount, total_taxable_amount

def update_stock_to_etims(doc, method):
    if doc.custom_send_stock_info_to_etims == 1:
        item_count = 0
        request_date = doc.posting_date
        request_time = doc.posting_time
        
        date_str = eTIMS.strf_date_object(request_date)
        time_str = eTIMS.strf_time(request_time)
        
        for item in doc.items:
                item_count += 1
        
        # if doc.custom_send_stock_info_to_tims:
        if doc.stock_entry_type == "Material Receipt":
            if doc.custom_is_import_stock == 1:
                stockIOSaveReq(doc, date_str, item_count, "01", doc.custom_target_tax_branch_office)
            else:
                stockIOSaveReq(doc, date_str, item_count, "06", doc.custom_target_tax_branch_office)

                
        if doc.stock_entry_type == "Material Transfer":
            is_inter_branch = check_if_interbranch(doc)
            
            if is_inter_branch:
                if doc.custom_update_both_branches:
                    stockIOSaveReq(doc, date_str, item_count, "13", doc.custom_source_tax_branch_office)
                    
                    stockIOSaveReq(doc, date_str, item_count, "04", doc.custom_target_tax_branch_office)
                    # if not doc.custom_is_return:
                    #     stockIOSaveReq(doc, date_str, item_count, "13", doc.custom_source_tax_branch_office)
                    
                    #     stockIOSaveReq(doc, date_str, item_count, "04", doc.custom_target_tax_branch_office)
                    # else:
                    #     stockIOSaveReq(doc, date_str, item_count, "12", doc.custom_source_tax_branch_office)
                    
                    #     stockIOSaveReq(doc, date_str, item_count, "03", doc.custom_target_tax_branch_office)

def get_etims_details(company, branch_id, owner, modified_by):
    query = """
        SELECT 
            tbc.update_stock_selling AS update_stock
        FROM
            `tabTIS Device Initialization` AS tdi
        LEFT JOIN
            `tabTax Branch Configurations` AS tbc
        ON
            tbc.tis_device_initialization = tdi.name
        WHERE 
            tdi.company = %s
        AND
            tdi.branch_id = %s
        AND
            tdi.active = 1
    """

    results = frappe.db.sql(query, (company, branch_id), as_dict=True)
    
    if results:
        creator = frappe.db.get_value("eTIMS Branch User", {"system_user": owner, "saved": 1}, "user_name")
        modifier = frappe.db.get_value("eTIMS Branch User", {"system_user": modified_by, "saved": 1}, "user_name")

        if not creator:
            frappe.throw("Sales Invoice Creater Not Registered As Branch Operator")
        
        if not modifier:
            frappe.throw("Sales Invoice Modifier Not Registered As Branch Operator")
            
        results[0]["creator"] = creator
        results[0]["modifier"] = modifier
        
    return results[0]
        
def stockIOSaveReq(doc, date_str, item_count, sar_type, branch_id):    
    headers = get_headers(branch_id, doc.company)
    etims_details = get_etims_details(doc.company, branch_id, doc.owner, doc.modified_by)

    payload = {
        "sarNo": get_etims_sar_no(doc, branch_id),
        "orgSarNo": 0,
        "regTyCd": "A",
        # "custTin": headers.get("tin"),
        # "custNm": doc.customer,
        "custBhfId": "01",
        "ocrnDt": date_str,
        "totItemCnt": item_count,
        "totTaxblAmt": doc.custom_total_taxable_amount,
        "totTaxAmt": doc.custom_total_tax_amount,
        "totAmt": round(doc.total_incoming_value, 2),
        "remark": doc.remarks if doc.remarks else '',
        "regrId": etims_details.get("creator"),
        "regrNm": etims_details.get("creator"),
        "modrId": etims_details.get("modifier"),
        "modrNm": etims_details.get("modifier"),
        "sarTyCd": sar_type,
        "itemList": etims_stock_item_list(doc)
        }
    
        
    if doc.custom_send_stock_info_to_etims == 1:
        try:
            response = requests.request(
                        "POST", 
                        eTIMS.tims_base_url() + 'insertStockIO',
                        json = payload, 
                        headers=headers
                    )
        
            response_json = response.json()

            if not response_json.get("resultCd") == '000':
                print(response_json.get("resultMsg"))
                # eTIMS.log_errors("Stock Entry", response_json.get("resultMsg"))
                frappe.throw(response_json.get("resultMsg"))
                
            
            doc.custom_updated_in_etims = 1   
            frappe.msgprint(response_json.get("resultMsg"))

        except:
            
            frappe.throw("Error: Oops Bad Request!")
    else:
        print(branch_id)
        print(payload)

def get_etims_sar_no(doc, branch_id):
    etims_sar_no = 1
    etims_sar_docs = frappe.db.get_all(
                                        "eTIMS Stock Release Number", 
                                        filters={"tax_branch_office": branch_id}, 
                                        fields=["sr_number"],
                                        order_by='sr_number desc',
                                        page_length = 1
                                    )
    if etims_sar_docs:
        new_sar_no = etims_sar_docs[0].get("sr_number") + 1
        
        new_doc = frappe.new_doc("eTIMS Stock Release Number") 
        new_doc.reference_type = doc.doctype
        new_doc.reference = doc.name
        new_doc.tax_branch_office = branch_id
        new_doc.sr_number = new_sar_no
        new_doc.insert()
        frappe.db.commit()

        return new_sar_no
    
    else:
        new_doc = frappe.new_doc("eTIMS Stock Release Number") 
        new_doc.reference_type = doc.doctype
        new_doc.reference = doc.name
        new_doc.tax_branch_office = branch_id
        new_doc.sr_number = etims_sar_no 
        
        new_doc.insert()
        frappe.db.commit()

        return etims_sar_no
      
def check_if_interbranch(item):
    interbranch_transfer = False
    
    s_warehouse = item.get("from_warehouse")
    t_warehouse = item.get("to_warehouse")
    
    s_warehouse_doc = frappe.get_doc("Warehouse", s_warehouse)
    t_warehouse_doc = frappe.get_doc("Warehouse", t_warehouse)
    
    if s_warehouse_doc.get("custom_tax_branch_office") and t_warehouse_doc.get("custom_tax_branch_office"):
    
        if not s_warehouse_doc.get("custom_tax_branch_office") == t_warehouse_doc.get("custom_tax_branch_office"):
            interbranch_transfer = True
            
    else:
        pass
    
    return interbranch_transfer

def get_warehouse_branch(warehouse_name):
    try:
        warehouse_doc = frappe.get_doc("Warehouse", warehouse_name)
        
        return warehouse_doc.get("custom_tax_branch_office")
    except:
        frappe.throw("No tax branch id")
    
def etims_stock_item_list(doc):
    stock_item_list = []
    for item in doc.items:
        etims_item_code = frappe.db.get_value("eTIMS Item", {"item": item.get("item_code")}, "etims_item_code")

        if not etims_item_code: 
            frappe.throw("item {} does not have a corresponding eTIMS item.".format(item.get("item_code")))

        item_detail = frappe.get_doc("eTIMS Item", etims_item_code)
        item_etims_data = {
                    "itemSeq": item.get("idx"),
                    "itemCd": item_detail.get("etims_item_code"),
                    "itemClsCd": item_detail.get("item_classification_code"),
                    "itemNm": item_detail.get("item_name"),
                    # "bcd":null,
                    "pkgUnitCd": item_detail.get("packaging_unit_code"),
                    "pkg": item.get("qty"),
                    "qtyUnitCd": item_detail.get("quantity_unit_code"),
                    "qty": item.get("qty"),
                    "prc": round(item.get("basic_rate"), 2),
                    "splyAmt": item.get("basic_amount"),
                    "dcRt": 0.0,
                    "dcAmt": 0.0,
                    "totDcAmt": 0.0,
                    "taxTyCd": item_detail.get("taxation_type_code"),
                    "taxblAmt": round((item.get("amount") - item.get("custom_tax_amount")), 2),
                    "taxAmt": item.get("custom_tax_amount"),
                    "totAmt": round(item.get("amount"), 2)
                }

        if not item_etims_data in stock_item_list:
            stock_item_list.append(item_etims_data)
            
    return stock_item_list

def get_tax_template_details(item_code):
    item_doc = frappe.get_doc("Item", item_code)
    if item_doc:
        for tax_item in item_doc.taxes:
            tax_code = frappe.get_doc("Item Tax Template", tax_item.get("item_tax_template"))
            
            if tax_code:
                return tax_code.get("custom_code")
    else:
        return "D"
    
def get_headers(branch_id, company):
    header_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id, "active":1, "company": company}, fields=["pin", "branch_id", "communication_key"])

    if header_docs:
        headers = {
            "tin":header_docs[0].get("pin"),
            "bhfId":header_docs[0].get("branch_id"),
            "cmcKey":header_docs[0].get("communication_key"),
        }
        
        return headers