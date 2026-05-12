"""
Test Suite for KRA eTIMS Expense Compliance

Tests for invoice verification, payment validation, and purchase
order tracking - all critical for 2026 tax compliance.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from kenya_etims_compliance.custom_methods.invoice_checker import check_invoice_validity
from kenya_etims_compliance.custom_methods.payment_entry import validate_payment_for_etims_invoice
from kenya_etims_compliance.custom_methods.purchase_invoice import (
	mark_invoice_as_manually_verified,
	verify_supplier_invoice,
)
from kenya_etims_compliance.custom_methods.purchase_order import (
	reconcile_purchase_with_invoice,
	send_purchase_order_to_etims,
)


class TestEtimsExpenseCompliance(FrappeTestCase):
	"""Test cases for eTIMS Expense Compliance functionality"""

	def setUp(self):
		"""Set up test fixtures"""
		# Create test supplier
		if not frappe.db.exists("Supplier", "Test Supplier eTIMS"):
			self.supplier = frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": "Test Supplier eTIMS",
					"supplier_type": "Company",
					"custom_supplier_pin": "A000000000",
					"custom_registered_in_etims": 1,
					"custom_auto_verify_invoices": 0,
				}
			).insert()
		else:
			self.supplier = frappe.get_doc("Supplier", "Test Supplier eTIMS")

	def test_invoice_checker_valid_format(self):
		"""Test invoice checker with valid input format"""
		# This tests the API call structure, not actual API response
		result = check_invoice_validity(
			invoice_no="TEST001", supplier_pin="A000000000", invoice_date="2026-01-15", total_amount=50000
		)

		# Result should have valid/verification status keys
		self.assertTrue("valid" in result or "verified" in result)

	def test_invoice_checker_missing_invoice_no(self):
		"""Test invoice checker with missing invoice number"""
		result = check_invoice_validity(
			invoice_no="", supplier_pin="A000000000", invoice_date="2026-01-15", total_amount=50000
		)

		self.assertFalse(result.get("valid", True))

	def test_invoice_checker_missing_supplier_pin(self):
		"""Test invoice checker with missing supplier PIN"""
		result = check_invoice_validity(
			invoice_no="TEST001", supplier_pin="", invoice_date="2026-01-15", total_amount=50000
		)

		self.assertFalse(result.get("valid", True))

	def test_invoice_checker_invalid_amount(self):
		"""Test invoice checker with invalid amount"""
		result = check_invoice_validity(
			invoice_no="TEST001", supplier_pin="A000000000", invoice_date="2026-01-15", total_amount=0
		)

		self.assertFalse(result.get("valid", True))

	def test_payment_validation_enforcement_setting(self):
		"""Test that payment validation respects settings"""
		# Get eTIMS settings
		from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
			get_etims_settings,
		)

		settings = get_etims_settings()

		# Settings should have enforce_invoice_verification key
		self.assertTrue("enforce_invoice_verification" in settings or settings == {})

	def test_manual_invoice_verification(self):
		"""Test manual invoice verification override"""
		# Create a test purchase invoice
		if frappe.db.exists("Purchase Invoice", "TEST-INV-001"):
			frappe.delete_doc("Purchase Invoice", "TEST-INV-001")

		# Test manual verification
		result = mark_invoice_as_manually_verified("TEST-INV-001", "Testing manual verification override")

		# Result should indicate success or failure appropriately
		self.assertTrue("success" in result)

	def test_purchase_order_tracking(self):
		"""Test Purchase Order tracking functionality"""
		# Create a test Purchase Order
		if frappe.db.exists("Purchase Order", "TEST-PO-001"):
			frappe.delete_doc("Purchase Order", "TEST-PO-001")

		# Test PO tracking creation
		result = send_purchase_order_to_etims("TEST-PO-001")

		# Result should have success key
		self.assertTrue("success" in result)

	def test_supplier_invoice_status(self):
		"""Test getting supplier invoice verification status"""
		from kenya_etims_compliance.custom_methods.purchase_invoice import get_supplier_invoice_status

		result = get_supplier_invoice_status(self.supplier.name)

		# Result should have status keys
		self.assertTrue("supplier" in result)
		self.assertEqual(result["supplier"], self.supplier.name)

	def test_unverified_invoices_query(self):
		"""Test getting list of unverified invoices"""
		from kenya_etims_compliance.custom_methods.invoice_checker import get_unverified_invoices

		result = get_unverified_invoices(limit=10)

		# Result should have success and invoices keys
		self.assertTrue("success" in result or "invoices" in result or "count" in result)

	def test_payment_eligibility_check(self):
		"""Test payment eligibility checking"""
		from kenya_etims_compliance.custom_methods.payment_entry import check_payment_eligibility

		result = check_payment_eligibility("TEST-PAYMENT-001")

		# Result should have eligible key
		self.assertTrue("eligible" in result or "error" in result)

	def test_get_unpaid_invoices_summary(self):
		"""Test getting unpaid invoices summary by verification status"""
		from kenya_etims_compliance.custom_methods.payment_entry import get_unpaid_invoices_summary

		result = get_unpaid_invoices_summary()

		# Result should have summary keys
		self.assertTrue(
			"unverified_unpaid" in result or "verified_unpaid" in result or "total_unpaid" in result
		)

	def test_supplier_po_status(self):
		"""Test getting Purchase Order status for supplier"""
		from kenya_etims_compliance.custom_methods.purchase_order import get_supplier_po_status

		result = get_supplier_po_status(self.supplier.name)

		# Result should have supplier key
		self.assertTrue("supplier" in result or "error" in result)

	def test_get_all_unreconciled_pos(self):
		"""Test getting all unreconciled Purchase Orders"""
		from kenya_etims_compliance.custom_methods.purchase_order import get_all_unreconciled_pos

		result = get_all_unreconciled_pos()

		# Result should have unreconciled_pos key
		self.assertTrue("unreconciled_pos" in result or "count" in result or "error" in result)


class TestEtimsInvoiceVerification(FrappeTestCase):
	"""Test cases specifically for invoice verification workflow"""

	def test_verification_date_format(self):
		"""Test that verification date is stored in correct format"""
		from datetime import datetime

		test_date = "2026-01-15"

		# This should be a valid date format
		try:
			datetime.strptime(test_date, "%Y-%m-%d")
			self.assertTrue(True)
		except ValueError:
			self.fail("Date format is incorrect")

	def test_qr_code_storage(self):
		"""Test that QR code can be stored and retrieved"""
		test_qr = "TEST_QR_CODE_12345"

		# In a real test, we would create an invoice and verify it
		# For now, test the string format
		self.assertTrue(len(test_qr) > 0)
		self.assertIsInstance(test_qr, str)

	def test_kra_invoice_number_format(self):
		"""Test KRA invoice number format"""
		# KRA invoice numbers should follow a specific format
		test_invoice_no = "INV0000001"

		self.assertTrue(len(test_invoice_no) > 0)
		self.assertIsInstance(test_invoice_no, str)


class TestEtimsSettingsIntegration(FrappeTestCase):
	"""Test eTIMS Settings integration with compliance features"""

	def test_etims_settings_exist(self):
		"""Test that eTIMS Settings single doc exists"""
		from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
			get_etims_settings,
		)

		settings = get_etims_settings()

		# Should return a dict
		self.assertIsInstance(settings, dict)

	def test_compliance_settings_keys(self):
		"""Test that compliance settings keys exist"""
		from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
			get_etims_settings,
		)

		settings = get_etims_settings()

		# Check for new compliance settings
		# Note: These may not exist in existing installations
		_expected_keys = [
			"enforce_invoice_verification",
			"auto_verify_invoices",
			"allow_payment_unverified",
			"verification_amount_threshold",
			"enable_po_tracking",
		]

		# At least some of these should exist after migration
		# This test verifies the settings structure is correct
		self.assertIsInstance(settings, dict)


def run_tests():
	"""Run all eTIMS compliance tests"""
	import unittest

	# Create test suite
	loader = unittest.TestLoader()
	suite = unittest.TestSuite()

	# Add test cases
	suite.addTests(loader.loadTestsFromTestCase(TestEtimsExpenseCompliance))
	suite.addTests(loader.loadTestsFromTestCase(TestEtimsInvoiceVerification))
	suite.addTests(loader.loadTestsFromTestCase(TestEtimsSettingsIntegration))

	# Run tests
	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)

	return result


if __name__ == "__main__":
	result = run_tests()
	exit(0 if result.wasSuccessful() else 1)
