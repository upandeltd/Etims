frappe.listview_settings["eTIMS Invoice Queue"] = frappe.listview_settings["eTIMS Invoice Queue"] || {};

const original_onload = frappe.listview_settings["eTIMS Invoice Queue"].onload;

frappe.listview_settings["eTIMS Invoice Queue"].onload = function (listview) {
	if (original_onload) {
		original_onload(listview);
	}

	// One-click retry for every Failed entry in the queue, without leaving the
	// list view. Reuses the same whitelisted bulk_retry_failed() the "Bulk
	// Retry Failed" button on eTIMS Settings calls, so behaviour (max_retries
	// guard, permission check) is identical - this just adds a second, more
	// direct entry point at the point of use.
	listview.page.add_inner_button(
		__("Retry All Failed"),
		function () {
			frappe.confirm(
				__("Retry all failed queue entries that haven't exceeded max retries?"),
				function () {
					frappe.call({
						method: "kenya_etims_compliance.custom_methods.queue_processor.bulk_retry_failed",
						freeze: true,
						freeze_message: __("Re-queuing failed entries..."),
						callback: function (r) {
							if (!r.message) return;
							const count = r.message.enqueued;
							if (count > 0) {
								frappe.show_alert({
									message: __("{0} entries re-queued for processing", [count]),
									indicator: "green",
								});
							} else {
								frappe.show_alert({
									message: __("No failed entries are eligible for retry"),
									indicator: "orange",
								});
							}
							listview.refresh();
						},
					});
				}
			);
		},
		__("Actions")
	);
};
