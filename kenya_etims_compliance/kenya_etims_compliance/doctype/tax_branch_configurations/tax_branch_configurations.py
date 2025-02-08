# Copyright (c) 2025, Upande Ltd and contributors
# For license information, please see license.txt
import json

import frappe
from frappe.model.document import Document


class TaxBranchConfigurations(Document):
    @frappe.whitelist()
    def create_tax_accounts(self):
        if not frappe.form_dict.message:
            frappe.throw("Missing 'message' in request data")

        disable_default_taxes(self.company)
        raw_data = json.loads(frappe.form_dict.message)        
        data = raw_data.get("data")

        if not data or not data.get("tax_accounts"):
            frappe.throw("Missing 'tax_accounts' field in the request data")
        
        for item in data.get("tax_accounts"):
            acc_exists = frappe.db.exists("Account", {"account_name": item.get("account_name"), "company": self.company})
            
            if not acc_exists:
                try:
                    new_acc = frappe.new_doc("Account")
                    new_acc.account_name = item.get("account_name")
                    new_acc.company = self.company
                    new_acc.parent_account = item.get("parent_account")
                    
                    new_acc.insert()
                    frappe.db.commit()
                    
                    frappe.msgprint(f'Account {new_acc.name} has been created.')
                except:
                    frappe.throw(f'Unexpected error with account {item.get("account_name")}!')
                    
            else:
                frappe.msgprint(f'Account {item.get("account_name")} exists for company {self.company}.')
                
def disable_default_taxes(company):
    disable_sales_taxes(company)
    disable_purchase_taxes(company)
    
def disable_sales_taxes(company):
    default_taxes = frappe.db.get_list("Sales Taxes and Charges Template", filters={"company": company, "is_default": 1}, fields=["name"])
    
    if default_taxes:
        for d_tax in default_taxes:
            doc = frappe.get_doc("Sales Taxes and Charges Template", d_tax.get("name"))
            doc.is_default = 0
            
            doc.save()
            frappe.db.commit()
    
def disable_purchase_taxes(company):
    default_taxes = frappe.db.get_list("Purchase Taxes and Charges Template", filters={"company": company, "is_default": 1}, fields=["name"])
    
    if default_taxes:
        for d_tax in default_taxes:
            doc = frappe.get_doc("Purchase Taxes and Charges Template", d_tax.get("name"))
            doc.is_default = 0
            
            doc.save()
            frappe.db.commit()