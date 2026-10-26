import requests, segno  #pyqrcode
from datetime import datetime, timedelta, time

import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS


ETIMS_TAX_CODES = ["A", "B", "C", "D", "E"]
# Zero-rated supplies are taxable at 0%: eTIMS counts them in totTaxblAmt
ZERO_RATED_TAX_CODE = "C"


def validate(doc, method):
    '''
    Method validate invoice number before submitting invoice
    '''
    if doc.custom_invoice_number and doc.name:
        doc_exists = frappe.db.exists("Sales Invoice", {"name": doc.name})

        if doc_exists:
            if doc.custom_update_invoice_in_tims:
                invoice_numbers = validate_inv_number(doc)

                if doc.custom_invoice_number in invoice_numbers:
                    insert_invoice_number(doc, method)


def insert_invoice_number(doc, method):
    '''
    Method sets increment for invoice number and orginal invoice number before submitting invoice
    '''
    scu = ""
    sales_warehouse = None
    item_count = 0
    if doc.name and doc.custom_update_invoice_in_tims:
        branch_id = eTIMS.get_user_branch_id()
        init_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id}, fields=["sales_control_unit_id", "default_sales_warehouse"])

        if init_docs:
            scu = init_docs[0].get("sales_control_unit_id")
            sales_warehouse = init_docs[0].get("default_sales_warehouse")

        if doc.items:
            item_count = len(doc.items)
            insert_tax_amounts(doc)

        total_discount_amount = get_total_discount(doc)

        total_vat_amount = fetch_total_vat(doc)
        total_non_vat_amount = fetch_total_non_vat(doc)

        last_inv_number = get_last_inv_number(doc, branch_id)

        frappe.db.set_value('Sales Invoice', doc.name, {
            "custom_invoice_number": last_inv_number,
            "custom_sales_control_unit": scu,
            "update_stock": 1,
            "set_warehouse": sales_warehouse,
            "custom_tax_branch_office": branch_id,
            "custom_total_taxable_amount": total_vat_amount,
            "custom_total_nontaxable_amount": total_non_vat_amount,
            "custom_item_count": item_count,
            "custom_total_discount_amount": total_discount_amount,
            "custom_total_before_discount": total_discount_amount + doc.base_grand_total
        }, update_modified=True)

        doc.reload()


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
            except Exception:
                frappe.log_error(frappe.get_traceback(), "eTIMS insert_tax_amounts")
                frappe.throw("Could not update tax amounts for eTIMS.")


def get_total_discount(doc):
    discount_amount = 0

    if doc.items:
        for item in doc.items:
            if item.get("discount_percentage") > 0:
                total_dsc = item.get("custom_discount_amount_kes") * item.get("qty")
                discount_amount += total_dsc

    return discount_amount


def get_taxable_amounts(doc):
    taxable_amounts_dict = {}

    try:
        if doc.items:
            for item in doc.items:
                if not item.get("custom_tax_code") in taxable_amounts_dict.keys():
                    taxable_amounts_dict[item.get("custom_tax_code")] = 0

                taxable_amounts_dict[item.get("custom_tax_code")] += item.base_net_amount
    except Exception:
        frappe.log_error(frappe.get_traceback(), "eTIMS get_taxable_amounts")
        frappe.throw("Could not calculate taxable amounts for eTIMS.")

    return taxable_amounts_dict


def fetch_total_vat(doc):
    '''
    Total taxable amount stored on the invoice.
    Zero-rated (C) rows count as taxable even though their tax amount is 0.
    '''
    taxable_amount = 0
    if doc.taxes:
        for item in doc.taxes:
            tax_amount = item.get("base_tax_amount_after_discount_amount") or 0
            row_taxable = item.get("custom_total_taxable_amount") or 0

            if item.get("custom_code") == ZERO_RATED_TAX_CODE:
                taxable_amount += row_taxable
            elif tax_amount > 0:
                taxable_amount += row_taxable
            elif tax_amount < 0 and doc.is_return:
                taxable_amount += row_taxable

    return taxable_amount


def fetch_total_non_vat(doc):
    taxable_non_vat_amount = 0
    if doc.taxes:
        for item in doc.taxes:
            tax_amount = item.get("base_tax_amount_after_discount_amount") or 0

            if tax_amount == 0 and item.get("custom_code") != ZERO_RATED_TAX_CODE:
                taxable_non_vat_amount += item.get("custom_total_taxable_amount") or 0

    return taxable_non_vat_amount


@frappe.whitelist()
def trnsSalesSaveWrReq(doc, method):
    '''
    Method that collects sales information and updates it to tims server
    '''
    if not doc.custom_update_invoice_in_tims:
        return

    headers = eTIMS.get_headers()

    request_date_and_time = doc.modified

    conc_datetime_str = eTIMS.strf_datetime_format(request_date_and_time)

    now = datetime.now()
    date_time_str = now.strftime("%Y%m%d%H%M%S")

    request_date = doc.posting_date
    date_str = eTIMS.strf_date_object(request_date)

    count = doc.custom_item_count

    # Build the item list first: every header total is derived from it,
    # so the header always matches what KRA validates against.
    item_list = etims_sale_item_list_sales(doc)
    tot_taxbl_amt = round(sum(i["taxblAmt"] for i in item_list), 2)
    tot_tax_amt = round(sum(i["taxAmt"] for i in item_list), 2)

    payload = {
        "trdInvcNo": doc.name,
        "invcNo": doc.custom_invoice_number,
        "orgInvcNo": doc.custom_original_invoice_number,
        "custTin": doc.tax_id,
        "custNm": doc.customer,
        "salesTyCd": doc.custom_sales_type_code,
        "rcptTyCd": doc.custom_receipt_type_code,
        "pmtTyCd": doc.custom_payment_type_code,
        "salesSttsCd": doc.custom_invoice_status_code,
        "cfmDt": conc_datetime_str,
        "salesDt": date_str,
        "stockRlsDt": date_time_str,
        "totItemCnt": count,
        "totTaxblAmt": tot_taxbl_amt,
        "totTaxAmt": tot_tax_amt,
        "totAmt": abs(doc.base_grand_total),
        "prchrAcptcYn": "N",
        "remark": doc.remarks,
        "regrId": doc.owner,
        "regrNm": doc.owner,
        "modrId": doc.modified_by,
        "modrNm": doc.modified_by,
        "receipt": {
            "custTin": doc.tax_id,
            # "custMblNo":null,
            "rcptPbctDt": date_time_str,
            # "trdeNm":null,
            # "adrs":null,
            # "topMsg":null,
            # "btmMsg":null,
            "prchrAcptcYn": "N"
        },
        "itemList": item_list
    }

    # Tax rate per code, taken from the tax rows' accounts
    tax_rates = {}
    for tax_item in doc.taxes:
        code = tax_item.get("custom_code")
        if code and code not in tax_rates:
            tax_rates[code] = abs(get_tax_account_rate(tax_item.get("account_head")) or 0)

    # Per-type totals, derived from the same item list
    for code in ETIMS_TAX_CODES:
        lines = [i for i in item_list if i["taxTyCd"] == code]
        payload[f"taxblAmt{code}"] = round(sum(i["taxblAmt"] for i in lines), 2)
        payload[f"taxAmt{code}"] = round(sum(i["taxAmt"] for i in lines), 2)
        payload[f"taxRt{code}"] = tax_rates.get(code, 0)

    if doc.is_return == 1:
        return_status = sales_return_information(doc)

        if return_status == "partial":
            payload["rfdDt"] = date_time_str
            payload["rfdRsnCd"] = doc.custom_credit_note_reason_code
        elif return_status == "full":
            payload["cnclReqDt"] = conc_datetime_str
            payload["cnclDt"] = conc_datetime_str
            payload["rfdDt"] = date_time_str
            payload["rfdRsnCd"] = doc.custom_credit_note_reason_code
        elif return_status == "null":
            frappe.throw("Invalid, return amount is greater than original amount!")

    try:
        response = requests.request(
            "POST",
            eTIMS.tims_base_url() + 'saveTrnsSalesOsdc',
            json=payload,
            headers=headers)
        response_json = response.json()

        if not response_json.get("resultCd") == '000':
            frappe.throw(response_json.get("resultMsg"))

        data = response_json.get("data")
        control_unit_date_time = eTIMS.strp_datetime_object(data.get("sdcDateTime"))
        control_unit_date = eTIMS.strp_date_object(data.get("sdcDateTime")[0:8])
        control_unit_time = eTIMS.strp_time_object(data.get("sdcDateTime")[8:14])

        doc.custom_current_receipt_number = data.get("curRcptNo")
        doc.custom_total_receipt_number = data.get("totRcptNo")
        doc.custom_internal_data = data.get("intrlData")
        doc.custom_receipt_signature = data.get("rcptSign")
        doc.custom_control_unit_date_time = control_unit_date_time
        doc.custom_control_unit_date = control_unit_date
        doc.custom_control_unit_time = control_unit_time

        file_name = create_qr_code(headers.get("tin"), headers.get("bhfId"), data.get("rcptSign"))

        attachment_url = create_attachment(file_name, doc.name)

        doc.custom_receipt_qr_code = attachment_url

        create_sales_receipt(data, doc.name)

        stockIOSaveReq(doc, date_str)
        doc.custom_update_sales_to_etims = 1
        print(payload)

        frappe.msgprint(response_json.get("resultMsg"))

    except frappe.ValidationError:
        # Our own frappe.throw (e.g. KRA's resultMsg): show it as-is
        raise
    except Exception:
        frappe.log_error(frappe.get_traceback(), "eTIMS saveTrnsSalesOsdc")
        frappe.throw("Oops Bad Request!")


@frappe.whitelist()
def resend_to_etims(invoice_name):
    '''
    Send an already-submitted Sales Invoice to eTIMS
    (e.g. one submitted while eTIMS was rejecting it).
    Usage: bench --site erp.upande.com execute
           kenya_etims_compliance.kenya_etims_compliance.custom_methods.sales_invoice.resend_to_etims
           --kwargs "{'invoice_name': 'SINV-00761'}"
    '''
    doc = frappe.get_doc("Sales Invoice", invoice_name)

    if doc.docstatus != 1:
        frappe.throw(f"{invoice_name} is not submitted. Submit it normally instead.")

    if doc.custom_receipt_signature:
        frappe.throw(f"{invoice_name} already has an eTIMS signature ({doc.custom_receipt_signature}).")

    if not doc.custom_update_invoice_in_tims:
        frappe.throw(f"{invoice_name} is not marked to update in eTIMS (custom_update_invoice_in_tims).")

    trnsSalesSaveWrReq(doc, "resend")

    # Document is submitted, so persist the eTIMS response fields directly
    doc.db_set({
        "custom_current_receipt_number": doc.custom_current_receipt_number,
        "custom_total_receipt_number": doc.custom_total_receipt_number,
        "custom_internal_data": doc.custom_internal_data,
        "custom_receipt_signature": doc.custom_receipt_signature,
        "custom_control_unit_date_time": doc.custom_control_unit_date_time,
        "custom_control_unit_date": doc.custom_control_unit_date,
        "custom_control_unit_time": doc.custom_control_unit_time,
        "custom_receipt_qr_code": doc.custom_receipt_qr_code,
        "custom_update_sales_to_etims": doc.custom_update_sales_to_etims,
    })
    frappe.db.commit()

    return doc.custom_receipt_signature


def stockIOSaveReq(doc, date_str):
    # sar_no, org_sar_no = get_etims_sar_no(doc)
    taxAmt = 0
    taxblAmt = 0
    if not doc.custom_update_invoice_in_tims:
        return

    headers = eTIMS.get_headers()
    stock_list = etims_sale_item_list_stock(doc)
    if not len(stock_list):
        return

    for item in doc.items:
        if item.get("custom_maintain_stock") == 1 and item.get("custom_tax_code") in ["B", "E"]:
            taxblAmt += item.get("base_net_amount")
            taxAmt += (item.get("base_amount") - item.get("base_net_amount"))

    payload = {
        "sarNo": get_etims_sar_no(doc),
        "orgSarNo": get_org_etims_sar_no(doc),
        "regTyCd": "A",
        "custTin": doc.tax_id,
        "custNm": doc.customer,
        "custBhfId": "",
        "ocrnDt": date_str,
        "totItemCnt": len(stock_list),
        "totTaxblAmt": abs(round(taxblAmt, 2)),
        "totTaxAmt": abs(round(taxAmt, 2)),
        "totAmt": abs(doc.base_grand_total),
        "remark": doc.remarks,
        "regrId": doc.owner,
        "regrNm": doc.owner,
        "modrId": doc.modified_by,
        "modrNm": doc.modified_by,
        "itemList": stock_list
    }

    if doc.is_return == 1:
        return_status = sales_return_information(doc)

        if return_status == "partial" or return_status == "full":
            payload["sarTyCd"] = "03"

        elif return_status == "null":
            frappe.throw("Invalid, return amount is greater than original amount!")

    else:
        payload["sarTyCd"] = "11"

    try:
        print(payload)
        response = requests.request(
            "POST",
            eTIMS.tims_base_url() + 'insertStockIO',
            json=payload,
            headers=headers
        )

        response_json = response.json()

        if not response_json.get("resultCd") == '000':
            frappe.throw(response_json.get("resultMsg"))

        frappe.msgprint(response_json.get("resultMsg"))

    except frappe.ValidationError:
        raise
    except Exception:
        frappe.log_error(frappe.get_traceback(), "eTIMS insertStockIO")
        frappe.throw("Oops Bad Request!")


def get_etims_sar_no(doc):
    etims_sar_no = 1
    try:
        etims_sar_docs = frappe.get_last_doc("eTIMS Stock Release Number", filters={"tax_branch_office": doc.custom_tax_branch_office})

        new_sar_no = etims_sar_docs.get("sr_number") + 1

        new_doc = frappe.new_doc("eTIMS Stock Release Number")
        new_doc.reference_type = doc.doctype
        new_doc.reference = doc.name
        new_doc.tax_branch_office = doc.custom_tax_branch_office
        new_doc.sr_number = new_sar_no
        new_doc.orginal_sr_number = get_org_etims_sar_no(doc)
        new_doc.insert()
        frappe.db.commit()

        return new_sar_no
    except Exception:
        new_doc = frappe.new_doc("eTIMS Stock Release Number")
        new_doc.reference_type = doc.doctype
        new_doc.reference = doc.name
        new_doc.tax_branch_office = doc.custom_tax_branch_office
        new_doc.sr_number = etims_sar_no
        new_doc.orginal_sr_number = get_org_etims_sar_no(doc)

        new_doc.insert()
        frappe.db.commit()

        return etims_sar_no


def get_org_etims_sar_no(doc):
    org_etims_sar_no = 0

    if doc.custom_original_invoice_number:
        prev_doc = frappe.db.get_all("eTIMS Stock Release Number", filters={"reference": doc.return_against}, fields=["sr_number"])

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


def get_last_inv_number(doc, branch_id):

    cur_number = 0
    last_inv_no = 0

    if doc.custom_update_invoice_in_tims:
        settings_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id}, fields=["*"])

        if settings_docs:
            last_inv_no = settings_docs[0].get("last_sales_invoice_number")

        try:
            last_inv = frappe.db.get_all(doc.doctype,
                                         filters={'name': ['!=', doc.name], 'custom_update_invoice_in_tims': 1, "custom_tax_branch_office": branch_id},
                                         fields=["custom_invoice_number"],
                                         order_by='custom_invoice_number desc',
                                         page_length=1
                                         )

            if last_inv[0]:
                last_inv_no = last_inv[0].get("custom_invoice_number")

            cur_number = last_inv_no + 1

        except Exception:

            cur_number = last_inv_no + 1

    return cur_number


def validate_inv_number(doc):
    invoice_numbers = []
    invoice_number_list = frappe.db.get_all("Sales Invoice", fields=["custom_invoice_number", "name"], order_by='custom_invoice_number desc')

    if invoice_number_list:
        for invoice_no in invoice_number_list:
            if not invoice_no.get("name") == doc.name:
                if not invoice_no.get("custom_invoice_number") in invoice_numbers:
                    invoice_numbers.append(invoice_no.get("custom_invoice_number"))

    return invoice_numbers


def etims_sale_item_list_sales(doc):
    sales_item_list = []
    for item in doc.items:
        item_tax_code = get_tax_template_details(item.get("item_tax_template"))
        item_detail = frappe.db.get_all("Item", filters={"disabled": 0, "item_code": item.get("item_code")}, fields=["*"])
        item_etims_data = {
            "itemSeq": item.get("idx"),
            "itemCd": item_detail[0].get("custom_item_code"),
            "itemClsCd": item_detail[0].get("custom_item_classification_code"),
            "itemNm": item_detail[0].get("custom_item_name"),
            # "bcd":null,
            "pkgUnitCd": item_detail[0].get("custom_packaging_unit_code"),
            "pkg": abs(item.get("qty")),
            "qtyUnitCd": item_detail[0].get("custom_quantity_unit_code"),
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
            "taxTyCd": item_tax_code,
            "taxblAmt": abs(round(item.get("base_net_amount"), 2)),
            "taxAmt": abs(round((item.get("base_amount") - item.get("base_net_amount")), 2)),
            "totAmt": abs(item.get("base_amount"))
        }

        if not item_etims_data in sales_item_list:
            sales_item_list.append(item_etims_data)

    return sales_item_list


def etims_sale_item_list_stock(doc):
    stock_item_list = []
    for item in doc.items:
        if item.custom_maintain_stock:
            item_tax_code = get_tax_template_details(item.get("item_tax_template"))
            item_detail = frappe.db.get_all("Item", filters={"disabled": 0, "item_code": item.get("item_code")}, fields=["*"])
            item_etims_data = {
                "itemSeq": item.get("idx"),
                "itemCd": item_detail[0].get("custom_item_code"),
                "itemClsCd": item_detail[0].get("custom_item_classification_code"),
                "itemNm": item_detail[0].get("custom_item_name"),
                "pkgUnitCd": item_detail[0].get("custom_packaging_unit_code"),
                "pkg": item.get("qty"),
                "qtyUnitCd": item_detail[0].get("custom_quantity_unit_code"),
                "qty": abs(item.get("qty")),
                "prc": abs(item.get("base_rate")),
                "splyAmt": abs(item.get("base_amount")),
                "dcRt": abs(item.get("discount_percentage")),
                "dcAmt": abs(round((item.get("custom_discount_amount_kes") * item.get("qty")), 2)),
                "totDcAmt": abs(round((item.get("custom_discount_amount_kes") * item.get("qty")), 2)),
                "taxTyCd": item_tax_code,
                "taxblAmt": abs(round(item.get("base_net_amount"), 2)),
                "taxAmt": abs(round((item.get("base_amount") - item.get("base_net_amount")), 2)),
                "totAmt": abs(item.get("base_amount"))
            }

            if not item_etims_data in stock_item_list:
                stock_item_list.append(item_etims_data)

    return stock_item_list


def get_tax_template_details(template_name):
    if not template_name:
        return "D"

    tax_doc = frappe.get_doc("Item Tax Template", template_name)
    if tax_doc and tax_doc.custom_code:
        return tax_doc.custom_code
    else:
        return "D"


def get_tax_account_rate(account_head):
    tax_acc_docs = frappe.db.get_all("Account", filters={"name": account_head}, fields=["tax_rate"])

    if tax_acc_docs:
        tax_rate = tax_acc_docs[0].get("tax_rate")

        return tax_rate

    return 0


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


def create_qr_code(pin, branch_id, rcpt_signature):
    header_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id, "active": 1}, fields=["api_mode"])

    if rcpt_signature:
        if header_docs:
            settings_doc = header_docs[0]

            file_name = rcpt_signature + ".png"

            file_path = frappe.get_site_path('private', 'files', file_name)

            if settings_doc.get("api_mode") == "Production":
                url = "https://etims.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data=" + pin + branch_id + rcpt_signature
            else:
                url = "https://etims-sbx.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data=" + pin + branch_id + rcpt_signature

            try:
                qrcode = segno.make_qr(url)
                qrcode.save(file_path, scale=5)

                return file_name

            except Exception:
                frappe.throw("QR Code Not Generated!")


def create_attachment(file_name, inv_name):
    new_attachment = frappe.new_doc("File")
    new_attachment.file_name = file_name
    new_attachment.file_url = "/private/files/" + file_name
    new_attachment.attached_to_doctype = "Sales Invoice"
    new_attachment.attached_to_name = inv_name
    new_attachment.is_private = 1

    new_attachment.save()
    frappe.db.commit()

    return new_attachment.get("file_url")


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
