// Copyright (c) 2024, Upande Ltd and contributors
// For license information, please see license.txt


frappe.ui.form.on("TIS Device Initialization", {
        verify_device: function(frm){
            // call with all options
            frappe.call({
                method: 'deviceVerificationReq',
                doc: frm.doc,
                // // freeze the screen until the request is completed
                freeze: true,
                callback: function(r)   {
                    // console.log(r.message)
                    let keys = Object.keys(r.message)
                    let values = Object.values(r.message)
                    frappe.msgprint({
                        title: __(keys[0]),
                        indicator: keys[0] === 'Success' ? 'green' : 'red',
                        message: __(values[0])
                    });

                    frm.refresh_field("communication_key")
                    frm.refresh_field("device_id")
                    frm.refresh_field("sales_control_unit_id")
                    frm.refresh_field("mrc_no")
                }
            })
        },

        refresh_org_info: function(frm){
            frappe.call({
                method: 'refresh_org_info',
                doc: frm.doc,
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
        },
    });
    
    