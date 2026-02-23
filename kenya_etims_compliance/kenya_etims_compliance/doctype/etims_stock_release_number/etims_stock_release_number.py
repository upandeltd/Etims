# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

from datetime import datetime
import frappe
from frappe.model.document import Document


class eTIMSStockReleaseNumber(Document):
	def validate(self):
		"""Validate before saving"""
		# Check branch access if RBAC is enabled
		from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import is_rbac_enabled
		from kenya_etims_compliance.utils.permissions import validate_branch_access

		if is_rbac_enabled():
			validate_branch_access(self)

	def on_submit(self):
		"""Sync to KRA on submit"""
		from kenya_etims_compliance.custom_methods.stock_release import sync_stock_release_number
		from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
			get_etims_settings,
			get_sar_type_for_doctype,
			is_rbac_enabled
		)
		from kenya_etims_compliance.utils.permissions import (
			require_sync_permission,
			log_permission_check
		)

		# Check if RBAC is enabled and user has sync permission
		if is_rbac_enabled():
			# Check permission before syncing
			log_permission_check("eTIMS Stock Release Number", "sync", True)
			require_sync_permission(lambda: None)()  # Decorator check
			# Re-check programmatically
			from kenya_etims_compliance.utils.permissions import can_sync_to_etims
			if not can_sync_to_etims(None):
				frappe.throw(
					"Permission Denied: You do not have permission to sync to eTIMS. "
					"This action requires eTIMS Administrator, Manager, or Operator role."
				)

		# Check if auto sync is enabled
		settings = get_etims_settings()
		if not settings.get("enable_auto_sync", 1):
			return

		# Use SAR type from doctype, or get default based on reference type
		sar_type = self.sar_type or get_sar_type_for_doctype(self.reference_type)

		result = sync_stock_release_number(
			self.sr_number,
			self.orginal_sr_number or 0,
			sar_type
		)

		if result.get("Error"):
			self.sync_status = "Failed"
			self.save()
			frappe.throw(result.get("Error"))
		else:
			self.synced_to_etims = 1
			self.sync_date = datetime.now()
			self.sync_status = "Success"
			self.save()

	def on_trash(self):
		"""Validate before deleting"""
		from kenya_etims_compliance.utils.permissions import can_delete_doctype

		if can_delete_doctype("eTIMS Stock Release Number"):
			# Check permission before allowing delete
			from kenya_etims_compliance.utils.permissions import is_etims_admin, is_etims_manager
			if not (is_etims_admin() or is_etims_manager()):
				frappe.throw(
					"Permission Denied: You cannot delete Stock Release Numbers. "
					"This action requires eTIMS Administrator or Manager role."
				)
		else:
			frappe.throw(
				"Permission Denied: You do not have permission to delete this record."
			)
