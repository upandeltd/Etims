frappe.query_reports["eTIMS Income Expense Validation"] = {
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
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Tax Branch Office",
		},
		{
			fieldname: "status",
			label: __("eTIMS Status"),
			fieldtype: "Select",
			options: "\nAll\nSuccess\nPending\nNot Required",
			default: "All",
		},
	],
};
