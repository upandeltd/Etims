from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from kenya_etims_compliance.custom_methods import queue_processor as qp


class TestIsPrimarySubmission(FrappeTestCase):
    def test_primary_endpoints_per_doctype(self):
        self.assertTrue(qp._is_primary_submission("Sales Invoice", "save_sales"))
        self.assertTrue(qp._is_primary_submission("Purchase Invoice", "insert_purchase"))
        self.assertTrue(qp._is_primary_submission("Stock Entry", "insert_stock_io"))

    def test_auxiliary_endpoint_is_not_primary(self):
        # save_stock_master is a Sales Invoice's post-signing follow-up call,
        # never its fiscal submission.
        self.assertFalse(qp._is_primary_submission("Sales Invoice", "save_stock_master"))

    def test_unknown_doctype_has_no_primary_endpoint(self):
        self.assertFalse(qp._is_primary_submission("Stock Entry", "save_sales"))


class TestEnqueueInvoiceStatusGuard(FrappeTestCase):
    @patch("kenya_etims_compliance.custom_methods.queue_processor.frappe")
    def test_primary_endpoint_stamps_source_doc(self, frappe_mock):
        queue_entry = MagicMock(name="entry")
        queue_entry.name = "Q-1"
        frappe_mock.get_doc.return_value = queue_entry
        doc = MagicMock()
        doc.doctype = "Sales Invoice"
        doc.name = "ACC-SINV-2026-00099"

        qp.enqueue_invoice(doc=doc, payload={}, api_endpoint="save_sales")

        frappe_mock.db.set_value.assert_called_once()
        args = frappe_mock.db.set_value.call_args.args
        self.assertEqual(args[0], "Sales Invoice")
        self.assertEqual(args[1], "ACC-SINV-2026-00099")
        self.assertEqual(args[2]["custom_etims_queue_status"], "Queued")

    @patch("kenya_etims_compliance.custom_methods.queue_processor.frappe")
    def test_auxiliary_endpoint_does_not_touch_source_doc(self, frappe_mock):
        queue_entry = MagicMock(name="entry")
        queue_entry.name = "Q-2"
        frappe_mock.get_doc.return_value = queue_entry
        doc = MagicMock()
        doc.doctype = "Sales Invoice"
        doc.name = "ACC-SINV-2026-00099"

        qp.enqueue_invoice(doc=doc, payload={}, api_endpoint="save_stock_master")

        # The queue row is still created and the job still enqueued — only the
        # shared status write on the invoice itself must be skipped.
        queue_entry.insert.assert_called_once()
        frappe_mock.enqueue.assert_called_once()
        frappe_mock.db.set_value.assert_not_called()


class TestUpdateSourceStatusGuard(FrappeTestCase):
    @patch("kenya_etims_compliance.custom_methods.queue_processor.frappe")
    def test_primary_entry_writes_shared_status(self, frappe_mock):
        entry = MagicMock(
            reference_doctype="Sales Invoice",
            reference_name="ACC-SINV-2026-00029",
            api_endpoint="save_sales",
            retry_count=1,
        )
        qp._update_source_status(entry, "Failed", "boom")
        frappe_mock.db.set_value.assert_called_once_with(
            "Sales Invoice",
            "ACC-SINV-2026-00029",
            {
                "custom_etims_queue_status": "Failed",
                "custom_etims_last_error": "boom",
                "custom_etims_retry_count": 1,
            },
            update_modified=False,
        )
        frappe_mock.db.commit.assert_called_once()

    @patch("kenya_etims_compliance.custom_methods.queue_processor.frappe")
    def test_auxiliary_entry_never_clobbers_shared_status(self, frappe_mock):
        # This is the exact ACC-SINV-2026-00032 scenario: a save_stock_master
        # entry timing out must not overwrite the invoice's already-Sent
        # signed-receipt status with "Failed".
        entry = MagicMock(
            reference_doctype="Sales Invoice",
            reference_name="ACC-SINV-2026-00032",
            api_endpoint="save_stock_master",
            retry_count=1,
        )
        qp._update_source_status(entry, "Failed", "KRA API timed out after 30 seconds")
        frappe_mock.db.set_value.assert_not_called()
        # Still commits whatever the caller already staged.
        frappe_mock.db.commit.assert_called_once()


class TestHandleSuccessDispatch(FrappeTestCase):
    @patch("kenya_etims_compliance.custom_methods.queue_processor._handle_sales_invoice_success")
    @patch("kenya_etims_compliance.custom_methods.queue_processor._update_source_status")
    @patch("kenya_etims_compliance.custom_methods.queue_processor.frappe")
    def test_primary_success_dispatches_to_sales_invoice_handler(
        self, _frappe_mock, update_status_mock, handler_mock
    ):
        entry = MagicMock(
            reference_doctype="Sales Invoice",
            reference_name="ACC-SINV-2026-00029",
            api_endpoint="save_sales",
        )
        qp._handle_success(entry, {"Success": {"rcptSign": "sig"}})
        handler_mock.assert_called_once_with("ACC-SINV-2026-00029", {"rcptSign": "sig"}, entry)
        update_status_mock.assert_called_once_with(entry, "Sent", commit=False)

    @patch("kenya_etims_compliance.custom_methods.queue_processor._handle_sales_invoice_success")
    @patch("kenya_etims_compliance.custom_methods.queue_processor._update_source_status")
    @patch("kenya_etims_compliance.custom_methods.queue_processor.frappe")
    def test_auxiliary_success_never_reaches_sales_invoice_handler(
        self, frappe_mock, update_status_mock, handler_mock
    ):
        # Regression for the exact ACC-SINV-2026-00029 / 00032 bug: a
        # successful save_stock_master entry used to be fed into the
        # save_sales response parser (wrong shape -> guaranteed exception,
        # silently swallowed) and to re-stamp the shared status field.
        entry = MagicMock(
            reference_doctype="Sales Invoice",
            reference_name="ACC-SINV-2026-00032",
            api_endpoint="save_stock_master",
        )
        qp._handle_success(entry, {"Success": {}})
        handler_mock.assert_not_called()
        update_status_mock.assert_not_called()
        frappe_mock.db.commit.assert_called_once()


class TestRetrySingleEntry(FrappeTestCase):
    @patch("kenya_etims_compliance.custom_methods.queue_processor.frappe")
    def test_queued_entry_is_retryable(self, frappe_mock):
        entry = MagicMock(status="Queued", name="40")
        frappe_mock.get_doc.return_value = entry
        out = qp.retry_single_entry("40")
        self.assertEqual(out, {"status": "enqueued"})
        frappe_mock.enqueue.assert_called_once()

    @patch("kenya_etims_compliance.custom_methods.queue_processor.frappe")
    def test_failed_entry_is_retryable(self, frappe_mock):
        entry = MagicMock(status="Failed", name="41")
        frappe_mock.get_doc.return_value = entry
        qp.retry_single_entry("41")
        frappe_mock.enqueue.assert_called_once()

    @patch("kenya_etims_compliance.custom_methods.queue_processor.frappe")
    def test_sent_entry_is_rejected(self, frappe_mock):
        entry = MagicMock(status="Sent", name="42")
        frappe_mock.get_doc.return_value = entry
        frappe_mock.throw.side_effect = Exception("blocked")
        with self.assertRaises(Exception):
            qp.retry_single_entry("42")
        frappe_mock.enqueue.assert_not_called()
