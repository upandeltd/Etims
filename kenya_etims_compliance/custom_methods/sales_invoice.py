import requests, segno, json  #pyqrcode
from datetime import datetime, timedelta, time

import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS
from frappe.exceptions import ValidationError


def validate(doc, method):
    '''
    Validation meethod
    '''
    if doc.name:
        doc_exists = frappe.db.exists("Sales Invoice", {"name": doc.name})
    
        if doc_exists:
            insert_tax_details(doc, method)
            
def confirm_etims_sinv(doc):
    # Skip execution if the document is being submitted
    if doc.docstatus == 1:
        return
    
    doc_exists = frappe.db.exists("eTIMS Sales Invoice", {"trader_invoice_number": doc.name})

    if doc_exists and doc_exists not in ["None", None]:
        frappe.throw(f'Delete eTIMS Sales Invoice <a href="/app/etims-sales-invoice/{doc_exists}" target="_blank">{doc_exists}</a> to continue editing.')
        
@frappe.whitelist()
def get_sinv_data(inv_name):    
    inv_data = frappe.get_doc("Sales Invoice", inv_name)

    return inv_data

@frappe.whitelist()
def get_etims_sinv_data(einv_name):    
    inv_data = frappe.get_doc("eTIMS Sales Invoice", einv_name)

    return inv_data

def insert_tax_details(doc,method):
    '''
    Method sets tax details e.g taxable amounts
    '''
    if doc.name and doc.custom_update_invoice_in_tims:                
        if doc.items:
            insert_tax_amounts(doc)
    
    
    auto_create_etims_sinv(doc.get("name"))
    # confirm_etims_sinv(doc)
                
def insert_tax_amounts(doc):
    if doc.items:
        taxable_amounts = get_taxable_amounts(doc)
        for key, value in taxable_amounts.items():
            try:
                if doc.taxes:
                    for item in doc.taxes:
                        if item.get("custom_code") == key:
                            tax_templates = frappe.db.get_all("Item Tax Template", filters={"custom_code": key}, fields=["custom_code_name"])
                            
                            if len(tax_templates):
                                frappe.db.set_value('Sales Taxes and Charges', 
                                                    item.get("name"),
                                                    {
                                                        'custom_total_taxable_amount': round(value, 2),
                                                        'custom_code_name': tax_templates[0].get("custom_code_name")
                                                    }, update_modified=True)
                                
                                frappe.db.commit()
                                doc.reload()
            except:
                frappe.throw(Exception)
            
def get_total_discount(doc):
    discount_amount = 0
    
    if doc.items:
        for item in doc.items:
            if item.get("discount_percentage") > 0:
                total_dsc = item.get("custom_discount_amount_kes") * item.get("qty")
                discount_amount +=  total_dsc 
                
    return discount_amount

def get_taxable_amounts(doc):
    taxable_amounts_dict = {}
    
    try:
        if doc.items:
            for item in doc.items:
                if not item.get("custom_tax_code") in taxable_amounts_dict.keys():
                    taxable_amounts_dict[item.get("custom_tax_code")] = 0
                
                taxable_amounts_dict[item.get("custom_tax_code")] += item.base_net_amount
    except:
        frappe.throw(Exception)

    return taxable_amounts_dict      

def fetch_total_vat(doc):
    taxable_amount = 0
    if doc.taxes:
        for item in doc.taxes:
            if item.get("base_tax_amount_after_discount_amount") > 0:
                taxable_amount += item.get("custom_total_taxable_amount")
            if item.get("base_tax_amount_after_discount_amount") < 0 and doc.is_return:
                taxable_amount += item.get("custom_total_taxable_amount")
                
    return taxable_amount
    
def fetch_total_non_vat(doc):
    taxable_non_vat_amount = 0
    if doc.taxes:
        for item in doc.taxes:
            if item.get("base_tax_amount_after_discount_amount") == 0:
                taxable_non_vat_amount += item.get("custom_total_taxable_amount")
                
    return taxable_non_vat_amount

def get_sales_type_code(sales_type):
    code = "P"
    key_value = {
        "N": "Normal",
        "C": "Copy",
        "T": "Training",
        "P": "Profoma"
        }
    for k, v in key_value.items():
        if sales_type == v:
            code = k
    return code

def get_rcpt_type_code(rcpt_type):
    code = "S"
    key_value = {
        "S": "Sale",
        "R": "Credit Note After Sale"
        }
    for k, v in key_value.items():
        if rcpt_type == v:
            code = k
    return code

def get_payment_type_code(pymnt_type):
    code = "01"
    key_value = {
        "01": "Cash",
        "02": "Credit",
        "03": "Cash/Credit",
        "04": "Bank Check",
        "05": "Debit&Credit Card",
        "06": "Mobile-Money",
        "07": "Other"
        }
    for k, v in key_value.items():
        if pymnt_type == v:
            code = k
    return code

def get_sales_status_code(sales_status):
    code = "02"
    key_value = {
        "01": "Wait for Approval",
        "02": "Approved",
        "03": "Cancel Request",
        "04": "Cancelled",
        "05": "Credit Note Generated",
        "06": "Transferred"
        }
    for k, v in key_value.items():
        if sales_status == v:
            code = k
    return code

@frappe.whitelist()
def create_etims_sinv():

    '''
    Method that collects sales information and updates it to tims server
    '''
    if not frappe.form_dict.message:
        frappe.throw("Missing 'message' in request data")

    raw_data = frappe.form_dict.message
    json_data = json.loads(raw_data)
    data_obj = json_data.get("data")
    doc_name = data_obj.get("doc_name")

    process_etims_sinv(doc_name)

@frappe.whitelist()
def auto_create_etims_sinv(doc_name):
    '''
    Method that collects sales information and updates it to tims server
    '''
    doc = frappe.get_doc("Sales Invoice", doc_name)
    
    if doc.custom_update_invoice_in_tims:
        branch_id = eTIMS.get_user_branch_id()
        
        settings_details = get_etims_details(doc.company, branch_id, doc.owner, doc.modified_by)

        if settings_details.get("auto_create_etims_sales_invoice")==1:
            process_etims_sinv(doc_name)

def process_etims_sinv(doc_name):
    payload = None
    doc = frappe.get_doc("Sales Invoice", doc_name)
    count = 0
    
    if doc.custom_update_invoice_in_tims:
        tax_code_list = []
        branch_id = eTIMS.get_user_branch_id()
        
        etims_details = get_etims_details(doc.company, branch_id, doc.owner, doc.modified_by)
                
        request_date_and_time = doc.modified
    
        conc_datetime_str = eTIMS.strf_datetime_format(request_date_and_time)
        
        now = datetime.now()
        date_time_str = now.strftime("%Y%m%d%H%M%S")
        
        request_date = doc.posting_date
        date_str = eTIMS.strf_date_object(request_date)
            
        count = len(doc.items)
                    
        payload = {
            "trdInvcNo": doc.name,
            "custTin": doc.tax_id,
            "custNm": doc.customer,
            "cfmDt": conc_datetime_str,
            "salesDt": date_str,
            "stockRlsDt": conc_datetime_str,
            "totItemCnt": count,
            "totDscAmt": abs(round(get_total_discount(doc), 2)),
            "totExDsc": abs(round((get_total_discount(doc) + doc.base_grand_total), 2)),
            "totNonTaxAmt": abs(round(fetch_total_non_vat(doc), 2)),
            "totTaxblAmt": abs(round(fetch_total_vat(doc), 2)),
            "totTaxAmt": abs(doc.base_total_taxes_and_charges),
            "totAmt": abs(doc.base_grand_total),
            "prchrAcptcYn":"N",
            "isRtn": doc.get("is_return"),
            "rtAgnst": doc.get("return_against"),
            "remark": doc.remarks,
            "update_stock": doc.update_stock,
            "regrNm": etims_details.get("creator"),
            "modrNm": etims_details.get("modifier"),
            "receipt":{
                "rcptPbctDt": date_time_str
                },
            "itemList": etims_sale_item_list_sales(doc)
        }
        
        for tax_item in doc.taxes:
            if not tax_item.get("custom_code") in tax_code_list:
                tax_code_list.append(tax_item.get("custom_code")) 
            
            if "A" in tax_code_list:
                if tax_item.custom_code == "A":
                    payload["taxblAmtA"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
                    payload["taxRtA"] =  abs(get_tax_account_rate(tax_item.get("account_head")))
                    payload["taxAmtA"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
            else:
                payload["taxblAmtA"] = 0
                payload["taxRtA"] =  0
                payload["taxAmtA"] = 0
            
            if "B" in tax_code_list:
                if tax_item.custom_code == "B":
                    payload["taxblAmtB"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
                    payload["taxRtB"] =  abs(get_tax_account_rate(tax_item.get("account_head")))
                    payload["taxAmtB"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
            else:
                payload["taxblAmtB"] = 0
                payload["taxRtB"] =  0
                payload["taxAmtB"] = 0
                
            if "C" in tax_code_list:
                if tax_item.custom_code == "C":
                    payload["taxblAmtC"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
                    payload["taxRtC"] =  abs(get_tax_account_rate(tax_item.get("account_head")))
                    payload["taxAmtC"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
            else:
                payload["taxblAmtC"] = 0
                payload["taxRtC"] =  0
                payload["taxAmtC"] = 0
                
            if "D" in tax_code_list:
                if tax_item.custom_code == "D":
                    payload["taxblAmtD"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
                    payload["taxRtD"] =  abs(get_tax_account_rate(tax_item.get("account_head")))
                    payload["taxAmtD"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
            else:
                payload["taxblAmtD"] = 0
                payload["taxRtD"] =  0
                payload["taxAmtD"] = 0
                
            if "E" in tax_code_list:
                if tax_item.custom_code == "E":
                    payload["taxblAmtE"] = abs(round(tax_item.get("custom_total_taxable_amount"), 2))
                    payload["taxRtE"] =  abs(get_tax_account_rate(tax_item.get("account_head")))
                    payload["taxAmtE"] = abs(tax_item.get("base_tax_amount_after_discount_amount"))
            else:
                payload["taxblAmtE"] = 0
                payload["taxRtE"] =  0
                payload["taxAmtE"] = 0
    
        try:
            doc_exists = frappe.db.exists("eTIMS Sales Invoice", {"trader_invoice_number": doc_name})

            if not doc_exists or doc_exists in ["None", None]:
                create_etims_sales_invoice(payload)

            else:
                update_existing_etims_sinv(doc_exists, payload)
                # frappe.throw(f'eTIMS Sales Invoice <a href="/app/etims-sales-invoice/{doc_exists}" target="_blank">{doc_exists}</a> already exists.')
            
        except ValidationError as e:
            frappe.throw(str(e))

def get_etims_sar_no(doc):
    etims_sar_no = 1
    branch_id = eTIMS.get_user_branch_id()
    try:
        etims_sar_docs = frappe.get_last_doc("eTIMS Stock Release Number", filters={"tax_branch_office": branch_id})
        
        new_sar_no = etims_sar_docs.get("sr_number") + 1
        
        new_doc = frappe.new_doc("eTIMS Stock Release Number") 
        new_doc.reference_type = doc.doctype
        new_doc.reference = doc.name
        new_doc.tax_branch_office = branch_id
        new_doc.sr_number = new_sar_no
        new_doc.orginal_sr_number = get_org_etims_sar_no(doc)
        new_doc.insert()
        frappe.db.commit()

        return new_sar_no
    except:
        new_doc = frappe.new_doc("eTIMS Stock Release Number") 
        new_doc.reference_type = doc.doctype
        new_doc.reference = doc.name
        new_doc.tax_branch_office = branch_id
        new_doc.sr_number = etims_sar_no 
        new_doc.orginal_sr_number = get_org_etims_sar_no(doc)
        
        new_doc.insert()
        frappe.db.commit()

        return etims_sar_no
    
def get_org_etims_sar_no(doc):
    org_etims_sar_no = 0
    
    if doc.custom_original_invoice_number:
        prev_doc  = frappe.db.get_all("eTIMS Stock Release Number", filters={"reference": doc.return_against}, fields=["sr_number"])
        
        org_etims_sar_no = prev_doc[0].get("sr_number")
    
        return org_etims_sar_no
    else:

        return org_etims_sar_no
    
def get_customer_details(customer):
    customer_kra_details = frappe.get_doc("Customer", customer)
    
    cust_dict = {
        "cust_pin": customer_kra_details.get("custom_customer_pin"),
        "cust_name": customer_kra_details.get("custom_customer_name")
    }
    
    return cust_dict


def etims_sale_item_list_sales(doc):
    sales_item_list = []
    for item in doc.items:
        etims_item_code = frappe.db.get_value("Item", {"name": item.get("item_code")}, "custom_etims_item_code")
        if not etims_item_code:
            frappe.throw("Item {} has not corresponding eTIMS Item.".format(item.get("item_code")))
            
        etims_item_exists = frappe.db.exists("eTIMS Item", {"etims_item_code": etims_item_code})
        if not etims_item_exists:
            frappe.throw("Item {} has not corresponding eTIMS Item.".format(item.get("item_code")))

        item_detail = frappe.get_doc("eTIMS Item", etims_item_exists)
        item_etims_data = {
					"itemSeq": item.get("idx"),
					"itemCd": item_detail.get("etims_item_code"),
					"itemClsCd": item_detail.get("item_classification_code"),
					"itemNm": item_detail.get("item_name"),
					# "bcd":null,
					"pkgUnitCd": item_detail.get("packaging_unit_code"),
					"pkg": abs(item.get("qty")),################################################################
					"qtyUnitCd": item_detail.get("quantity_unit_code"),
					"qty": abs(item.get("qty")),
					"prc": abs(item.get("base_rate")),
					"splyAmt": abs(item.get("base_amount")),
					"dcRt": abs(item.get("discount_percentage")),
					"dcAmt": abs(round((item.get("custom_discount_amount_kes") * item.get("qty")), 2)),
					# "isrccCd":null,
					# "isrccNm":null,
					# "isrcRt":null,
					# "isrcAmt":null,
                    "totDcAmt": abs(round((item.get("custom_discount_amount_kes") * item.get("qty")), 2)),
					"taxTyCd": item_detail.get("taxation_type_code"),
					"taxblAmt": abs(round(item.get("base_net_amount"), 2)),
					"taxAmt": abs(round((item.get("base_amount") - item.get("base_net_amount")), 2)),
					"totAmt": abs(item.get("base_amount")),
                    "update_stock": item.get("custom_maintain_stock")
				}

        if not item_etims_data in sales_item_list:
            sales_item_list.append(item_etims_data)
            
    return sales_item_list

def get_tax_template_details(template_name):
    tax_doc = frappe.get_doc("Item Tax Template", template_name)
    if tax_doc:
      
        tax_code =  tax_doc.custom_code
    
        return tax_code
    else:
        return "D"

def get_tax_account_rate(account_head):
    tax_acc_docs = frappe.db.get_all("Account", filters={"name": account_head}, fields=["tax_rate"])
    
    if tax_acc_docs:
        tax_rate = tax_acc_docs[0].get("tax_rate")
        
        return tax_rate
    
def create_sales_receipt(data, doc_name):
    control_unit_date_time = eTIMS.strp_datetime_object(data.get("sdcDateTime"))
    
    new_rcpt_doc = frappe.new_doc("eTIMS Sales Receipt")
    new_rcpt_doc.receipt_number = data.get("curRcptNo")
    new_rcpt_doc.total_receipt_number = data.get("totRcptNo")
    new_rcpt_doc.internal_data = data.get("intrlData")
    new_rcpt_doc.receipt_signature = data.get("rcptSign")
    new_rcpt_doc.control_unit_date_time = control_unit_date_time
    new_rcpt_doc.reference = doc_name
   
    new_rcpt_doc.insert()
    
    frappe.db.commit()

def sales_return_information(doc):
    diff_amount = 0
    return_status = ""
    
    if doc.is_return:
        if doc.return_against:
            return_amount = doc.grand_total
            return_against = frappe.get_doc("Sales Invoice", doc.return_against)
            prev_return_amount = return_against.grand_total
            
            diff_amount = prev_return_amount + return_amount
            
        if diff_amount > 0:
            return_status = "partial"
        elif diff_amount == 0:
            return_status = "full"
        elif diff_amount < 0:
            return_status = "null"
        
    return return_status


def get_etims_details(company, branch_id, owner, modified_by):
    query = """
        SELECT 
            tdi.sales_control_unit_id AS scu,
            tbc.update_stock_selling AS update_stock,
            tbc.auto_create_etims_sales_invoice
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

def create_etims_sales_invoice(payload):
    doc_exists = frappe.db.exists("eTIMS Sales Invoice", {"trader_invoice_number": payload.get("trdInvcNo")})

    if doc_exists:
        update_existing_etims_sinv(doc_exists, payload)

    new_doc = frappe.new_doc("eTIMS Sales Invoice")
    new_doc.trader_invoice_number = payload.get("trdInvcNo")
    new_doc.customer_tin = payload.get("custTin")
    new_doc.customer_name = payload.get("custNm")
    new_doc.sales_date = payload.get("salesDt")
    new_doc.update_stock = payload.get("update_stock")
    new_doc.confirmation_date = payload.get("cfmDt")
    new_doc.stock_release_date = payload.get("stockRlsDt")
    new_doc.total_item_count = payload.get("totItemCnt")
    new_doc.total_discount_amount = payload.get("totDscAmt")
    new_doc.total_before_discount = payload.get("totExDsc")
    new_doc.total_taxable_amount = payload.get("totTaxblAmt")
    new_doc.total_non_taxable_amount = payload.get("totNonTaxAmt")
    new_doc.total_tax_amount = payload.get("totTaxAmt")
    new_doc.total_amount = payload.get("totAmt")
    new_doc.purchase_accept = payload.get("prchrAcptcYn")
    new_doc.remark = payload.get("remark")
    new_doc.registration_name = payload.get("regrNm")
    new_doc.modifier_name = payload.get("modrNm")
    new_doc.receipt_publish_date = payload.get("receipt")["rcptPbctDt"]
    new_doc.taxable_amount_a = payload.get("taxblAmtA")
    new_doc.taxable_amount_b = payload.get("taxblAmtB")
    new_doc.taxable_amount_c = payload.get("taxblAmtC")
    new_doc.taxable_amount_d = payload.get("taxblAmtD")
    new_doc.taxable_amount_e = payload.get("taxblAmtE")
    new_doc.tax_rate_a = payload.get("taxRtA")
    new_doc.tax_rate_b = payload.get("taxRtB")
    new_doc.tax_rate_c = payload.get("taxRtC")
    new_doc.tax_rate_d = payload.get("taxRtD")
    new_doc.tax_rate_e = payload.get("taxRtE")
    new_doc.tax_amount_a = payload.get("taxAmtA")
    new_doc.tax_amount_b = payload.get("taxAmtB")
    new_doc.tax_amount_c = payload.get("taxAmtC")
    new_doc.tax_amount_d = payload.get("taxAmtD")
    new_doc.tax_amount_e = payload.get("taxAmtE")
    new_doc.is_return = payload.get("isRtn")
    new_doc.return_against = payload.get("rtAgnst")
    
    for item in payload.get("itemList"):
        new_doc.append("items", {
            "item_sequence_number": item.get("itemSeq") ,
            "etims_item_code": item.get("itemCd") ,
            "item_classification_code": item.get("itemClsCd") ,
            "item_name": item.get("itemNm") ,
            "packaging_unit_code": item.get("pkgUnitCd") ,
            "quantity_unit_code": item.get("qtyUnitCd") ,
            "update_stock": item.get("custom_maintain_stock"),
            "package": item.get("pkg") ,
            "quantity": item.get("qty") ,
            "unit_price": item.get("prc") ,
            "supply_amount": item.get("splyAmt") ,
            "discount_rate": item.get("dcRt") ,
            "total_discount_amount": item.get("dcAmt") ,
            "tax_type_code": item.get("taxTyCd") ,
            "taxable_amount": item.get("taxblAmt") ,
            "tax_amount": item.get("taxAmt") ,
            "total_amount": item.get("totAmt"),
            "update_stock": item.get("update_stock")
        })
        
    new_doc.insert()
    frappe.db.commit()

    # frappe.msgprint(f'eTIMS Sales Invoice <a href="/app/etims-sales-invoice/{new_doc.name}" target="_blank">{new_doc.name}</a> has been created.')

def update_existing_etims_sinv(etims_sinv_name, payload):
    etims_sinv_doc = frappe.get_doc("eTIMS Sales Invoice", etims_sinv_name)

    etims_sinv_doc.trader_invoice_number = payload.get("trdInvcNo")
    etims_sinv_doc.customer_tin = payload.get("custTin")
    etims_sinv_doc.customer_name = payload.get("custNm")
    etims_sinv_doc.sales_date = payload.get("salesDt")
    etims_sinv_doc.update_stock = payload.get("update_stock")
    etims_sinv_doc.confirmation_date = payload.get("cfmDt")
    etims_sinv_doc.stock_release_date = payload.get("stockRlsDt")
    etims_sinv_doc.total_item_count = payload.get("totItemCnt")
    etims_sinv_doc.total_discount_amount = payload.get("totDscAmt")
    etims_sinv_doc.total_before_discount = payload.get("totExDsc")
    etims_sinv_doc.total_taxable_amount = payload.get("totTaxblAmt")
    etims_sinv_doc.total_non_taxable_amount = payload.get("totNonTaxAmt")
    etims_sinv_doc.total_tax_amount = payload.get("totTaxAmt")
    etims_sinv_doc.total_amount = payload.get("totAmt")
    etims_sinv_doc.purchase_accept = payload.get("prchrAcptcYn")
    etims_sinv_doc.remark = payload.get("remark")
    etims_sinv_doc.registration_name = payload.get("regrNm")
    etims_sinv_doc.modifier_name = payload.get("modrNm")
    etims_sinv_doc.receipt_publish_date = payload.get("receipt")["rcptPbctDt"]
    etims_sinv_doc.taxable_amount_a = payload.get("taxblAmtA")
    etims_sinv_doc.taxable_amount_b = payload.get("taxblAmtB")
    etims_sinv_doc.taxable_amount_c = payload.get("taxblAmtC")
    etims_sinv_doc.taxable_amount_d = payload.get("taxblAmtD")
    etims_sinv_doc.taxable_amount_e = payload.get("taxblAmtE")
    etims_sinv_doc.tax_rate_a = payload.get("taxRtA")
    etims_sinv_doc.tax_rate_b = payload.get("taxRtB")
    etims_sinv_doc.tax_rate_c = payload.get("taxRtC")
    etims_sinv_doc.tax_rate_d = payload.get("taxRtD")
    etims_sinv_doc.tax_rate_e = payload.get("taxRtE")
    etims_sinv_doc.tax_amount_a = payload.get("taxAmtA")
    etims_sinv_doc.tax_amount_b = payload.get("taxAmtB")
    etims_sinv_doc.tax_amount_c = payload.get("taxAmtC")
    etims_sinv_doc.tax_amount_d = payload.get("taxAmtD")
    etims_sinv_doc.tax_amount_e = payload.get("taxAmtE")
    etims_sinv_doc.is_return = payload.get("isRtn")
    etims_sinv_doc.return_against = payload.get("rtAgnst")

    etims_sinv_doc.items = []
    etims_sinv_doc.save()

    for item in payload.get("itemList"):
        etims_sinv_doc.append("items", {
            "item_sequence_number": item.get("itemSeq") ,
            "etims_item_code": item.get("itemCd") ,
            "item_classification_code": item.get("itemClsCd") ,
            "item_name": item.get("itemNm") ,
            "packaging_unit_code": item.get("pkgUnitCd") ,
            "quantity_unit_code": item.get("qtyUnitCd") ,
            "update_stock": item.get("custom_maintain_stock"),
            "package": item.get("pkg") ,
            "quantity": item.get("qty") ,
            "unit_price": item.get("prc") ,
            "supply_amount": item.get("splyAmt") ,
            "discount_rate": item.get("dcRt") ,
            "total_discount_amount": item.get("dcAmt") ,
            "tax_type_code": item.get("taxTyCd") ,
            "taxable_amount": item.get("taxblAmt") ,
            "tax_amount": item.get("taxAmt") ,
            "total_amount": item.get("totAmt"),
            "update_stock": item.get("update_stock")
        })
        
    etims_sinv_doc.save()

    frappe.db.commit()
        