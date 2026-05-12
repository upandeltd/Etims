"""
Comprehensive test suite for Kenya eTims Compliance core custom_methods.
"""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from kenya_etims_compliance.custom_methods.invoice_checker import (
	check_invoice_validity,
)
from kenya_etims_compliance.custom_methods.item import (
	autofill_tims_info,
	create_item_digit_code,
	get_item_status,
	get_status_code,
)
from kenya_etims_compliance.custom_methods.payment_entry import (
	validate_payment_for_etims_invoice,
)
from kenya_etims_compliance.custom_methods.purchase_invoice import (
	get_total_discount as get_purchase_total_discount,
)
from kenya_etims_compliance.custom_methods.purchase_invoice import (
	validate as validate_purchase_invoice,
)
from kenya_etims_compliance.custom_methods.queue_processor import (
	get_queue_status,
	should_use_queue,
)
from kenya_etims_compliance.custom_methods.sales_invoice import (
	get_total_discount,
	insert_tax_amounts,
	validate_inv_number,
)
from kenya_etims_compliance.custom_methods.stock import (
	check_if_interbranch,
	insert_tax_rate_and_amount,
)


class MockRow:
	"""Simple row-like object that supports .get() like frappe document children."""

	def __init__(self, **kwargs):
		self.__dict__.update(kwargs)

	def get(self, key, default=None):
		return getattr(self, key, default)


class TestItemCustomMethods(FrappeTestCase):
	"""Tests for kenya_etims_compliance.custom_methods.item"""

	def test_get_status_code_unsent(self):
		self.assertEqual(get_status_code("Unsent"), 1)

	def test_get_status_code_waiting(self):
		self.assertEqual(get_status_code("Waiting"), 2)

	def test_get_status_code_approved(self):
		self.assertEqual(get_status_code("Approved"), 3)

	def test_get_status_code_other(self):
		self.assertEqual(get_status_code("Unknown"), 4)

	def test_get_item_status_enabled(self):
		doc = MagicMock()
		doc.disabled = False
		self.assertEqual(get_item_status(doc), "Y")

	def test_get_item_status_disabled(self):
		doc = MagicMock()
		doc.disabled = True
		self.assertEqual(get_item_status(doc), "N")

	@patch("kenya_etims_compliance.custom_methods.item.item_code_increment")
	def test_create_item_digit_code_empty(self, mock_increment):
		mock_increment.return_value = []
		doc = MagicMock()
		result = create_item_digit_code(doc)
		self.assertEqual(result, "0000001")

	@patch("kenya_etims_compliance.custom_methods.item.item_code_increment")
	def test_create_item_digit_code_existing(self, mock_increment):
		mock_increment.return_value = ["0000001", "0000005"]
		doc = MagicMock()
		result = create_item_digit_code(doc)
		self.assertEqual(result, "0000006")

	@patch("kenya_etims_compliance.custom_methods.item.get_taxation_type", return_value="A")
	@patch("kenya_etims_compliance.custom_methods.item.get_item_code", return_value="ORIGTYPEPKQT0000001")
	@patch("kenya_etims_compliance.custom_methods.item.get_item_prices", return_value=100.0)
	@patch("kenya_etims_compliance.custom_methods.item.get_item_type_code", return_value="TYPE")
	@patch("kenya_etims_compliance.custom_methods.item.get_item_qty_unit_codes", return_value="QT")
	@patch("kenya_etims_compliance.custom_methods.item.get_item_pkg_unit_codes", return_value="PK")
	@patch("kenya_etims_compliance.custom_methods.item.frappe.throw")
	def test_autofill_tims_info(
		self,
		mock_throw,
		mock_pkg,
		mock_qty,
		mock_type,
		mock_prices,
		mock_code,
		mock_tax,
	):
		doc = MagicMock()
		doc.custom_update_item_to_tims = 1
		doc.item_code = "ITEM001"
		doc.item_name = "Item Name"
		doc.custom_default_quantity_unit = "Each"
		doc.custom_default_packing_unit = "Box"
		doc.disabled = False
		doc.taxes = [MagicMock()]
		doc.owner = "owner@example.com"
		doc.modified_by = "modifier@example.com"
		doc.custom_default_unit_price = None
		doc.custom_item_code = None
		doc.custom_origin_place_code_nation = "ORIG"

		autofill_tims_info(doc, None)

		self.assertEqual(doc.custom_item_name, "ITEM001")
		self.assertEqual(doc.custom_item_standard_name, "Item Name")
		self.assertEqual(doc.custom_quantity_unit_code, "QT")
		self.assertEqual(doc.custom_packaging_unit_code, "PK")
		self.assertEqual(doc.custom_used__unused, "Y")
		self.assertEqual(doc.custom_item_type_code, "TYPE")
		self.assertEqual(doc.custom_registration_id, "owner@example.com")
		self.assertEqual(doc.custom_registration_name, "owner@example.com")
		self.assertEqual(doc.custom_modifier_id, "modifier@example.com")
		self.assertEqual(doc.custom_modifier_name, "modifier@example.com")
		self.assertEqual(doc.custom_taxation_type_code, "A")
		self.assertEqual(doc.custom_default_unit_price, 100.0)
		self.assertEqual(doc.custom_item_code, "ORIGTYPEPKQT0000001")
		mock_throw.assert_not_called()


class TestStockCustomMethods(FrappeTestCase):
	"""Tests for kenya_etims_compliance.custom_methods.stock"""

	@patch("kenya_etims_compliance.custom_methods.stock.frappe.db.get_all")
	def test_insert_tax_rate_and_amount(self, mock_get_all):
		mock_get_all.return_value = [{"tax_rate": 16.0}]

		item1 = MockRow(custom_tax_code="B", basic_amount=116.0)
		item2 = MockRow(custom_tax_code="E", basic_amount=100.0)

		doc = MagicMock()
		doc.items = [item1, item2]

		insert_tax_rate_and_amount(doc, None)

		self.assertEqual(item1.custom_rate, 16.0)
		self.assertEqual(item1.custom_tax_amount, round(16.0, 2))

		expected_tax2 = round(100 - 100 / 1.16, 2)
		self.assertAlmostEqual(item2.custom_tax_amount, expected_tax2, places=2)

		expected_total_tax = round(16.0 + expected_tax2, 2)
		expected_total_taxable = round(216 - (16.0 + expected_tax2), 2)
		self.assertEqual(doc.custom_total_tax_amount, expected_total_tax)
		self.assertEqual(doc.custom_total_taxable_amount, expected_total_taxable)

	@patch("kenya_etims_compliance.custom_methods.stock.frappe.get_doc")
	def test_check_if_interbranch_different(self, mock_get_doc):
		wh1 = MagicMock()
		wh1.get = MagicMock(return_value="001")
		wh2 = MagicMock()
		wh2.get = MagicMock(return_value="002")

		mock_get_doc.side_effect = [wh1, wh2]

		item = MockRow(from_warehouse="WH-001", to_warehouse="WH-002")
		result = check_if_interbranch(item)
		self.assertTrue(result)

	@patch("kenya_etims_compliance.custom_methods.stock.frappe.get_doc")
	def test_check_if_interbranch_same(self, mock_get_doc):
		wh1 = MagicMock()
		wh1.get = MagicMock(return_value="001")
		wh2 = MagicMock()
		wh2.get = MagicMock(return_value="001")

		mock_get_doc.side_effect = [wh1, wh2]

		item = MockRow(from_warehouse="WH-001", to_warehouse="WH-002")
		result = check_if_interbranch(item)
		self.assertFalse(result)


class TestSalesInvoiceCustomMethods(FrappeTestCase):
	"""Tests for kenya_etims_compliance.custom_methods.sales_invoice"""

	@patch("kenya_etims_compliance.custom_methods.sales_invoice.frappe.db.get_all")
	def test_validate_inv_number(self, mock_get_all):
		mock_get_all.return_value = [
			{"name": "SINV-001", "custom_invoice_number": 10},
			{"name": "SINV-002", "custom_invoice_number": 20},
			{"name": "SINV-003", "custom_invoice_number": 30},
		]

		doc = MagicMock()
		doc.name = "SINV-002"

		result = validate_inv_number(doc)
		self.assertNotIn(20, result)
		self.assertIn(10, result)
		self.assertIn(30, result)

	def test_get_total_discount_with_discount(self):
		item1 = MockRow(discount_percentage=10, custom_discount_amount_kes=5, qty=2)
		item2 = MockRow(discount_percentage=0, custom_discount_amount_kes=0, qty=1)
		doc = MagicMock()
		doc.items = [item1, item2]
		result = get_total_discount(doc)
		self.assertEqual(result, 10.0)

	def test_get_total_discount_without_discount(self):
		item1 = MockRow(discount_percentage=0, custom_discount_amount_kes=0, qty=1)
		doc = MagicMock()
		doc.items = [item1]
		result = get_total_discount(doc)
		self.assertEqual(result, 0)

	@patch("kenya_etims_compliance.custom_methods.sales_invoice.frappe.db.get_all")
	@patch("kenya_etims_compliance.custom_methods.sales_invoice.frappe.db.set_value")
	@patch("kenya_etims_compliance.custom_methods.sales_invoice.get_taxable_amounts")
	def test_insert_tax_amounts(self, mock_get_taxable_amounts, mock_set_value, mock_get_all):
		mock_get_taxable_amounts.return_value = {"A": 100.0, "B": 200.0}
		mock_get_all.return_value = [{"custom_code_name": "VAT A"}]

		tax_item1 = MockRow(custom_code="A", name="TAX-001")
		tax_item2 = MockRow(custom_code="B", name="TAX-002")
		doc = MagicMock()
		doc.items = [MagicMock()]
		doc.taxes = [tax_item1, tax_item2]

		insert_tax_amounts(doc)

		mock_set_value.assert_any_call(
			"Sales Taxes and Charges",
			"TAX-001",
			{"custom_total_taxable_amount": 100.0, "custom_code_name": "VAT A"},
			update_modified=True,
		)
		mock_set_value.assert_any_call(
			"Sales Taxes and Charges",
			"TAX-002",
			{"custom_total_taxable_amount": 200.0, "custom_code_name": "VAT A"},
			update_modified=True,
		)
		self.assertEqual(mock_set_value.call_count, 2)


class TestPurchaseInvoiceCustomMethods(FrappeTestCase):
	"""Tests for kenya_etims_compliance.custom_methods.purchase_invoice"""

	@patch("kenya_etims_compliance.custom_methods.purchase_invoice.insert_invoice_number")
	@patch("kenya_etims_compliance.custom_methods.purchase_invoice.validate_inv_number")
	@patch("kenya_etims_compliance.custom_methods.purchase_invoice.frappe.db.exists")
	def test_validate(self, mock_exists, mock_validate_inv_number, mock_insert_invoice_number):
		mock_exists.return_value = True
		mock_validate_inv_number.return_value = [10, 20, 30]

		doc = MagicMock()
		doc.custom_invoice_number = 20
		doc.name = "PINV-001"

		validate_purchase_invoice(doc, None)

		mock_exists.assert_called_once_with("Purchase Invoice", {"name": "PINV-001"})
		mock_validate_inv_number.assert_called_once_with(doc)
		mock_insert_invoice_number.assert_called_once_with(doc, None)

	def test_get_total_discount_with_discount(self):
		item1 = MockRow(discount_percentage=10, discount_amount=5, qty=2)
		item2 = MockRow(discount_percentage=0, discount_amount=0, qty=1)
		doc = MagicMock()
		doc.items = [item1, item2]
		result = get_purchase_total_discount(doc)
		self.assertEqual(result, 10.0)

	def test_get_total_discount_without_discount(self):
		item1 = MockRow(discount_percentage=0, discount_amount=0, qty=1)
		doc = MagicMock()
		doc.items = [item1]
		result = get_purchase_total_discount(doc)
		self.assertEqual(result, 0)


class TestPaymentEntryCustomMethods(FrappeTestCase):
	"""Tests for kenya_etims_compliance.custom_methods.payment_entry"""

	@patch("kenya_etims_compliance.custom_methods.payment_entry.get_etims_settings")
	@patch("kenya_etims_compliance.custom_methods.payment_entry.frappe.get_doc")
	@patch("kenya_etims_compliance.custom_methods.payment_entry.frappe.throw")
	def test_validate_payment_unverified_blocks(self, mock_throw, mock_get_doc, mock_settings):
		mock_settings.return_value = {"enforce_invoice_verification": 1, "allow_payment_unverified": 0}

		inv = MagicMock()
		inv.name = "PINV-001"
		inv.supplier = "Supplier A"
		inv.grand_total = 1000
		inv.custom_invoice_verified = 0
		inv.custom_kra_invoice_number = ""
		inv.get = MagicMock(side_effect=lambda k, default=None: getattr(inv, k, default))
		mock_get_doc.return_value = inv

		ref = MockRow(reference_doctype="Purchase Invoice", reference_name="PINV-001", allocated_amount=500)
		doc = MagicMock()
		doc.references = [ref]

		validate_payment_for_etims_invoice(doc, None)

		mock_throw.assert_called_once()
		self.assertIn("Cannot make payment", str(mock_throw.call_args))

	@patch("kenya_etims_compliance.custom_methods.payment_entry.get_etims_settings")
	@patch("kenya_etims_compliance.custom_methods.payment_entry.frappe.get_doc")
	def test_validate_payment_verified_passes(self, mock_get_doc, mock_settings):
		mock_settings.return_value = {"enforce_invoice_verification": 1, "allow_payment_unverified": 0}

		inv = MagicMock()
		inv.name = "PINV-001"
		inv.supplier = "Supplier A"
		inv.grand_total = 1000
		inv.custom_invoice_verified = 1
		inv.custom_kra_invoice_number = "KRA-123"
		inv.custom_verification_override_reason = ""
		inv.get = MagicMock(side_effect=lambda k, default=None: getattr(inv, k, default))
		mock_get_doc.return_value = inv

		ref = MockRow(reference_doctype="Purchase Invoice", reference_name="PINV-001", allocated_amount=500)
		doc = MagicMock()
		doc.references = [ref]

		# Should not raise
		validate_payment_for_etims_invoice(doc, None)

	@patch("kenya_etims_compliance.custom_methods.payment_entry.get_etims_settings")
	@patch("kenya_etims_compliance.custom_methods.payment_entry.frappe.get_doc")
	@patch("kenya_etims_compliance.custom_methods.payment_entry.frappe.msgprint")
	def test_validate_payment_manual_verified_notice(self, mock_msgprint, mock_get_doc, mock_settings):
		mock_settings.return_value = {"enforce_invoice_verification": 1, "allow_payment_unverified": 0}

		inv = MagicMock()
		inv.name = "PINV-001"
		inv.supplier = "Supplier A"
		inv.grand_total = 1000
		inv.custom_invoice_verified = 1
		inv.custom_kra_invoice_number = "MANUAL_OVERRIDE"
		inv.custom_verification_override_reason = "Override reason"
		inv.get = MagicMock(side_effect=lambda k, default=None: getattr(inv, k, default))
		mock_get_doc.return_value = inv

		ref = MockRow(reference_doctype="Purchase Invoice", reference_name="PINV-001", allocated_amount=500)
		doc = MagicMock()
		doc.references = [ref]

		validate_payment_for_etims_invoice(doc, None)

		mock_msgprint.assert_called_once()
		self.assertIn("manually verified", str(mock_msgprint.call_args).lower())


class TestInvoiceCheckerCustomMethods(FrappeTestCase):
	"""Tests for kenya_etims_compliance.custom_methods.invoice_checker"""

	@patch("kenya_etims_compliance.custom_methods.invoice_checker.frappe.has_permission")
	@patch("kenya_etims_compliance.custom_methods.invoice_checker.eTIMS.invoiceCheckerReq")
	def test_check_invoice_validity_success(self, mock_checker, mock_has_perm):
		mock_has_perm.return_value = True
		mock_checker.return_value = {
			"Success": {
				"qrCode": "QR123",
				"invcNo": "INV001",
				"spplrTin": "A000000000",
				"invcDt": "20260115",
				"totAmt": 5000,
			}
		}

		result = check_invoice_validity("INV001", "A000000000", "2026-01-15", 5000)

		self.assertTrue(result["valid"])
		self.assertEqual(result["qr_code"], "QR123")
		self.assertEqual(result["kra_invoice_number"], "INV001")

	@patch("kenya_etims_compliance.custom_methods.invoice_checker.frappe.has_permission")
	@patch("kenya_etims_compliance.custom_methods.invoice_checker.eTIMS.invoiceCheckerReq")
	def test_check_invoice_validity_failure(self, mock_checker, mock_has_perm):
		mock_has_perm.return_value = True
		mock_checker.return_value = {"Error": "Invoice not found"}

		result = check_invoice_validity("INV001", "A000000000", "2026-01-15", 5000)

		self.assertFalse(result["valid"])
		self.assertIn("Invoice not found", result["error"])


class TestQueueProcessorCustomMethods(FrappeTestCase):
	"""Tests for kenya_etims_compliance.custom_methods.queue_processor"""

	@patch("kenya_etims_compliance.custom_methods.queue_processor.get_etims_settings")
	def test_should_use_queue_enabled(self, mock_settings):
		mock_settings.return_value = {"enable_queue": 1}
		self.assertTrue(should_use_queue())

	@patch("kenya_etims_compliance.custom_methods.queue_processor.get_etims_settings")
	def test_should_use_queue_disabled(self, mock_settings):
		mock_settings.return_value = {"enable_queue": 0}
		self.assertFalse(should_use_queue())

	@patch("kenya_etims_compliance.custom_methods.queue_processor.frappe.has_permission")
	@patch("kenya_etims_compliance.custom_methods.queue_processor.frappe.db.count")
	def test_get_queue_status(self, mock_count, mock_has_perm):
		mock_has_perm.return_value = True
		mock_count.side_effect = [5, 2, 10, 1, 0]

		result = get_queue_status()

		self.assertEqual(result["Queued"], 5)
		self.assertEqual(result["Processing"], 2)
		self.assertEqual(result["Sent"], 10)
		self.assertEqual(result["Failed"], 1)
		self.assertEqual(result["Cancelled"], 0)
		self.assertEqual(result["total"], 18)


if __name__ == "__main__":
	import unittest

	loader = unittest.TestLoader()
	suite = unittest.TestSuite()
	suite.addTests(loader.loadTestsFromTestCase(TestItemCustomMethods))
	suite.addTests(loader.loadTestsFromTestCase(TestStockCustomMethods))
	suite.addTests(loader.loadTestsFromTestCase(TestSalesInvoiceCustomMethods))
	suite.addTests(loader.loadTestsFromTestCase(TestPurchaseInvoiceCustomMethods))
	suite.addTests(loader.loadTestsFromTestCase(TestPaymentEntryCustomMethods))
	suite.addTests(loader.loadTestsFromTestCase(TestInvoiceCheckerCustomMethods))
	suite.addTests(loader.loadTestsFromTestCase(TestQueueProcessorCustomMethods))
	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)
	exit(0 if result.wasSuccessful() else 1)
