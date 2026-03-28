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
			options: "\nPending\nMatched\nMatched (Auto-Created)\nAmount Mismatch\nMissing Locally\nNot in KRA\nReview Required",
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
			frappe.call({
				method: "kenya_etims_compliance.custom_methods.reconciliation.run_reconciliation_manual",
				freeze: true,
				freeze_message: __("Running reconciliation..."),
				callback: function (r) {
					if (r.message) {
						frappe.msgprint(r.message);
						report.refresh();
					}
				},
			});
		});
	},
};
