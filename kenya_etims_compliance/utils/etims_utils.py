from datetime  import datetime

import frappe
from kenya_etims_compliance.utils.kra_client import KRAClient

class eTIMS():
    @staticmethod
    def get_headers():
        branch_id = eTIMS.get_user_branch_id()
        header_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id, "active":1}, fields=["pin", "branch_id", "communication_key"])
        
        if header_docs:
            headers = {
                "tin":header_docs[0].get("pin"),
                "bhfId":header_docs[0].get("branch_id"),
                "cmcKey":header_docs[0].get("communication_key"),
            }
            
            return headers
        
    @staticmethod
    def get_base_url():
        base_url = frappe.utils.get_url()
        
        return base_url

    @staticmethod
    def strf_datetime_object(datetime_data):
        datetime_object = datetime.strptime(datetime_data, '%Y-%m-%d %H:%M:%S')
        date_time_str = datetime_object.strftime("%Y%m%d%H%M%S")
        
        return date_time_str
    
    @staticmethod
    def strf_datetime_format(datetime_data):
        date_time_str  = ""
        if isinstance(datetime_data, str):
            try:
                datetime_object = datetime.strptime(datetime_data, '%Y-%m-%d %H:%M:%S.%f')
                date_time_str = datetime_object.strftime("%Y%m%d%H%M%S")
          
            except Exception as e:
                frappe.log_error("eTIMS: Utils error", str(e))
                datetime_object = datetime.strptime(datetime_data, '%Y-%m-%d %H:%M:%S')
                date_time_str = datetime_object.strftime("%Y%m%d%H%M%S")
      
        else:     
            date_time_str = datetime_data.strftime("%Y%m%d%H%M%S")
        
        return date_time_str
    
    @staticmethod
    def strf_date_object(date_data):
        date_str = ""
        try:
            date_object = datetime.strptime(date_data, '%Y-%m-%d')
            date_str = date_object.strftime("%Y%m%d")
                    
        except Exception as e:
            frappe.log_error("eTIMS: Utils error", str(e))
            date_str = date_data.strftime("%Y%m%d")
        
        return date_str
    
    @staticmethod
    def strf_time(time_data):
        time_str = ""
        try:
            time_object = datetime.strptime(time_data, '%H:%M:%S')
            time_str = time_object.strftime("%H%M%S")
        except Exception as e:
            frappe.log_error("eTIMS: Utils error", str(e))
            time_object = datetime.strptime(time_data, '%H:%M:%S.%f')
            time_str = time_object.strftime("%H%M%S")
   
        return time_str
    
    @staticmethod
    def get_response_data(response):    
        if response.get("message"):
            return response.get("message")
        else:
            return response
    
    @staticmethod
    def tims_base_url():
        """Get TIS base URL from settings"""
        from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import get_api_url

        branch_id = eTIMS.get_user_branch_id()
        settings_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id, "active":1}, fields=["*"])

        if settings_docs:
            api_mode = settings_docs[0].api_mode
            return get_api_url(api_mode)

        # Fallback: use default sandbox URL when no active device found
        return get_api_url("Sandbox")

    @staticmethod
    def verify_supplier_pin(supplier_pin):
        """Verify supplier PIN via KRA selectCustomer endpoint."""
        if not supplier_pin or len(supplier_pin) != 10:
            return {"Error": "Invalid PIN format"}
        client = KRAClient()
        return client.post("selectCustomer", {"custmTin": supplier_pin})

    @staticmethod
    def strp_datetime_object(date_time_str):
        datetime_object = datetime.strptime(date_time_str, '%Y%m%d%H%M%S')
        
        return datetime_object
    
    @staticmethod
    def strp_date_object(date_str):
        date_object = datetime.strptime(date_str, '%Y%m%d')
        
        return date_object.date()
    
    @staticmethod
    def strp_time_object(time_str):
        time_object = datetime.strptime(time_str, '%H%M%S')
        
        return time_object.time()
    
    @staticmethod
    def get_item_barcode(item_code, uom):
        item_barcodes = frappe.db.get_all("Item Barcode", filters={"parent": item_code, "uom": uom}, fields=["barcode"])
        
        if item_barcodes:
            
            return item_barcodes[0].get("barcode")
        
    @staticmethod
    def log_errors(title, description):
        """Log errors to Error Logging doctype if enabled in settings"""
        from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import get_etims_settings

        settings = get_etims_settings()
        if not settings.get("enable_error_logging", 1):
            return

        new_doc = frappe.new_doc("Error Logging")
        new_doc.title = title
        new_doc.description = description

        new_doc.insert()

    @staticmethod
    def handle_api_response(response_json):
        """Handle API response with proper error code mapping"""
        result_cd = response_json.get("resultCd")
        result_msg = response_json.get("resultMsg", "Unknown error")

        if result_cd == '000':
            return {"Success": response_json.get("data")}
        elif result_cd == '400':
            error_msg = f"Bad Request: {result_msg}"
            eTIMS.log_errors("API Error (400)", error_msg)
            return {"Error": error_msg}
        elif result_cd == '401':
            error_msg = f"Unauthorized: {result_msg}"
            eTIMS.log_errors("API Error (401)", error_msg)
            return {"Error": error_msg}
        elif result_cd == '500':
            error_msg = f"Server Error: {result_msg}"
            eTIMS.log_errors("API Error (500)", error_msg)
            return {"Error": error_msg}
        else:
            return {"Error": f"Error {result_cd}: {result_msg}"}
            
    @staticmethod
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
            new_doc.orginal_sr_number = eTIMS.get_org_etims_sar_no(doc)
            new_doc.insert()

            return new_sar_no
        except Exception as e:
            frappe.log_error("eTIMS: Utils error", str(e))
            new_doc = frappe.new_doc("eTIMS Stock Release Number") 
            new_doc.reference_type = doc.doctype
            new_doc.reference = doc.name
            new_doc.tax_branch_office = doc.custom_tax_branch_office
            new_doc.sr_number = etims_sar_no 
            new_doc.orginal_sr_number = eTIMS.get_org_etims_sar_no(doc)
            
            new_doc.insert()

            return etims_sar_no

        
    @staticmethod
    def get_org_etims_sar_no(doc):
        org_etims_sar_no = 0
        
        if doc.custom_original_invoice_number:
            prev_doc  = frappe.db.get_all("eTIMS Stock Release Number", filters={"reference": doc.return_against}, fields=["sr_number"])
            
            org_etims_sar_no = prev_doc[0].get("sr_number")
        
            return org_etims_sar_no
        else:

            return org_etims_sar_no
        
        
    # def get_last_inv_number(doc, last_set_no, last_no):
    #     branch_id = eTIMS.get_user_branch_id()
    #     cur_number = 0
    #     last_inv_no = 0
    #     # no_list = []
    #     settings_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id}, fields=["*"])
    #     # invs_nos = frappe.db.get_all(doc.doctype,
    #     #                                 filters = {'name': ['!=', doc.name], "custom_tax_branch_office": branch_id},
    #     #                                 fields=[last_no]
    #     #                             )
    #     # for inv_no in invs_nos:
    #     #     if not inv_no.get(last_no) in no_list:
    #     #         no_list.append(inv_no.get(last_no))
                
    #     if settings_docs:
    #         # last_inv_no = settings_docs[0].get("last_sales_invoice_number")
            
    #         last_inv_no = settings_docs[0].get(last_set_no)
    
    #     try:
    #         last_inv = frappe.db.get_all(doc.doctype,
    #                                         filters = {'name': ['!=', doc.name], "custom_tax_branch_office": branch_id},
    #                                         fields=[last_no],
    #                                         order_by='{} desc'.format(last_no),
    #                                         page_length = 1
    #                                     )
            
    #         if last_inv[0]:
    #             # print(last_inv)
    #             last_inv_no = last_inv[0].get(last_no)
                
    #         cur_number = last_inv_no + 1
            
    #     except Exception:

    #         cur_number = last_inv_no + 1
        
    #     return cur_number
    
    # def get_last_sr_number():
    #     etims_sar_no = 0
    #     branch_id = eTIMS.get_user_branch_id()
    #     settings_docs = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": branch_id}, fields=["last_stock_release_number"])
        
    #     if settings_docs:            
    #         etims_sar_no = settings_docs[0].get("last_stock_release_number")
            
    #     try:
    #         etims_sar_docs = frappe.get_last_doc("eTIMS Stock Release Number", filters={"tax_branch_office": branch_id})
            
    #         etims_sar_no = etims_sar_docs.get("sr_number") + 1
            
    #     except Exception:
    #         etims_sar_no += 1
        
    #     return etims_sar_no
     
        
    @staticmethod
    def get_user_branch_id():
        current_user = frappe.session.user
            
        tax_branch_perms = frappe.db.get_all("User Permission", filters={"user":current_user, "allow": "Tax Branch Office", "is_default": 1}, fields =["for_value"])
                
        if tax_branch_perms:
            tax_branch_id_current_user = tax_branch_perms[0].get("for_value")
            
            return  tax_branch_id_current_user

        
    @staticmethod
    def itemSaveReq(doc_name):
        item = frappe.get_doc("Item", doc_name)

        if not item.get("custom_item_classification_code"):
            frappe.throw("Missing Item Classification Code!")

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

        client = KRAClient()
        result = client.save_item(payload)

        if "Success" in result:
            item.custom_registered_in_tims = 1
            item.save()
            return {"Success": "Item registered successfully"}

        return result
    
        
    @staticmethod
    def map_new_item(item):
        item_exists = check_if_item_exits(item.get("itemNm"))
    
        if item_exists == False:
            # create item if not exists
            create_new_item_doctype(item)
            
        else:
            pass
        
    @staticmethod
    def get_name_of_user(user):
        user_full_name = frappe.db.get_value("User", user, 'full_name')

        return user_full_name

    # Search Endpoints - Phase 1.2

    @staticmethod
    def searchItem(item_code=None, item_name=None, last_req_dt=None):
        """Search items in eTIMS (Section 7.13)"""
        payload = {}
        if item_code:
            payload["itemCd"] = item_code
        if item_name:
            payload["itemNm"] = item_name
        if last_req_dt:
            payload["lastReqDt"] = eTIMS.strf_datetime_format(last_req_dt)

        client = KRAClient()
        return client.search_item(payload)

    @staticmethod
    def searchStockMove(sar_no=None, last_req_dt=None):
        """Search stock movements in eTIMS (Section 7.15)"""
        payload = {}
        if sar_no:
            payload["sarNo"] = sar_no
        if last_req_dt:
            payload["lastReqDt"] = eTIMS.strf_datetime_format(last_req_dt)

        client = KRAClient()
        return client.search_stock_move(payload)

    @staticmethod
    def searchTrns(invoice_no=None, last_req_dt=None, trns_type=None):
        """Search transactions in eTIMS (Section 7.14/7.20)
        trns_type: 'sales' or 'purchase'
        """

        payload = {}
        if invoice_no:
            payload["invcNo"] = invoice_no
        if last_req_dt:
            payload["lastReqDt"] = eTIMS.strf_datetime_format(last_req_dt)

        if trns_type == 'sales':
            endpoint = 'searchTrnsSales'
        elif trns_type == 'purchase':
            endpoint = 'searchTrnsPurchase'
        else:
            return {"Error": "Invalid transaction type. Use 'sales' or 'purchase'"}

        client = KRAClient()
        return client.search_trns(endpoint, payload)

    # Stock Release Number Management - Phase 2.1

    @staticmethod
    def stockReleaseNoSaveReq(sar_no, org_sar_no=0, sar_type=None):
        """Save stock release number to eTIMS (Section 7.16)

        Args:
            sar_no: Stock release number
            org_sar_no: Original stock release number (default: 0)
            sar_type: SAR type code (default: from settings, typically '11')
        """
        client = KRAClient()

        if sar_type is None:
            sar_type = client.settings.get("default_sar_type_sales", "11")

        payload = {
            "sarNo": sar_no,
            "orgSarNo": org_sar_no,
            "sarTyCd": sar_type
        }

        return client.stock_release_no_save(payload)

    @staticmethod
    def searchStockReleaseNo(sar_no=None, last_req_dt=None):
        """Search stock release numbers in eTIMS (Section 7.17)"""
        payload = {}
        if sar_no:
            payload["sarNo"] = sar_no
        if last_req_dt:
            payload["lastReqDt"] = eTIMS.strf_datetime_format(last_req_dt)

        client = KRAClient()
        return client.search_stock_release_no(payload)

    @staticmethod
    def selectStockReleaseNoList(last_req_dt=None):
        """Get stock release number list from eTIMS (Section 7.18)"""
        payload = {}
        if last_req_dt:
            payload["lastReqDt"] = eTIMS.strf_datetime_format(last_req_dt)

        client = KRAClient()
        return client.select_stock_release_no_list(payload)

    # Detail Query Endpoints - Phase 3.1

    @staticmethod
    def selectItem(item_code):
        """Get item details from eTIMS (Section 7.9)"""
        client = KRAClient()
        return client.select_item({"itemCd": item_code})

    @staticmethod
    def selectTrnsSalesInfo(invoice_no):
        """Get sales transaction details from eTIMS (Section 7.21)"""
        client = KRAClient()
        return client.select_trns_sales_info({"invcNo": invoice_no})

    @staticmethod
    def selectTrnsPurchaseInfo(invoice_no):
        """Get purchase transaction details from eTIMS (Section 7.21)"""
        client = KRAClient()
        return client.select_trns_purchase_info({"invcNo": invoice_no})

    # Medium Priority Features - Phase 4

    @staticmethod
    def selectNoticeInfo(notice_no):
        """Get notice details from eTIMS (Section 7.23)"""
        client = KRAClient()
        return client.select_notice_info({"ntcNo": notice_no})

    @staticmethod
    def selectOrgUsrInfo():
        """Get organization/user info from eTIMS (Section 7.5)"""
        client = KRAClient()
        return client.select_org_usr_info()

    # Invoice Verification - Phase 1: Invoice Checker API Integration

    @staticmethod
    def invoiceCheckerReq(invoice_no, supplier_pin, invoice_date, total_amount):
        """Check invoice validity via KRA Invoice Checker API

        Verifies if a supplier invoice is valid in KRA eTIMS system.
        This is critical for 2026 tax compliance - all purchases must be verified.

        Args:
            invoice_no: Supplier invoice number
            supplier_pin: Supplier Tax PIN
            invoice_date: Invoice date (YYYY-MM-DD or datetime object)
            total_amount: Total invoice amount (float/decimal)

        Returns:
            {"Success": {...}} or {"Error": "..."}
        """
        payload = {
            "invcNo": invoice_no,
            "spplrTin": supplier_pin,
            "invcDt": eTIMS.strf_date_object(invoice_date),
            "totAmt": str(total_amount)
        }

        client = KRAClient()
        result = client.select_trns_purchase_info(payload)

        # If successful, verify the invoice details match
        if "Success" in result:
            invoice_data = result["Success"]
            if invoice_data and invoice_data.get("invcNo") != invoice_no:
                return {"Error": "Invoice number mismatch in KRA system"}

        return result

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
 
    new_item_doc.custom_modifier_id = current_user
    
    if item.get("taxTyCd"):
        tax_template = get_item_tax_template(item.get("taxTyCd"))
        new_item_doc.append("taxes",{
            "item_tax_template": tax_template
        })
        
    
    new_item_doc.insert()
    new_item_doc.custom_update_item_to_tims = 1
    
    new_item_doc.save()

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
    except Exception as e:
        frappe.log_error("eTIMS: Utils error", str(e))
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


def get_next_sar_number(doc, branch_id):
    """Get next SAR number with database locking to prevent duplicates.

    Uses SELECT ... FOR UPDATE to lock rows. MUST be called BEFORE the
    KRA API call (during payload construction) to minimize lock hold time.
    Lock is released when the enclosing transaction commits.
    """
    last_sar = frappe.db.sql("""
        SELECT sr_number FROM `tabeTIMS Stock Release Number`
        WHERE tax_branch_office = %s
        ORDER BY sr_number DESC
        LIMIT 1
        FOR UPDATE
    """, (branch_id,), as_dict=True)

    next_number = (last_sar[0].sr_number + 1) if last_sar else 1

    new_doc = frappe.new_doc("eTIMS Stock Release Number")
    new_doc.reference_type = doc.doctype
    new_doc.reference = doc.name
    new_doc.tax_branch_office = branch_id
    new_doc.sr_number = next_number
    new_doc.orginal_sr_number = get_org_sar_number(doc)
    new_doc.insert()

    return next_number


def get_org_sar_number(doc):
    """Get original SAR number for returns/amendments."""
    if not doc.get("custom_original_invoice_number"):
        return 0

    prev = frappe.db.get_all(
        "eTIMS Stock Release Number",
        filters={"reference": doc.return_against},
        fields=["sr_number"],
        page_length=1
    )
    return prev[0].sr_number if prev else 0
