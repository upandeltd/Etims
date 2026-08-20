// Copyright (c) 2023, Upande Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("eTIMS Stock Information", {
	search_stock_movement: function(frm){
        // call with all options
        frappe.call({
            method: 'stockMoveReq',
            doc: frm.doc,
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

                frm.refresh_field("last_search_date_and_time")
            },
            error: function(r) {
                frappe.msgprint({
                    title: __('Connection Error'),
                    indicator: 'red',
                    message: __('Could not reach eTIMS: {0}', [frappe.utils.escape_html(String((r && r.message) || ''))])
                });
            }
        })
    },
	search_stock_master: function(frm){
        frappe.call({
            method: 'stockMasterSearchReq',
            doc: frm.doc,
            freeze: true,
            callback: function(r)   {
                if (!r || !r.message || !Object.keys(r.message).length) return;
                let keys = Object.keys(r.message);
                let values = Object.values(r.message);
                frappe.msgprint({
                    title: __(keys[0]),
                    indicator: keys[0] === 'Success' ? 'green' : 'red',
                    message: __('{0}', [frappe.utils.escape_html(String(values[0] ?? ''))])
                });
                frm.refresh_field("items")
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
