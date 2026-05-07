// Copyright (c) 2026, Upande Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("eTIMS Invoice Queue", {
	refresh(frm) {
		// Add retry button for Failed entries
		if (frm.doc.status === "Failed") {
			frm.add_custom_button(__("Retry Now"), function() {
				frappe.call({
					method: "kenya_etims_compliance.custom_methods.queue_processor.retry_single_entry",
					args: { queue_entry_name: frm.doc.name },
					callback: function(r) {
						if (r.message && r.message.status === "enqueued") {
							frappe.show_alert({
								message: __("Queue entry re-queued for processing"),
								indicator: "green"
							});
							frm.reload_doc();
						}
					}
				});
			}, __("Actions"));
		}

		// Add process button for Queued entries
		if (frm.doc.status === "Queued") {
			frm.add_custom_button(__("Process Now"), function() {
				frappe.call({
					method: "kenya_etims_compliance.custom_methods.queue_processor.retry_single_entry",
					args: { queue_entry_name: frm.doc.name },
					callback: function(r) {
						if (r.message && r.message.status === "enqueued") {
							frappe.show_alert({
								message: __("Queue entry sent to background worker"),
								indicator: "blue"
							});
							frm.reload_doc();
						}
					}
				});
			}, __("Actions"));
		}
	}
});
