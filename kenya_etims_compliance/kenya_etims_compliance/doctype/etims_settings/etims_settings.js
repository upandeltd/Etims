// Copyright (c) 2026, Upande Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("eTIMS Settings", {
	refresh(frm) {
		// Test Connection button
		frm.add_custom_button(__("Test Connection"), function () {
			frappe.call({
				method: "kenya_etims_compliance.custom_methods.device_status.check_connection",
				freeze: true,
				freeze_message: __("Testing OSCU/VSCU connection..."),
				callback: function (r) {
					if (r.message) {
						let result = r.message;
						if (result.connected) {
							frappe.msgprint({
								title: __("Connection Successful"),
								indicator: "green",
								message: __("OSCU/VSCU is online. Response time: {0}ms", [result.response_time_ms]),
							});
						} else {
							frappe.msgprint({
								title: __("Connection Failed"),
								indicator: "red",
								message: __("OSCU/VSCU is unreachable: {0}", [result.error]),
							});
						}
					}
				},
			});
		}, __("eTIMS Actions"));

		// Bulk Retry Failed button
		frm.add_custom_button(__("Bulk Retry Failed"), function () {
			frappe.confirm(
				__("Retry all failed queue entries that haven't exceeded max retries?"),
				function () {
					frappe.call({
						method: "kenya_etims_compliance.custom_methods.queue_processor.bulk_retry_failed",
						freeze: true,
						freeze_message: __("Re-queuing failed entries..."),
						callback: function (r) {
							if (r.message) {
								frappe.show_alert({
									message: __("{0} entries re-queued for processing", [r.message.enqueued]),
									indicator: "green",
								});
								// Refresh dashboard
								frm.trigger("refresh");
							}
						},
					});
				}
			);
		}, __("eTIMS Actions"));

		// Queue Dashboard
		render_queue_dashboard(frm);
	},
});

function render_queue_dashboard(frm) {
	frappe.call({
		method: "kenya_etims_compliance.custom_methods.queue_processor.get_queue_status",
		callback: function (r) {
			if (!r.message) return;

			let stats = r.message;
			let wrapper = frm.fields_dict.enable_queue.$wrapper;

			// Remove existing dashboard if any
			wrapper.parent().find(".etims-queue-dashboard").remove();

			let colors = {
				Queued: "#2490ef",
				Processing: "#f39c12",
				Sent: "#28a745",
				Failed: "#dc3545",
				Cancelled: "#6c757d",
			};

			let html = `
				<div class="etims-queue-dashboard" style="margin: 15px 0; padding: 15px; background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px;">
					<h6 style="margin-bottom: 10px; font-weight: 600;">Invoice Queue Status</h6>
					<div style="display: flex; gap: 12px; flex-wrap: wrap;">`;

			for (let [status, count] of Object.entries(stats)) {
				if (status === "total") continue;
				let color = colors[status] || "#6c757d";
				html += `
					<div style="text-align: center; min-width: 70px;">
						<div style="font-size: 20px; font-weight: 700; color: ${color};">${count}</div>
						<div style="font-size: 11px; color: var(--text-muted);">${status}</div>
					</div>`;
			}

			html += `
					</div>
					<div style="margin-top: 10px; font-size: 11px; color: var(--text-muted);">
						Total: ${stats.total} &nbsp;|&nbsp;
						<a href="/app/etims-invoice-queue">View Queue List</a>
					</div>
				</div>`;

			wrapper.parent().append(html);
		},
	});
}
