// Copyright (c) 2023, Upande Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("eTIMS Item Information", {
    search_item_classification: function(frm){
        // call with all options
        frappe.call({
            method: 'itemClsSearchReq',
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

    view_itemcls_search_response: function(frm){
        frappe.set_route("List/eTIMS Item Classification/List")
    },

    consolidate_bom_items: function(frm){
        // call with all options
        frappe.call({
            method: 'consolidate_item_bom',
            doc: frm.doc,
            // // disable the button until the request is completed
            btn: $('.primary-action'),
            // // freeze the screen until the request is completed
            freeze: true,
            callback: function(r)   {

                refresh_field("bom_items")
                refresh_field("etims_item_code")
            }
        })
    },

    request_items: function(frm){
        // call with all options
        frappe.call({
            method: 'itemSearchReq',
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

                refresh_field("registered_items")
                refresh_field("item_last_search_date_and_time")
            }
        })
    },

    save_item_composition: function(frm){
        // call with all options
        frappe.call({
            method: 'itemSaveComposition',
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

                refresh_field("saved_in_etims")
                // refresh_field("bom_items")
            }
        })
    },
});

