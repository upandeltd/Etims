# kenya_etims_compliance/utils/kra_client.py
import time
import traceback
import requests

import frappe


class KRAClient:
    """Centralized KRA eTIMS API client with timeout, retry, and error handling.

    Uses frappe.log_error() for transaction-safe logging instead
    of inserting Error Logging docs (which can cascade-fail inside before_submit).
    """

    def __init__(self, branch_id=None):
        self.branch_id = branch_id or self._get_user_branch_id()
        self.headers = self._load_headers()
        self._settings = None

    @property
    def settings(self):
        if self._settings is None:
            from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import get_etims_settings
            self._settings = get_etims_settings()
        return self._settings

    def post(self, endpoint, payload, reference_doctype=None, reference_name=None):
        """POST to KRA API with circuit breaker, timeout, retry, and audit trail.

        Args:
            endpoint: API endpoint name (e.g. 'saveTrnsSalesOsdc')
            payload: dict to POST as JSON
            reference_doctype: optional — for audit trail (e.g. 'Sales Invoice')
            reference_name: optional — for audit trail (e.g. 'ACC-SINV-2026-00001')

        Returns:
            {"Success": <data>} or {"Error": "<message>", "Retryable": bool}
        """
        # Circuit breaker: block if 5+ recent failures (auto-resets after 5 minutes)
        failure_count = frappe.cache.get_value("etims_circuit_breaker") or 0
        if failure_count >= 5:
            return {
                "Error": "eTIMS circuit breaker is open. Too many recent failures. Will auto-reset in 5 minutes.",
                "Retryable": True
            }

        timeout = self.settings.get("api_timeout", 30)
        max_retries = self.settings.get("max_retry_attempts", 3) if self.settings.get("enable_retry_logic") else 1
        retry_delay = self.settings.get("retry_delay", 2)
        url = self._get_base_url() + endpoint

        for attempt in range(max_retries):
            try:
                response = requests.post(url, json=payload, headers=self.headers, timeout=timeout)
                if not response.content or not response.content.strip():
                    self._log_error(endpoint, f"Empty response body (HTTP {response.status_code})")
                    return {"Error": f"KRA API returned empty response (HTTP {response.status_code})", "Retryable": True}
                result = self._handle_response(response.json(), endpoint)
                if "Success" in result:
                    self._log_api_call(
                        endpoint, reference_doctype, reference_name,
                        "000", "Success", "success"
                    )
                else:
                    self._log_api_call(
                        endpoint, reference_doctype, reference_name,
                        "", result.get("Error", "Unknown error"), "failure"
                    )
                return result
            except requests.JSONDecodeError:
                self._log_error(endpoint, f"Invalid JSON response (HTTP {response.status_code}): {response.text[:500]}")
                return {"Error": f"KRA API returned invalid JSON (HTTP {response.status_code})", "Retryable": True}
            except requests.ConnectionError:
                frappe.cache.set_value(
                    "etims_circuit_breaker",
                    (frappe.cache.get_value("etims_circuit_breaker") or 0) + 1,
                    expires_in_sec=300
                )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                self._log_error(endpoint, f"Connection failed after {max_retries} attempts")
                self._log_api_call(
                    endpoint, reference_doctype, reference_name,
                    "CONN_ERR", f"Connection failed after {max_retries} attempts", "failure"
                )
                return {"Error": f"KRA API unreachable after {max_retries} attempts", "Retryable": True}
            except requests.Timeout:
                frappe.cache.set_value(
                    "etims_circuit_breaker",
                    (frappe.cache.get_value("etims_circuit_breaker") or 0) + 1,
                    expires_in_sec=300
                )
                self._log_error(endpoint, f"Timeout after {timeout}s")
                self._log_api_call(
                    endpoint, reference_doctype, reference_name,
                    "TIMEOUT", f"Request timed out after {timeout}s", "failure"
                )
                return {"Error": f"KRA API timed out after {timeout} seconds", "Retryable": True}
            except Exception as e:
                self._log_error(endpoint, traceback.format_exc())
                return {"Error": f"KRA API error: {str(e)}", "Retryable": False}

        return {"Error": "KRA API request failed", "Retryable": False}

    # --- Convenience methods ---

    def save_sales(self, payload, reference_doctype=None, reference_name=None):
        return self.post("saveTrnsSalesOsdc", payload, reference_doctype, reference_name)

    def insert_purchase(self, payload, reference_doctype=None, reference_name=None):
        return self.post("insertTrnsPurchase", payload, reference_doctype, reference_name)

    def insert_stock_io(self, payload, reference_doctype=None, reference_name=None):
        return self.post("insertStockIO", payload, reference_doctype, reference_name)

    def save_item(self, payload, reference_doctype=None, reference_name=None):
        return self.post("saveItem", payload, reference_doctype, reference_name)

    def search_item(self, payload):
        return self.post("searchItem", payload)

    def search_stock_move(self, payload):
        return self.post("searchStockMove", payload)

    def search_trns(self, endpoint, payload):
        return self.post(endpoint, payload)

    def stock_release_no_save(self, payload, reference_doctype=None, reference_name=None):
        return self.post("stockReleaseNoSaveReq", payload, reference_doctype, reference_name)

    def search_stock_release_no(self, payload):
        return self.post("searchStockReleaseNo", payload)

    def select_stock_release_no_list(self, payload):
        return self.post("selectStockReleaseNoList", payload)

    def select_item(self, payload):
        return self.post("selectItem", payload)

    def select_trns_sales_info(self, payload):
        return self.post("selectTrnsSalesInfo", payload)

    def select_trns_purchase_info(self, payload):
        return self.post("selectTrnsPurchaseInfo", payload)

    def select_notice_info(self, payload):
        return self.post("selectNoticeInfo", payload)

    def select_org_usr_info(self):
        return self.post("selectOrgUsrInfo", {})

    def check_status(self):
        """Check OSCU/VSCU connection status using selectOrgUsrInfo (Spec 6.8, 21.7.8).

        Returns dict with connected (bool), response_time_ms (int), error (str).
        """
        import time as _time
        start = _time.monotonic()
        try:
            result = self.select_org_usr_info()
            elapsed_ms = int((_time.monotonic() - start) * 1000)
            if "Success" in result:
                return {"connected": True, "response_time_ms": elapsed_ms, "error": ""}
            return {"connected": False, "response_time_ms": elapsed_ms, "error": result.get("Error", "Unknown error")}
        except Exception as e:
            elapsed_ms = int((_time.monotonic() - start) * 1000)
            return {"connected": False, "response_time_ms": elapsed_ms, "error": str(e)}

    # --- Internal helpers ---

    def _get_user_branch_id(self):
        current_user = frappe.session.user
        perms = frappe.db.get_all(
            "User Permission",
            filters={"user": current_user, "allow": "Tax Branch Office", "is_default": 1},
            fields=["for_value"]
        )
        return perms[0].get("for_value") if perms else None

    def _load_headers(self):
        if not self.branch_id:
            return {}
        header_docs = frappe.db.get_all(
            "TIS Device Initialization",
            filters={"branch_id": self.branch_id, "active": 1},
            fields=["pin", "branch_id", "communication_key"]
        )
        if header_docs:
            return {
                "tin": header_docs[0].get("pin"),
                "bhfId": header_docs[0].get("branch_id"),
                "cmcKey": header_docs[0].get("communication_key"),
            }
        return {}

    def _get_base_url(self):
        from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import get_api_url
        docs = frappe.db.get_all(
            "TIS Device Initialization",
            filters={"branch_id": self.branch_id, "active": 1},
            fields=["api_mode"]
        )
        api_mode = docs[0].api_mode if docs else "Sandbox"
        return get_api_url(api_mode)

    def _handle_response(self, response_json, endpoint=""):
        from kenya_etims_compliance.utils.error_codes import get_error_message, get_warning_message

        result_cd = response_json.get("resultCd")
        result_msg = response_json.get("resultMsg", "Unknown error")

        # Check for warning codes (Spec 21.6.4)
        warning_cd = response_json.get("wrnCd")
        if warning_cd is not None and int(warning_cd) > 0:
            warn_msg, warn_action = get_warning_message(warning_cd)
            frappe.msgprint(
                msg=f"{warn_msg}. {warn_action}",
                title="KRA Warning",
                indicator="orange",
            )

        if result_cd == "000":
            frappe.cache.delete_value("etims_circuit_breaker")
            return {"Success": response_json.get("data")}

        # Look up specific error message from error code mapping
        mapped_msg, recommended_action = get_error_message(result_cd)
        error_detail = f"{endpoint} error ({result_cd}): {mapped_msg}"
        if recommended_action:
            error_detail += f" — {recommended_action}"
        # Include original KRA message for context
        if result_msg and result_msg != mapped_msg:
            error_detail += f" [KRA: {result_msg}]"

        self._log_error(endpoint, error_detail)
        return {"Error": error_detail}

    def _log_api_call(self, endpoint, reference_doctype, reference_name, result_cd, result_msg, status):
        """Log each API call to Integration Request for audit trail.

        Only logs when reference_doctype is provided. Never raises — logging must
        never break the main submission flow.
        """
        if not reference_doctype:
            return
        try:
            frappe.get_doc({
                "doctype": "Integration Request",
                "integration_type": "Remote",
                "integration_request_service": "eTIMS",
                "reference_doctype": reference_doctype,
                "reference_name": reference_name,
                "url": endpoint,
                "data": frappe.as_json({"endpoint": endpoint, "timestamp": frappe.utils.now()}),
                "output": frappe.as_json({"resultCd": str(result_cd), "resultMsg": str(result_msg)[:500]}),
                "status": "Completed" if status == "success" else "Failed",
                "error": str(result_msg)[:500] if status != "success" else None,
            }).insert(ignore_permissions=True)
        except Exception as e:
            frappe.log_error("eTIMS: KRA client error", str(e))
            pass  # Never let audit logging break the main operation

    def _log_error(self, title, description):
        """Log errors using frappe.log_error (transaction-safe).

        Previously used frappe.new_doc('Error Logging').insert()
        which is unsafe inside before_submit hooks (can cascade transaction failures).
        frappe.log_error writes to the Error Log doctype which is committed
        independently of the current transaction.
        """
        try:
            frappe.log_error(
                title=f"KRA API: {title}"[:140],
                message=str(description)[:2000]
            )
        except Exception as e:
            frappe.log_error("eTIMS: KRA client error", str(e))
            pass  # Never let logging break the actual operation
