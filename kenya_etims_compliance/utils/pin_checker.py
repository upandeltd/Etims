"""KRA PIN Checker by PIN integration (developer.go.ke).

OAuth client_credentials → bearer token (cached for 60 minutes) → POST PIN.

NOTE: The original implementation read ``pin_checker_consumer_key`` and
``pin_checker_consumer_secret`` from ``eTIMS Settings`` via ``get_password()``.
Those fields do not exist on the live DocType meta (verified read-only on
toysam — see /tmp/etims-review-2026-08-20.md, MEDIUM / LOW highlights).
Until the fields are added, ``_get_token`` raises a clear
``frappe.ValidationError`` with an actionable message so an operator sees
what to configure instead of a generic ``NoneType`` crash.
"""

import base64
import re

import frappe
import requests

CACHE_KEY = "kra_pin_checker_token"
TOKEN_TTL = 3300  # 55 min — KRA token expires in 3600s, refresh 5 min early

SANDBOX_BASE = "https://sbx.kra.go.ke"
PRODUCTION_BASE = "https://api.kra.go.ke"


def _settings():
	return frappe.get_cached_doc("eTIMS Settings")


def _base_url():
	mode = (_settings().get("pin_checker_mode") or "Sandbox").strip()
	return PRODUCTION_BASE if mode == "Production" else SANDBOX_BASE


def _get_token():
	"""Fetch (and cache) a bearer token from KRA."""
	cached = frappe.cache.get_value(CACHE_KEY)
	if cached:
		return cached

	s = _settings()
	# Original code used ``s.get_password("pin_checker_consumer_key", raise_exception=False)``
	# but those fieldnames do not exist on the live DocType meta — see module
	# docstring. Fall back to plain ``get()`` (which already returns ``None``)
	# and surface the gap with a translated ValidationError.
	key = s.get("pin_checker_consumer_key")
	secret = s.get("pin_checker_consumer_secret")
	if not key or not secret:
		frappe.throw(
			_(
				"PIN Checker credentials are not configured: eTIMS Settings is "
				"missing the fields 'pin_checker_consumer_key' and "
				"'pin_checker_consumer_secret'. Add them to eTIMS Settings "
				"before using the PIN Checker."
			),
			frappe.ValidationError,
		)

	credentials = base64.b64encode(f"{key}:{secret}".encode()).decode()
	resp = requests.get(
		f"{_base_url()}/v1/token/generate",
		params={"grant_type": "client_credentials"},
		headers={"Authorization": f"Basic {credentials}"},
		timeout=15,
	)
	resp.raise_for_status()
	body = resp.json()
	token = body.get("access_token")
	if not token:
		raise ValueError(f"KRA token endpoint returned no access_token: {body}")

	frappe.cache.set_value(CACHE_KEY, token, expires_in_sec=TOKEN_TTL)
	return token


def check_pin(pin):
	"""Validate a KRA PIN via PIN Checker by PIN.

	Returns one of:
	    {"valid": True, "data": {KRAPIN, TypeOfTaxpayer, Name, StatusOfPIN}}
	    {"valid": False, "message": "..."}
	"""
	if not pin:
		return {"valid": False, "message": "No PIN provided"}
	if not re.match(r"^[AP]\d{9}[A-Z]$", pin):
		return {
			"valid": False,
			"message": "PIN format invalid. Expected: 'A' or 'P' + 9 digits + letter (e.g. P051234567T)",
		}

	try:
		token = _get_token()
	except (requests.ConnectionError, requests.Timeout, requests.HTTPError, ValueError, frappe.ValidationError) as e:
		return {"valid": False, "message": f"Could not authenticate with KRA: {e!s}"}

	try:
		resp = requests.post(
			f"{_base_url()}/checker/v1/pinbypin",
			json={"KRAPIN": pin},
			headers={
				"Content-Type": "application/json",
				"Authorization": f"Bearer {token}",
			},
			timeout=20,
		)
	except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
		return {"valid": False, "message": f"Could not reach KRA: {e!s}"}

	# Token may have expired between cache lookup and call — try once more
	if resp.status_code == 401:
		frappe.cache.delete_value(CACHE_KEY)
		try:
			token = _get_token()
			resp = requests.post(
				f"{_base_url()}/checker/v1/pinbypin",
				json={"KRAPIN": pin},
				headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
				timeout=20,
			)
		except (requests.ConnectionError, requests.Timeout, requests.HTTPError, ValueError, frappe.ValidationError) as e:
			return {"valid": False, "message": f"Auth retry failed: {e!s}"}

	try:
		body = resp.json()
	except ValueError:
		return {"valid": False, "message": f"KRA returned non-JSON (HTTP {resp.status_code}): {resp.text[:200]}"}

	if body.get("Status") == "OK" and body.get("PINDATA"):
		return {"valid": True, "data": body["PINDATA"], "code": body.get("ResponseCode")}

	# Detect KRA gateway 5xx errors (their backend is down, nothing we can do)
	fault = body.get("fault") or {}
	if resp.status_code >= 500 or fault:
		fault_reason = fault.get("detail", {}).get("reason") or fault.get("faultstring", "")
		mode = (_settings().get("pin_checker_mode") or "Sandbox").strip()
		return {
			"valid": False,
			"message": (
				f"KRA {mode} backend is unreachable (HTTP {resp.status_code}). "
				f"This is a KRA-side outage, not a configuration problem. "
				f"Detail: {fault_reason or 'no reason given'}. "
				f"{'Try again in a few minutes, or switch to Production in eTIMS Settings if you have prod credentials.' if mode == 'Sandbox' else 'Try again shortly or contact KRA support.'}"
			),
			"code": resp.status_code,
		}

	return {
		"valid": False,
		"message": body.get("Message") or f"KRA error {body.get('ResponseCode', resp.status_code)}",
		"code": body.get("ResponseCode"),
	}
