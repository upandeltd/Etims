# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

"""
eTIMS Role Installation

This script creates eTIMS-specific roles with appropriate permissions
for the Kenya eTIMS Compliance application.
"""

import frappe


def create_etims_roles():
	"""Create all eTIMS-specific roles"""
	
	roles = [
		{
			"doctype": "Role",
			"role_name": "eTIMS Administrator",
			"desk_access": 1,
			"is_custom": 1,
			"description": "Full access to all eTIMS functions and settings management",
			"restrict_to_domain": 0,
		},
		{
			"doctype": "Role",
			"role_name": "eTIMS Manager",
			"desk_access": 1,
			"is_custom": 1,
			"description": "Branch-level oversight with full operations access per branch",
			"restrict_to_domain": 0,
		},
		{
			"doctype": "Role",
			"role_name": "eTIMS Operator",
			"desk_access": 1,
			"is_custom": 1,
			"description": "Day-to-day eTIMS operations - create transactions, view data, no delete",
			"restrict_to_domain": 0,
		},
		{
			"doctype": "Role",
			"role_name": "eTIMS Auditor",
			"desk_access": 0,
			"is_custom": 1,
			"description": "Read-only access for audit and review purposes",
			"restrict_to_domain": 0,
		},
		{
			"doctype": "Role",
			"role_name": "eTIMS Sales Clerk",
			"desk_access": 1,
			"is_custom": 1,
			"description": "Sales Invoice sync and item search operations",
			"restrict_to_domain": 0,
		},
		{
			"doctype": "Role",
			"role_name": "eTIMS Purchase Clerk",
			"desk_access": 1,
			"is_custom": 1,
			"description": "Purchase Invoice sync and item search operations",
			"restrict_to_domain": 0,
		},
		{
			"doctype": "Role",
			"role_name": "eTIMS Store Keeper",
			"desk_access": 1,
			"is_custom": 1,
			"description": "Stock Entry and Stock Release Number management",
			"restrict_to_domain": 0,
		},
	]
	
	created_roles = []
	for role_data in roles:
		if not frappe.db.exists("Role", {"role_name": role_data["role_name"]}):
			role = frappe.get_doc(role_data)
			role.insert()
			created_roles.append(role.role_name)
			frappe.msgprint(f"Created role: {role.role_name}")
		else:
			frappe.msgprint(f"Role already exists: {role_data['role_name']}")
	
	return created_roles


def update_existing_doctype_permissions():
	"""Update existing doctypes with proper eTIMS role permissions"""
	
	# Doctypes that should restrict delete for non-admin roles
	restricted_delete_doctypes = [
		"eTIMS Stock Release Number",
		"eTIMS Sales Receipt",
		"TIS Device Initialization",
		"Tax Branch Office",
		"TIS Communication Key",
		"eTIMS Code Information",
		"eTIMS Settings",
	]
	
	# Remove delete permission from Sales User, Purchase User, Stock User
	standard_roles = ["Sales User", "Purchase User", "Stock User"]
	
	for doctype_name in restricted_delete_doctypes:
		if frappe.db.exists("DocType", doctype_name):
			try:
				doc = frappe.get_doc("DocType", doctype_name)
				if doc.permissions:
					# Update permissions - remove delete from standard roles
					updated = False
					for perm in doc.permissions:
						if perm.get("role") in standard_roles:
							if perm.delete == 1:
								perm.delete = 0
								updated = True
								frappe.msgprint(f"Removed delete permission from {perm.get('role')} for {doctype_name}")
					
					if updated:
						doc.save()
			except Exception as e:
				frappe.msgprint(f"Error updating {doctype_name}: {str(e)}")


def add_etims_role_permissions():
	"""Add eTIMS-specific role permissions to key doctypes"""
	
	# Define permission sets for different role levels
	admin_permissions = {
		"create": 1, "delete": 1, "email": 1, "export": 1,
		"print": 1, "read": 1, "report": 1, "share": 1, "write": 1
	}
	
	manager_permissions = {
		"create": 1, "delete": 1, "email": 1, "export": 1,
		"print": 1, "read": 1, "report": 1, "share": 1, "write": 1
	}
	
	operator_permissions = {
		"create": 1, "delete": 0, "email": 0, "export": 1,
		"print": 1, "read": 1, "report": 1, "share": 1, "write": 1
	}
	
	auditor_permissions = {
		"create": 0, "delete": 0, "email": 0, "export": 1,
		"print": 1, "read": 1, "report": 1, "share": 0, "write": 0
	}
	
	clerk_permissions = {
		"create": 1, "delete": 0, "email": 1, "export": 1,
		"print": 1, "read": 1, "report": 1, "share": 1, "write": 1
	}
	
	store_keeper_permissions = {
		"create": 1, "delete": 0, "email": 1, "export": 1,
		"print": 1, "read": 1, "report": 1, "share": 1, "write": 1
	}
	
	# Define which roles get which permissions per doctype
	doctype_permissions = {
		"eTIMS Stock Release Number": {
			"eTIMS Administrator": admin_permissions,
			"eTIMS Manager": manager_permissions,
			"eTIMS Store Keeper": store_keeper_permissions,
			"eTIMS Auditor": auditor_permissions,
		},
		"eTIMS Sales Receipt": {
			"eTIMS Administrator": admin_permissions,
			"eTIMS Manager": manager_permissions,
			"eTIMS Sales Clerk": clerk_permissions,
			"eTIMS Auditor": auditor_permissions,
		},
		"eTIMS Settings": {
			"eTIMS Administrator": admin_permissions,
			"eTIMS Auditor": auditor_permissions,
		},
		"TIS Device Initialization": {
			"eTIMS Administrator": admin_permissions,
			"eTIMS Manager": manager_permissions,
			"eTIMS Auditor": auditor_permissions,
		},
		"Tax Branch Office": {
			"eTIMS Administrator": admin_permissions,
			"eTIMS Manager": manager_permissions,
			"eTIMS Auditor": auditor_permissions,
		},
		"TIS Communication Key": {
			"eTIMS Administrator": admin_permissions,
			"eTIMS Auditor": auditor_permissions,
		},
		"eTIMS Code Information": {
			"eTIMS Administrator": admin_permissions,
			"eTIMS Manager": manager_permissions,
			"eTIMS Operator": operator_permissions,
			"eTIMS Sales Clerk": clerk_permissions,
			"eTIMS Purchase Clerk": clerk_permissions,
			"eTIMS Store Keeper": clerk_permissions,
			"eTIMS Auditor": auditor_permissions,
		},
		"eTIMS Notice": {
			"eTIMS Administrator": admin_permissions,
			"eTIMS Manager": manager_permissions,
			"eTIMS Auditor": auditor_permissions,
		},
		"eTIMS Customer": {
			"eTIMS Administrator": admin_permissions,
			"eTIMS Manager": manager_permissions,
			"eTIMS Sales Clerk": clerk_permissions,
			"eTIMS Auditor": auditor_permissions,
		},
		"Error Logging": {
			"eTIMS Administrator": admin_permissions,
			"eTIMS Manager": manager_permissions,
			"eTIMS Auditor": auditor_permissions,
		},
	}
	
	# Update doctypes with new role permissions
	for doctype_name, role_perms in doctype_permissions.items():
		if not frappe.db.exists("DocType", doctype_name):
			continue
			
		try:
			doc = frappe.get_doc("DocType", doctype_name)
			
			# Get existing permissions to avoid duplicates
			existing_roles = {p.get("role") for p in doc.permissions} if doc.permissions else set()
			
			for role_name, permissions in role_perms.items():
				# Check if role permission already exists
				if role_name not in existing_roles:
					doc.append("permissions", {
						**permissions,
						"role": role_name,
					})
			
			doc.save()
			frappe.msgprint(f"Updated permissions for {doctype_name}")
			
		except Exception as e:
			frappe.msgprint(f"Error updating {doctype_name}: {str(e)}")


def before_install():
	"""Run before app installation to set up roles"""
	try:
		create_etims_roles()
		update_existing_doctype_permissions()
		add_etims_role_permissions()
		frappe.msgprint("eTIMS roles installed successfully!")
	except Exception as e:
		frappe.msgprint(f"Error installing eTIMS roles: {str(e)}")
		raise


if __name__ == "__main__":
	before_install()
