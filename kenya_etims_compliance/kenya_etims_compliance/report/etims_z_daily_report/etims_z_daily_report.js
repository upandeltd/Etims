// Copyright (c) 2026, Upande Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["eTIMS Z Daily Report"] = {
	filters: [
		{
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Tax Branch Office",
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
	],
	onload: function (report) {
		report.page.add_inner_button(__("Close Z Report"), function () {
			const values = report.get_values();
			if (!values.date || !values.branch) {
				frappe.msgprint(__("Set Date and Branch before closing the Z report."));
				return;
			}
			frappe.confirm(
				__("Close the Z report for {0}, branch {1}? This cannot be undone for this day.", [
					values.date,
					values.branch,
				]),
				function () {
					frappe.call({
						method:
							"kenya_etims_compliance.kenya_etims_compliance.report.etims_z_daily_report.etims_z_daily_report.close_z_report",
						args: { date: values.date, branch: values.branch, company: values.company },
						freeze: true,
						freeze_message: __("Closing Z report..."),
						callback: function (r) {
							if (r.message && r.message.status === "success") {
								frappe.msgprint(__("Z report closed for {0}.", [r.message.closed_date]));
								report.refresh();
							}
						},
					});
				}
			);
		});
	},
};
