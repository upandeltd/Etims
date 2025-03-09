frappe.ui.form.on('BOM',{
    refresh: function(frm){
        if(frm.doc.custom_updated_to_etims==0 && frm.doc.name){
            frm.add_custom_button('Save To eTIMS', () => {
                send_bom_info_to_etims(frm);
            }, "Actions");
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

function send_bom_info_to_etims(frm) {
    frappe.confirm(
        'Are you sure you want to register this BOM to eTIMS?',
        () => {
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
        }
    );
}