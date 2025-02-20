frappe.ui.form.on("Sales Invoice",{
    refresh:function(frm){
        if(frm.doc.custom_update_invoice_in_tims){
            if(frm.doc.docstatus==0){
                frm.add_custom_button('Preview eTIMS Information', () => {
                    preview_etims_info(frm);
                }, "Preview");

                frm.add_custom_button('eTIMS Sales Invoice', () => {
                    create_etims_sinv(frm);
                }, "Create");
            }
        }
    },
    is_return:function(frm){
        updateSalesType(frm)

        refresh_field("custom_receipt_type_code")
        refresh_field("custom_invoice_status_code")
        refresh_field("custom_credit_note_reason_code")
    },
    onload:function(frm){
        if(frm.doc.custom_update_invoice_in_tims){
            if(frm.doc.docstatus==0){
                frm.add_custom_button('Preview eTIMS Information', () => {
                    preview_etims_info(frm);
                }, "Preview");

                frm.add_custom_button('eTIMS Sales Invoice', () => {
                    preview_etims_info(frm);
                }, "Create");
            }
        }

        updateSalesType(frm)

        refresh_field("custom_receipt_type_code")
        refresh_field("custom_invoice_status_code")
        refresh_field("custom_credit_note_reason_code")
    },

    after_save:function(frm){
        if(frm.doc.update_stock == 1){
            if(frm.doc.set_warehouse){
                // console.log(frm.doc.set_warehouse)
                frm.fields_dict.items.grid.grid_rows.forEach((row) => {
                    if (row){
                        row.doc.warehouse = frm.doc.set_warehouse
                    }
                })
            }
        }

        if(frm.doc.custom_update_invoice_in_tims){
            if(frm.doc.docstatus==0){
                frm.add_custom_button('Preview eTIMS Information', () => {
                    preview_etims_info(frm);
                }, "Preview");
            }

            frm.add_custom_button('eTIMS Sales Invoice', () => {
                preview_etims_info(frm);
            }, "Create");
        }
    }
})

function updateSalesType(frm){
    if(frm.doc.is_return == 1){
        frm.doc.custom_receipt_type_code = "R"
        frm.doc.custom_invoice_status_code = "05"
        frm.doc.custom_credit_note_reason_code = "06"
    }else{
        frm.doc.custom_receipt_type_code = "S"
        frm.doc.custom_invoice_status_code = "02"
        frm.doc.custom_credit_note_reason_code = ""
    }
}

function preview_etims_info(frm){
    // call with all options
    frappe.call({
        method: 'kenya_etims_compliance.kenya_etims_compliance.doctype.etims_sales_invoice.etims_sales_invoice.get_set_options',
        args: {
            message:{
                data:{
                    doc_name: frm.doc.name
                }
            }
        },
        callback: (r) => {
            let dataFields = [
                {
                    label: 'Sales Type',
                    fieldname: 'stc',
                    fieldtype: 'Select',
                    options: ["Copy", "Normal", "Profoma", "Training"],
                    reqd: 1,
                    default: r.message.sales_type_code
                },
                {
                    label: 'Receipt Type',
                    fieldname: 'rtc',
                    fieldtype: 'Select',
                    options: ["Sale", "Credit Note After Sale"],
                    reqd: 1,
                    default: r.message.receipt_type_code
                },
                {
                    fieldtype: 'Column Break'
                },
                {
                    label: 'Payment Type',
                    fieldname: 'ptc',
                    fieldtype: 'Select',
                    options: ["Cash", "Credit", "Cash/Credit", "Bank Check", "Debit&Credit Card", "Mobile-Money", "Other"],
                    reqd: 1,
                    default: r.message.payment_type_code
                },
                {
                    label: 'Invoice Status',
                    fieldname: 'isc',
                    fieldtype: 'Select',
                    options: ["Wait for Approval", "Approved", "Cancel Request", "Cancelled", "Credit Note Generated", "Transferred"],
                    reqd: 1,
                    default: r.message.sales_status_code
                }
            ];
            
            // Conditionally add the credit note reason code field
            if (frm.doc.is_return) {
                dataFields.push({
                    label: 'Credit Note Reason Code',
                    fieldname: 'rrc',
                    fieldtype: 'Select',
                    options: ["Missing Quantity", "Missing Data", "Damaged", "Wasted", "Raw Material Shortage", "Refund"],
                    reqd: 1,
                    default: r.message.credit_note_reason_code
                });
            }
            
            let d = new frappe.ui.Dialog({
                title: 'Update eTIMS Details',
                fields: dataFields,
                primary_action_label: 'Update Details',
                primary_action(taxation_details) {    
                    taxation_details.doc_name = frm.doc.name
                    console.log(taxation_details)               
                    frappe.call({
                        method: 'kenya_etims_compliance.kenya_etims_compliance.doctype.etims_sales_invoice.etims_sales_invoice.update_etims_values',
                        args: {
                            message:{
                                data:{
                                    details: taxation_details
                                }
                            }
                        },
                        callback: function(response) {
                            
                        }
                    });
                
                    d.hide()
                }
            });
            d.show();
        },
        error: (r) => {
        // on error
        }
   })
}

function create_etims_sinv(frm){
    frappe.call({
        method: 'kenya_etims_compliance.custom_methods.sales_invoice.create_etims_sinv',
        args: {
            message:{
                data:{
                    doc_name: frm.doc.name
                }
            }
        },
        callback: (r) => {

        }
    })
}