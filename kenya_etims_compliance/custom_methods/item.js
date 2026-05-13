frappe.ui.form.on('Item', {
	custom_register_item: function (frm) {
		// Pre-validation before calling KRA API
		frappe.call({
			method: "kenya_etims_compliance.custom_methods.item.validate_item_for_etims",
			args: { doc_name: frm.doc.name },
			callback: function (r) {
				if (r.message && !r.message.valid) {
					const error_html = r.message.errors.map(e => `<li>${e}</li>`).join('');
					frappe.msgprint({
						title: __("Item cannot be registered in eTIMS"),
						indicator: 'red',
						message: `<ul>${error_html}</ul>`
					});
					return;
				}
				// Validation passed — proceed with registration
				_registerItem(frm);
			}
		});
	},

	custom_update_item: function (frm) {
		frappe.call({
			"method": "kenya_etims_compliance.custom_methods.item.importItemUpdateReq",
			args: { doc_name: frm.doc.name },
			freeze: true,
			callback: function (r) {
				let keys = Object.keys(r.message);
				let values = Object.values(r.message);
				frappe.msgprint({
					title: __(keys[0]),
					indicator: keys[0] === 'Success' ? 'green' : 'red',
					message: __(values[0])
				});
			}
		});
	},

	custom_search_item_in_etims: function (frm) {
		frappe.call({
			"method": "kenya_etims_compliance.custom_methods.item.searchItemReq",
			args: {
				"item_code": frm.doc.custom_item_code || null,
				"item_name": frm.doc.custom_item_name || null
			},
			freeze: true,
			callback: function (r) {
				let keys = Object.keys(r.message);
				let values = Object.values(r.message);
				frappe.msgprint({
					title: __(keys[0]),
					indicator: keys[0] === 'Success' ? 'green' : 'red',
					message: __(JSON.stringify(values[0], null, 2))
				});
			}
		});
	},

	custom_update_item_to_tims: function (frm) {
		if (frm.doc.custom_update_item_to_tims) {
			frappe.show_alert({
				message: __("eTIMS fields will be auto-populated on Save. Review before registering."),
				indicator: 'blue'
			}, 5);
		}
	}
});

function _registerItem(frm) {
	frappe.call({
		"method": "kenya_etims_compliance.custom_methods.item.itemSaveReq",
		args: { doc_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Registering item in eTIMS..."),
		callback: function (r) {
			let keys = Object.keys(r.message);
			let values = Object.values(r.message);
			frappe.msgprint({
				title: __(keys[0]),
				indicator: keys[0] === 'Success' ? 'green' : 'red',
				message: __(values[0])
			});
			if (keys[0] === 'Success') {
				frm.reload_doc();
			}
		}
	});
}
