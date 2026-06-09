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


class TestRealtimeEmit(FrappeTestCase):
    @patch("kenya_etims_compliance.custom_methods.queue_processor.frappe")
    def test_emit_after_qr_written(self, frappe_mock):
        # Arrange a doc whose QR is set; call the private helper directly.
        from kenya_etims_compliance.custom_methods import queue_processor as qp
        from kenya_etims_compliance.custom_methods import sales_invoice as si

        doc = MagicMock()
        doc.name = "SINV-0009"
        doc.custom_receipt_qr_url = "https://etims.kra.go.ke/...sig"
        doc.posting_date = "2026-06-09"
        frappe_mock.get_doc.return_value = doc
        # Patch the eTIMS date helpers too so the test exercises only the emit, not real
        # date parsing of the sdcDateTime literal.
        # NOTE: create_qr_code/create_attachment/create_sales_receipt/stockIOSaveReq are
        # imported function-locally from custom_methods.sales_invoice (hoisting them to
        # queue_processor's top would create a circular import via
        # sales_invoice -> queue_processor), so they are patched at their SOURCE module.
        with patch.object(qp, "eTIMS") as etims_mock, \
             patch.object(si, "create_qr_code", return_value=("f.png", "https://etims.kra.go.ke/...sig")), \
             patch.object(si, "create_attachment", return_value="/private/files/f.png"), \
             patch.object(si, "create_sales_receipt"), \
             patch.object(si, "stockIOSaveReq"), \
             patch.object(qp, "KRAClient"):
            etims_mock.strp_datetime_object.return_value = None
            etims_mock.strp_date_object.return_value = None
            etims_mock.strp_time_object.return_value = None
            etims_mock.strf_date_object.return_value = "20260609"
            qp._handle_sales_invoice_success(
                "SINV-0009",
                {"sdcDateTime": "20260609120000", "rcptSign": "sig"},
                MagicMock(branch_id=""),
            )
        # Assert a publish_realtime call for our event/invoice happened
        calls = [
            c
            for c in frappe_mock.publish_realtime.call_args_list
            if c.args and c.args[0] == "etims_invoice_signed"
        ]
        self.assertTrue(calls, "expected etims_invoice_signed emit")
        payload = calls[0].args[1] if len(calls[0].args) > 1 else calls[0].kwargs.get("message")
        self.assertEqual(payload["invoice"], "SINV-0009")
        self.assertTrue(calls[0].kwargs.get("after_commit"))
