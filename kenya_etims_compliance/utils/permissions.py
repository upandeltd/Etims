# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

"""
eTIMS Permissions Helper Module

This module provides permission helper functions for role-based access control
in the Kenya eTIMS Compliance application.
"""

import frappe
from functools import wraps


# Role definitions
ETIMS_ADMIN = "eTIMS Administrator"
ETIMS_MANAGER = "eTIMS Manager"
ETIMS_OPERATOR = "eTIMS Operator"
ETIMS_AUDITOR = "eTIMS Auditor"
ETIMS_SALES_CLERK = "eTIMS Sales Clerk"
ETIMS_PURCHASE_CLERK = "eTIMS Purchase Clerk"
ETIMS_STORE_KEEPER = "eTIMS Store Keeper"

# Permission levels
PERM_ADMIN = "admin"
PERM_MANAGER = "manager"
PERM_OPERATOR = "operator"
PERM_AUDITOR = "auditor"

# Critical doctypes that require special permissions
CRITICAL_DOCTYPES = [
	"eTIMS Stock Release Number",
	"eTIMS Sales Receipt",
	"TIS Device Initialization",
	"Tax Branch Office",
	"TIS Communication Key",
	"eTIMS Settings",
]

# Doctypes that can be modified by operators
OPERATOR_WRITE_DOCTYPES = [
	"eTIMS Code Information",
	"eTIMS Notice",
	"eTIMS Customer",
]

# Clerk-specific doctypes
SALES_CLERK_DOCTYPES = [
	"eTIMS Sales Receipt",
	"Sales Invoice",
	"Item",
]

PURCHASE_CLERK_DOCTYPES = [
	"Purchase Invoice",
	"Item",
]

STORE_KEEPER_DOCTYPES = [
	"eTIMS Stock Release Number",
	"Stock Entry",
]


def get_user_etims_roles():
	"""Get list of eTIMS roles for current user"""
	all_roles = frappe.get_roles()
	etims_roles = [
		r for r in all_roles 
		if r.startswith("eTIMS")
	]
	return etims_roles


def is_etims_admin():
	"""Check if current user is eTIMS Administrator"""
	return ETIMS_ADMIN in frappe.get_roles()


def is_etims_manager():
	"""Check if current user is eTIMS Manager"""
	return ETIMS_MANAGER in frappe.get_roles()


def is_etims_operator():
	"""Check if current user is eTIMS Operator"""
	return ETIMS_OPERATOR in frappe.get_roles()


def is_etims_auditor():
	"""Check if current user is eTIMS Auditor"""
	return ETIMS_AUDITOR in frappe.get_roles()


def is_etims_clerk():
	"""Check if current user is any eTIMS Clerk role"""
	clerk_roles = [ETIMS_SALES_CLERK, ETIMS_PURCHASE_CLERK]
	user_roles = frappe.get_roles()
	return any(role in user_roles for role in clerk_roles)


def is_sales_clerk():
	"""Check if current user is eTIMS Sales Clerk"""
	return ETIMS_SALES_CLERK in frappe.get_roles()


def is_purchase_clerk():
	"""Check if current user is eTIMS Purchase Clerk"""
	return ETIMS_PURCHASE_CLERK in frappe.get_roles()


def is_store_keeper():
	"""Check if current user is eTIMS Store Keeper"""
	return ETIMS_STORE_KEEPER in frappe.get_roles()


def has_etims_role(role_name):
	"""Check if current user has specific eTIMS role"""
	return role_name in frappe.get_roles()


def can_modify_doctype(doctype, perm_type="write"):
	"""Check if user can modify a specific doctype
	
	Args:
		doctype: Doctype name to check
		perm_type: Permission type (read, write, create, delete)
	
	Returns:
		bool: True if user has permission
	"""
	# Administrators can do everything
	if is_etims_admin():
		return True
	
	# Auditors can only read
	if is_etims_auditor():
		return perm_type == "read"
	
	# Check doctype-specific permissions
	if perm_type == "delete":
		# Only Admin and Manager can delete from critical doctypes
		if doctype in CRITICAL_DOCTYPES:
			return is_etims_manager()
	
	# Operators can write to operator doctypes
	if is_etims_operator() and perm_type in ["read", "write", "create"]:
		if doctype in OPERATOR_WRITE_DOCTYPES:
			return True
	
	# Clerks have limited access
	if is_sales_clerk() and doctype in SALES_CLERK_DOCTYPES:
		if perm_type != "delete":
			return True
	
	if is_purchase_clerk() and doctype in PURCHASE_CLERK_DOCTYPES:
		if perm_type != "delete":
			return True
	
	if is_store_keeper() and doctype in STORE_KEEPER_DOCTYPES:
		if perm_type != "delete":
			return True
	
	# Managers have broad access
	if is_etims_manager():
		return True
	
	# Default: check standard Frappe permissions
	return frappe.has_permission(doctype, perm_type)


def can_delete_doctype(doctype):
	"""Check if user can delete from doctype
	
	Args:
		doctype: Doctype name to check
	
	Returns:
		bool: True if user has delete permission
	"""
	return can_modify_doctype(doctype, "delete")


def can_sync_to_etims(doctype):
	"""Check if user can sync documents to eTIMS
	
	Only Admin, Manager, and Operators can sync.
	"""
	if is_etims_admin():
		return True
	
	if is_etims_manager():
		return True
	
	if is_etims_operator():
		return True
	
	# Clerks cannot sync
	return False


def can_view_sensitive_fields(doctype):
	"""Check if user can view sensitive fields (communication keys, etc.)
	
	Only Admin and Manager can view sensitive fields.
	"""
	if is_etims_admin():
		return True
	
	if is_etims_manager():
		return True
	
	return False


def can_manage_settings():
	"""Check if user can manage eTIMS Settings
	
	Only Administrators can manage settings.
	"""
	return is_etims_admin()


def get_user_permission_level():
	"""Get the highest permission level for current user
	
	Returns:
		str: Permission level (admin, manager, operator, auditor, clerk, none)
	"""
	if is_etims_admin():
		return PERM_ADMIN
	
	if is_etims_manager():
		return PERM_MANAGER
	
	if is_etims_operator():
		return PERM_OPERATOR
	
	if is_etims_auditor():
		return PERM_AUDITOR
	
	if is_etims_clerk():
		return "clerk"
	
	return "none"


def check_permission(perm_type="read", doctype=None):
	"""Decorator to check permission before executing function
	
	Args:
		perm_type: Permission type required (default: "read")
		doctype: Doctype to check (optional)
	
	Example:
		@check_permission("write", "eTIMS Settings")
		def update_settings():
			# This function will only run if user has write permission
	"""
	def decorator(func):
		@wraps(func)
		def wrapper(*args, **kwargs):
			# Check doctype permission if specified
			if doctype:
				if not can_modify_doctype(doctype, perm_type):
					frappe.throw(
						f"Permission Denied: You do not have {perm_type} "
						f"permission for {doctype}"
					)
			
			# Check settings permission
			elif perm_type in ["write", "create", "delete"]:
				if not can_modify_doctype("eTIMS Settings", perm_type):
					# Settings require admin permission
					if not is_etims_admin():
						frappe.throw(
							f"Permission Denied: You do not have {perm_type} "
							f"permission. This action requires eTIMS Administrator role."
						)
			
			return func(*args, **kwargs)
		return wrapper
	return decorator


def validate_branch_access(doc):
	"""Validate that user has access to the document's branch
	
	Args:
		doc: Document object with tax_branch_office field
	
	Throws:
		PermissionError if user doesn't have access to the branch
	"""
	user_branch = frappe.db.get_value(
		"User Permission", 
		{
			"user": frappe.session.user,
			"allow": "Tax Branch Office",
			"is_default": 1
		},
		"for_value"
	)
	
	if not user_branch:
		frappe.throw(
			"Permission Denied: You must be assigned to a Tax Branch Office. "
			"Please contact your administrator."
	)
	
	# Check if document has a branch field
	if hasattr(doc, "tax_branch_office") and doc.tax_branch_office:
		doc_branch = doc.tax_branch_office
		
		# Admin and Manager can access all branches (for oversight)
		if is_etims_admin() or is_etims_manager():
			return
		
		# Other roles can only access their assigned branch
		if doc_branch != user_branch:
			frappe.throw(
				f"Permission Denied: You do not have access to branch {doc_branch}. "
				f"Your assigned branch is {user_branch}."
			)


def log_permission_check(doctype, action, result):
	"""Log permission check for audit trail
	
	Args:
		doctype: Doctype being accessed
		action: Action being performed (read, write, delete, etc.)
		result: Whether permission was granted
	"""
	from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import get_etims_settings
	
	settings = get_etims_settings()
	if not settings.get("enable_error_logging", 1):
		return
	
	log_entry = {
		"user": frappe.session.user,
		"doctype": doctype,
		"action": action,
		"result": "Granted" if result else "Denied",
		"branch": frappe.db.get_value(
			"User Permission", 
			{
				"user": frappe.session.user,
				"allow": "Tax Branch Office",
				"is_default": 1
			},
			"for_value"
		)
	}
	
	# Log to Error Logging doctype
	try:
		log_doc = frappe.new_doc("Error Logging")
		log_doc.title = f"Permission Check: {action} on {doctype}"
		log_doc.description = (
			f"User: {log_entry['user']}\n"
			f"Doctype: {log_entry['doctype']}\n"
			f"Action: {log_entry['action']}\n"
			f"Result: {log_entry['result']}\n"
			f"Branch: {log_entry.get('branch', 'N/A')}"
		)
		log_doc.insert()
	except Exception:
		pass  # Silently fail if logging fails


# Permission check decorators for common operations
def require_etims_role(role_name):
	"""Decorator to require specific eTIMS role"""
	def decorator(func):
		@wraps(func)
		def wrapper(*args, **kwargs):
			if not has_etims_role(role_name):
				frappe.throw(
					f"Permission Denied: This action requires {role_name} role"
				)
			return func(*args, **kwargs)
		return wrapper
	return decorator


def require_admin():
	"""Decorator to require eTIMS Administrator role"""
	return require_etims_role(ETIMS_ADMIN)


def require_manager():
	"""Decorator to require eTIMS Manager or Administrator"""
	def decorator(func):
		@wraps(func)
		def wrapper(*args, **kwargs):
			if not (is_etims_admin() or is_etims_manager()):
				frappe.throw(
					f"Permission Denied: This action requires eTIMS Manager or Administrator role"
				)
			return func(*args, **kwargs)
		return wrapper
	return decorator


def require_sync_permission():
	"""Decorator to require permission to sync to eTIMS"""
	def decorator(func):
		@wraps(func)
		def wrapper(*args, **kwargs):
			if not can_sync_to_etims(None):
				frappe.throw(
					"Permission Denied: You do not have permission to sync to eTIMS. "
					"This action requires eTIMS Administrator, Manager, or Operator role."
				)
			return func(*args, **kwargs)
		return wrapper
	return decorator
