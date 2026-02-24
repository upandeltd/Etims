// Copyright (c) 2023, Upande Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("eTIMS Import Item Information", {
	search_import_item: function(frm){
        // call with all options
        frappe.call({
            method: 'importItemSearchReq',
            doc: frm.doc,
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

                frm.refresh_field("import_items")
                frm.refresh_field("last_search_date_and_time")
            }
        })
    },

    consolidate_updated_import_items: function(frm){
        // call with all options
        frappe.call({
            method: 'insert_items',
            doc: frm.doc,
            // // freeze the screen until the request is completed
            freeze: true,
            callback: function(r)   {

                frm.refresh_field("import_items_for_update")
            }
        })
    },

    update_import_items: function(frm){
        // call with all options
        frappe.call({
            method: 'importItemUpdateReq',
            doc: frm.doc,
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

                frm.refresh_field("import_items_for_update")
            }
        })
    },
});
