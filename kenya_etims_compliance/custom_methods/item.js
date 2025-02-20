frappe.ui.form.on('Item',{
    onload: function(frm){
        if(!frm.doc.custom_registered_in_tims==1){
            frm.add_custom_button('Register To eTIMS', () => {
                send_item_info_to_etims(frm);
            }, "Actions");
        }
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

// Define the delete_items function
function send_item_info_to_etims(frm) {
    frappe.confirm(
        'Are you sure you want to register this item to eTIMS?',
        () => {
            frappe.call({
                "method": "kenya_etims_compliance.custom_methods.item.itemSaveReq?doc_name=" + frm.doc.custom_etims_item,
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
    );
}