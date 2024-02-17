frappe.ui.form.on('Item',{
    custom_register_item: function(frm) {
        frappe.call({
            "method": "kenya_etims_compliance.custom_methods.item.itemSaveReq?doc_name=" + frm.doc.name,
            freeze: true,
            callback: function(r)   {
                keys = Object.keys(r.message)
                values = Object.values(r.message)
                frappe.msgprint({
                    title: __(keys[0]),
                    indicator: 'green',
                    message: __(values[0])
                });
                
            }		
        })
    },

    custom_save_item_composition: function(frm) {
        frappe.call({
            "method": "kenya_etims_compliance.custom_methods.item.itemSaveComposition?doc_name=" + frm.doc.name,
            freeze: true,
            callback: function(r)   {
                keys = Object.keys(r.message)
                values = Object.values(r.message)
                frappe.msgprint({
                    title: __(keys[0]),
                    indicator: 'green',
                    message: __(values[0])
                });
                
            }		
        })
    },

    custom_update_item: function(frm) {
        frappe.call({
            "method": "kenya_etims_compliance.custom_methods.item.importItemUpdateReq?doc_name=" + frm.doc.name,
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

                
            }		
        })
    }
})



