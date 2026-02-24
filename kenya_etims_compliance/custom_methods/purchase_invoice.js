frappe.ui.form.on("Purchase Invoice",{
    is_return:function(frm){
        if(frm.doc.is_return == 1){
            is_return_doc(frm)

        }else{
            frm.doc.custom_receipt_type_code = "P"
            frm.doc.custom_purchase_status_code = "02"
        }

        frm.refresh_field("custom_receipt_type_code")
        frm.refresh_field("custom_purchase_status_code")
    },

    onload:function(frm){
        if(frm.doc.is_return == 1){
            is_return_doc(frm)

            frm.refresh_field("custom_receipt_type_code")
            frm.refresh_field("custom_purchase_status_code")
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

    refresh: function(frm) {
        // Add Verify Invoice with KRA button
        // Only show if invoice is not verified and is saved (has a name)
        if (frm.doc.name && frm.doc.name !== 'New Purchase Invoice') {
            if (!frm.doc.custom_invoice_verified) {
                frm.add_custom_button(__('Verify Invoice with KRA'), function() {
                    verify_invoice_with_kra(frm);
                }, __('eTIMS Actions'));
            } else {
                // Show verification status indicator
                if (frm.dashboard) {
                    frm.dashboard.add_indicator(
                        __('Verified with KRA: {0}', [frm.doc.custom_verification_date]),
                        'green'
                    );
                }
            }

            // Show QR Code button if verified
            if (frm.doc.custom_invoice_verified && frm.doc.custom_qr_code) {
                frm.add_custom_button(__('Show QR Code'), function() {
                    show_qr_code(frm);
                }, __('eTIMS Actions'));
            }

            // Add Manual Verification Override button (for exceptional cases)
            if (!frm.doc.custom_invoice_verified) {
                frm.add_custom_button(__('Mark as Manually Verified'), function() {
                    mark_as_manually_verified(frm);
                }, __('eTIMS Actions'));
            }
        }
    },

    custom_search_purchase_transaction: function(frm) {
        frappe.call({
            "method": "kenya_etims_compliance.custom_methods.purchase_invoice.searchPurchaseTrnsReq",
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

function is_return_doc(frm){

    frm.doc.custom_receipt_type_code = "R"
    frm.doc.custom_purchase_status_code = "05"

}

// =============================================================================
// Invoice Verification Functions - Phase 1: Invoice Checker API Integration
// =============================================================================

function verify_invoice_with_kra(frm) {
    frappe.call({
        method: 'kenya_etims_compliance.custom_methods.purchase_invoice.verify_supplier_invoice',
        args: {
            docname: frm.doc.name
        },
        freeze: true,
        freeze_message: __('Verifying invoice with KRA eTIMS...'),
        callback: function(r) {
            if (r.message) {
                if (r.message.verified) {
                    frappe.msgprint({
                        title: __('Verification Successful'),
                        message: __('Invoice verified successfully with KRA eTIMS system.'),
                        indicator: 'green'
                    });
                    frm.reload_doc();
                } else {
                    // Show detailed error
                    let error_msg = r.message.error || r.message.message || 'Unknown error';
                    frappe.msgprint({
                        title: __('Verification Failed'),
                        message: __(
                            'Invoice could not be verified with KRA eTIMS.<br><br>' +
                            '<b>Reason:</b> {0}<br><br>' +
                            'Please check:<br>' +
                            '1. Supplier Tax PIN is correct<br>' +
                            '2. Invoice number matches supplier\'s records<br>' +
                            '3. Invoice date and amount are accurate<br><br>' +
                            'Contact the supplier if verification continues to fail.',
                            error_msg
                        ),
                        indicator: 'red'
                    });
                }
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    message: __('An unexpected error occurred during verification.'),
                    indicator: 'red'
                });
            }
        }
    });
}

function show_qr_code(frm) {
    let qr_code = frm.doc.custom_qr_code;

    if (!qr_code) {
        frappe.msgprint(__('No QR Code available for this invoice.'));
        return;
    }

    // Create dialog to show QR code
    let dialog = new frappe.ui.Dialog({
        title: __('KRA eTIMS QR Code'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'qr_code_display',
                options: `
                    <div style="text-align: center; padding: 20px;">
                        <p style="margin-bottom: 15px;">This invoice has been verified with KRA eTIMS.</p>
                        <div style="background: white; padding: 20px; display: inline-block; border: 1px solid #ddd; border-radius: 8px;">
                            <code style="font-size: 11px; word-break: break-all;">${qr_code}</code>
                        </div>
                        <p style="margin-top: 15px; color: #666; font-size: 12px;">
                            Verification Date: ${frm.doc.custom_verification_date || 'N/A'}<br>
                            KRA Invoice Number: ${frm.doc.custom_kra_invoice_number || 'N/A'}
                        </p>
                    </div>
                `
            }
        ],
        primary_action: function() {
            dialog.hide();
        },
        primary_action_label: __('Close')
    });

    dialog.show();
}

function mark_as_manually_verified(frm) {
    frappe.prompt([
        {
            fieldname: 'reason',
            fieldtype: 'Text',
            label: __('Reason for Manual Verification'),
            description: __('Please provide a reason for marking this invoice as manually verified. This will be logged for audit purposes.'),
            reqd: 1
        }
    ], function(values) {
        frappe.call({
            method: 'kenya_etims_compliance.custom_methods.purchase_invoice.mark_invoice_as_manually_verified',
            args: {
                docname: frm.doc.name,
                reason: values.reason
            },
            freeze: true,
            callback: function(r) {
                if (r.message && r.message.success) {
                    frappe.msgprint({
                        title: __('Manual Verification'),
                        message: __('Invoice marked as manually verified. Note: This may not be accepted by KRA for tax deduction.'),
                        indicator: 'yellow'
                    });
                    frm.reload_doc();
                } else {
                    frappe.msgprint({
                        title: __('Error'),
                        message: r.message ? r.message.message : __('Failed to mark invoice as manually verified'),
                        indicator: 'red'
                    });
                }
            }
        });
    }, __('Manual Verification Override'), __('Verify'));
}