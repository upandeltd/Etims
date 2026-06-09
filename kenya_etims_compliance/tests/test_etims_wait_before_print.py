from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
    get_etims_settings,
)
from kenya_etims_compliance.custom_methods import etims_status


class TestEtimsWaitSettings(FrappeTestCase):
    @patch(
        "kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings.frappe.get_single"
    )
    def test_wait_defaults_present_when_unset(self, get_single):
        # Single doc returns None for the new fields -> defaults must apply
        doc = MagicMock()
        doc.as_dict.return_value = {}
        doc.get.side_effect = lambda k, d=None: None
        get_single.return_value = doc
        settings = get_etims_settings()
        self.assertEqual(settings["wait_for_etims_before_print"], 1)
        self.assertEqual(settings["etims_print_wait_seconds"], 6)


class TestSigningStatus(FrappeTestCase):
    @patch("kenya_etims_compliance.custom_methods.etims_status.frappe")
    def test_returns_signed_payload(self, frappe_mock):
        frappe_mock.db.get_value.return_value = {
            "custom_update_invoice_in_tims": 1,
            "custom_etims_queue_status": "Sent",
            "custom_update_sales_to_etims": 1,
            "custom_receipt_qr_url": "https://etims.kra.go.ke/...",
            "custom_invoice_number": 42,
        }
        out = etims_status.get_etims_signing_status("SINV-0001")
        self.assertTrue(out["signing_enabled"])
        self.assertTrue(out["signed"])
        self.assertEqual(out["status"], "Sent")
        self.assertEqual(out["invoice_number"], 42)
        frappe_mock.has_permission.assert_called_once()

    @patch("kenya_etims_compliance.custom_methods.etims_status.frappe")
    def test_unsigned_invoice(self, frappe_mock):
        frappe_mock.db.get_value.return_value = {
            "custom_update_invoice_in_tims": 1,
            "custom_etims_queue_status": "Queued",
            "custom_update_sales_to_etims": 0,
            "custom_receipt_qr_url": None,
            "custom_invoice_number": None,
        }
        out = etims_status.get_etims_signing_status("SINV-0002")
        self.assertFalse(out["signed"])
        self.assertIsNone(out["qr_url"])

    @patch("kenya_etims_compliance.custom_methods.etims_status.frappe")
    def test_missing_invoice_returns_disabled(self, frappe_mock):
        frappe_mock.db.get_value.return_value = None
        out = etims_status.get_etims_signing_status("NOPE")
        self.assertFalse(out["signing_enabled"])
        self.assertFalse(out["signed"])
