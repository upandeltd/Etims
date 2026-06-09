from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
    get_etims_settings,
)


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
