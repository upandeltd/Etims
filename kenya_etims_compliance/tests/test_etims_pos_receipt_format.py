"""Render-level regression tests for the Kenya eTIMS POS Receipt print format.

These render the *actual shipped* ``raw_commands`` template (read from the
print-format JSON) through a Jinja env that mirrors Frappe's — a
``SandboxedEnvironment`` WITHOUT ``trim_blocks``/``lstrip_blocks`` — so the
blank-line behaviour matches production. No Frappe site/DB is required:
``frappe`` is mocked and the real ``escpos_qr`` helper is used.

Covers the three reported issues:
  1. Non-VAT business must NOT print VAT breakdown (Total VAT / TAX SUMMARY /
     "Prices Inclusive of VAT").
  2. QR command must be emitted for a real-length KRA URL.
  3. Spacing: no large runs of blank lines (the un-trimmed Jinja bug).
"""
import json
import os
import re
import unittest
from types import SimpleNamespace

from jinja2.sandbox import SandboxedEnvironment

from kenya_etims_compliance.utils.escpos import escpos_qr

_JSON_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "kenya_etims_compliance",
    "print_format",
    "kenya_etims_pos_receipt",
    "kenya_etims_pos_receipt.json",
)

# Production-length KRA URL: base(77) + PIN(11) + branch(2) + signature(16) = 106
_QR_URL = (
    "https://etims.kra.go.ke/common/link/etims/receipt/indexEtimsReceiptData?Data="
    "P051234567X" "00" "A1B2C3D4E5F6G7H8"
)


class _D:
    """Dict-backed mock returning sane defaults for unset attributes."""

    _ZERO = ("amount", "qty", "total", "rate", "count", "number", "percentage",
             "docstatus", "copy", "taxable")

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __getattr__(self, name):
        return 0 if any(t in name for t in self._ZERO) else ""

    def get_formatted(self, field, *a, **k):
        return str(self.__dict__.get(field, ""))


class _FakeDB:
    def __init__(self, vat):
        self.vat = vat

    def get_value(self, *a, **k):
        return {}

    def get_single_value(self, doctype, field):
        if field == "vat_obligation":
            return "Registered" if self.vat else "Not Registered"
        return 0 if field == "training_mode" else None


def _make_doc(vat, signed=True):
    tax_code = "A" if vat else "D"
    items = [
        _D(item_name="Coca Cola 500ml", custom_tax_code=tax_code, qty=2,
           base_rate=80.0, base_amount=160.0, discount_percentage=0,
           custom_discount_amount_kes=0),
    ]
    taxes = ([_D(custom_code="A", custom_total_taxable_amount=189.66,
                 base_tax_amount_after_discount_amount=30.34)] if vat else [])
    return _D(
        company="Mama Mboga Stores Ltd", items=items, taxes=taxes,
        payments=[_D(mode_of_payment="Cash", amount=220.0)],
        meta=_D(is_submittable=1), docstatus=1, is_return=0,
        custom_original_invoice_number=0, name="ACC-SINV-2026-00042",
        owner="cashier@store.ke", custom_item_count=2, total_qty=3,
        base_net_total=(189.66 if vat else 220.0),
        custom_total_taxable_amount=(189.66 if vat else 0),
        custom_total_nontaxable_amount=(0 if vat else 220.0),
        base_total_taxes_and_charges=(30.34 if vat else 0),
        base_grand_total=220.0, paid_amount=220.0, change_amount=0,
        custom_etims_queue_status=("Sent" if signed else ""),
        custom_sales_control_unit=("KRACU0100000001" if signed else ""),
        custom_invoice_number=42,
        custom_current_receipt_number=42, custom_total_receipt_number=42,
        custom_receipt_label="NS",
        custom_control_unit_date=("2026-06-10" if signed else ""),
        custom_control_unit_time=("14:39:00" if signed else ""),
        custom_internal_data=("ABCD1234EFGH5678IJKL9012MNOP" if signed else ""),
        custom_receipt_signature=("A1B2C3D4E5F6G7H8" if signed else ""),
        custom_receipt_qr_url=(_QR_URL if signed else ""),
    )


def _load_template():
    with open(os.path.normpath(_JSON_PATH)) as f:
        return json.load(f)["raw_commands"]


def _render(vat, signed=True):
    env = SandboxedEnvironment()  # mirrors Frappe: no trim_blocks/lstrip_blocks
    env.filters["safe"] = lambda v: v
    frappe = SimpleNamespace(
        get_doc=lambda dt, name: _D(tax_id="P051234567X"),
        db=_FakeDB(vat),
    )
    return env.from_string(_load_template()).render(
        doc=_make_doc(vat, signed), frappe=frappe, escpos_qr=escpos_qr,
    )


def _visible_lines(rendered):
    """Strip ESC/POS control bytes + the QR command blob; return text lines."""
    s = re.sub(r"\x1d\x28\x6b.*?\x1d\x03\x00\x31\x51\x30", "", rendered, flags=re.S)
    s = re.sub(r"[\x00-\x1f]", lambda m: "\n" if m.group() == "\n" else "", s)
    return s.split("\n")


def _max_blank_run(lines):
    run = best = 0
    for ln in lines:
        run = run + 1 if ln.strip() == "" else 0
        best = max(best, run)
    return best


class TestPosReceiptVatGating(unittest.TestCase):
    def test_non_vat_receipt_hides_all_vat_surfaces(self):
        out = _render(vat=False)
        self.assertNotIn("Total VAT", out)
        self.assertNotIn("TAX SUMMARY", out)
        self.assertNotIn("Prices Inclusive", out)
        # The non-taxable total still prints.
        self.assertIn("Non-Taxable Amount", out)

    def test_vat_receipt_shows_vat_surfaces(self):
        out = _render(vat=True)
        self.assertIn("Total VAT", out)
        self.assertIn("TAX SUMMARY", out)
        self.assertIn("Prices Inclusive", out)


class TestPosReceiptSpacing(unittest.TestCase):
    def test_no_large_blank_runs_vat(self):
        # Pre-fix this section produced ~30 consecutive blank lines.
        self.assertLessEqual(_max_blank_run(_visible_lines(_render(vat=True))), 2)

    def test_no_large_blank_runs_non_vat(self):
        self.assertLessEqual(_max_blank_run(_visible_lines(_render(vat=False))), 2)


class TestPosReceiptSignedState(unittest.TestCase):
    def test_signed_invoice_shows_control_unit_block(self):
        out = _render(vat=True, signed=True)
        self.assertIn("CONTROL UNIT FISCAL DETAILS", out)
        self.assertNotIn("eTIMS verification pending", out)

    def test_unsigned_invoice_shows_pending_not_blank_fiscal_block(self):
        # An invoice that was never eTIMS-signed (no receipt signature) must NOT
        # print a CONTROL UNIT FISCAL DETAILS header with empty fields.
        out = _render(vat=False, signed=False)
        self.assertNotIn("CONTROL UNIT FISCAL DETAILS", out)
        self.assertIn("eTIMS verification pending", out)


class TestPosReceiptQr(unittest.TestCase):
    def test_escpos_qr_emits_for_real_length_url(self):
        self.assertTrue(escpos_qr(_QR_URL, 6, "M"))

    def test_qr_command_present_in_signed_render(self):
        # GS ( k QR store/print command prefix must appear once signed.
        self.assertIn("\x1d\x28\x6b", _render(vat=True, signed=True))

    def test_qr_absent_until_signed(self):
        self.assertNotIn("\x1d\x28\x6b", _render(vat=True, signed=False))


if __name__ == "__main__":
    unittest.main()
