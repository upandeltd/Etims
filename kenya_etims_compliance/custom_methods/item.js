frappe.ui.form.on('Item',{
    custom_register_item: function(frm) {
        frappe.call({
            "method": "kenya_etims_compliance.custom_methods.item.itemSaveReq",
            args: { doc_name: frm.doc.name },
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
            "method": "kenya_etims_compliance.custom_methods.item.importItemUpdateReq",
            args: { doc_name: frm.doc.name },
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
    },

    custom_search_item_in_etims: function(frm) {
        frappe.call({
            "method": "kenya_etims_compliance.custom_methods.item.searchItemReq",
            args: {
                "item_code": frm.doc.custom_item_code || null,
                "item_name": frm.doc.custom_item_name || null
            },
            freeze: true,
            callback: function(r) {
                let keys = Object.keys(r.message)
                let values = Object.values(r.message)
                frappe.msgprint({
                    title: __(keys[0]),
                    indicator: keys[0] === 'Success' ? 'green' : 'red',
                    message: __(JSON.stringify(values[0], null, 2))
                });
            }
        })
    }
})



