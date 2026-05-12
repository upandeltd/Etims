import frappe
from frappe.model.document import Document


class eTIMSPurchaseRegisterEntry(Document):
	def before_save(self):
		# Auto-link to Supplier by PIN
		if self.supplier_pin and not self.supplier:
			supplier = frappe.db.get_value("Supplier", {"custom_supplier_pin": self.supplier_pin}, "name")
			if supplier:
				self.supplier = supplier

		# Audit trail for variance acceptance
		if self.variance_accepted and not self.accepted_by:
			self.accepted_by = frappe.session.user
			self.accepted_on = frappe.utils.now_datetime()
