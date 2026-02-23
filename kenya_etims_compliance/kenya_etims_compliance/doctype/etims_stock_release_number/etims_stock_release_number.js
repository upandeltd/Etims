// Copyright (c) 2024, Upande Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("eTIMS Stock Release Number", {
	refresh: function(frm) {
		// Add "Sync to eTIMS" button if not already synced
		if (!frm.doc.synced_to_etims && frm.doc.docstatus === 1) {
			frm.add_custom_button(__('Sync to eTIMS'), function() {
				frm.trigger('sync_to_etims');
			}, __('Actions'));
		}

		// Add "View Details" button
		if (frm.doc.docstatus === 0 && frm.doc.sr_number) {
			frm.add_custom_button(__('Search in eTIMS'), function() {
				frm.trigger('search_in_etims');
			}, __('Actions'));
		}
	},

	sync_to_etims: function(frm) {
		frappe.call({
			method: "kenya_etims_compliance.custom_methods.stock_release.sync_stock_release_number",
			args: {
				sar_no: frm.doc.sr_number,
				org_sar_no: frm.doc.orginal_sr_number || 0,
				sar_type: frm.doc.sar_type || '11'
			},
			freeze: true,
			callback: function(r) {
				let keys = Object.keys(r.message)
				let values = Object.values(r.message)
				frappe.msgprint({
					title: __(keys[0]),
					indicator: keys[0] === 'Success' ? 'green' : 'red',
					message: __(values[0])
				});

				if (keys[0] === 'Success') {
					frm.set_value('synced_to_etims', 1);
					frm.set_value('sync_date', new Date());
					frm.set_value('sync_status', 'Success');
					frm.refresh();
				} else {
					frm.set_value('sync_status', 'Failed');
					frm.refresh();
				}
			}
		})
	},

	search_in_etims: function(frm) {
		frappe.call({
			method: "kenya_etims_compliance.custom_methods.stock_release.search_stock_release_no",
			args: {
				sar_no: frm.doc.sr_number
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
});
