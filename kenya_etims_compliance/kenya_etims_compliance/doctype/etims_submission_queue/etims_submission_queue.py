import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, add_to_date


MAX_BACKOFF_MINUTES = 240  # 4 hours cap


class eTIMSSubmissionQueue(Document):
	def before_save(self):
		if not self.idempotency_key:
			import uuid
			self.idempotency_key = str(uuid.uuid4())

		if not self.max_attempts:
			self.max_attempts = 5

	def process(self):
		"""Process this queue entry — reconstruct payload and retry submission."""
		if self.status not in ("Queued", "Failed"):
			return

		# Check reference document still exists
		if not frappe.db.exists(self.reference_doctype, self.reference_name):
			self.status = "Dead"
			self.last_error = "Referenced document no longer exists"
			self.save(ignore_permissions=True)
			frappe.db.commit()
			return

		self.status = "Processing"
		self.attempts = (self.attempts or 0) + 1
		self.save(ignore_permissions=True)
		frappe.db.commit()

		try:
			doc = frappe.get_doc(self.reference_doctype, self.reference_name)

			# Call submission functions — catch frappe.throw() which raises ValidationError
			if self.reference_doctype == "Sales Invoice":
				from kenya_etims_compliance.custom_methods.sales_invoice import trnsSalesSaveWrReq
				trnsSalesSaveWrReq(doc, "on_submit")
			elif self.reference_doctype == "Purchase Invoice":
				from kenya_etims_compliance.custom_methods.purchase_invoice import trnsPurchaseSaveReq
				trnsPurchaseSaveReq(doc, "on_submit")
			elif self.reference_doctype == "Stock Entry":
				from kenya_etims_compliance.custom_methods.stock import update_stock_to_etims
				update_stock_to_etims(doc, "on_submit")

			self.status = "Success"
			self.last_error = ""
			self.save(ignore_permissions=True)
			frappe.db.commit()

		except Exception as e:
			# Rollback any partial changes from the failed submission
			frappe.db.rollback()

			self.reload()  # Reload after rollback
			self.status = "Failed"
			self.last_error = str(e)[:500]

			if self.attempts >= self.max_attempts:
				self.status = "Dead"
				self._notify_dead()

			# Exponential backoff with cap
			backoff_minutes = min(15 * (2 ** (self.attempts - 1)), MAX_BACKOFF_MINUTES)
			self.next_retry_at = add_to_date(now_datetime(), minutes=backoff_minutes)
			self.save(ignore_permissions=True)
			frappe.db.commit()

	def _notify_dead(self):
		"""Send notification when entry exceeds max retries."""
		try:
			from kenya_etims_compliance.custom_methods.notifications import send_queue_failure_alert
			send_queue_failure_alert(self.name)
		except Exception:
			pass  # Don't break queue processing on notification failure


@frappe.whitelist()
def retry_queue_entry(name):
	"""Manually retry a failed/dead queue entry. Resets attempts."""
	doc = frappe.get_doc("eTIMS Submission Queue", name)
	if doc.status not in ("Failed", "Dead"):
		frappe.throw(f"Cannot retry entry with status: {doc.status}")

	doc.status = "Queued"
	doc.attempts = 0
	doc.next_retry_at = None
	doc.last_error = ""
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"status": "requeued"}


@frappe.whitelist()
def enqueue_submission(reference_doctype, reference_name, endpoint):
	"""Create a queue entry if one doesn't already exist for this document."""
	existing = frappe.db.exists("eTIMS Submission Queue", {
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"status": ["in", ["Queued", "Processing", "Failed"]],
	})

	if existing:
		return {"status": "already_queued", "name": existing}

	doc = frappe.get_doc({
		"doctype": "eTIMS Submission Queue",
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"endpoint": endpoint,
		"status": "Queued",
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"status": "queued", "name": doc.name}
