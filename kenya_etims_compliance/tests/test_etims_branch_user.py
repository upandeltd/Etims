"""Tests for eTIMS Branch User registration guards.

Covers the two failures users hit when their Frappe login exceeds KRA's 20-char
``userId`` limit:
  * the ≤20 length guard on ``user_id`` (clear message instead of KRA's cryptic one)
  * resolving an item's creator/modifier via the ``system_user`` link, so item
    registration recognises a branch user whose KRA ``user_id`` is a short id.
"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from kenya_etims_compliance.custom_methods.item import _get_branch_user_name
from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_branch_user import (
    etims_branch_user as bu_mod,
)


class TestBranchUserGuards(FrappeTestCase):
    def _login(self):
        return frappe.db.get_value("User", {"enabled": 1}, "name")

    def test_over_30_user_id_is_blocked_with_clear_message(self):
        bu = frappe.new_doc("eTIMS Branch User")
        bu.user_id = "x" * 31  # > 30 guard
        bu.user_name = "Mustafa"
        with self.assertRaises(frappe.ValidationError):
            bu.validate()

    def test_validate_tolerates_unmigrated_system_user_field(self):
        # Reproduces the AttributeError crash on sites where `system_user` was
        # not migrated: validate must not touch the field when meta lacks it.
        bu = frappe.new_doc("eTIMS Branch User")
        bu.user_id = "mustafa@sajmustafa.com"
        bu.user_name = "Mustafa"
        bu._meta = MagicMock()
        bu._meta.has_field.return_value = False
        bu.validate()  # must not raise AttributeError

    def test_user_id_up_to_30_passes(self):
        bu = frappe.new_doc("eTIMS Branch User")
        bu.user_id = "mustafa@sajmustafa.com"  # 22 chars — allowed under the 30 guard
        bu.user_name = "Mustafa"
        bu.system_user = self._login()
        bu.validate()  # must not raise
        self.assertEqual(bu.user_id, "mustafa@sajmustafa.com")

    def test_userid_truncated_to_20_in_kra_payload(self):
        bu = frappe.new_doc("eTIMS Branch User")
        bu.user_id = "mustafa@sajmustafa.com"  # 22 chars stored on the record
        bu.user_name = "Mustafa"
        bu.password = "x"
        bu.registration_id = "reg01"
        bu.registration_name = "Reg"
        bu.modifier_id = "mod01"
        bu.modifier_name = "Mod"
        bu.system_user = self._login()
        bu.used_unused = "Y"

        captured = {}
        client = MagicMock()
        client.post.side_effect = lambda endpoint, payload, **_kwargs: captured.update(
            endpoint=endpoint, payload=payload
        ) or {"Success": None}

        with patch.object(bu_mod, "KRAClient", return_value=client):
            bu.bhfUserSaveReq()

        self.assertEqual(captured["endpoint"], "saveBhfUser")
        self.assertEqual(captured["payload"]["userId"], "mustafa@sajmustafa.c")  # 20 chars
        self.assertEqual(len(captured["payload"]["userId"]), 20)
        # The record itself keeps the full value for creator matching.
        self.assertEqual(bu.user_id, "mustafa@sajmustafa.com")

    def test_bhf_user_save_reports_error_without_saving_when_headers_missing(self):
        """Regression: KRAClient's require_auth pre-flight must surface a clear
        local error instead of the old code silently POSTing with no auth
        headers and returning KRA's opaque 'There is no Header information'.
        """
        bu = frappe.new_doc("eTIMS Branch User")
        bu.user_id = "edwin"
        bu.user_name = "edwin"
        bu.password = "x"
        bu.registration_name = "edwin"
        bu.modifier_name = "edwinY"
        bu.system_user = self._login()
        bu.used_unused = "Y"

        client = MagicMock()
        client.post.return_value = {
            "Error": (
                "No active TIS Device Initialization for branch 'None'. Cannot call "
                "KRA API without authentication headers (tin, bhfId, cmcKey)."
            ),
            "Retryable": False,
        }

        with patch.object(bu_mod, "KRAClient", return_value=client):
            result = bu.bhfUserSaveReq()

        self.assertIn("Error", result)
        self.assertIn("authentication headers", result["Error"])
        self.assertNotEqual(bu.saved, 1)

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
