import frappe, traceback
from kenya_etims_compliance.utils.etims_utils import eTIMS

def update_stock_to_etims(doc, method):
    if not doc.stock_updated == 1:
        for item in doc.items:
            if not item.stock_updated == 1:
                try:
                    create_stock_trns_entry(doc, item)
                    doc.stock_updated = 1
                except:
                    frappe.throw(traceback.format_exc())
                
                doc.save()
                
def create_stock_trns_entry(doc, item):   
    tax_branch, self_pin = get_branch_and_pin()
    
    print("*"*80)
    print(tax_branch)
    
    if doc.customer_tin == self_pin:
        if not doc.customer_branch == "00":
            source_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": "00"}, fields=["warehouse_name", "name"])
            
            target_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": doc.customer_branch}, fields=["warehouse_name", "name"])
            
            if source_warehouse and target_warehouse:
                source_store = source_warehouse[0].get("name")
                receipt_store = target_warehouse[0].get("name")
                
                if not item.stock_updated:                
                    new_item_doc = frappe.new_doc("Stock Entry")
                    new_item_doc.stock_entry_type = "Material Transfer"
                    # new_item_doc.custom_send_to_tims = 1
                    new_item_doc.append("items", {
                        "item_code": item.get("item_name"),
                        "s_warehouse": source_store,
                        "t_warehouse": receipt_store,
                        "qty": item.get("unit_quantity")
                    })
                    
                    new_item_doc.insert()
                    # new_item_doc.submit()
                    item.stock_updated = 1
                    doc.save()    
            else:
                frappe.throw("Warehouse not found for tax branch!")
                
        elif doc.customer_branch == "00" and not tax_branch == "00":
            print("yooooh")
            source_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": tax_branch}, fields=["warehouse_name", "name"])
            
            target_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": doc.customer_branch}, fields=["warehouse_name", "name"])
            
            if source_warehouse and target_warehouse:
                source_store = source_warehouse[0].get("name")
                receipt_store = target_warehouse[0].get("name")
                
                if not item.stock_updated:                
                    new_item_doc = frappe.new_doc("Stock Entry")
                    new_item_doc.stock_entry_type = "Material Transfer"
                    # new_item_doc.custom_send_to_tims = 1
                    new_item_doc.append("items", {
                        "item_code": item.get("item_name"),
                        "s_warehouse": source_store,
                        "t_warehouse": receipt_store,
                        "qty": item.get("unit_quantity")
                    })
                    
                    new_item_doc.insert()
                    # new_item_doc.submit()
                    item.stock_updated = 1
                    doc.save()    
            else:
                frappe.throw("Warehouse not found for tax branch!")

def get_branch_and_pin():
    tax_branch = eTIMS.get_user_branch_id()
    print("&"*90)
    print(tax_branch)
    own_pin = ""
    
    init_doc = frappe.db.get_all("TIS Device Initialization", filters={"branch_id": tax_branch}, fields=["pin"])
    
    if init_doc:
        own_pin = init_doc[0].get("pin")
        
    return tax_branch, own_pin
        
    