// Copyright (c) 2023, Upande Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("eTIMS Code Information", {
    search_code: function(frm){
        // call with all options
        frappe.call({
            method: 'codeSearchReq',
            doc: frm.doc,
            // // freeze the screen until the request is completed
            freeze: true,
            callback: function(r)  {
                let keys = Object.keys(r.message)
                let values = Object.values(r.message)
                frappe.msgprint({
                    title: __(keys[0]),
                    indicator: 'green',
                    message: __(values[0])
                });

                frm.refresh_field("last_search_date_and_time")
            }
        })
    },
    
    code_response_url: function(frm){
        frappe.set_route("List", "eTIMS Code Classification")
    },

    search_customer: function(frm){
        // call with all options
        frappe.call({
            method: 'custSearchReq',
            doc: frm.doc,
            // // freeze the screen until the request is completed
            freeze: true,
            callback: function(r)   {
                let keys = Object.keys(r.message)
                let values = Object.values(r.message)
                frappe.msgprint({
                    title: __(keys[0]),
                    indicator: 'green',
                    message: __(values[0])
                });

                frm.refresh_field("customer_details")
            }
        })
    },

    search_notice: function(frm){
        // call with all options
        frappe.call({
            method: 'noticeSearchReq',
            doc: frm.doc,
            // // freeze the screen until the request is completed
            freeze: true,
            callback: function(r)   {
                let keys = Object.keys(r.message)
                let values = Object.values(r.message)
                frappe.msgprint({
                    title: __(keys[0]),
                    indicator: 'green',
                    message: __(values[0])
                });

                frm.refresh_field("notices")
                frm.refresh_field("last_request_date")
            }
        })

        // doc.save()
    }
});
