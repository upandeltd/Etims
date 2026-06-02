frappe.ui.form.on('Customer',{
    custom_check_pin_with_kra: function(frm) {
        if (!frm.doc.tax_id) {
            frappe.msgprint({
                title: __('Missing PIN'),
                indicator: 'orange',
                message: __('Enter a Tax ID (KRA PIN) before checking with KRA.')
            });
            return;
        }
        frappe.call({
            method: 'kenya_etims_compliance.custom_methods.customer.check_pin_with_kra',
            args: { pin: frm.doc.tax_id },
            freeze: true,
            freeze_message: __('Validating PIN against KRA iTax...'),
            callback: function(r) {
                const m = r.message || {};
                if (!m.found) {
                    frappe.msgprint({
                        title: __('PIN Not Valid'),
                        indicator: 'red',
                        message: m.message || __('KRA rejected this PIN.')
                    });
                    return;
                }
                const d = m.data || {};
                // Auto-fill name fields when blank
                if (d.taxpayer_name && !frm.doc.custom_customer_name) {
                    frm.set_value('custom_customer_name', d.taxpayer_name);
                }
                if (d.taxpayer_name && (!frm.doc.customer_name || frm.doc.customer_name === frm.doc.name)) {
                    frm.set_value('customer_name', d.taxpayer_name);
                }
                // Status-based indicator
                let indicator = 'green', title = __('PIN Valid — Active');
                if (d.status_of_pin === 'Suspended') { indicator = 'orange'; title = __('PIN Valid but SUSPENDED'); }
                else if (d.status_of_pin === 'Cancelled' || d.status_of_pin === 'Stopped') {
                    indicator = 'red';
                    title = __('PIN ') + d.status_of_pin.toUpperCase();
                }
                frappe.msgprint({
                    title: title,
                    indicator: indicator,
                    message: __('PIN: <b>{0}</b><br>Name: <b>{1}</b><br>Type: {2}<br>Status: <b>{3}</b>',
                        [d.taxpayer_pin || '-', d.taxpayer_name || '-', d.taxpayer_type || '-', d.status_of_pin || '-'])
                });
            }
        });
    },
    custom_register_customer: function(frm) {
        if(frm.doc.custom_is_registered != 1){
            frappe.call({
                "method": "kenya_etims_compliance.custom_methods.customer.bhfCustSaveReq",
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

