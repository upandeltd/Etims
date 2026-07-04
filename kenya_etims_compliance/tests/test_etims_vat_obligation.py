"""Tests for the VAT-obligation enforcement layer.

A company with no VAT obligation must never charge or transmit VAT. The layer
has two parts, tested here:
  * enforce_vat_obligation (before_validate) — removes VAT-bearing tax rows
  * _normalize_payload_non_vat (build_sales_payload) — forces a clean band-D payload
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from kenya_etims_compliance.custom_methods import sales_invoice as si


def _tax(account, rate):
    """A stand-in Sales Taxes and Charges row supporting .get() and attributes."""
    t = SimpleNamespace(account_head=account, rate=rate)
    t.get = lambda k, d=None: getattr(t, k, d)
    return t


def _doc(taxes, *, etims_bound=1):
    """Stand-in Sales Invoice with a settable child table, like a real doc."""
    doc = SimpleNamespace(taxes=list(taxes), custom_update_invoice_in_tims=etims_bound)
    doc.get = lambda k, d=None: getattr(doc, k, d)
    doc.set = lambda k, v: setattr(doc, k, v)
    return doc


class TestEnforceVatObligation(FrappeTestCase):
    @patch.object(si, "get_etims_settings")
    def test_registered_company_is_noop(self, settings):
        settings.return_value = {"vat_obligation": "Registered"}
        doc = _doc([_tax("VAT", 16)])
        si.enforce_vat_obligation(doc, "before_validate")
        self.assertEqual(len(doc.taxes), 1)  # untouched

    @patch.object(si, "get_etims_settings")
    def test_non_etims_invoice_is_noop(self, settings):
        settings.return_value = {"vat_obligation": "Not Registered"}
        doc = _doc([_tax("VAT", 16)], etims_bound=0)
        si.enforce_vat_obligation(doc, "before_validate")
        self.assertEqual(len(doc.taxes), 1)  # out of scope

    @patch.object(si, "frappe")
    @patch.object(si, "get_etims_settings")
    def test_removes_only_vat_bearing_rows(self, settings, frappe_mock):
        settings.return_value = {"vat_obligation": "Not Registered"}
        # 16% VAT row removed; a 0%-rated (zero-rated/exempt) row kept.
        doc = _doc([_tax("VAT 16% - X", 16), _tax("Zero Rated - X", 0)])
        si.enforce_vat_obligation(doc, "before_validate")
        self.assertEqual([t.account_head for t in doc.taxes], ["Zero Rated - X"])
        frappe_mock.msgprint.assert_called_once()

    @patch.object(si, "get_etims_settings")
    def test_idempotent_when_no_rated_rows(self, settings):
        settings.return_value = {"vat_obligation": "Not Registered"}
        doc = _doc([_tax("Zero Rated - X", 0)])
        si.enforce_vat_obligation(doc, "before_validate")
        self.assertEqual(len(doc.taxes), 1)  # nothing to remove

    @patch.object(si, "get_etims_settings")
    def test_noop_when_no_tax_rows(self, settings):
        settings.return_value = {"vat_obligation": "Not Registered"}
        doc = _doc([])
        si.enforce_vat_obligation(doc, "before_validate")
        self.assertEqual(doc.taxes, [])


class TestNormalizePayloadNonVat(FrappeTestCase):
    def test_folds_all_bands_into_d_and_zeroes_vat(self):
        payload = {
            "totTaxblAmt": 1000,
            "totTaxAmt": 160,
            # A pre-existing VAT (B) band that must be wiped:
            "taxblAmtB": 1000, "taxAmtB": 160, "taxRtB": 16,
            "itemList": [
                {"itemNm": "Widget", "taxblAmt": 600, "taxTyCd": "B", "taxAmt": 96},
                {"itemNm": "Gadget", "taxblAmt": 400, "taxTyCd": "B", "taxAmt": 64},
            ],
        }
        out = si._normalize_payload_non_vat(payload)

        # Whole supply now sits in band D at 0%.
        self.assertEqual(out["taxblAmtD"], 1000)
        self.assertEqual(out["taxAmtD"], 0)
        self.assertEqual(out["totTaxAmt"], 0)
        self.assertEqual(out["totTaxblAmt"], 1000)
        # VAT bands wiped.
        for code in ("A", "B", "C", "E"):
            self.assertEqual(out[f"taxblAmt{code}"], 0)
            self.assertEqual(out[f"taxAmt{code}"], 0)
        # Every line is Non-VAT with zero tax.
        for li in out["itemList"]:
            self.assertEqual(li["taxTyCd"], "D")
            self.assertEqual(li["taxAmt"], 0)

    def test_band_total_sums_line_taxable_amounts(self):
        payload = {
            "itemList": [
                {"itemNm": "A", "taxblAmt": 250.5, "taxTyCd": "B", "taxAmt": 40},
                {"itemNm": "B", "taxblAmt": 749.5, "taxTyCd": "B", "taxAmt": 120},
            ],
        }
        out = si._normalize_payload_non_vat(payload)
        self.assertEqual(out["taxblAmtD"], 1000.0)
        self.assertEqual(out["totTaxblAmt"], 1000.0)


class TestVatObligationDefault(FrappeTestCase):
    @patch(
        "kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings.frappe.get_single"
    )
    def test_defaults_to_registered_when_unset(self, get_single):
        from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
            get_etims_settings,
        )

        doc = MagicMock()
        doc.as_dict.return_value = {}
        get_single.return_value = doc
        self.assertEqual(get_etims_settings()["vat_obligation"], "Registered")


class TestVatObligationIntegration(FrappeTestCase):
    """Real-engine test: proves ERPNext actually zeroes the VAT after the hook
    re-maps the line to the Non-VAT (D) template — the mechanism the mocked unit
    tests deliberately stub out. Builds its own tax templates; rolls back per test.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = frappe.db.get_value("Company", {}, "name")
        cls.customer = frappe.db.get_value("Customer", {}, "name")
        cls.item = frappe.db.get_value("Item", {"is_sales_item": 1, "disabled": 0}, "name")
        cls.vat_account = frappe.db.get_value(
            "Account", {"account_type": "Tax", "is_group": 0, "company": cls.company}, "name"
        )

    def _ensure_template(self, code, rate, title):
        name = frappe.db.get_value("Item Tax Template", {"custom_code": code})
        if name:
            return name
        doc = frappe.new_doc("Item Tax Template")
        doc.title = title
        doc.company = self.company
        doc.custom_code = code
        doc.append("taxes", {"tax_type": self.vat_account, "tax_rate": rate})
        doc.insert(ignore_permissions=True)
        return doc.name

    def _build_inclusive_invoice(self, item_template):
        si_doc = frappe.new_doc("Sales Invoice")
        si_doc.company = self.company
        si_doc.customer = self.customer
        si_doc.set_posting_time = 1
        si_doc.append(
            "items",
            {"item_code": self.item, "qty": 1, "rate": 116, "item_tax_template": item_template},
        )
        si_doc.append(
            "taxes",
            {
                "charge_type": "On Net Total",
                "account_head": self.vat_account,
                "description": "VAT",
                "rate": 16,
                "included_in_print_rate": 1,
            },
        )
        return si_doc

    def test_non_vat_company_actually_loses_vat_inclusive_total_preserved(self):
        if not all([self.company, self.customer, self.item, self.vat_account]):
            self.skipTest("Site lacks company/customer/item/tax-account master data")

        b16 = self._ensure_template("B", 16, "TEST KRA B 16")

        # Baseline: VAT-registered behaviour — 16% inclusive yields net 100, VAT 16, gross 116.
        baseline = self._build_inclusive_invoice(b16)
        baseline.run_method("set_missing_values")
        baseline.run_method("calculate_taxes_and_totals")
        self.assertGreater(flt(baseline.base_total_taxes_and_charges), 0, "baseline should carry VAT")
        gross = flt(baseline.base_grand_total)

        # Non-VAT company: the hook removes the VAT row, then ERPNext recomputes.
        frappe.db.set_single_value("eTIMS Settings", "vat_obligation", "Not Registered")
        frappe.clear_document_cache("eTIMS Settings", "eTIMS Settings")
        inv = self._build_inclusive_invoice(b16)
        inv.custom_update_invoice_in_tims = 1
        inv.run_method("set_missing_values")
        inv.run_method("before_validate")  # fires enforce_vat_obligation via doc_events
        inv.run_method("set_missing_values")
        inv.run_method("calculate_taxes_and_totals")

        # The VAT-bearing tax row was removed...
        self.assertFalse([t for t in inv.taxes if flt(t.rate) > 0], "no rated VAT row may remain")
        # ...ERPNext genuinely removed the VAT from the booked invoice...
        self.assertEqual(flt(inv.base_total_taxes_and_charges), 0, "VAT must be zero on the books")
        # ...while the inclusive gross total is preserved (no silent revenue change).
        self.assertEqual(flt(inv.base_grand_total), gross)
