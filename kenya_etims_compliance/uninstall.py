import frappe

APP_NAME = "kenya_etims_compliance"
LINK_FIELDTYPES = ("Link", "Table", "Table MultiSelect")


def before_uninstall():
	"""Remove customizations on other doctypes that point at this app's doctypes.

	Frappe's uninstall drops the app's doctypes and deletes Custom Fields /
	Property Setters tagged with the app's module, but it never touches
	DocType Links (Customize Form > Connections), which have no module field,
	nor untagged Custom Fields. Left behind, these reference doctypes that no
	longer exist and break saving Customize Form / Custom Field on the parent
	doctype ("DocType ... not found", "Options must be a valid DocType").
	"""
	modules = frappe.get_all("Module Def", filters={"app_name": APP_NAME}, pluck="name")
	app_doctypes = frappe.get_all("DocType", filters={"module": ["in", modules]}, pluck="name")
	if not app_doctypes:
		return

	affected = set()

	for link in frappe.get_all(
		"DocType Link",
		filters={"link_doctype": ["in", app_doctypes], "parent": ["not in", app_doctypes]},
		fields=["name", "parent"],
	):
		frappe.db.delete("DocType Link", {"name": link.name})
		affected.add(link.parent)

	for field in frappe.get_all(
		"Custom Field",
		filters={
			"fieldtype": ["in", LINK_FIELDTYPES],
			"options": ["in", app_doctypes],
			"dt": ["not in", app_doctypes],
		},
		fields=["name", "dt"],
	):
		frappe.delete_doc("Custom Field", field.name, ignore_permissions=True, force=True)
		affected.add(field.dt)

	for doctype in affected:
		frappe.clear_cache(doctype=doctype)
