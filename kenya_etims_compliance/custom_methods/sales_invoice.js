frappe.ui.form.on("Sales Invoice",{
    is_return:function(frm){
        updateSalesType(frm)

        frm.refresh_field("custom_receipt_type_code")
        frm.refresh_field("custom_invoice_status_code")
        frm.refresh_field("custom_credit_note_reason_code")
    },
    onload:function(frm){
        updateSalesType(frm)

        frm.refresh_field("custom_receipt_type_code")
        frm.refresh_field("custom_invoice_status_code")
        frm.refresh_field("custom_credit_note_reason_code")
    },

    refresh: function(frm) {
        // eTIMS Actions button group — shown for saved/submitted invoices
        if (frm.doc.name && frm.doc.name !== 'New Sales Invoice') {

            // Search Sales Transaction on eTIMS
            frm.add_custom_button(__('Search Sales Transaction'), function() {
                if (!frm.doc.custom_invoice_number) {
                    frappe.msgprint({
                        title: __('No Invoice Number'),
                        indicator: 'orange',
                        message: __('This invoice does not have an eTIMS invoice number assigned yet.')
                    });
                    return;
                }
                frappe.call({
                    method: 'kenya_etims_compliance.custom_methods.sales_invoice.searchSalesTrnsReq',
                    args: { invoice_no: frm.doc.custom_invoice_number },
                    freeze: true,
                    freeze_message: __('Searching eTIMS...'),
                    callback: function(r) {
                        if (r.message) {
                            let keys = Object.keys(r.message);
                            let values = Object.values(r.message);
                            frappe.msgprint({
                                title: __(keys[0]),
                                indicator: keys[0] === 'Success' ? 'green' : 'red',
                                message: __(JSON.stringify(values[0], null, 2))
                            });
                        }
                    }
                });
            }, __('eTIMS Actions'));

            // Show QR Code if available
            if (frm.doc.custom_receipt_qr_code) {
                frm.add_custom_button(__('Show QR Code'), function() {
                    show_sales_qr_code(frm);
                }, __('eTIMS Actions'));
            }

            // Dashboard indicator when invoice has been submitted to eTIMS
            if (frm.doc.custom_invoice_number && frm.dashboard) {
                frm.dashboard.add_indicator(
                    __('Submitted to eTIMS: {0}', [frm.doc.custom_invoice_number]),
                    'green'
                );
            }
        }
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
    },

    custom_search_sales_transaction: function(frm) {
        frappe.call({
            "method": "kenya_etims_compliance.custom_methods.sales_invoice.searchSalesTrnsReq",
            args: {
                "invoice_no": frm.doc.custom_invoice_number || null
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

function show_sales_qr_code(frm) {
    let qr_code = frm.doc.custom_receipt_qr_code;
    if (!qr_code) {
        frappe.msgprint(__('No QR Code available for this invoice.'));
        return;
    }
    let dialog = new frappe.ui.Dialog({
        title: __('eTIMS Receipt QR Code'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'qr_code_display',
                options: `
                    <div style="text-align:center;padding:20px;">
                        <p>This invoice has been submitted to KRA eTIMS.</p>
                        <div style="background:#fff;padding:20px;display:inline-block;border:1px solid #ddd;border-radius:8px;">
                            <code style="font-size:11px;word-break:break-all;">${qr_code}</code>
                        </div>
                        <p style="margin-top:15px;color:#666;font-size:12px;">
                            Control Unit Date: ${frm.doc.custom_control_unit_date || 'N/A'}<br>
                            eTIMS Invoice #: ${frm.doc.custom_invoice_number || 'N/A'}
                        </p>
                    </div>`
            }
        ],
        primary_action: function() { dialog.hide(); },
        primary_action_label: __('Close')
    });
    dialog.show();
}