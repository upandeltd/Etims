# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt
import traceback

import frappe
from frappe.model.document import Document

class eTIMSImportItem(Document):
    def after_insert(self):
        create_and_link_erpnext_stock_entry(self)
    

def create_and_link_erpnext_stock_entry(item):
    to_warehouse = get_target_warehouse()
    
    if not item.get("stock_entry_created") == 1:
        stk_doc_exists = frappe.db.exists("Stock Entry", {"custom_task_code": item.get("task_code"), "custom_is_import_stock":1})
        
        if not stk_doc_exists:
            new_stk_entry_doc = frappe.new_doc("Stock Entry")
            new_stk_entry_doc.stock_entry_type = "Material Receipt"
            new_stk_entry_doc.to_warehouse = to_warehouse
            new_stk_entry_doc.custom_task_code = item.get("task_code")
            new_stk_entry_doc.custom_is_import_stock = 1
                    
            try:
                item_dict = assign_stock_item(item)
            
                new_stk_entry_doc.append("items", item_dict)

                new_stk_entry_doc.save()

                # update etims purchase item
                frappe.db.set_value('eTIMS Import Item', item.name, {'stock_entry_created': 1, 'stock_entry': new_stk_entry_doc.name}, update_modified=True)
                
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
        
            
def assign_stock_item(item):  
    item_dict =  {
        "item_code": item.get("item_name"),
        "qty": item.get("quantity")
    } 

    return item_dict

def get_target_warehouse():        
        user_branch = get_user_branch_perms()

        target_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": user_branch}, fields=["warehouse_name", "name"])
        
        return target_warehouse[0].get("name")
        
def get_user_branch_perms():
    cur_user = frappe.session.user
      
    user_branch_permissions = frappe.db.get_all("User Permission", filters={"user": cur_user, "allow": "Tax Branch Office", "is_default": 1}, fields=["for_value"])
    
    if user_branch_permissions:
                
        return user_branch_permissions[0].get("for_value")