frappe.listview_settings["Item"] = frappe.listview_settings["Item"] || {};

const original_onload = frappe.listview_settings["Item"].onload;

frappe.listview_settings["Item"].onload = function (listview) {
	if (original_onload) {
		original_onload(listview);
	}

	// Add eTIMS registration status indicator column
	listview.page.add_inner_button(
		__("Register in eTIMS"),
		function () {
			const items = listview.get_checked_items();
			if (!items.length) {
				frappe.msgprint(__("Please select items to register"));
				return;
			}

			const item_names = items.map(i => i.name);

			// Pre-validate before bulk register
			_validateAndBulkRegister(item_names, listview);
		},
		__("Actions")
	);

	// Refresh button state on selection change
	listview.page.body.on("change", ".list-row-checkbox", function () {
		const checked = listview.get_checked_items().length;
		if (checked > 0) {
			listview.page.btn_primary || listview.page.set_primary_action(
				__("Register {0} Item(s)", [checked]),
				function () {
					const items = listview.get_checked_items().map(i => i.name);
					_validateAndBulkRegister(items, listview);
				}
			);
		}
	});
};

function _validateAndBulkRegister(item_names, listview) {
	frappe.call({
		method: "kenya_etims_compliance.custom_methods.item.validate_items_for_etims",
		args: { items: JSON.stringify(item_names) },
		freeze: true,
		freeze_message: __("Validating items..."),
		callback: function (r) {
			const result = r.message || {};
			const valid = result.valid || [];
			const invalid = result.invalid || [];

			if (invalid.length > 0) {
				let error_html = invalid.map(function (i) {
					return `<tr>
						<td><strong>${i.item}</strong></td>
						<td><ul>${i.errors.map(e => `<li>${e}</li>`).join('')}</ul></td>
					</tr>`;
				}).join('');

				frappe.msgprint({
					title: __("{0} of {1} items failed validation", [invalid.length, item_names.length]),
					indicator: 'orange',
					message: `
						<p>${__("Only valid items will be registered.")}</p>
						<table class="table table-bordered table-hover" style="font-size:12px">
							<thead><tr><th>Item</th><th>Errors</th></tr></thead>
							<tbody>${error_html}</tbody>
						</table>
					`
				});
			}

			if (valid.length === 0) {
				frappe.msgprint({
					title: __("No valid items"),
					indicator: 'red',
					message: __("None of the selected items passed validation. Please fix the errors and try again.")
				});
				return;
			}

			// Proceed with bulk registration for valid items only
			frappe.call({
				method: "kenya_etims_compliance.custom_methods.bulk_operations.bulk_register_items",
				args: { items: JSON.stringify(valid) },
				freeze: true,
				freeze_message: __("Registering {0} items in eTIMS...", [valid.length]),
				callback: function (r2) {
					if (r2.message) {
						frappe.msgprint({
							title: __("Bulk Registration Complete"),
							indicator: r2.message.failed > 0 ? 'orange' : 'green',
							message: __(
								"{0} of {1} items registered successfully. {2} failed.",
								[r2.message.success, r2.message.total, r2.message.failed]
							)
						});
						listview.refresh();
					}
				}
			});
		}
	});
}
