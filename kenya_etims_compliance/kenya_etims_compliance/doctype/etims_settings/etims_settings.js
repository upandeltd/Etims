// Copyright (c) 2026, Upande Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("eTIMS Settings", {
	refresh(frm) {
		// Run Setup Wizard button
		frm.add_custom_button(__("Run Setup Wizard"), function () {
			frappe.set_route("app", "etims-setup-wizard");
		}, __("eTIMS Actions"));

		// View Dashboard Data button
		frm.add_custom_button(__("View Dashboard"), function () {
			frappe.call({
				method: "kenya_etims_compliance.custom_methods.dashboard.get_dashboard_data",
				callback: function (r) {
					if (!r.message) return;
					render_dashboard_modal(r.message);
				},
			});
		}, __("eTIMS Actions"));

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
							// bulk_retry_failed() hands off to a background job,
							// so no synchronous count is available.
							if (r.message && r.message.scheduled) {
								frappe.show_alert({
									message: __("Retry scheduled - eligible failed entries are being re-queued"),
									indicator: "green",
								});
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

function render_dashboard_modal(d) {
	const supplier_rate = d.total_suppliers
		? Math.round((d.verified_suppliers / d.total_suppliers) * 100)
		: 0;
	const success_color = d.sales_success_rate >= 90 ? "green" : d.sales_success_rate >= 70 ? "orange" : "red";
	const deadline_color = d.days_to_deadline > 7 ? "green" : d.days_to_deadline > 3 ? "orange" : "red";

	frappe.msgprint({
		title: __("eTIMS Dashboard"),
		indicator: "blue",
		message: `
			<div class="etims-dashboard-modal">
				<div class="etims-dashboard-grid">
					${dashboard_card("Sales Transmitted", d.sales_transmitted, "blue", "/app/sales-invoice")}
					${dashboard_card("Sales Pending", d.sales_pending, "orange", "/app/sales-invoice")}
					${dashboard_card("Sales Success Rate", d.sales_success_rate + "%", success_color, "/app/sales-invoice")}
					${dashboard_card("Queue Failed", d.queue_failed, "red", "/app/etims-invoice-queue")}
					${dashboard_card("Purchases Matched", d.purchase_matched, "green", "/app/purchase-invoice")}
					${dashboard_card("Purchases Unmatched", d.purchase_unmatched, "orange", "/app/purchase-invoice")}
					${dashboard_card("Input VAT at Risk", format_currency(d.input_vat_at_risk), "red", "/app/purchase-invoice")}
					${dashboard_card("Suppliers Verified", d.verified_suppliers + " / " + d.total_suppliers, "blue", "/app/supplier")}
					${dashboard_card("Compliance Score", d.compliance_score, d.compliance_score >= 80 ? "green" : "orange", "/app/etims-compliance-score")}
					${dashboard_card("Days to Deadline", d.days_to_deadline, deadline_color, "/app/etims-vat-return-preview")}
					${dashboard_card("Queue Pending", d.queue_pending, "blue", "/app/etims-invoice-queue")}
					${dashboard_card("Errors This Month", d.errors_this_month || "—", "red", "/app/error-log")}
				</div>
				<div class="etims-dashboard-progress">
					<h6>${__("Supplier Verification")}</h6>
					<div class="progress">
						<div class="progress-bar bg-${supplier_rate >= 80 ? "success" : supplier_rate >= 50 ? "warning" : "danger"} etims-progress-width-${Math.round(supplier_rate / 5) * 5}" role="progressbar" aria-valuenow="${supplier_rate}" aria-valuemin="0" aria-valuemax="100">${supplier_rate}%</div>
					</div>
					<p class="text-muted text-xs mt-2">${d.verified_suppliers} of ${d.total_suppliers} suppliers with PIN are verified</p>
				</div>
			</div>
		`,
	});
}

function dashboard_card(label, value, color, link) {
	return `
		<a href="${link}" class="etims-dashboard-card etims-dashboard-card--${color}">
			<div class="etims-dashboard-card__label">${__(label)}</div>
			<div class="etims-dashboard-card__value">${value}</div>
		</a>
	`;
}

function render_queue_dashboard(frm) {
	frappe.call({
		method: "kenya_etims_compliance.custom_methods.queue_processor.get_queue_status",
		callback: function (r) {
			if (!r.message) return;

			let stats = r.message;
			let wrapper = frm.fields_dict.enable_queue.$wrapper;

			// Remove existing dashboard if any
			wrapper.parent().find(".etims-queue-dashboard").remove();

			let color_class = {
				Queued: "etims-text-blue",
				Processing: "etims-text-orange",
				Sent: "etims-text-green",
				Failed: "etims-text-red",
				Cancelled: "etims-text-gray",
			};

			let status_items = [];
			for (let [status, count] of Object.entries(stats)) {
				if (status === "total") continue;
				let cls = color_class[status] || "etims-text-gray";
				status_items.push(`
					<div class="etims-queue-item">
						<div class="etims-queue-item__count ${cls}">${count}</div>
						<div class="etims-queue-item__label">${status}</div>
					</div>
				`);
			}

			let html = `
				<div class="etims-queue-dashboard">
					<div class="etims-queue-dashboard__header">
						<h6>${__("Invoice Queue Status")}</h6>
						<a href="/app/etims-invoice-queue" class="etims-queue-dashboard__link">${__("View Queue List")}</a>
					</div>
					<div class="etims-queue-dashboard__grid">
						${status_items.join("")}
					</div>
					<div class="etims-queue-dashboard__footer">
						${__("Total")}: ${stats.total}
					</div>
				</div>
			`;

			wrapper.parent().append(html);
		},
	});
}
