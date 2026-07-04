"""Tests for bulk_update_and_register_items (the list-view "Update Item To TIMS").

Verifies the enable+autofill+register flow: valid items are saved (flag on) and
registered, invalid items are skipped & reported, and a KRA failure rolls back
only that item.
"""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from kenya_etims_compliance.custom_methods import bulk_operations as bulk
from kenya_etims_compliance.custom_methods import item as item_mod
from kenya_etims_compliance.utils import etims_utils


class TestBulkUpdateAndRegister(FrappeTestCase):
    @patch.object(etims_utils, "eTIMS")
    @patch.object(item_mod, "validate_item_for_etims")
    @patch.object(bulk, "frappe")
    def test_skips_invalid_and_registers_valid(self, frappe_mock, validate_mock, etims_mock):
        validate_mock.side_effect = lambda n: (
            {"valid": True} if n == "GOOD" else {"valid": False, "errors": ["missing classification"]}
        )
        doc = MagicMock()
        doc.custom_update_item_to_tims = 0
        frappe_mock.get_doc.return_value = doc
        etims_mock.itemSaveReq.return_value = {"Success": "ok"}

        out = bulk.bulk_update_and_register_items(["GOOD", "BAD"])

        self.assertEqual(out["total"], 2)
        self.assertEqual(out["success"], 1)
        self.assertEqual(out["failed"], 1)
        self.assertEqual([i["item"] for i in out["invalid"]], ["BAD"])
        doc.save.assert_called_once()  # flag enabled + autofilled
        etims_mock.itemSaveReq.assert_called_once_with("GOOD")

    @patch.object(etims_utils, "eTIMS")
    @patch.object(item_mod, "validate_item_for_etims")
    @patch.object(bulk, "frappe")
    def test_kra_failure_rolls_back_that_item(self, frappe_mock, validate_mock, etims_mock):
        validate_mock.return_value = {"valid": True}
        doc = MagicMock()
        doc.custom_update_item_to_tims = 0
        frappe_mock.get_doc.return_value = doc
        etims_mock.itemSaveReq.return_value = {"Error": "Item not registered"}

        out = bulk.bulk_update_and_register_items(["X"])

        self.assertEqual(out["success"], 0)
        self.assertEqual(out["failed"], 1)
        self.assertEqual(out["invalid"][0]["item"], "X")
        # The item's partial changes were rolled back to its savepoint.
        frappe_mock.db.rollback.assert_called_with(save_point="etims_bulk_item")

    @patch.object(bulk, "frappe")
    def test_empty_selection_is_noop(self, frappe_mock):
        out = bulk.bulk_update_and_register_items([])
        self.assertEqual(out, {"total": 0, "success": 0, "failed": 0, "invalid": []})
