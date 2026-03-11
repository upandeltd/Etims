# Copyright (c) 2026, Upande Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class eTIMSInvoiceQueue(Document):
    def before_insert(self):
        if not self.queued_at:
            self.queued_at = frappe.utils.now_datetime()
        if not self.max_retries:
            self.max_retries = frappe.db.get_single_value("eTIMS Settings", "max_retry_attempts") or 3
        if not self.status:
            self.status = "Queued"
