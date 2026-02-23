# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
	get_etims_settings,
	get_api_timeout,
	get_sar_type_for_doctype,
	get_retry_settings,
	get_api_url
)


class TesteTIMSSettings(FrappeTestCase):
	"""Test cases for eTIMS Settings"""

	def setUp(self):
		frappe.flags.in_test = True

	def test_get_etims_settings(self):
		"""Test getting eTIMS settings"""
		settings = get_etims_settings()
		self.assertIsInstance(settings, dict)
		self.assertIn("default_sar_type_sales", settings)
		self.assertIn("api_timeout", settings)

	def test_get_api_timeout(self):
		"""Test getting API timeout"""
		timeout = get_api_timeout()
		self.assertIsInstance(timeout, int)
		self.assertGreater(timeout, 0)

	def test_get_sar_type_for_doctype_sales(self):
		"""Test getting SAR type for Sales Invoice"""
		sar_type = get_sar_type_for_doctype("Sales Invoice")
		self.assertEqual(sar_type, "11")

	def test_get_sar_type_for_doctype_purchase(self):
		"""Test getting SAR type for Purchase Invoice"""
		sar_type = get_sar_type_for_doctype("Purchase Invoice")
		self.assertEqual(sar_type, "02")

	def test_get_sar_type_for_doctype_stock_entry(self):
		"""Test getting SAR type for Stock Entry"""
		sar_type = get_sar_type_for_doctype("Stock Entry")
		self.assertEqual(sar_type, "06")

	def test_get_sar_type_for_doctype_unknown(self):
		"""Test getting SAR type for unknown doctype returns default"""
		sar_type = get_sar_type_for_doctype("Unknown DocType")
		self.assertEqual(sar_type, "11")  # Default to sales

	def test_get_retry_settings(self):
		"""Test getting retry settings"""
		retry_settings = get_retry_settings()
		self.assertIsInstance(retry_settings, dict)
		self.assertIn("enabled", retry_settings)
		self.assertIn("max_attempts", retry_settings)
		self.assertIn("delay", retry_settings)

	def test_get_api_url_production(self):
		"""Test getting production API URL"""
		url = get_api_url("Production")
		self.assertIn("etims-api.kra.go.ke", url)

	def test_get_api_url_sandbox(self):
		"""Test getting sandbox API URL"""
		url = get_api_url("Sandbox")
		self.assertIn("etims-api-sbx.kra.go.ke", url)
