# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

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
        new_purchase_doc.
    
    def create_supplier(self):
        supplier_exists = frappe.db.exists("Supplier")
        
        if not supplier_exists:
            new_supplier = frappe.new_doc("Supplier")
            new_supplier.supplier_name = self.supplier_name
            new_supplier.custom_supplier_pin = self.supplier_pin
            new_supplier.custom_branch_id = self.supplier_branch_id
        
            new_supplier.insert()
            frappe.db.commit()