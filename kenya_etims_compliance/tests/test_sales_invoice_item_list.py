from unittest.mock import MagicMock, patch

from frappe import _dict
from frappe.tests.utils import FrappeTestCase

from kenya_etims_compliance.custom_methods import sales_invoice as si

ITEM_DETAIL = {
    "custom_item_code": "KE0VRU0000001",
    "custom_item_classification_code": "50110000",
    "custom_item_name": "Raw Meat",
    "custom_packaging_unit_code": "VR",
    "custom_quantity_unit_code": "U",
}


def _row(item_code="Raw Meat", qty=1, rate=100, tax_template="VAT-A-Exempt - MBL"):
    amount = qty * rate
    return _dict(
        {
            "idx": 1,
            "item_code": item_code,
            "qty": qty,
            "base_rate": rate,
            "base_amount": amount,
            "base_net_amount": amount,
            "item_tax_template": tax_template,
            "custom_discount_amount_kes": 0,
            "discount_percentage": 0,
            "custom_maintain_stock": 1,
        }
    )


class TestEtimsSaleItemListSales(FrappeTestCase):
    """The saveTrnsSalesOsdc item-list builder: merge-by-(itemCd, taxTyCd) and
    the prc/splyAmt reconstruction identity KRA's per-item check relies on.
    """

    @patch("kenya_etims_compliance.custom_methods.sales_invoice.split_item_tax")
    @patch("kenya_etims_compliance.custom_methods.sales_invoice.get_tax_template_details")
    @patch("kenya_etims_compliance.custom_methods.sales_invoice.frappe")
    def test_merge_reconstructs_supply_amount_at_multiple_rates(
        self, frappe_mock, tax_code_mock, split_tax_mock
    ):
        # Same item, same tax band, two different rates -- exactly the
        # ACC-SINV-2026-00031 return/credit shape that triggered KRA 910
        # "Supply/Taxable/Total amount is incorrect for item KE0VRU0000001".
        doc = MagicMock()
        doc.items = [
            _row(qty=276, rate=700),
            _row(qty=4, rate=900),
        ]
        frappe_mock.db.get_all.return_value = [ITEM_DETAIL]
        tax_code_mock.return_value = "A"
        split_tax_mock.side_effect = lambda gross, *_: (abs(gross), 0)

        result = si.etims_sale_item_list_sales(doc)

        self.assertEqual(len(result), 1, "same item/tax-band rows must merge into one itemList entry")
        row = result[0]
        self.assertEqual(row["qty"], 280)
        self.assertEqual(row["splyAmt"], 196800.0)
        # The bug: rounding prc to 2dp before this multiply drifts splyAmt by
        # ~0.80 at this quantity, which is what KRA's cross-check rejected.
        self.assertAlmostEqual(row["qty"] * row["prc"], row["splyAmt"], delta=0.01)

    @patch("kenya_etims_compliance.custom_methods.sales_invoice.split_item_tax")
    @patch("kenya_etims_compliance.custom_methods.sales_invoice.get_tax_template_details")
    @patch("kenya_etims_compliance.custom_methods.sales_invoice.frappe")
    def test_single_row_recovers_exact_rate(self, frappe_mock, tax_code_mock, split_tax_mock):
        doc = MagicMock()
        doc.items = [_row(qty=10, rate=700)]
        frappe_mock.db.get_all.return_value = [ITEM_DETAIL]
        tax_code_mock.return_value = "A"
        split_tax_mock.side_effect = lambda gross, *_: (abs(gross), 0)

        result = si.etims_sale_item_list_sales(doc)

        self.assertEqual(result[0]["prc"], 700)

    @patch("kenya_etims_compliance.custom_methods.sales_invoice.split_item_tax")
    @patch("kenya_etims_compliance.custom_methods.sales_invoice.get_tax_template_details")
    @patch("kenya_etims_compliance.custom_methods.sales_invoice.frappe")
    def test_different_tax_bands_stay_separate(self, frappe_mock, tax_code_mock, split_tax_mock):
        doc = MagicMock()
        doc.items = [
            _row(qty=1, rate=700, tax_template="VAT-A-Exempt - MBL"),
            _row(qty=1, rate=700, tax_template="VAT-B-16% - MBL"),
        ]
        frappe_mock.db.get_all.return_value = [ITEM_DETAIL]
        tax_code_mock.side_effect = ["A", "B"]
        split_tax_mock.side_effect = lambda gross, *_: (abs(gross), 0)

        result = si.etims_sale_item_list_sales(doc)

        self.assertEqual(len(result), 2, "rows sharing an item but not a tax band must stay separate")


class TestEtimsSaleItemListStock(FrappeTestCase):
    """stockIOSaveReq does `if len(etims_sale_item_list_stock(doc)):` -- the
    builder must always return a list, never fall through to an implicit
    None (the exact bug that crashed post-signing stock sync for every
    invoice: TypeError: object of type 'NoneType' has no len()).
    """

    @patch("kenya_etims_compliance.custom_methods.sales_invoice.split_item_tax")
    @patch("kenya_etims_compliance.custom_methods.sales_invoice.get_tax_template_details")
    @patch("kenya_etims_compliance.custom_methods.sales_invoice.frappe")
    def test_returns_list_with_stock_items(self, frappe_mock, tax_code_mock, split_tax_mock):
        doc = MagicMock()
        doc.items = [_row(qty=5, rate=100)]
        frappe_mock.db.get_all.return_value = [ITEM_DETAIL]
        tax_code_mock.return_value = "A"
        split_tax_mock.side_effect = lambda gross, *_: (abs(gross), 0)

        result = si.etims_sale_item_list_stock(doc)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_returns_empty_list_without_stock_items(self):
        doc = MagicMock()
        row = _row()
        row["custom_maintain_stock"] = 0
        doc.items = [row]

        result = si.etims_sale_item_list_stock(doc)

        self.assertEqual(result, [])
