// Copyright (c) 2024, Upande Ltd and contributors
// For license information, please see license.txt


frappe.ui.form.on("TIS Device Initialization", {
    // refresh(frm) {
    
        // },
    
        verify_device: function(frm){
            // call with all options
            frappe.call({
                method: 'deviceVerificationReq',
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
    
                    refresh_field("communication_key")
                    refresh_field("device_id")
                    refresh_field("sales_control_unit_id")
                    refresh_field("mrc_no")
                }
            })
        },
    });
    
    