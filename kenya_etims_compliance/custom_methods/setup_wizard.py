"""eTIMS Setup Wizard — guided first-time configuration.

8 steps:
1. Select company, confirm KRA PIN
2. Choose Sandbox/Production, test connectivity
3. Enter device serial number, initialize device
4. Create Tax Branch Office, assign to current user
5. Fetch item classification codes from KRA
6. Auto-create Item Tax Templates A-E
7. Bulk register items to eTIMS
8. Verify setup with test round-trip

Each step is a separate whitelisted method called from the client wizard page.
"""

import re

import frappe
import requests
from frappe import _
from frappe.utils import now_datetime


@frappe.whitelist()
def get_setup_status():
	"""Check what's already configured — wizard skips completed steps."""
	if "System Manager" not in frappe.get_roles() and "eTIMS Administrator" not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	status = {
		"company": None,
		"pin": None,
		"device_initialized": False,
		"branch_configured": False,
		"classifications_fetched": False,
		"tax_templates_exist": False,
		"items_registered": 0,
		"items_total": 0,
	}

	# Check company with Tax ID
	companies = frappe.get_all(
		"Company", filters={"tax_id": ["is", "set"]}, fields=["name", "tax_id"], limit=1
	)
	if companies:
		status["company"] = companies[0].name
		status["pin"] = companies[0].tax_id

	# Check device initialization
	device_names = frappe.get_all(
		"TIS Device Initialization", filters={"active": 1}, pluck="name", limit=1
	)
	if device_names:
		device = frappe.get_doc("TIS Device Initialization", device_names[0])
		if device.get_password("communication_key", raise_exception=False):
			status["device_initialized"] = True

	# Check branch
	branches = frappe.get_all("Tax Branch Office", limit=1)
	if branches:
		status["branch_configured"] = True

	# Check classifications
	classifications = frappe.db.count("eTIMS Item Classification")
	status["classifications_fetched"] = classifications > 0

	# Check tax templates
	templates = frappe.get_all(
		"Item Tax Template", filters={"custom_code": ["in", ["A", "B", "C", "D", "E"]]}, limit=5
	)
	status["tax_templates_exist"] = len(templates) >= 5

	# Check items
	status["items_total"] = frappe.db.count("Item", filters={"disabled": 0})
	status["items_registered"] = frappe.db.count(
		"Item",
		filters={
			"disabled": 0,
			"custom_registered_in_tims": 1,
		},
	)

	return status


@frappe.whitelist()
def step1_validate_company(company):
	"""Step 1: Validate company has a KRA PIN."""
	if "System Manager" not in frappe.get_roles() and "eTIMS Administrator" not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	tax_id = frappe.db.get_value("Company", company, "tax_id")
	if not tax_id:
		return {"status": "error", "message": "Company has no Tax ID (KRA PIN) configured"}

	if not re.match(r"^[A-Z]\d{9}$", tax_id):
		return {
			"status": "warning",
			"message": f"PIN format may be incorrect: {tax_id}. Expected: letter + 9 digits",
		}

	return {"status": "success", "pin": tax_id, "company": company}


@frappe.whitelist()
def step2_test_connectivity(api_mode="Sandbox"):
	"""Step 2: Test connectivity to KRA eTIMS API."""
	if "System Manager" not in frappe.get_roles() and "eTIMS Administrator" not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
		get_api_url,
	)

	# Probe the REQUESTED api_mode directly. Going through KRAClient().post()
	# would resolve the URL from TIS Device Initialization.api_mode and ignore
	# the operator's choice — so step 2 would report "Connected to Production"
	# after actually probing Sandbox (or vice versa). Bypass KRAClient here:
	# this is a connectivity probe, not a real KRA call that needs the audit
	# trail or circuit breaker.
	url = get_api_url(api_mode).rstrip("/") + "/selectCodeList"
	payload = {"lastReqDt": "20200101000000"}
	try:
		resp = requests.post(
			url,
			json=payload,
			headers={"Content-Type": "application/json"},
			timeout=10,
		)
	except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
		return {"status": "error", "message": str(e)[:200]}
	# Any HTTP response — success, app error, or 4xx — means we reached the
	# requested endpoint. 5xx is "we got there but their backend is down".
	if resp.status_code >= 500:
		return {
			"status": "error",
			"message": f"KRA {api_mode} backend returned HTTP {resp.status_code}",
		}
	return {"status": "success", "message": f"Connected to {api_mode} API", "url": url}


@frappe.whitelist()
def step3_initialize_device(company, branch_id, serial_number, api_mode="Sandbox"):
	"""Step 3: Initialize TIS device with KRA."""
	if "System Manager" not in frappe.get_roles() and "eTIMS Administrator" not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	# Create Tax Branch Office if not exists
	if not frappe.db.exists("Tax Branch Office", branch_id):
		frappe.get_doc(
			{
				"doctype": "Tax Branch Office",
				"branch_id": branch_id,
			}
		).insert(ignore_permissions=True)

	# Create or update TIS Device Initialization
	existing = frappe.db.exists("TIS Device Initialization", {"branch_id": branch_id})
	if existing:
		doc = frappe.get_doc("TIS Device Initialization", existing)
	else:
		doc = frappe.new_doc("TIS Device Initialization")

	doc.company = company
	doc.pin = frappe.db.get_value("Company", company, "tax_id")
	doc.branch_id = branch_id
	doc.device_serial_number = serial_number
	doc.api_mode = api_mode
	doc.active = 1

	if not existing:
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)

	# Initialize with KRA
	result = doc.deviceVerificationReq()
	# Intentional checkpoint: persist the (expensive) KRA device initialization
	# before assigning the branch, so a later failure does not force re-running
	# the device verification.
	frappe.db.commit()

	if "Success" in result:
		# Assign branch to current user
		_assign_branch_to_user(branch_id)
		return {"status": "success", "message": result["Success"], "device": doc.name}
	else:
		return {"status": "error", "message": result.get("Error", "Device initialization failed")}


@frappe.whitelist()
def step4_assign_branch(branch_id):
	"""Step 4: Assign Tax Branch Office to current user."""
	if "System Manager" not in frappe.get_roles() and "eTIMS Administrator" not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	_assign_branch_to_user(branch_id)
	return {"status": "success", "message": f"Branch {branch_id} assigned to {frappe.session.user}"}


@frappe.whitelist()
def step5_fetch_classifications():
	"""Step 5: Fetch item classification codes from KRA."""
	if "System Manager" not in frappe.get_roles() and "eTIMS Administrator" not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	from kenya_etims_compliance.utils.kra_client import KRAClient

	client = KRAClient()
	result = client.post("selectItemClsList", {"lastReqDt": "20200101000000"})

	if result.get("Success"):
		data = result["Success"]
		cls_list = data.get("itemClsList") if isinstance(data, dict) else []

		created = 0
		for cls in cls_list or []:
			code = cls.get("itemClsCd")
			if code and not frappe.db.exists("eTIMS Item Classification", code):
				frappe.get_doc(
					{
						"doctype": "eTIMS Item Classification",
						"item_class_code": code,
						"item_class_name": cls.get("itemClsNm", ""),
						"item_class_level": cls.get("itemClsLvl"),
						"taxation_type_code": cls.get("taxTyCd", ""),
						"usedunused": cls.get("useYn", "Y"),
					}
				).insert(ignore_permissions=True)
				created += 1

		# No explicit commit: the whitelisted request auto-commits on success and
		# rolls back the whole step on failure (atomic — no partial classifications).
		return {
			"status": "success",
			"created": created,
			"total": frappe.db.count("eTIMS Item Classification"),
		}
	else:
		return {"status": "error", "message": result.get("Error", "Failed to fetch classifications")}


KRA_TAX_CODES = {
	"A": {"name": "Exempt", "rate": 0},
	"B": {"name": "16.00%", "rate": 16},
	"C": {"name": "0%", "rate": 0},
	"D": {"name": "Non-VAT", "rate": 0},
	"E": {"name": "8%", "rate": 8},
}


def get_kra_tax_codes():
	"""KRA tax type codes A-E with display names and default rates.

	Per the KRA TIS for OSCU/VSCU spec (receipt tax summary: Exempt, VAT at
	16%, Zero rated, Non Vatable, VAT at 8%) and confirmed against a live
	KRA-compliant company's Chart of Accounts import (Tax Master Data:
	VAT-A-Exempt, VAT-B-16.00%, VAT-C-0%, VAT-D-Non-VAT, VAT-E-8%) — NOT the
	app's own prior guess. Do not reorder without re-checking both sources:
	A and B are not "A=standard rate", they are Exempt/16% respectively.
	"""
	return KRA_TAX_CODES


def build_kra_tax_template(company, code, info):
	"""Build a KRA-band Item Tax Template doc (code + name + tax row).

	The tax row's account MUST be specific to this KRA band — bands A-E have
	different accounting treatment, so the lookup matches ``Account.custom_tax_code``
	to this band's code, never "any Tax-type account for the company" — that
	would silently commingle unrelated bands' collections into one GL bucket.
	If no such account exists yet, one is auto-created (see
	``_get_or_create_band_account``). A company with no Duties and Taxes
	group to nest under gets a template with no tax row (a valid, inert
	Item Tax Template — ``Item Tax Template.validate()`` doesn't require
	one) and a logged warning, rather than posting to the wrong account.
	"""
	account_name = _get_or_create_band_account(company, code, info)
	template = frappe.get_doc(
		{
			"doctype": "Item Tax Template",
			"title": f"KRA {code} - {info['name']}",
			"company": company,
			"custom_code": code,
			"custom_code_name": info["name"],
		}
	)
	if account_name:
		template.append("taxes", {"tax_type": account_name, "tax_rate": info["rate"]})
	else:
		frappe.log_error(
			title="eTIMS: KRA tax band unmapped",
			message=(
				f"No Duties and Taxes group account found for company {company!r} to create "
				f"the KRA band {code} - {info['name']} account under. Created "
				f"'KRA {code} - {info['name']}' without a tax row; postings for this band "
				f"won't hit any GL account until one is created and tagged custom_tax_code={code!r}."
			),
		)
	return template


def _get_or_create_band_account(company, code, info):
	"""Find the company's GL account tagged for this KRA band, or create one.

	New accounts are named ``VAT-{code}-{name}`` (e.g. ``VAT-A-Exempt``) —
	the same convention used by other KRA-compliant companies' Chart of
	Accounts (see Tax Master Data reference import) — nested under the
	company's Tax-type group account (standard CoA: "Duties and Taxes").
	Returns None if the company has no such group to nest under.

	Always (re)writes the account's own ``tax_rate`` to match this band.
	``Item Tax Template Detail.tax_rate`` has a ``fetch_from: tax_type.tax_rate``
	/ ``fetch_if_empty`` property setter, and Frappe treats ``0`` as empty for
	that check — so every 0%-rate band (Exempt, Zero Rated, Non-VAT) refetches
	from the Account on each save. Leaving the Account's rate stale (e.g. from
	a reused pre-existing account) silently overwrites the template row the
	next time it's saved; keeping the Account itself correct makes that fetch
	a no-op instead of a corruption.
	"""
	existing = frappe.get_all(
		"Account",
		filters={"company": company, "custom_tax_code": code, "is_group": 0},
		fields=["name"],
		limit=1,
	)
	if existing:
		frappe.db.set_value("Account", existing[0].name, "tax_rate", info["rate"])
		return existing[0].name

	parent = frappe.get_all(
		"Account",
		filters={"company": company, "account_type": "Tax", "is_group": 1},
		fields=["name"],
		order_by="lft",
		limit=1,
	)
	if not parent:
		return None

	account = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": f"VAT-{code}-{info['name']}",
			"parent_account": parent[0].name,
			"company": company,
			"account_type": "Tax",
			"custom_tax_code": code,
			"tax_rate": info["rate"],
		}
	)
	account.insert(ignore_permissions=True)
	return account.name


@frappe.whitelist()
def step6_create_tax_templates(company):
	"""Step 6: Auto-create Item Tax Templates for KRA tax codes A-E."""
	if "System Manager" not in frappe.get_roles() and "eTIMS Administrator" not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	created = 0
	for code, info in KRA_TAX_CODES.items():
		if frappe.db.exists("Item Tax Template", {"company": company, "custom_code": code}):
			continue
		build_kra_tax_template(company, code, info).insert(ignore_permissions=True)
		created += 1

	# No explicit commit: the request auto-commits on success and rolls back the
	# whole step on failure (atomic — no partial tax templates).
	return {"status": "success", "created": created}


@frappe.whitelist()
def step7_bulk_register_items(limit=50):
	"""Step 7: Register unregistered items to eTIMS in batch."""
	if "System Manager" not in frappe.get_roles() and "eTIMS Administrator" not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	from kenya_etims_compliance.custom_methods.bulk_operations import bulk_register_items

	items = frappe.get_all(
		"Item",
		filters={
			"custom_registered_in_tims": 0,
			"custom_item_classification_code": ["is", "set"],
			"disabled": 0,
		},
		fields=["name"],
		limit=limit,
	)

	item_names = [i.name for i in items]
	if not item_names:
		return {"status": "success", "message": "All items already registered", "total": 0}

	result = bulk_register_items(item_names)
	return {"status": "success", **result}


@frappe.whitelist()
def step8_verify_setup():
	"""Step 8: Verify everything is configured correctly."""
	if "System Manager" not in frappe.get_roles() and "eTIMS Administrator" not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	checks = []

	# Check 1: Company PIN
	companies = frappe.get_all("Company", filters={"tax_id": ["is", "set"]}, limit=1)
	checks.append({"check": "Company KRA PIN", "passed": bool(companies)})

	# Check 2: Active device
	devices = frappe.get_all(
		"TIS Device Initialization", filters={"active": 1, "communication_key": ["is", "set"]}, limit=1
	)
	checks.append({"check": "Device Initialized", "passed": bool(devices)})

	# Check 3: Branch configured
	branches = frappe.get_all("Tax Branch Office", limit=1)
	checks.append({"check": "Branch Configured", "passed": bool(branches)})

	# Check 4: User has branch permission
	from kenya_etims_compliance.utils.etims_utils import eTIMS

	branch_id = eTIMS.get_user_branch_id()
	checks.append({"check": "User Branch Permission", "passed": bool(branch_id)})

	# Check 5: Classifications loaded
	cls_count = frappe.db.count("eTIMS Item Classification")
	checks.append({"check": f"Item Classifications ({cls_count})", "passed": cls_count > 0})

	# Check 6: Tax templates exist
	templates = frappe.get_all(
		"Item Tax Template", filters={"custom_code": ["in", ["A", "B", "C", "D", "E"]]}, limit=5
	)
	checks.append({"check": f"Tax Templates ({len(templates)}/5)", "passed": len(templates) >= 5})

	# Check 7: Scheduler running
	checks.append(
		{"check": "Scheduler Active", "passed": frappe.utils.scheduler.is_scheduler_inactive() is False}
	)

	all_passed = all(c["passed"] for c in checks)
	return {
		"status": "success" if all_passed else "warning",
		"checks": checks,
		"all_passed": all_passed,
	}


def _assign_branch_to_user(branch_id):
	"""Assign Tax Branch Office to current user via User Permission."""
	user = frappe.session.user
	existing = frappe.db.exists(
		"User Permission",
		{
			"user": user,
			"allow": "Tax Branch Office",
			"for_value": branch_id,
		},
	)
	if not existing:
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "Tax Branch Office",
				"for_value": branch_id,
				"is_default": 1,
			}
		).insert(ignore_permissions=True)
		# No explicit commit — the caller's request commits on success.
