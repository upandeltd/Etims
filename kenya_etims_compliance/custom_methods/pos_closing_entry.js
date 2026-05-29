// Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("POS Closing Entry", {
	setup: function (frm) {
        if(frm.doc.docstatus == 1 && frm.doc.custom_all_invoices_submitted==0){
            frm.add_custom_button(__('Submit Sales Invoices'), () => {
                submit_sales_invoice(frm);
            });
        }
	},

    refresh: function (frm) {
		if(frm.doc.docstatus == 1 && frm.doc.custom_all_invoices_submitted==0){
            frm.add_custom_button(__('Submit Sales Invoices'), () => {
                submit_sales_invoice(frm);
            });
        }
	}
});

function submit_sales_invoice(frm){
    frappe.call({
        "method": "kenya_etims_compliance.custom_methods.pos_closing_entry.submit_invoice?doc_name=" + frm.doc.name,
        freeze: true,
        callback: function(r)   {
            // console.log(r.message)
            let keys = r
            
        }		
    })
}