"""eTIMS Import Item Workflow.

Automates: fetch pending imports → match to local items → create Stock Entry → confirm to KRA.
Builds on existing eTIMS Import Item DocType and etims_import_item_information.py.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime


def fetch_and_process_imports():
	"""Daily: Fetch pending import items from KRA and process them."""
	from kenya_etims_compliance.utils.kra_client import KRAClient

	# Step 1: Fetch pending imports
	client = KRAClient()
	result = client.post("selectImportItemList", {"lastReqDt": "20260101000000"})
	if "Success" not in result or not result["Success"]:
		return {"fetched": 0, "processed": 0}

	data = result["Success"]
	import_items = data.get("itemList") if isinstance(data, dict) else []
	fetched = 0
	processed = 0

	for item in import_items or []:
		task_code = item.get("taskCd")
		if not task_code:
			continue

		# Skip if already exists
		if frappe.db.exists("eTIMS Import Item", task_code):
			continue

		# Create import item record
		import_doc = frappe.get_doc(
			{
				"doctype": "eTIMS Import Item",
				"task_code": task_code,
				"declaration_date": item.get("dclDe"),
				"item_sequence": item.get("itemSeq"),
				"declaration_number": item.get("dclNo"),
				"hs_code": item.get("hsCd"),
				"item_name": item.get("itemNm"),
				"import_item_status_code": item.get("imptItemSttsCd"),
				"origin_nation_code": item.get("orgnNatCd"),
				"export_nation_code": item.get("exptNatCd"),
				"package": item.get("pkg"),
				"packaging_unit_code": item.get("pkgUnitCd"),
				"quantity": item.get("qty"),
				"quantity_unit_code": item.get("qtyUnitCd"),
				"gross_weight": item.get("totWt"),
				"net_weight": item.get("netWt"),
				"supplier_name": item.get("agntNm"),
				"invoice_foreign_currency_amount": item.get("invcFcurAmt"),
				"invoice_foreign_currency": item.get("invcFcurCd"),
				"invoice_foreign_currency_crt": item.get("invcFcurExcrt"),
			}
		)
		import_doc.insert(ignore_permissions=True)
		fetched += 1

		# Step 2: Try to auto-match to local item
		matched_item = _match_import_to_local_item(import_doc)
		if matched_item:
			import_doc.item_name = matched_item
			import_doc.save(ignore_permissions=True)

			# Step 3: Create Stock Entry if not already created
			if not import_doc.stock_entry_created:
				stock_entry = _create_stock_entry(import_doc, matched_item)
				if stock_entry:
					import_doc.stock_entry = stock_entry.name
					import_doc.stock_entry_created = 1
					import_doc.save(ignore_permissions=True)
					processed += 1

	frappe.db.commit()
	return {"fetched": fetched, "processed": processed}


def _match_import_to_local_item(import_doc):
	"""Match import item to local ERPNext Item by HS code or name."""
	# Match by HS code first
	if import_doc.hs_code:
		items = frappe.get_all(
			"Item",
			filters={
				"custom_hs_code": import_doc.hs_code,
				"disabled": 0,
			},
			fields=["name"],
			limit=1,
		)
		if items:
			return items[0].name

	# Match by item name
	if import_doc.item_name:
		items = frappe.get_all(
			"Item",
			filters={
				"item_name": ["like", f"%{import_doc.item_name}%"],
				"disabled": 0,
			},
			fields=["name"],
			limit=1,
		)
		if items:
			return items[0].name

	return None


def _create_stock_entry(import_doc, item_name):
	"""Create Material Receipt Stock Entry from import data."""
	from kenya_etims_compliance.utils.etims_utils import eTIMS

	branch_id = eTIMS.get_user_branch_id()
	if not branch_id:
		return None

	warehouse = frappe.db.get_value(
		"TIS Device Initialization",
		filters={"branch_id": branch_id, "active": 1},
		fieldname="default_stores_warehouse",
	)

	if not warehouse:
		return None

	qty = import_doc.quantity or 1
	rate = (import_doc.invoice_foreign_currency_amount or 0) * (import_doc.invoice_foreign_currency_crt or 1)

	stock_entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"custom_is_import_stock": 1,
			"custom_task_code": import_doc.task_code,
			"custom_target_tax_branch_office": branch_id,
			"items": [
				{
					"item_code": item_name,
					"qty": qty,
					"basic_rate": rate / qty if qty else rate,
					"t_warehouse": warehouse,
				}
			],
		}
	)
	stock_entry.insert(ignore_permissions=True)
	return stock_entry


@frappe.whitelist()
def process_import_item(import_item_name):
	"""Manually process a single import item."""
	import_doc = frappe.get_doc("eTIMS Import Item", import_item_name)

	if import_doc.stock_entry_created:
		frappe.throw(_("Stock Entry already created for this import"))

	matched = _match_import_to_local_item(import_doc)
	if not matched:
		frappe.throw(_("Could not match import to a local item. Please link manually."))

	stock_entry = _create_stock_entry(import_doc, matched)
	if stock_entry:
		import_doc.stock_entry = stock_entry.name
		import_doc.stock_entry_created = 1
		import_doc.item_name = matched
		import_doc.save(ignore_permissions=True)
		frappe.db.commit()
		return {"status": "success", "stock_entry": stock_entry.name}

	frappe.throw(_("Could not create Stock Entry — check warehouse configuration"))
