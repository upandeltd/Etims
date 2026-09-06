"""Unit tests for ``escpos_qr`` length-prefix handling and omission logging.

``escpos_qr`` builds a raw ESC/POS command string for print-format Jinja
templates. It must never raise (see the module docstring in escpos.py), and
when it can't safely emit a QR code it must say so via frappe.log_error
instead of silently returning "" with no trace — a receipt whose KRA-issued
verification-URL signature happens to land in an unsafe length range would
otherwise lose its QR code with zero visibility.

These tests stub frappe.log_error so no site connection is required.
"""
import unittest
from unittest import mock

try:
	from kenya_etims_compliance.utils import escpos

	_IMPORT_OK = True
except Exception:  # pragma: no cover - frappe not importable in this context
	_IMPORT_OK = False


@unittest.skipUnless(_IMPORT_OK, "kenya_etims_compliance.utils.escpos unavailable")
class TestEscposQr(unittest.TestCase):
	def setUp(self):
		self._p = mock.patch.object(escpos.frappe, "log_error", lambda *a, **k: None, create=True)
		self._p.start()
		self.addCleanup(self._p.stop)

	def test_short_url_returns_command(self):
		"""Regression: existing short-data behavior is unchanged."""
		url = "https://etims-sbx.kra.go.ke/x?Data=" + "A" * 5  # ~41 chars
		result = escpos.escpos_qr(url)
		self.assertTrue(result)
		self.assertTrue(result.startswith(escpos._GS_K))

	def test_no_data_returns_empty(self):
		self.assertEqual(escpos.escpos_qr(""), "")
		self.assertEqual(escpos.escpos_qr(None), "")

	def test_300_char_url_now_supported(self):
		"""The old hardcoded-128 cap silently dropped this length even though
		it is genuinely byte-safe: store_len=303 -> pL=47, pH=1, both < 128."""
		url = "A" * 300
		result = escpos.escpos_qr(url)
		self.assertTrue(result)
		self.assertTrue(result.startswith(escpos._GS_K))

	def test_unsafe_length_returns_empty_and_logs(self):
		"""A length landing in the pL>=128 gap (200 chars -> store_len=203,
		pL=203) — close to a realistic KRA receipt-verification URL — must be
		refused AND logged, not silently dropped."""
		url = "A" * 200
		with mock.patch.object(escpos.frappe, "log_error", create=True) as mock_log:
			result = escpos.escpos_qr(url)
		self.assertEqual(result, "")
		mock_log.assert_called_once()
		self.assertIn("eTIMS", mock_log.call_args[1].get("title", ""))

	def test_module_size_and_ec_level_out_of_range_fall_back_to_defaults(self):
		result = escpos.escpos_qr("short", module_size=999, ec_level="Z")
		self.assertTrue(result)


if __name__ == "__main__":
	unittest.main()
