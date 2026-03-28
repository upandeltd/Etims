/**
 * Supplier eTIMS Integration Client Script
 *
 * Adds eTIMS-specific functionality to the Supplier doctype.
 */

frappe.ui.form.on('Supplier', {
    refresh: function(frm) {
        // Add eTIMS verification status indicator
        if (frm.doc.custom_registered_in_etims) {
            if (frm.dashboard) {
                frm.dashboard.add_indicator(__('Registered in eTIMS'), 'green');
            }

            // Show additional info if auto-verify is enabled
            if (frm.doc.custom_auto_verify_invoices) {
                if (frm.dashboard) {
                    frm.dashboard.add_indicator(__('Auto-Verify Enabled'), 'blue');
                }
            }
        }

        // Add "Test eTIMS Connection" button if Tax PIN is set
        if (frm.doc.custom_supplier_pin && frm.doc.custom_supplier_pin.length === 11) {
            frm.add_custom_button(__('Test eTIMS Connection'), function() {
                test_etims_supplier_connection(frm);
            }, __('eTIMS Actions'));
        }

        // Add "Verify Supplier Registration" button
        if (frm.doc.custom_supplier_pin && !frm.doc.custom_registered_in_etims) {
            frm.add_custom_button(__('Verify Supplier Registration'), function() {
                frappe.msgprint(__(
                    'Please verify with the supplier that they are registered in KRA eTIMS system. ' +
                    'Once confirmed, check the "Registered in eTIMS" checkbox.'
                ));
            }, __('eTIMS Actions'));
        }

        // Add "View Invoice Statistics" button
        frm.add_custom_button(__('View Invoice Statistics'), function() {
            view_supplier_invoice_stats(frm);
        }, __('eTIMS Actions'));

        // KRA PIN Verification
        if (frm.doc.custom_supplier_pin && !frm.is_new()) {
            frm.add_custom_button(__('Verify KRA PIN'), function() {
                frappe.call({
                    method: 'kenya_etims_compliance.utils.etims_utils.verify_supplier',
                    args: { supplier_name: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Verifying with KRA...'),
                    callback: function(r) {
                        if (r.message && r.message.status === 'success') {
                            frappe.show_alert({message: r.message.message, indicator: 'green'});
                        } else {
                            frappe.show_alert({message: (r.message && r.message.message) || 'Failed', indicator: 'red'});
                        }
                        frm.reload_doc();
                    }
                });
            }, __('eTIMS'));

            if (frm.doc.custom_kra_pin_verified) {
                frm.dashboard.set_headline(__('KRA PIN Verified'));
            }
        }
    },

    // Validate Tax PIN format
    custom_supplier_pin: function(frm) {
        const tax_pin = frm.doc.custom_supplier_pin;

        if (tax_pin && tax_pin.length > 0) {
            // KRA Tax PIN format: A followed by 9 digits (e.g., A000000000)
            const pin_pattern = /^A\d{9}$/;

            if (!pin_pattern.test(tax_pin)) {
                frappe.msgprint({
                    title: __('Invalid Tax PIN Format'),
                    message: __(
                        'KRA Tax PIN should be in the format A followed by 9 digits. ' +
                        'Example: A000000000'
                    ),
                    indicator: 'orange'
                });
            }
        }
    },

    // Warn if auto-verify is enabled but supplier is not registered
    custom_registered_in_etims: function(frm) {
        if (frm.doc.custom_auto_verify_invoices && !frm.doc.custom_registered_in_etims) {
            frappe.msgprint({
                title: __('Warning'),
                message: __(
                    'Auto-verify is enabled but the supplier is not marked as registered in eTIMS. ' +
                    'Please verify the supplier\'s eTIMS registration status.'
                ),
                indicator: 'yellow'
            });
        }
    },

    custom_auto_verify_invoices: function(frm) {
        if (frm.doc.custom_auto_verify_invoices && !frm.doc.custom_registered_in_etims) {
            frappe.msgprint({
                title: __('Warning'),
                message: __(
                    'Auto-verify should only be enabled for suppliers who are registered in KRA eTIMS. ' +
                    'Please confirm the supplier is registered before enabling auto-verification.'
                ),
                indicator: 'yellow'
            });
        }
    }
});

/**
 * Test eTIMS connection for supplier
 */
function test_etims_supplier_connection(frm) {
    frappe.call({
        method: 'kenya_etims_compliance.custom_methods.invoice_checker.check_invoice_validity',
        args: {
            invoice_no: 'TEST',
            supplier_pin: frm.doc.custom_supplier_pin,
            invoice_date: frappe.datetime.nowdate(),
            total_amount: 0
        },
        freeze: true,
        freeze_message: __('Testing eTIMS connection...'),
        callback: function(r) {
            // This will likely fail for a test invoice, but we can check
            // if the connection was successful (not a network error)
            frappe.msgprint({
                title: __('Connection Test'),
                message: __(
                    'eTIMS API connection test completed. ' +
                    'Check results for details.'
                ),
                indicator: r.message ? 'green' : 'yellow'
            });
        }
    });
}

/**
 * View invoice statistics for this supplier
 */
function view_supplier_invoice_stats(frm) {
    frappe.call({
        method: 'kenya_etims_compliance.custom_methods.purchase_invoice.get_supplier_invoice_status',
        args: {
            supplier: frm.doc.name
        },
        freeze: true,
        callback: function(r) {
            if (r.message) {
                const stats = r.message;
                const html = `
                    <div style="padding: 15px;">
                        <h5>Invoice Verification Statistics</h5>
                        <table class="table table-bordered">
                            <tr>
                                <th>Total Invoices</th>
                                <td>${stats.total_invoices || 0}</td>
                            </tr>
                            <tr>
                                <th>Verified Invoices</th>
                                <td style="color: green;">${stats.verified_invoices || 0}</td>
                            </tr>
                            <tr>
                                <th>Unverified Invoices</th>
                                <td style="color: red;">${stats.unverified_invoices || 0}</td>
                            </tr>
                            <tr>
                                <th>Verification Rate</th>
                                <td><b>${stats.verification_rate || 'N/A'}</b></td>
                            </tr>
                        </table>
                        <p class="text-muted text-center">
                            ${stats.verification_rate === '100.0%' ?
                                'Excellent! All invoices are verified.' :
                                'Some invoices require verification for full tax compliance.'
                            }
                        </p>
                    </div>
                `;

                const dialog = new frappe.ui.Dialog({
                    title: __('Supplier Invoice Statistics'),
                    fields: [
                        {
                            fieldtype: 'HTML',
                            fieldname: 'stats_html',
                            options: html
                        }
                    ],
                    primary_action: function() {
                        dialog.hide();
                    },
                    primary_action_label: __('Close')
                });

                dialog.show();
            }
        }
    });
}
