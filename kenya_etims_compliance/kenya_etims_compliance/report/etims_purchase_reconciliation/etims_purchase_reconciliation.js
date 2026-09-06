frappe.query_reports["eTIMS Purchase Reconciliation"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "match_status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nPending\nMatched\nMatched (Auto-Created)\nAmount Mismatch\nMissing Locally\nNot in KRA\nAccepted\nReview Required",
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Tax Branch Office",
		},
	],

	onload: function (report) {
		report.page.add_inner_button(__("Run Reconciliation"), function () {
			// Reconcile the period you are looking at, not an implicit "last
			// month" that may be nowhere in the visible range.
			const from_date = report.get_filter_value("from_date");
			frappe.call({
				method: "kenya_etims_compliance.custom_methods.reconciliation.run_reconciliation_manual",
				args: {
					period: from_date ? from_date.slice(0, 7) : null,
					branch: report.get_filter_value("branch") || null,
				},
				freeze: true,
				freeze_message: __("Running reconciliation..."),
				callback: function (r) {
					// The server msgprints the summary; only the log link is news.
					if (r.message && r.message.log) {
						frappe.set_route("Form", "eTIMS Reconciliation Log", r.message.log);
					} else {
						report.refresh();
					}
				},
			});
		});
	},
};
