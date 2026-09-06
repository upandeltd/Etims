"""
Test Suite for Kenya eTIMS Compliance Utils Module

Tests datetime formatting, API response handling, SAR number logic,
KRAClient behaviour, and error-code mappings.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase

from kenya_etims_compliance.utils.error_codes import (
	KRA_ERROR_CODES,
	KRA_WARNING_CODES,
	get_error_message,
	get_warning_message,
)
from kenya_etims_compliance.utils.etims_utils import (
	eTIMS,
	get_next_sar_number,
	get_org_sar_number,
)
from kenya_etims_compliance.utils.kra_client import KRAClient


class TestETIMSDatetimeUtils(FrappeTestCase):
	"""Tests for eTIMS static datetime/date/time formatting helpers."""

	def test_strf_datetime_object_valid_string(self):
		"""strf_datetime_object should convert '2024-03-15 10:30:00' -> '20240315103000'."""
		result = eTIMS.strf_datetime_object("2024-03-15 10:30:00")
		self.assertEqual(result, "20240315103000")

	def test_strf_datetime_format_with_string(self):
		"""strf_datetime_format should accept a plain datetime string."""
		result = eTIMS.strf_datetime_format("2024-03-15 10:30:00")
		self.assertEqual(result, "20240315103000")

	def test_strf_datetime_format_with_datetime_object(self):
		"""strf_datetime_format should accept a datetime object."""
		dt = datetime(2024, 3, 15, 10, 30, 0)
		result = eTIMS.strf_datetime_format(dt)
		self.assertEqual(result, "20240315103000")

	def test_strf_datetime_format_with_microseconds(self):
		"""strf_datetime_format should strip microseconds from string input."""
		result = eTIMS.strf_datetime_format("2024-03-15 10:30:00.123456")
		self.assertEqual(result, "20240315103000")

	def test_strf_date_object_valid_string(self):
		"""strf_date_object should convert '2024-03-15' -> '20240315'."""
		result = eTIMS.strf_date_object("2024-03-15")
		self.assertEqual(result, "20240315")

	def test_strf_time_valid_string(self):
		"""strf_time should convert '10:30:00' -> '103000'."""
		result = eTIMS.strf_time("10:30:00")
		self.assertEqual(result, "103000")

	def test_strf_time_with_microseconds_fallback(self):
		"""strf_time should fall back to parsing microseconds when plain HMS fails."""
		result = eTIMS.strf_time("10:30:00.123456")
		self.assertEqual(result, "103000")


class TestETIMSResponseUtils(FrappeTestCase):
	"""Tests for eTIMS response helpers."""

	def test_get_response_data_with_message_key(self):
		"""get_response_data should return the 'message' value when present."""
		response = {"message": {"status": "ok"}, "other": "data"}
		result = eTIMS.get_response_data(response)
		self.assertEqual(result, {"status": "ok"})

	def test_get_response_data_without_message_key(self):
		"""get_response_data should return the whole dict when 'message' is absent."""
		response = {"status": "ok"}
		result = eTIMS.get_response_data(response)
		self.assertEqual(result, {"status": "ok"})

	@patch("kenya_etims_compliance.utils.etims_utils.eTIMS.log_errors")
	def test_handle_api_response_success(self, mock_log_errors):
		"""handle_api_response should return {'Success': data} for resultCd '000'."""
		response = {"resultCd": "000", "resultMsg": "OK", "data": {"invNo": "123"}}
		result = eTIMS.handle_api_response(response)
		self.assertIn("Success", result)
		self.assertEqual(result["Success"], {"invNo": "123"})
		mock_log_errors.assert_not_called()

	@patch("kenya_etims_compliance.utils.etims_utils.eTIMS.log_errors")
	def test_handle_api_response_400(self, mock_log_errors):
		"""handle_api_response should log and return error for resultCd '400'."""
		response = {"resultCd": "400", "resultMsg": "Bad payload"}
		result = eTIMS.handle_api_response(response)
		self.assertIn("Error", result)
		self.assertIn("Bad Request", result["Error"])
		mock_log_errors.assert_called_once()

	@patch("kenya_etims_compliance.utils.etims_utils.eTIMS.log_errors")
	def test_handle_api_response_401(self, mock_log_errors):
		"""handle_api_response should log and return error for resultCd '401'."""
		response = {"resultCd": "401", "resultMsg": "Unauthorized"}
		result = eTIMS.handle_api_response(response)
		self.assertIn("Error", result)
		self.assertIn("Unauthorized", result["Error"])
		mock_log_errors.assert_called_once()

	@patch("kenya_etims_compliance.utils.etims_utils.eTIMS.log_errors")
	def test_handle_api_response_500(self, mock_log_errors):
		"""handle_api_response should log and return error for resultCd '500'."""
		response = {"resultCd": "500", "resultMsg": "Server exploded"}
		result = eTIMS.handle_api_response(response)
		self.assertIn("Error", result)
		self.assertIn("Server Error", result["Error"])
		mock_log_errors.assert_called_once()

	@patch("kenya_etims_compliance.utils.etims_utils.eTIMS.log_errors")
	def test_handle_api_response_unknown_code(self, mock_log_errors):
		"""handle_api_response should return generic error for unhandled codes (e.g. 999)."""
		response = {"resultCd": "999", "resultMsg": "Unknown disaster"}
		result = eTIMS.handle_api_response(response)
		self.assertIn("Error", result)
		self.assertIn("999", result["Error"])
		mock_log_errors.assert_not_called()


class TestSARNumberUtils(FrappeTestCase):
	"""Tests for get_next_sar_number and get_org_sar_number."""

	@patch("kenya_etims_compliance.utils.etims_utils.frappe.qb", new_callable=MagicMock)
	@patch("kenya_etims_compliance.utils.etims_utils.frappe.new_doc")
	@patch("kenya_etims_compliance.utils.etims_utils.get_org_sar_number")
	def test_get_next_sar_number_increment(self, mock_get_org, mock_new_doc, mock_qb):
		"""get_next_sar_number should increment the highest existing sr_number by 1."""
		mock_query = mock_qb.from_.return_value
		mock_query.where.return_value = mock_query
		mock_query.orderby.return_value = mock_query
		mock_query.limit.return_value = mock_query
		mock_query.for_update.return_value = mock_query
		mock_query.select.return_value = mock_query
		mock_query.run.return_value = [{"sr_number": 42}]
		mock_get_org.return_value = 0

		mock_doc_instance = MagicMock()
		mock_new_doc.return_value = mock_doc_instance

		mock_doc = MagicMock()
		mock_doc.doctype = "Stock Entry"
		mock_doc.name = "SE-0001"

		result = get_next_sar_number(mock_doc, branch_id="HO")
		self.assertEqual(result, 43)
		mock_query.for_update.assert_called_once()
		mock_query.run.assert_called_once_with(as_dict=True)
		self.assertEqual(mock_doc_instance.sr_number, 43)
		mock_doc_instance.insert.assert_called_once()

	@patch("kenya_etims_compliance.utils.etims_utils.frappe.qb", new_callable=MagicMock)
	@patch("kenya_etims_compliance.utils.etims_utils.frappe.new_doc")
	@patch("kenya_etims_compliance.utils.etims_utils.get_org_sar_number")
	def test_get_next_sar_number_first_entry(self, mock_get_org, mock_new_doc, mock_qb):
		"""get_next_sar_number should return 1 when no previous SAR records exist."""
		mock_query = mock_qb.from_.return_value
		mock_query.where.return_value = mock_query
		mock_query.orderby.return_value = mock_query
		mock_query.limit.return_value = mock_query
		mock_query.for_update.return_value = mock_query
		mock_query.select.return_value = mock_query
		mock_query.run.return_value = []
		mock_get_org.return_value = 0

		mock_doc_instance = MagicMock()
		mock_new_doc.return_value = mock_doc_instance

		mock_doc = MagicMock()
		mock_doc.doctype = "Stock Entry"
		mock_doc.name = "SE-0001"

		result = get_next_sar_number(mock_doc, branch_id="HO")
		self.assertEqual(result, 1)
		self.assertEqual(mock_doc_instance.sr_number, 1)
		mock_doc_instance.insert.assert_called_once()

	@patch("kenya_etims_compliance.utils.etims_utils.frappe.db.get_all")
	def test_get_org_sar_number_with_original_invoice(self, mock_get_all):
		"""get_org_sar_number should return previous sr_number when original invoice exists."""
		mock_get_all.return_value = [{"sr_number": 7}]

		mock_doc = MagicMock()
		mock_doc.custom_original_invoice_number = "INV-001"
		mock_doc.return_against = "SINV-OLD-001"

		result = get_org_sar_number(mock_doc)
		self.assertEqual(result, 7)
		mock_get_all.assert_called_once_with(
			"eTIMS Stock Release Number",
			filters={"reference": "SINV-OLD-001"},
			fields=["sr_number"],
			page_length=1,
		)

	def test_get_org_sar_number_without_original_invoice(self):
		"""get_org_sar_number should return 0 when there is no original invoice."""
		mock_doc = MagicMock()
		mock_doc.custom_original_invoice_number = None
		result = get_org_sar_number(mock_doc)
		self.assertEqual(result, 0)

	@patch("kenya_etims_compliance.utils.etims_utils.frappe.db.get_all")
	def test_get_org_sar_number_empty_result(self, mock_get_all):
		"""get_org_sar_number should return 0 when query returns no records."""
		mock_get_all.return_value = []

		mock_doc = MagicMock()
		mock_doc.custom_original_invoice_number = "INV-001"
		mock_doc.return_against = "SINV-OLD-001"

		result = get_org_sar_number(mock_doc)
		self.assertEqual(result, 0)


class TestKRAClient(FrappeTestCase):
	"""Tests for KRAClient circuit breaker, missing headers, and post behaviour."""

	def _make_client(self, headers=None):
		"""Return a KRAClient with internal dependencies already patched."""
		with patch.object(KRAClient, "_get_user_branch_id", return_value="001"):
			with patch.object(KRAClient, "_load_headers", return_value=headers or {}):
				client = KRAClient()
		return client

	@patch("kenya_etims_compliance.utils.kra_client.frappe.cache.get_value")
	def test_circuit_breaker_open(self, mock_cache_get):
		"""post should return circuit-breaker error when failure_count >= 5."""
		mock_cache_get.return_value = 5
		client = self._make_client(headers={"tin": "P001"})

		result = client.post("saveItem", {"itemCd": "123"})
		self.assertIn("Error", result)
		self.assertIn("circuit breaker", result["Error"])
		self.assertTrue(result.get("Retryable"))

	def test_missing_headers(self):
		"""post should return an error when headers are empty."""
		client = self._make_client(headers={})

		with patch("kenya_etims_compliance.utils.kra_client.frappe.cache.get_value", return_value=0):
			result = client.post("saveItem", {"itemCd": "123"})

		self.assertIn("Error", result)
		self.assertIn("No active TIS Device Initialization", result["Error"])
		self.assertFalse(result.get("Retryable"))

	@patch("kenya_etims_compliance.utils.kra_client.requests.post")
	@patch("kenya_etims_compliance.utils.kra_client.frappe.cache.delete_value")
	@patch("kenya_etims_compliance.utils.kra_client.frappe.cache.get_value")
	@patch(
		"kenya_etims_compliance.utils.kra_client.get_etims_settings",
		return_value={"api_timeout": 10, "max_retry_attempts": 3, "enable_retry_logic": 0, "retry_delay": 1},
	)
	def test_post_success(self, mock_settings, mock_cache_get, mock_cache_del, mock_requests_post):
		"""post should return {'Success': data} on a valid 200 response with resultCd '000'."""
		mock_cache_get.return_value = 0

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.content = b'{"resultCd":"000","data":{"itemCd":"123"}}'
		mock_response.json.return_value = {"resultCd": "000", "data": {"itemCd": "123"}}
		mock_requests_post.return_value = mock_response

		client = self._make_client(headers={"tin": "P001", "bhfId": "001", "cmcKey": "KEY"})
		result = client.post("saveItem", {"itemCd": "123"})

		self.assertIn("Success", result)
		self.assertEqual(result["Success"], {"itemCd": "123"})
		mock_cache_del.assert_called_once_with("etims_circuit_breaker")

	@patch("kenya_etims_compliance.utils.kra_client.requests.post")
	@patch("kenya_etims_compliance.utils.kra_client.frappe.cache.get_value")
	@patch(
		"kenya_etims_compliance.utils.kra_client.get_etims_settings",
		return_value={"api_timeout": 10, "max_retry_attempts": 3, "enable_retry_logic": 0, "retry_delay": 1},
	)
	def test_post_json_decode_error(self, mock_settings, mock_cache_get, mock_requests_post):
		"""post should return an error when response is not valid JSON."""
		mock_cache_get.return_value = 0

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.content = b"not-json"
		# requests.JSONDecodeError inherits from ValueError in modern requests
		mock_response.json.side_effect = ValueError("No JSON")
		mock_requests_post.return_value = mock_response

		client = self._make_client(headers={"tin": "P001"})
		result = client.post("saveItem", {"itemCd": "123"})

		self.assertIn("Error", result)
		self.assertIn("invalid JSON", result["Error"])
		self.assertTrue(result.get("Retryable"))

	@patch("kenya_etims_compliance.utils.kra_client.requests.post")
	@patch("kenya_etims_compliance.utils.kra_client.frappe.cache.get_value")
	@patch("kenya_etims_compliance.utils.kra_client.frappe.cache.set_value")
	@patch(
		"kenya_etims_compliance.utils.kra_client.get_etims_settings",
		return_value={"api_timeout": 10, "max_retry_attempts": 1, "enable_retry_logic": 0, "retry_delay": 0},
	)
	def test_post_connection_error(self, mock_settings, mock_cache_set, mock_cache_get, mock_requests_post):
		"""post should return a retryable error on ConnectionError."""
		mock_cache_get.return_value = 0
		mock_requests_post.side_effect = requests.ConnectionError("No route")

		client = self._make_client(headers={"tin": "P001"})
		result = client.post("saveItem", {"itemCd": "123"})

		self.assertIn("Error", result)
		self.assertIn("unreachable", result["Error"])
		self.assertTrue(result.get("Retryable"))
		mock_cache_set.assert_called()

	@patch("kenya_etims_compliance.utils.kra_client.requests.post")
	@patch("kenya_etims_compliance.utils.kra_client.frappe.cache.get_value")
	@patch("kenya_etims_compliance.utils.kra_client.frappe.cache.set_value")
	@patch(
		"kenya_etims_compliance.utils.kra_client.get_etims_settings",
		return_value={"api_timeout": 10, "max_retry_attempts": 1, "enable_retry_logic": 0, "retry_delay": 0},
	)
	def test_post_timeout(self, mock_settings, mock_cache_set, mock_cache_get, mock_requests_post):
		"""post should return a retryable error on Timeout."""
		mock_cache_get.return_value = 0
		mock_requests_post.side_effect = requests.Timeout("Too slow")

		client = self._make_client(headers={"tin": "P001"})
		result = client.post("saveItem", {"itemCd": "123"})

		self.assertIn("Error", result)
		self.assertIn("timed out", result["Error"])
		self.assertTrue(result.get("Retryable"))
		mock_cache_set.assert_called()


class TestErrorCodes(FrappeTestCase):
	"""Tests for error_codes mapping utilities."""

	def test_get_error_message_known_code(self):
		"""get_error_message should return mapped (message, action) for known codes."""
		msg, action = get_error_message("000")
		self.assertEqual(msg, "Success")
		self.assertEqual(action, "")

		msg, action = get_error_message("040")
		self.assertEqual(msg, "Authentication failed")
		self.assertIn("TIN", action)

	def test_get_error_message_unknown_code(self):
		"""get_error_message should return a fallback for unknown codes."""
		msg, action = get_error_message("XYZ999")
		self.assertIn("Unrecognized error code", msg)
		self.assertIn("Contact KRA support", action)

	def test_get_warning_message_known(self):
		"""get_warning_message should return mapped values for known warning codes."""
		msg, _action = get_warning_message(0)
		self.assertEqual(msg, "Normal operation")

		msg, _action = get_warning_message(1)
		self.assertEqual(msg, "Memory capacity low")

	def test_get_warning_message_unknown(self):
		"""get_warning_message should return a fallback for unknown warning codes."""
		msg, _action = get_warning_message(99)
		self.assertIn("Unknown warning code", msg)

	def test_error_codes_dict_not_empty(self):
		"""KRA_ERROR_CODES should contain the expected entries."""
		self.assertIn("000", KRA_ERROR_CODES)
		self.assertIn("500", KRA_ERROR_CODES)

	def test_warning_codes_dict_not_empty(self):
		"""KRA_WARNING_CODES should contain expected entries."""
		self.assertIn(0, KRA_WARNING_CODES)
		self.assertIn(2, KRA_WARNING_CODES)


if __name__ == "__main__":
	import unittest

	loader = unittest.TestLoader()
	suite = unittest.TestSuite()
	suite.addTests(loader.loadTestsFromTestCase(TestETIMSDatetimeUtils))
	suite.addTests(loader.loadTestsFromTestCase(TestETIMSResponseUtils))
	suite.addTests(loader.loadTestsFromTestCase(TestSARNumberUtils))
	suite.addTests(loader.loadTestsFromTestCase(TestKRAClient))
	suite.addTests(loader.loadTestsFromTestCase(TestErrorCodes))
	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)
	exit(0 if result.wasSuccessful() else 1)
