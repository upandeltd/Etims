frappe.ui.form.on("eTIMS Reconciliation Log", {
	refresh: function (frm) {
		if (frm.is_new()) return;

		if (frm.doc.status === "Closed") {
			frm.dashboard.set_headline(
				__("Closed by {0} on {1}", [frm.doc.closed_by, frm.doc.closed_on])
			);
			frm.add_custom_button(__("Re-open Period"), function () {
				// Reopening a filed period is auditable, never silent.
				frappe.prompt(
					{
						fieldname: "reason",
						label: __("Reason"),
						fieldtype: "Small Text",
						reqd: 1,
					},
					function (values) {
						frappe.call({
							method: "kenya_etims_compliance.custom_methods.reconciliation.reopen_period",
							args: { log_name: frm.doc.name, reason: values.reason },
							freeze: true,
							callback: () => frm.reload_doc(),
						});
					},
					__("Re-open {0}", [frm.doc.period]),
					__("Re-open")
				);
			});
			return;
		}

		// Draft: the numbers are only as fresh as the last run, so offer both
		// a re-run and the close that re-runs before it freezes anything.
		frm.add_custom_button(__("Re-run"), function () {
			frappe.call({
				method: "kenya_etims_compliance.custom_methods.reconciliation.run_reconciliation_manual",
				args: { period: frm.doc.period, branch: frm.doc.branch },
				freeze: true,
				freeze_message: __("Reconciling {0}...", [frm.doc.period]),
				callback: () => frm.reload_doc(),
			});
		});

		frm.add_custom_button(__("Close Period"), function () {
			frappe.confirm(
				__("Close {0}? Unresolved exceptions will block the close.", [frm.doc.period]),
				function () {
					frappe.call({
						method: "kenya_etims_compliance.custom_methods.reconciliation.close_period",
						args: { period: frm.doc.period, branch: frm.doc.branch },
						freeze: true,
						freeze_message: __("Closing {0}...", [frm.doc.period]),
						callback: () => frm.reload_doc(),
					});
				}
			);
		});
		frm.change_custom_button_type(__("Close Period"), null, "primary");
	},
});
