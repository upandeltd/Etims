frappe.listview_settings["Item"] = frappe.listview_settings["Item"] || {};

const original_onload = frappe.listview_settings["Item"].onload;

frappe.listview_settings["Item"].onload = function(listview) {
	if (original_onload) {
		original_onload(listview);
	}

	listview.page.add_action_item(__("Register in eTIMS"), function() {
		const items = listview.get_checked_items();
		if (!items.length) {
			frappe.msgprint(__("Please select items to register"));
			return;
		}

		const item_names = items.map(i => i.name);

		frappe.call({
			method: "kenya_etims_compliance.custom_methods.bulk_operations.bulk_register_items",
			args: { items: JSON.stringify(item_names) },
			freeze: true,
			freeze_message: __("Registering {0} items in eTIMS...", [item_names.length]),
			callback: function(r) {
				if (r.message) {
					frappe.msgprint(
						__("{0} of {1} items registered successfully. {2} failed.", [
							r.message.success, r.message.total, r.message.failed
						])
					);
					listview.refresh();
				}
			}
		});
	});
};
