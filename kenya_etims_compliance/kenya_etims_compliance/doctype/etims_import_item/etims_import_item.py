# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt
import traceback

import frappe
from frappe.model.document import Document

class eTIMSImportItem(Document):
    def on_change(self):
        create_and_link_erpnext_purchase_invoice(self)

def create_and_link_erpnext_purchase_invoice(item):
    print(item)
    create_supplier(item.get("supplier_name"))
    if not item.get("purchase_invoice_created") == 1:
        purchase_invoice_exists = frappe.db.exists("Purchase Invoice", {"custom_task_code": item.get("task_code"), "custom_import_purchase":1})
        
        if not purchase_invoice_exists:
            new_purchase_doc = frappe.new_doc("Purchase Invoice")
            new_purchase_doc.supplier = item.get("supplier_name")
            new_purchase_doc.custom_purchase_type_code = "N"
            new_purchase_doc.custom_task_code = item.get("task_code")
            new_purchase_doc.update_stock = 1
            new_purchase_doc.custom_import_purchase = 1
            
            create_buying_price_list(item)
        
            try:
                item_dict = assign_purchase_item(item)
            
                new_purchase_doc.append("items", item_dict)
                
                new_purchase_doc.save()

                # update etims purchase item
                frappe.db.set_value('eTIMS Import Item', item.name, {'purchase_invoice_created': 1, 'invoice': new_purchase_doc.name}, update_modified=True)
                
                frappe.db.commit()
            except:
                frappe.throw(traceback.format_exc())
                    
def create_supplier(supplier_name):
    supplier_exists = frappe.db.exists("Supplier", {"supplier_name": supplier_name})
    
    if not supplier_exists:
        new_supplier = frappe.new_doc("Supplier")
        new_supplier.supplier_name = supplier_name
        # new_supplier.supplier_group = "All Suppliers Group"
    
        new_supplier.insert()
        frappe.db.commit()
            
def create_buying_price_list(item):
    item_price_ksh = (item.get("invoice_foreign_currency_amount")/item.get("package"))*item.get("invoice_foreign_currency_crt")
    
    price_list_exists = frappe.db.exists("Item Price", {"item_code": item.item_name, "price_list": "Standard Buying"})
    
    if not price_list_exists:
        new_price_list = frappe.new_doc("Item Price")
        new_price_list.item_code = item.get("item_name")
        new_price_list.price_list = "Standard Buying"
        new_price_list.price_list_rate = item_price_ksh
        new_price_list.insert()
        
        frappe.db.commit()
        
            
def assign_purchase_item(item_detail):        
    item_dict = {
        "item_code": item_detail.get("item_name"),
        "item_name": item_detail.get("item_name"),
        "rate": item_detail.get("tax_rate"),
        "qty": item_detail.get("package"),
    }

    return item_dict
