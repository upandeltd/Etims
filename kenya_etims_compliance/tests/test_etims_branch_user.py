"""Tests for eTIMS Branch User registration guards.

Covers the two failures users hit when their Frappe login exceeds KRA's 20-char
``userId`` limit:
  * the ≤20 length guard on ``user_id`` (clear message instead of KRA's cryptic one)
  * resolving an item's creator/modifier via the ``system_user`` link, so item
    registration recognises a branch user whose KRA ``user_id`` is a short id.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from kenya_etims_compliance.custom_methods.item import _get_branch_user_name


class TestBranchUserGuards(FrappeTestCase):
    def _login(self):
        return frappe.db.get_value("User", {"enabled": 1}, "name")

    def test_over_30_user_id_is_blocked_with_clear_message(self):
        bu = frappe.new_doc("eTIMS Branch User")
        bu.user_id = "x" * 31  # > 30 guard
        bu.user_name = "Mustafa"
        with self.assertRaises(frappe.ValidationError):
            bu.validate()

    def test_user_id_up_to_30_passes(self):
        bu = frappe.new_doc("eTIMS Branch User")
        bu.user_id = "mustafa@sajmustafa.com"  # 22 chars — allowed under the 30 guard
        bu.user_name = "Mustafa"
        bu.system_user = self._login()
        bu.validate()  # must not raise
        self.assertEqual(bu.user_id, "mustafa@sajmustafa.com")

    def test_creator_resolved_via_system_user_link(self):
        login = self._login()
        bu = frappe.new_doc("eTIMS Branch User")
        bu.user_id = "kra-short-id"  # short KRA id, NOT the login
        bu.user_name = "Branch Clerk"
        bu.system_user = login
        bu.password = "x"
        bu.registration_id = "reg01"
        bu.registration_name = "Reg"
        bu.modifier_id = "mod01"
        bu.modifier_name = "Mod"
        bu.used_unused = "Y"
        bu.saved = 1
        bu.insert(ignore_permissions=True)

        # An item created by `login` must resolve even though user_id != login.
        self.assertEqual(_get_branch_user_name(login), "Branch Clerk")
        self.assertIsNone(_get_branch_user_name("nobody@nowhere.test"))
