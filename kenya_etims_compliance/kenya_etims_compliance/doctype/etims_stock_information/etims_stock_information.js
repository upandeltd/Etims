// Copyright (c) 2023, Upande Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("eTIMS Stock Information", {
	search_stock_movement: function(frm){
        // call with all options
        frappe.call({
            method: 'stockMoveReq',
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

                refresh_field("last_search_date_and_time")
            }
        })
    },

    view_stock_movement: function(frm){
        frappe.set_route("List/eTIMS Stock Movement/List")
    },

    consolidate_stock: function(frm){
        // call with all options
        frappe.call({
            method: 'insert_items',
            doc: frm.doc,
            // // disable the button until the request is completed
            btn: $('.primary-action'),
            // // freeze the screen until the request is completed
            freeze: true,
            callback: function(r)   {

                refresh_field("items")
            }
        })
    },
    
    save_stock: function(frm) {
        // call with all options
        frappe.call({
            method: 'stockMasterSaveReq',
            doc: frm.doc,
            // // disable the button until the request is completed
            btn: $('.primary-action'),
            // // freeze the screen until the request is completed
            freeze: true,
            callback: function(r)   {
                // console.log(r.message)
                refresh_field("items")
                let keys = Object.keys(r.message)
                let values = Object.values(r.message)
                frappe.msgprint({
                    title: __(keys[0]),
                    indicator: 'green',
                    message: __(values[0])
                });
            }
        })
    }
});
