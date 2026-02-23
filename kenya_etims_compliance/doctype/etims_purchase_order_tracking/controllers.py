# Copyright (c) 2026, Upande Ltd and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.model.db import Database

# noinspection PyUnresolvedReferences
from frappe.desk.form.meta import build_custom_fields
from frappe.custom import customize


class eTIMSPurchaseOrderTrackingControllers:
    """Controllers for eTIMS Purchase Order Tracking"""

    def validate(self):
        """Validate document"""
        pass

    def on_update(self):
        """On update"""
        pass

    def on_submit(self):
        """On submit"""
        pass

    def on_cancel(self):
        """On cancel"""
        pass
