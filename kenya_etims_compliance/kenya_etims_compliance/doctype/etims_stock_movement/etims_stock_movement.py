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
        source_warehouse, target_warehouse = self.get_source_and_target_warehouse()
        
        if source_warehouse and target_warehouse:                
            new_stock_doc = frappe.new_doc("Stock Entry")
            new_stock_doc.stock_entry_type = "Material Transfer"
            new_stock_doc.custom_total_tax_amount = self.total_vat
            new_stock_doc.custom_send_stock_info_to_etims = 1
            new_stock_doc.from_warehouse = source_warehouse
            new_stock_doc.to_warehouse = target_warehouse
            
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

    def get_source_and_target_warehouse(self):
        source_store = ""
        receipt_store = ""
        
        self_pin = get_kra_pin()
        user_branch_list = get_user_branch_perms()
      
        if self.customer_tin == self_pin:
            if self.customer_branch:
                if self.customer_branch in user_branch_list:
                
                    if not self.customer_branch == "00":
                        source_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": "00"}, fields=["warehouse_name", "name"])
                        
                        target_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": self.customer_branch}, fields=["warehouse_name", "name"])
                    
                        if source_warehouse and target_warehouse:
                            source_store = source_warehouse[0].get("name")
                            receipt_store = target_warehouse[0].get("name")
                          
                    elif self.customer_branch == "00":
                        user_branch_list.remove("00")
                    
                        source_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": user_branch_list[0]}, fields=["warehouse_name", "name"])
                        
                        target_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": "00"}, fields=["warehouse_name", "name"])
                    
                        if source_warehouse and target_warehouse:
                            source_store = source_warehouse[0].get("name")
                            receipt_store = target_warehouse[0].get("name")
                 
                else:
                    frappe.throw("User Not Permitted Tax Branch Oficce {}".format(self.customer_branch))
                            
        return source_store, receipt_store
                      
def assign_stock_item(item):  
    item_dict =  {
        "item_code": item.get("item_name"),
        "qty": item.get("unit_quantity"),
        "custom_tax_code": item.get("taxation_type_code"),
        "custom_tax_amount":item.get("tax_amount")
    }   
    
    
    return item_dict

def get_kra_pin():
    own_pin = ""
    
    init_doc = frappe.db.get_all("TIS Device Initialization", fields=["pin"])
    
    if init_doc:
        own_pin = init_doc[0].get("pin")
        
    return own_pin
        
def get_user_branch_perms():
    cur_user = frappe.session.user
    user_branch_list = []
    
    user_branch_permissions = frappe.db.get_all("User Permission", filters={"user": cur_user, "allow": "Tax Branch Office"}, fields=["for_value"])
    
    if user_branch_permissions:
        for item in user_branch_permissions:
            if not item.get("for_value") in user_branch_list:
                user_branch_list.append(item.get("for_value"))
                
    return user_branch_list
    