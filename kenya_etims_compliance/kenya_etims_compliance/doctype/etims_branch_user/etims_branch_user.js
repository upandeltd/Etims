// Copyright (c) 2024, Upande Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("eTIMS Branch User", {
    register_user: function(frm){
        // call with all options
        frappe.call({
            method: 'bhfUserSaveReq',
            doc: frm.doc,
            // // disable the button until the request is completed
            btn: $('.primary-action'),
            // // freeze the screen until the request is completed
            freeze: true,
            callback: function(r)   {
                // console.log(r.message)
                if (!r || !r.message || !Object.keys(r.message).length) return;
                let keys = Object.keys(r.message);
                let values = Object.values(r.message);
                frappe.msgprint({
                    title: __(keys[0]),
                    indicator: keys[0] === 'Success' ? 'green' : 'red',
                    message: __('{0}', [frappe.utils.escape_html(String(values[0] ?? ''))])
                });

                refresh_field("saved")
            },
            error: function(r) {
                frappe.msgprint({
                    title: __('Connection Error'),
                    indicator: 'red',
                    message: __('Could not reach eTIMS: {0}', [frappe.utils.escape_html(String((r && r.message) || ''))])
                });
            }
        })
    }
});
