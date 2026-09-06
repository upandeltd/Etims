import frappe
from frappe import _
from frappe.model.document import Document


class eTIMSReconciliationLog(Document):
	def validate(self):
		"""A closed period is a filed snapshot — reopen it before changing it.

		`close_period` and `reopen_period` in
		`kenya_etims_compliance.custom_methods.reconciliation` are the only
		sanctioned transitions; everything else that reaches a closed log,
		including a hand edit in the Desk, is refused here.
		"""
		if self.is_new():
			return

		if self.status == "Closed" and frappe.db.get_value(
			"eTIMS Reconciliation Log", self.name, "status"
		) == "Closed":
			frappe.throw(_("Period {0} is closed. Re-open it before making changes.").format(self.period))
