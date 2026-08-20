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

    pos_profile: function(frm) {
        // Auto-set eTIMS signing based on POS Profile setting
        if (frm.doc.pos_profile) {
            frappe.db.get_value('POS Profile', frm.doc.pos_profile,
                'custom_enable_etims_signing', (r) => {
                    if (r && r.custom_enable_etims_signing) {
                        frm.set_value('custom_update_invoice_in_tims', 1);
                    }
                }
            );
        }
    },

    refresh: function(frm) {
        // eTIMS Queue Status indicator
        if (frm.doc.custom_etims_queue_status) {
            let color = {
                "Queued": "blue",
                "Processing": "orange",
                "Sent": "green",
                "Failed": "red"
            }[frm.doc.custom_etims_queue_status] || "grey";

            frm.dashboard.set_headline(
                __("eTIMS Status: {0}", [frm.doc.custom_etims_queue_status]),
                color
            );

            if (frm.doc.custom_etims_queue_status === "Failed" && frm.doc.custom_etims_queue_entry) {
                frm.add_custom_button(__("Retry eTIMS"), function() {
                    frappe.call({
                        method: "kenya_etims_compliance.custom_methods.queue_processor.retry_single_entry",
                        args: { queue_entry_name: frm.doc.custom_etims_queue_entry },
                        callback: function(r) {
                            if (r.message) {
                                frappe.show_alert({message: __("Invoice re-queued for eTIMS"), indicator: "green"});
                                frm.reload_doc();
                            }
                        }
                    });
                }, __("eTIMS Actions"));
            }
        }

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
                        if (!r || !r.message || !Object.keys(r.message).length) return;
                        let keys = Object.keys(r.message);
                        let values = Object.values(r.message);
                        frappe.msgprint({
                            title: __(keys[0]),
                            indicator: keys[0] === 'Success' ? 'green' : 'red',
                            message: __('{0}', [frappe.utils.escape_html(JSON.stringify(values[0] ?? '', null, 2))])
                        });
                    },
                    error: function(r) {
                        frappe.msgprint({
                            title: __('Connection Error'),
                            indicator: 'red',
                            message: __('Could not reach eTIMS: {0}', [frappe.utils.escape_html(String((r && r.message) || ''))])
                        });
                    }
                });
            }, __('eTIMS Actions'));

            // Print Copy (Spec 4.1.2)
            if (frm.doc.docstatus === 1 && frm.doc.custom_update_sales_to_etims) {
                frm.add_custom_button(__('Print Copy'), function() {
                    frappe.call({
                        method: 'kenya_etims_compliance.custom_methods.device_status.increment_copy_count',
                        args: { invoice_name: frm.doc.name },
                        callback: function(r) {
                            if (r.message) {
                                frm.reload_doc();
                                frappe.show_alert({
                                    message: __('Copy #{0} — printing with COPY watermark', [r.message.count]),
                                    indicator: 'blue'
                                });
                                // Trigger print with copy flag
                                frm.print_doc();
                            }
                        }
                    });
                }, __('eTIMS Actions'));
            }

            // Show QR Code if available
            if (frm.doc.custom_receipt_qr_code) {
                frm.add_custom_button(__('Show QR Code'), function() {
                    show_sales_qr_code(frm);
                }, __('eTIMS Actions'));
            }

            // Sign Now — submitted invoice that was never sent to eTIMS
            // (signing was off at submit, so no queue entry exists). Distinct
            // from "Retry eTIMS", which only fires on a Failed queue entry.
            if (frm.doc.docstatus === 1
                && !frm.doc.custom_update_sales_to_etims
                && !frm.doc.custom_etims_queue_status) {
                frm.add_custom_button(__('Send to eTIMS'), function() {
                    frappe.confirm(
                        __('Sign this submitted invoice to eTIMS now? It will be assigned a new eTIMS invoice number and recorded in the current eTIMS window. If this period\'s VAT return is already filed, use a credit note instead.'),
                        function() {
                            frappe.call({
                                method: 'kenya_etims_compliance.custom_methods.sales_invoice.sign_submitted_invoice',
                                args: { invoice_name: frm.doc.name },
                                freeze: true,
                                freeze_message: __('Queuing for eTIMS...'),
                                callback: function(r) {
                                    if (r.message) {
                                        frappe.show_alert({
                                            message: __('Queued for eTIMS (Invoice No: {0})', [r.message.invoice_number]),
                                            indicator: 'green'
                                        });
                                        frm.reload_doc();
                                    }
                                }
                            });
                        }
                    );
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
                if (!r || !r.message || !Object.keys(r.message).length) return;
                let keys = Object.keys(r.message)
                let values = Object.values(r.message)
                frappe.msgprint({
                    title: __(keys[0]),
                    indicator: keys[0] === 'Success' ? 'green' : 'red',
                    message: __('{0}', [frappe.utils.escape_html(JSON.stringify(values[0] ?? '', null, 2))])
                });
            },
            error: function(r) {
                frappe.msgprint({
                    title: __('Connection Error'),
                    indicator: 'red',
                    message: __('Could not reach eTIMS: {0}', [frappe.utils.escape_html(String((r && r.message) || ''))])
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
                    <div class="card card-body text-center">
                        <p>This invoice has been submitted to KRA eTIMS.</p>
                        <div class="border rounded p-4 d-inline-block">
                            <code class="etims-qr-code">${qr_code}</code>
                        </div>
                        <p class="text-muted text-xs mt-3">
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