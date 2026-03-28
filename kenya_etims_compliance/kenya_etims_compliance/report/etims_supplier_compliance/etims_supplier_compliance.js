frappe.query_reports["eTIMS Supplier Compliance"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nCompliant\nAt Risk\nNon-Compliant\nUnknown",
		},
	],
};
