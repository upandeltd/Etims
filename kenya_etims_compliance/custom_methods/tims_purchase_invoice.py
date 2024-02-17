import frappe
from kenya_tims_compliance.utils.etims_utils import eTIMS

def update_stock_to_etims(doc, method):
    if not doc.stock_updated == 1:
        for item in doc.items:
            if not item.stock_updated == 1:
                try:
                    create_stock_receipt_entry(item)
                    doc.stock_updated = 1
                except:
                    frappe.throw("Failed!")
                    
                doc.save()
                
def create_stock_receipt_entry(item):   
    tax_branch = "00"

    store_warehouse = frappe.db.get_all("Warehouse", filters={"warehouse_type": "Stores", "is_group": 0, "custom_tax_branch_office": tax_branch}, fields=["warehouse_name", "name"])
    
    if store_warehouse:
        receipt_store = store_warehouse[0].get("name")
        new_item_doc = frappe.new_doc("Stock Entry")
        new_item_doc.stock_entry_type = "Material Receipt"
        # new_item_doc.custom_send_to_tims = 1
        new_item_doc.append("items", {
            "item_code": item.get("item_name"),
            "t_warehouse": receipt_store,
            "qty": item.get("package")
        })
        
        new_item_doc.insert()
        new_item_doc.submit()
        
        item.stock_updated = 1
        frappe.db.commit()   
    else:
        frappe.throw("No warehouse set for tax branch!")
