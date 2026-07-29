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


def before_install():
	"""Run before app installation to set up roles"""
	try:
		create_etims_roles()
		frappe.msgprint("eTIMS roles installed successfully!")
	except Exception as e:
		frappe.msgprint(f"Error installing eTIMS roles: {e!s}")
		raise


if __name__ == "__main__":
	before_install()
