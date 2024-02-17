frappe.ui.form.on('Customer',{
    custom_register_customer: function(frm) {
        if(!frm.doc.custom_is_registered == 1){
            frappe.call({
                "method": "kenya_tims_compliance.custom_methods.customer.bhfCustSaveReq?doc_name=" + frm.doc.name,
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

