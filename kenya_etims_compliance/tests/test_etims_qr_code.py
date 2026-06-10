"""Unit tests for ``create_qr_code`` / ``create_attachment`` hardening.

``create_qr_code`` runs inside the eTIMS post-success handler *after* the queue
status is committed "Sent". It must therefore be total (always return a
2-tuple) and never raise — otherwise the document save is aborted and the
receipt signature + control-unit data are silently lost (a compliance defect,
not just a missing QR).

These tests stub the frappe DB/site access and segno so no site connection or
disk write is required.
"""
import unittest
from unittest import mock

try:
    from kenya_etims_compliance.custom_methods import sales_invoice as si
    _IMPORT_OK = True
except Exception:  # pragma: no cover - frappe not importable in this context
    _IMPORT_OK = False

_SIG = "A1B2C3D4E5F6G7H8"


@unittest.skipUnless(_IMPORT_OK, "kenya_etims_compliance.custom_methods.sales_invoice unavailable")
class TestCreateQrCode(unittest.TestCase):
    def setUp(self):
        self._p = [
            mock.patch.object(si.frappe, "get_site_path", lambda *a, **k: "/tmp/_qrtest.png"),
            mock.patch.object(si.frappe, "log_error", lambda *a, **k: None, create=True),
            mock.patch.object(si.frappe, "get_traceback", lambda *a, **k: "tb", create=True),
        ]
        for p in self._p:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._p])

    def test_returns_none_none_without_signature(self):
        self.assertEqual(si.create_qr_code("P051234567X", "00", ""), (None, None))

    def test_returns_none_none_without_active_device(self):
        with mock.patch.object(si.frappe.db, "get_all", return_value=[]):
            self.assertEqual(si.create_qr_code("P051234567X", "00", _SIG), (None, None))

    def test_production_host_and_full_url(self):
        with mock.patch.object(si.frappe.db, "get_all", return_value=[{"api_mode": "Production"}]), \
             mock.patch.object(si.segno, "make_qr"):
            file_name, url = si.create_qr_code("P051234567X", "00", _SIG)
        self.assertEqual(file_name, _SIG + ".png")
        self.assertTrue(url.startswith("https://etims.kra.go.ke"))
        self.assertTrue(url.endswith("P051234567X" "00" + _SIG))

    def test_sandbox_host(self):
        with mock.patch.object(si.frappe.db, "get_all", return_value=[{"api_mode": "Sandbox"}]), \
             mock.patch.object(si.segno, "make_qr"):
            _, url = si.create_qr_code("P051234567X", "00", _SIG)
        self.assertTrue(url.startswith("https://etims-sbx.kra.go.ke"))

    def test_segno_failure_keeps_url_and_never_raises(self):
        def boom(*a, **k):
            raise RuntimeError("boom")
        with mock.patch.object(si.frappe.db, "get_all", return_value=[{"api_mode": "Production"}]), \
             mock.patch.object(si.segno, "make_qr", boom):
            file_name, url = si.create_qr_code("P051234567X", "00", _SIG)
        self.assertIsNone(file_name)  # PNG attachment skipped
        self.assertTrue(url.startswith("https://etims.kra.go.ke"))  # thermal QR still works

    def test_create_attachment_skips_when_file_name_falsy(self):
        self.assertIsNone(si.create_attachment(None, "ACC-SINV-0001"))
        self.assertIsNone(si.create_attachment("", "ACC-SINV-0001"))


if __name__ == "__main__":
    unittest.main()
