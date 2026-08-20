# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

"""
eTIMS Permissions Helper Module

This module provides permission helper functions for role-based access control
in the Kenya eTIMS Compliance application.
"""

from functools import wraps

import frappe
from frappe import _

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
	# Hold KRA device/user credentials, so deletion is Admin/Manager-only.
	"eTIMS Branch User",
	"eTIMS Branch Information",
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
	etims_roles = [r for r in all_roles if r.startswith("eTIMS")]
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


def is_privileged():
	"""True when the caller outranks the subtractive eTIMS role rules.

	Frappe grants the ``Administrator`` user *every* role on the site, so a
	naive ``is_etims_auditor()`` test matches Administrator and every
	dual-role user. Narrowing rules must therefore skip anyone who holds a
	role that outranks the restriction being applied, otherwise a user gains
	*less* access by being given an extra role.
	"""
	if frappe.session.user == "Administrator":
		return True
	roles = frappe.get_roles()
	return bool({"System Manager", ETIMS_ADMIN, ETIMS_MANAGER} & set(roles))


def has_etims_role(role_name):
	"""Check if current user has specific eTIMS role"""
	return role_name in frappe.get_roles()


def can_modify_doctype(doctype, perm_type="write", doc=None):
	"""Check if user can modify a specific doctype.

	`frappe.has_permission` is the base grant. eTIMS role checks may only
	NARROW the result (auditor read-only; manager-or-admin-only delete on
	critical doctypes). Never widen past what Frappe itself grants.

	Args:
		doctype: DocType name to check
		perm_type: Permission type (read, write, create, delete)
		doc: Optional document instance; forwarded to frappe.has_permission
			for User Permission / share checks.

	Returns:
		bool: True if user has permission
	"""
	# Auditor is read-only — but only when auditor is the caller's highest
	# standing. Administrator holds every role on a Frappe site, so this must
	# never fire for a privileged user (see is_privileged).
	if is_etims_auditor() and perm_type != "read" and not is_privileged():
		return False

	# Only Admin / Manager may delete from the listed critical doctypes.
	if perm_type == "delete" and doctype in CRITICAL_DOCTYPES:
		if not is_etims_admin() and not is_etims_manager():
			return False

	# Delegate the base grant to Frappe — user roles, user permissions, shares.
	return frappe.has_permission(doctype, perm_type, doc=doc)


def can_delete_doctype(doctype, doc=None):
	"""Check if user can delete from doctype.

	Args:
		doctype: DocType name to check
		doc: Optional document instance

	Returns:
		bool: True if user has delete permission
	"""
	return can_modify_doctype(doctype, "delete", doc=doc)


def can_sync_to_etims(doctype, doc=None):
	"""Check if user can sync documents to eTIMS.

	Mirrors the legacy role policy (Admin / Manager / Operator only) but
	USES its `doctype` argument: the base grant comes from
	`frappe.has_permission(doctype, "write", doc=doc)`. A user without
	write permission on the doctype can never sync, regardless of role.

	Args:
		doctype: DocType the sync targets. MUST be a real doctype name —
			passing None is a programming error and will be rejected.
		doc: Optional document instance to scope the check.

	Returns:
		bool: True if user can sync
	"""
	if not doctype or not isinstance(doctype, str):
		frappe.throw(
			_("can_sync_to_etims() requires a doctype name; got {0}").format(repr(doctype)),
			title=_("Internal: permission check missing target"),
		)

	# Base grant: write permission on the target doctype, resolved through
	# can_modify_doctype so the auditor read-only rule composes here too
	# (an auditor must never be able to push data to KRA).
	if not can_modify_doctype(doctype, "write", doc=doc):
		return False

	# Legacy role restriction: clerks cannot trigger syncs even if they
	# somehow hold Frappe write on the doctype. Skipped for privileged
	# callers, who hold every role on a Frappe site.
	if is_privileged():
		return True
	if is_sales_clerk() or is_purchase_clerk() or is_store_keeper():
		return False

	return True


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
					frappe.throw(f"Permission Denied: You do not have {perm_type} permission for {doctype}")

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
	"""Validate that user has access to the document's branch.

	Reads ``is_branch_isolation_enforced()`` to decide whether branch
	scoping is on at all (no-op when disabled). Honours
	``is_cross_branch_allowed()`` so Managers/Admins get the documented
	cross-branch view only when the setting is explicitly on.

	Args:
		doc: Document object with tax_branch_office field

	Throws:
		PermissionError if user doesn't have access to the branch
	"""
	# Imported lazily: settings helpers live in the doctype module to avoid
	# an import cycle (etims_settings imports nothing from us today, but
	# keeping it local also avoids the cost when permissions is loaded
	# purely for a role check that doesn't touch branch logic).
	from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
		is_branch_isolation_enforced,
		is_cross_branch_allowed,
	)

	# Branch isolation off → everyone is allowed across branches.
	if not is_branch_isolation_enforced():
		return

	# Cross-branch explicitly enabled for managers/admins → bypass for them.
	cross_branch = is_cross_branch_allowed() and (
		is_etims_admin() or is_etims_manager() or "System Manager" in frappe.get_roles()
	)
	if (
		frappe.session.user == "Administrator"
		or cross_branch
		or is_etims_admin()
		or is_etims_manager()
	):
		return

	user_branch = frappe.db.get_value(
		"User Permission",
		{"user": frappe.session.user, "allow": "Tax Branch Office", "is_default": 1},
		"for_value",
	)

	# Fallback for single-branch setups: use the only active TIS Device
	if not user_branch:
		devices = frappe.db.get_all(
			"TIS Device Initialization", filters={"active": 1}, fields=["branch_id"], limit=2
		)
		if len(devices) == 1:
			user_branch = devices[0].get("branch_id")

	if not user_branch:
		frappe.throw(
			"Permission Denied: You must be assigned to a Tax Branch Office. "
			"Please contact your administrator."
		)

	# Check if document has a branch field
	if hasattr(doc, "tax_branch_office") and doc.tax_branch_office:
		doc_branch = doc.tax_branch_office

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
	from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
		get_etims_settings,
	)

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
			{"user": frappe.session.user, "allow": "Tax Branch Office", "is_default": 1},
			"for_value",
		),
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
	except (frappe.DoesNotExistError, frappe.ValidationError) as e:
		frappe.log_error(title="eTIMS: Permission check logging failed", message=str(e))
		# Silently fail if logging fails


# Permission check decorators for common operations
def require_etims_role(role_name):
	"""Decorator to require specific eTIMS role"""

	def decorator(func):
		@wraps(func)
		def wrapper(*args, **kwargs):
			if not has_etims_role(role_name):
				frappe.throw(f"Permission Denied: This action requires {role_name} role")
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
				frappe.throw(_("Permission Denied: This action requires eTIMS Manager or Administrator role"))
			return func(*args, **kwargs)

		return wrapper

	return decorator

def require(doctype, ptype="write", doc=None):
	"""Throw ``frappe.PermissionError`` unless the caller has the given perm.

	This is the entry point every state-changing whitelisted endpoint should
	call first. It delegates to ``frappe.has_permission(..., throw=True)``,
	which respects user roles, user permissions, and shares. eTIMS role
	rules (``can_modify_doctype``) only ever narrow that base grant.

	Args:
		doctype: DocType name the action targets.
		ptype: Permission type (read, write, create, delete, submit, cancel,
			amend). Default ``"write"``.
		doc: Optional document instance; forwarded so the framework can
			apply User Permission / share checks against it.

	Returns:
		None on success; raises ``frappe.PermissionError`` otherwise.
	"""
	if not doctype or not isinstance(doctype, str):
		frappe.throw(
			_("require() needs a doctype name; got {0}").format(repr(doctype)),
			frappe.PermissionError,
		)
	# Two-layer check so the eTIMS-narrowed rule still applies, but the base
	# grant is the framework's own permission resolver.
	if not can_modify_doctype(doctype, ptype, doc=doc):
		frappe.throw(
			_("Permission Denied: {0} ({1}) is not permitted for {2}.").format(
				_(ptype), frappe.session.user, _(doctype)
			),
			frappe.PermissionError,
		)
