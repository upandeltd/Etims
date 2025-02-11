// Copyright (c) 2025, Upande Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Tax Branch Configurations", {
    // =============================================================== //
    //                             General                             //
    // =============================================================== //
    onload(frm){
        if(!frm.doc.tax_accounts){
            // Loop through accounts and add them to the child table
            accounts.forEach(account => {
                let child = frm.add_child("tax_accounts");
                child.account_name = account.account_name;
                child.tax_code = account.tax_code;
                child.account_type = account.account_type;
                child.tax_rate = account.tax_rate;
            });

            // Refresh the field to reflect changes
            frm.refresh_field("tax_accounts");
        }

        frm.set_query("parent_tax_account", function() {
            return {
                "filters": {
                    "company": frm.doc.company
                }
            };
        });
    },
    parent_tax_account(frm){
        if(frm.doc.tax_accounts){
            if(frm.doc.parent_tax_account && frm.doc.__islocal){
                frm.doc.tax_accounts.forEach(row => {
                    row.parent_account = frm.doc.parent_tax_account;
                });

                frm.refresh_field("tax_accounts");
            }
        }    
    },

    // =============================================================== //
    //                             Accounts                            //
    // =============================================================== //
    create_accounts(frm) {
        if(!frm.doc.__islocal){
            frappe.confirm('This action will disable any other default tax templates for sales and purchase, proceed?',
                () => {
                    frappe.call({
                        method: "create_tax_accounts",
                        doc: frm.doc,
                        args: {
                            message:{
                                data:{
                                    tax_accounts: frm.doc.tax_accounts
                                }
                            }
                        },
                        callback: function (r) {
                            if(r.message){
                                if(r.message.status == "Success"){

                                    frm.refresh_field("accounts_created")
                                }
                                frm.save()
                            }
                        }
                    })
                }, () => {
                    frappe.msgprint("Action rejected by user!")
            })
        }else{
            frappe.msgprint("You need to save the document first!")
        }
        
	},

    // =============================================================== //
    //                       Item Tax Templates                        //
    // =============================================================== //

    get_item_taxes(frm) {
        if(!frm.doc.item_tax_configuration.length > 0){
            // Loop through accounts and add them to the child table
            item_tax_templates.forEach(tax_template => {
                let child = frm.add_child("item_tax_configuration");
                child.title = tax_template.title;
                child.code = tax_template.code;
                child.code_name = tax_template.code_name;
                child.tax_rate = tax_template.tax_rate
                frappe.db.get_value("Account", {"company": frm.doc.company, "custom_tax_code": tax_template.code}, "name")
                .then(r => {
                    if(r.message){
                        child.account = r.message.name
                    }
                })
            });

            // Refresh the field to reflect changes
            frm.refresh_field("item_tax_configuration");
        }
    },
    
    create_taxes(frm) {
        if(!frm.doc.__islocal){
            frappe.confirm('This action will disable any other default tax templates for sales and purchase, proceed?',
                () => {
                    frappe.call({
                        method: "create_item_tax_templates",
                        doc: frm.doc,
                        args: {
                            message:{
                                data:{
                                    taxes: frm.doc.item_tax_configuration
                                }
                            }
                        },
                        callback: function (r) {
                            if(r.message){
                                if(r.message.status == "Success"){
                                    frm.refresh_field("item_tax_configuration")
                                }
                                frm.save()
                            }
                        }
                    })
                }, () => {
                    frappe.msgprint("Action rejected by user!")
            })
        }else{
            frappe.msgprint("You need to save the document first!")
        }
        
	},
    // =============================================================== //
    //                       Stock Settings                            //
    // =============================================================== //
    update_stock_selling(frm){
        if(frm.doc.update_stock_selling == 1){
            frappe.msgprint("If this action is enabled, Sales Invoices with update stock option enabled will also send the stock movement and stock master data to eTIMS.")
        }else{
            frappe.msgprint("If this action is disabled, Sales Invoices with update stock option enabled will not send the stock movement and stock master data to eTIMS.")
        }
    },
    update_stock_purchase(frm){
        if(frm.doc.update_stock_purchase == 1){
            frappe.msgprint("If this action is enabled, Purchase Invoices with update stock option enabled will also send the stock movement and stock master data to eTIMS.")
        }else{
            frappe.msgprint("If this action is disabled, Purchase Invoices with update stock option enabled will not send the stock movement and stock master data to eTIMS.")
        }
    },
    get_item_groups(frm){
        frappe.call({
            method: "get_item_groups",
            doc: frm.doc,
            callback: function (r) {
                if(r.message){
                    if(r.message.status == "Success"){

                        frm.refresh_field("item_group_codes")
                    }
                    frm.save()
                }
            }
        })
    },
    update_codes(frm){

    },
});


// =============================================================== //
//                      Initial Settings Data                      //
// =============================================================== //
const accounts = [
    {
        "account_name": "VAT-A-Exempt",
        "tax_code": "A",
        "account_type": "Tax",
        "tax_rate": 0
    },
    {
        "account_name": "VAT-B-16.00%",
        "tax_code": "B",
        "account_type": "Tax",
        "tax_rate": 16
    },
    {
        "account_name": "VAT-C-0%",
        "tax_code": "C",
        "account_type": "Tax",
        "tax_rate": 0
    },
    {
        "account_name": "VAT-D-Non-VAT",
        "tax_code": "D",
        "account_type": "Tax",
        "tax_rate": 0
    },
    {
        "account_name": "VAT-E-8%",
        "tax_code": "E",
        "account_type": "Tax",
        "tax_rate": 8
    }
]

const item_tax_templates = [
   {
        "title": "VAT-A-Exempt",
        "code_name": "A-Exempt",
        "code": "A",
        "tax_rate": 0,
        "account": ""
   },
   {
        "title": "VAT-B-16%",
        "code_name": "B-16.00%",
        "code": "B",
        "tax_rate": 16,
        "account": ""
    },
    {
        "title": "VAT-C-0%",
        "code_name": "C-0%",
        "code": "C",
        "tax_rate": 0,
        "account": ""
   },
   {
        "title": "VAT-D-Non-VAT",
        "code_name": "D-Non-VAT",
        "code": "D",
        "tax_rate": 0,
        "account": ""
    },
    {
        "title": "VAT-E-8%",
        "code_name": "E-8%",
        "code": "E",
        "tax_rate": 8,
        "account": ""
    }
]