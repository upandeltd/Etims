// Copyright (c) 2023, Upande Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("eTIMS Branch Information", {
    search_branch_info: function(frm){
        // call with all options
        frappe.call({
            method: 'bhfSearchReq',
            doc: frm.doc,
            // // disable the button until the request is completed
            btn: $('.primary-action'),
            // // freeze the screen until the request is completed
            freeze: true,
            callback: function(r)   {
                // console.log(r.message)
                let keys = Object.keys(r.message)
                let values = Object.values(r.message)
                frappe.msgprint({
                    title: __(keys[0]),
                    indicator: 'green',
                    message: __(values[0])
                });

                refresh_field("branch_details_tab")
            }
        })
    }
});
