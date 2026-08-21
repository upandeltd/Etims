# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from kenya_etims_compliance.utils.permissions import require


class eTIMSSettings(Document):
	def validate(self):
		"""Validate settings before saving"""
		self.validate_timeout()
		self.validate_retry_settings()
		self.validate_search_limits()

	def validate_timeout(self):
		"""Validate API timeout is positive and reasonable"""
		if self.api_timeout and self.api_timeout < 1:
			frappe.throw(_("API Timeout must be at least 1 second"))
		if self.api_timeout and self.api_timeout > 300:
			frappe.msgprint(_("Warning: API timeout exceeds 5 minutes. This may cause issues."))

	def validate_retry_settings(self):
		"""Validate retry settings"""
		if self.enable_retry_logic:
			if self.max_retry_attempts and self.max_retry_attempts < 1:
				frappe.throw(_("Max Retry Attempts must be at least 1"))
			if self.max_retry_attempts and self.max_retry_attempts > 10:
				frappe.msgprint(_("Warning: High retry count may cause delays."))
			if self.retry_delay and self.retry_delay < 0:
				frappe.throw(_("Retry Delay cannot be negative"))

	def validate_search_limits(self):
		"""Validate search result limits"""
		if self.max_search_limit and self.default_search_limit:
			if self.default_search_limit > self.max_search_limit:
				frappe.throw(_("Default Search Limit cannot exceed Max Search Limit"))


@frappe.whitelist()
def get_etims_settings():
	"""Get eTIMS settings with defaults.

	Caller is authorised if they have any write on eTIMS Settings OR are an
	eTIMS Admin/Manager. The full dict is returned to Admin/Manager; a
	limited subset is returned to a write-only caller to keep compliance
	and RBAC toggles out of every clerk's hands.
	"""
	from kenya_etims_compliance.utils.permissions import is_etims_admin, is_etims_manager

	is_privileged = is_etims_admin() or is_etims_manager() or "System Manager" in frappe.get_roles()
	if not is_privileged:
		# Anyone else still needs to read settings — they may legitimately
		# need api_timeout / sar types — but must not see compliance or RBAC
		# toggles. require() is on read here.
		require("eTIMS Settings", "read")

	_defaults = {
		"default_sar_type_sales": "11",
		"default_sar_type_purchase": "02",
		"default_sar_type_stock_entry": "06",
		"api_timeout": 30,
		"production_api_url": "https://etims-api.kra.go.ke/etims-api/",
		"sandbox_api_url": "https://etims-api-sbx.kra.go.ke/etims-api/",
		"enable_retry_logic": 1,
		"max_retry_attempts": 3,
		"retry_delay": 2,
		"default_search_limit": 100,
		"max_search_limit": 1000,
		"enable_error_logging": 1,
		"enable_auto_sync": 1,
		"enable_queue": 1,
		"queue_max_retries": 10,
		"queue_retry_interval": 5,
		"wait_for_etims_before_print": 1,
		"etims_print_wait_seconds": 6,
		"vat_obligation": "Registered",
	}

	try:
		settings = frappe.get_single("eTIMS Settings")
	except frappe.DoesNotExistError as e:
		frappe.log_error(title="eTIMS: Settings load failed", message=str(e))
		return _defaults

	# Build the full dict (Admin/Manager path) by overlaying the Single on
	# defaults — same behaviour as before.
	doc_dict = settings.as_dict()
	result = dict(_defaults)
	for k, v in doc_dict.items():
		if k.startswith("_") or k in ("name", "doctype", "owner", "creation", "modified", "modified_by", "docstatus", "idx"):
			continue
		if v is not None:
			result[k] = v
	if not result.get("production_api_url"):
		result["production_api_url"] = _defaults["production_api_url"]
	if not result.get("sandbox_api_url"):
		result["sandbox_api_url"] = _defaults["sandbox_api_url"]

	if is_privileged:
		return result

	# Non-Admin path: only keys needed for normal operation. RBAC, branch
	# isolation, error logging, queue internals and compliance scoring all
	# stay out.
	limited_keys = (
		"default_sar_type_sales",
		"default_sar_type_purchase",
		"default_sar_type_stock_entry",
		"api_timeout",
		"enable_retry_logic",
		"max_retry_attempts",
		"retry_delay",
		"enable_queue",
		"enable_auto_sync",
		"wait_for_etims_before_print",
		"etims_print_wait_seconds",
		"vat_obligation",
		"production_api_url",
		"sandbox_api_url",
	)
	return {k: result[k] for k in limited_keys if k in result}


def get_api_timeout():
	"""Get API timeout from settings"""
	settings = get_etims_settings()
	return settings.get("api_timeout", 30)


def get_sar_type_for_doctype(doctype):
	"""Get default SAR type for a given doctype"""
	settings = get_etims_settings()

	sar_type_mapping = {
		"Sales Invoice": settings.get("default_sar_type_sales", "11"),
		"Purchase Invoice": settings.get("default_sar_type_purchase", "02"),
		"Stock Entry": settings.get("default_sar_type_stock_entry", "06"),
	}

	return sar_type_mapping.get(doctype, "11")  # Default to sales SAR type


def get_retry_settings():
	"""Get retry settings"""
	settings = get_etims_settings()
	return {
		"enabled": settings.get("enable_retry_logic", 1),
		"max_attempts": settings.get("max_retry_attempts", 3),
		"delay": settings.get("retry_delay", 2),
	}


def get_api_url(api_mode):
	"""Get API URL based on mode"""
	settings = get_etims_settings()

	if api_mode == "Production":
		return settings.get("production_api_url", "https://etims-api.kra.go.ke/etims-api/")
	else:
		return settings.get("sandbox_api_url", "https://etims-api-sbx.kra.go.ke/etims-api/")


def is_rbac_enabled():
	"""Check if Role-Based Access Control is enabled"""
	settings = get_etims_settings()
	return settings.get("enable_rbac", 1)


def is_branch_isolation_enforced():
	"""Check if branch isolation is enforced"""
	settings = get_etims_settings()
	return settings.get("enforce_branch_isolation", 1)


def is_cross_branch_allowed():
	"""Check if cross-branch operations are allowed for managers"""
	settings = get_etims_settings()
	return settings.get("allow_cross_branch_operations", 0)


def is_permission_logging_enabled():
	"""Check if permission logging is enabled"""
	settings = get_etims_settings()
	return settings.get("enable_permission_logging", 1)
