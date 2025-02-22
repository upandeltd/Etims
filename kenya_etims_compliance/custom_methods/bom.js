frappe.ui.form.on('BOM',{
    onload: function(frm){
        frm.set_query("item", function() {
            return {
                "filters": {
                    "custom_registered_in_tims": 1,
                    "is_stock_item": 1            }
            };
        });
    },

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
                    message: __('BOM Is Already Registered!')
                });
        }
        
    },
    item: function(frm){
        if(frm.doc.item){
            frappe.db.get_value('eTIMS Item', {item: frm.doc.item}, 'etims_item_code')
            .then(r => {
                let values = r.message;
                frm.doc.custom_etims_item_code = values.etims_item_code
            })
        }
    }
})