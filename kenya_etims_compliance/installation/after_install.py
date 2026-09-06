import frappe


def after_install():
	"""Run after app installation to create required single DocType records."""
	create_etims_settings()
	create_kra_tax_templates()


def create_etims_settings():
	"""Create eTIMS Settings single record if it doesn't exist."""
	if not frappe.db.exists("eTIMS Settings"):
		frappe.get_doc({"doctype": "eTIMS Settings"}).insert(ignore_permissions=True)
		frappe.db.commit()


def create_kra_tax_templates():
	"""Create the KRA tax-band Item Tax Templates (codes A-E) for every company.

	Runs on app install so invoices never silently transmit as non-VAT "D" due
	to a missing template. Idempotent: skips a code once any template with that
	custom_code exists (same rule as setup_wizard.step6_create_tax_templates).
	Companies are discovered at install time; a company added later is handled
	by the Setup Wizard step 6, which shares this function's logic.
	"""
	from kenya_etims_compliance.custom_methods.setup_wizard import (
		build_kra_tax_template,
		get_kra_tax_codes,
	)

	companies = frappe.get_all("Company", pluck="name")
	created = 0
	for company in companies:
		for code, info in get_kra_tax_codes().items():
			if frappe.db.exists("Item Tax Template", {"company": company, "custom_code": code}):
				continue
			build_kra_tax_template(company, code, info).insert(ignore_permissions=True)
			created += 1
	if created:
		frappe.db.commit()

