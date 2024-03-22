frappe.ui.form.on('BOM',{
    custom_save_item_composition: function(frm) {
        console.log("hello")
        if(!frm.doc.custom_updated_to_etims == 1){
            frappe.call({
                "method": "kenya_etims_compliance.custom_methods.bom.itemSaveComposition?doc_name=" + frm.doc.name,
                freeze: true,
                callback: function(r)   {
                   return
                }		
            })
        }
        else{            
                // with options
                frappe.msgprint({
                    title: __('Notification'),
                    indicator: 'red',
                    message: __('Customer Is Already Registered!')
                });
        }
        
    }
})