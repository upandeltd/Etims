# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

"""
eTIMS Role Installation — kept for back-compat; the actual role creation is
driven by ``fixtures/role.json`` via ``sync_fixtures`` at the end of ``bench
install`` / ``bench migrate``. Earlier this module pre-created the same seven
roles under ``before_install`` and then ``sync_fixtures`` delete-and-reinserted
them — wiping the descriptions that were just written. The fixture is the
single source of truth now.
"""

import frappe


def create_etims_roles():
	"""Create all eTIMS-specific roles from the role.json fixture data.

	Mirrors the data in ``fixtures/role.json`` for callers that need the
	descriptions locally (e.g. ``bench execute``). ``before_install`` /
	``after_install`` flows should rely on ``sync_fixtures`` instead.
	"""

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
