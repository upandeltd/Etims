# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class eTIMSSettings(Document):
	def validate(self):
		"""Validate settings before saving"""
		self.validate_timeout()
		self.validate_retry_settings()
		self.validate_search_limits()

	def validate_timeout(self):
		"""Validate API timeout is positive and reasonable"""
		if self.api_timeout and self.api_timeout < 1:
			frappe.throw("API Timeout must be at least 1 second")
		if self.api_timeout and self.api_timeout > 300:
			frappe.msgprint("Warning: API timeout exceeds 5 minutes. This may cause issues.")

	def validate_retry_settings(self):
		"""Validate retry settings"""
		if self.enable_retry_logic:
			if self.max_retry_attempts and self.max_retry_attempts < 1:
				frappe.throw("Max Retry Attempts must be at least 1")
			if self.max_retry_attempts and self.max_retry_attempts > 10:
				frappe.msgprint("Warning: High retry count may cause delays.")
			if self.retry_delay and self.retry_delay < 0:
				frappe.throw("Retry Delay cannot be negative")

	def validate_search_limits(self):
		"""Validate search result limits"""
		if self.max_search_limit and self.default_search_limit:
			if self.default_search_limit > self.max_search_limit:
				frappe.throw("Default Search Limit cannot exceed Max Search Limit")


@frappe.whitelist()
def get_etims_settings():
	"""Get eTIMS settings with defaults"""
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
	}

	try:
		settings = frappe.get_single("eTIMS Settings")
	except Exception:
		# Return defaults if the Single record has not been saved yet
		return _defaults

	return {
		"default_sar_type_sales": settings.default_sar_type_sales or "11",
		"default_sar_type_purchase": settings.default_sar_type_purchase or "02",
		"default_sar_type_stock_entry": settings.default_sar_type_stock_entry or "06",
		"api_timeout": settings.api_timeout or 30,
		"production_api_url": settings.production_api_url or "https://etims-api.kra.go.ke/etims-api/",
		"sandbox_api_url": settings.sandbox_api_url or "https://etims-api-sbx.kra.go.ke/etims-api/",
		"enable_retry_logic": settings.enable_retry_logic if settings.enable_retry_logic is not None else 1,
		"max_retry_attempts": settings.max_retry_attempts or 3,
		"retry_delay": settings.retry_delay or 2,
		"default_search_limit": settings.default_search_limit or 100,
		"max_search_limit": settings.max_search_limit or 1000,
		"enable_error_logging": settings.enable_error_logging if settings.enable_error_logging is not None else 1,
		"enable_auto_sync": settings.enable_auto_sync if settings.enable_auto_sync is not None else 1,
		"enable_queue": settings.enable_queue if hasattr(settings, "enable_queue") and settings.enable_queue is not None else 1,
		"queue_max_retries": settings.queue_max_retries if hasattr(settings, "queue_max_retries") else 10,
		"queue_retry_interval": settings.queue_retry_interval if hasattr(settings, "queue_retry_interval") else 5,
	}


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

