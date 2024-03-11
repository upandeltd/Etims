# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe, traceback

from kenya_etims_compliance.utils.etims_utils import eTIMS

class eTIMSStockMovement(Document):
    
    def after_insert(self):
        if not self.stock_updated == 1:
            self.create_stock_trns_entry()
            # print(")"*70)
            # print(response)
            # if response == True:
            #     print("True")
            #     self.stock_updated = 1

            # self.save()
                    
    def create_stock_trns_entry(self):   
        tax_branch, self_pin = get_branch_and_pin()
        
        current_user_roles = frappe.get_roles()
        
        if "Tax Admin" or "Administrator" in current_user_roles:
            if self.customer_tin == self_pin:
                if not self.customer_branch == "00":
                    source_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": "00"}, fields=["warehouse_name", "name"])
                    
                    target_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": self.customer_branch}, fields=["warehouse_name", "name"])
                    
                    if source_warehouse and target_warehouse:
                        source_store = source_warehouse[0].get("name")
                        receipt_store = target_warehouse[0].get("name")
                                    
                        new_stock_doc = frappe.new_doc("Stock Entry")
                        new_stock_doc.stock_entry_type = "Material Transfer"
                        new_stock_doc.custom_total_tax_amount = self.total_vat
                        new_stock_doc.custom_send_stock_info_to_etims = 1
                        new_stock_doc.from_warehouse = source_store
                        new_stock_doc.to_warehouse = receipt_store
                        
                        if self.items:
                            for item in self.items:
                                if not item.get("stock_updated") == 1:
                                    try:
                                        item_dict = assign_stock_item(item)
                                    
                                        new_stock_doc.append("items", item_dict)
                                    
                                        new_stock_doc.save()
                                        # update etims purchase item
                                        frappe.db.set_value('eTIMS Stock Movement Item', item.name, {'stock_updated': 1}, update_modified=True)
                                        frappe.db.set_value('eTIMS Stock Movement', self.name, {'stock_updated': 1, "stock_entry": new_stock_doc.name}, update_modified=True)
                                        
                                        frappe.db.commit()
                                    except:
                                        frappe.throw(traceback.format_exc())
                        else:
                            print("()"*89)
                            print("oakety")
                    else:  
                        frappe.throw("Warehouse not found for tax branch!")

              
                elif self.customer_branch == "00" and not tax_branch == "00":
                    
                    source_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": tax_branch}, fields=["warehouse_name", "name"])
                    
                    target_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": self.customer_branch}, fields=["warehouse_name", "name"])
                    
                    if source_warehouse and target_warehouse:
                        source_store = source_warehouse[0].get("name")
                        receipt_store = target_warehouse[0].get("name")
                        print("*"*80)
                        print(source_store, receipt_store)
                        
                                   
                        new_stock_doc = frappe.new_doc("Stock Entry")
                        new_stock_doc.stock_entry_type = "Material Transfer"
                        new_stock_doc.custom_total_tax_amount = self.total_vat
                        new_stock_doc.custom_send_stock_info_to_etims = 1
                        new_stock_doc.from_warehouse = source_store
                        new_stock_doc.to_warehouse = receipt_store
                            
                        if self.items:
                            for item in self.items:
                                if not item.get("stock_updated") == 1:
                                    try:
                                        item_dict = assign_stock_item(item)
                                    
                                        new_stock_doc.append("items", item_dict)
                                    
                                        new_stock_doc.save()
                                        # update etims purchase item
                                        frappe.db.set_value('eTIMS Stock Movement Item', item.name, {'stock_updated': 1}, update_modified=True)
                                        frappe.db.set_value('eTIMS Stock Movement', self.name, {'stock_updated': 1, "stock_entry": new_stock_doc.name}, update_modified=True)
                                        
                                        frappe.db.commit()
                                    except:
                                        frappe.throw(traceback.format_exc())
                        else:
                            print("()"*89)
                            print("oakety")
                    else:  
                        frappe.throw("Warehouse not found for tax branch!")
                            

def assign_stock_item(item):  
    item_dict =  {
        "item_code": item.get("item_name"),
        "qty": item.get("unit_quantity"),
        "custom_tax_code": item.get("taxation_type_code"),
        "custom_tax_amount":item.get("tax_amount")
    }   
    
    
    return item_dict

def get_branch_and_pin():
    own_pin = ""
    tax_branch = ""
    settings_doc = frappe.get_doc("TIS Settings", "TIS Settings")
    if settings_doc:
        tax_branch = settings_doc.get("branch_id")
    
    init_doc = frappe.db.get_all("TIS Device Initialization", fields=["pin"])
    
    if init_doc:
        own_pin = init_doc[0].get("pin")
        
    return tax_branch, own_pin
        
    