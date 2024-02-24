# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt
import traceback

import frappe
from frappe.model.document import Document


class eTIMSPurchaseInvoice(Document):

    def after_insert(self):
        self.create_supplier()
        
        if not self.erpnext_purchase_invoice_updated == 1:
            self.create_and_link_erpnext_purchase_invoice()
            

    def create_and_link_erpnext_purchase_invoice(self):
        new_purchase_doc = frappe.new_doc("Purchase Invoice")
        new_purchase_doc.supplier = self.supplier_name
        new_purchase_doc.custom_purchase_is_from_etims = 1
        new_purchase_doc.tax_id = self.supplier_pin
        new_purchase_doc.custom_purchase_type_code = "N"
        new_purchase_doc.custom_receipt_type_code = self.receipt_type_code
        new_purchase_doc.custom_payment_type_code = self.payment_type_code
        new_purchase_doc.bill_no = self.supplier_invoice_number
        new_purchase_doc.bill_date = self.sale_date
        
        for item in self.items:
            if not item.updated_in_purchase == 1:
                try:
                    item_dict = assign_purchase_item(item)
                
                    new_purchase_doc.append("items", item_dict)
                    
                    new_purchase_doc.save()

                    frappe.db.commit()
                except:
                    frappe.throw(traceback.format_exc())

    
    def create_supplier(self):
        supplier_exists = frappe.db.exists("Supplier")
        
        if not supplier_exists:
            new_supplier = frappe.new_doc("Supplier")
            new_supplier.supplier_name = self.supplier_name
            new_supplier.custom_supplier_pin = self.supplier_pin
            new_supplier.custom_branch_id = self.supplier_branch_id
        
            new_supplier.insert()
            frappe.db.commit()
            
def assign_purchase_item(item_detail):        
    item_dict = {
        "item_code": item_detail.get("item_name"),
        "item_name": item_detail.get("item_name"),
        "rate": item_detail.get("prc"),
        "qty": item_detail.get("splyAmt"),
        "discount_rate": item_detail.get("discount_percentage"),
        # "discount_amount": item_detail.get("discount_amount"),
        # "taxation_type_code": item_detail.get("taxTyCd"),
        # "taxable_amount": item_detail.get("taxblAmt"),
        # "tax_amount": item_detail.get("taxAmt"),
        # "total_amount": item_detail.get("totAmt")
    }

    return item_dict