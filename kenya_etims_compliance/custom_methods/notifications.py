"""eTIMS Compliance Notifications.

Uses Frappe's built-in Notification system — no custom DocTypes needed.
Call these from scheduler tasks to send alerts.
"""

import frappe
from frappe import _
from frappe.utils import getdate


def send_filing_deadline_reminder():
	"""Send VAT filing deadline reminder (5 days and 1 day before 20th)."""
	today = getdate()
	filing_day = 20

	days_remaining = filing_day - today.day
	if days_remaining not in (5, 1):
		return

	subject = _("VAT Filing Deadline: {0} days remaining").format(days_remaining)
	message = _(
		"Your VAT return is due on the 20th of this month. "
		"{0} days remaining. Please review the eTIMS VAT Return Preview report "
		"before filing on iTax."
	).format(days_remaining)

	_send_to_etims_admins(subject, message)


def send_queue_failure_alert(queue_entry_name):
	"""Send alert when a queue entry exceeds max retries."""
	entry = frappe.get_doc("eTIMS Invoice Queue", queue_entry_name)

	subject = _("eTIMS Submission Failed: {0}").format(entry.reference_name)
	message = _(
		"eTIMS submission for {doctype} {name} has failed after {attempts} attempts. "
		"Last error: {error}. Please check the Invoice Queue."
	).format(
		doctype=entry.reference_doctype,
		name=entry.reference_name,
		attempts=entry.retry_count,
		error=entry.last_error or "Unknown",
	)

	_send_to_etims_admins(subject, message)


def send_kra_notice_alert(notice_name):
	"""Send alert when a new KRA notice is fetched."""
	notice = frappe.get_doc("eTIMS Notice", notice_name)

	subject = _("New KRA Notice: {0}").format(notice.title)
	message = _("KRA has published a new notice: {0}\n\n{1}").format(notice.title, notice.contents or "")

	_send_to_etims_admins(subject, message)


def _send_to_etims_admins(subject, message):
	"""Send notification to all users with eTIMS Administrator role."""
	admins = frappe.get_all(
		"Has Role",
		filters={
			"role": "eTIMS Administrator",
			"parenttype": "User",
		},
		fields=["parent"],
		limit_page_length=0,
	)

	for admin in admins:
		user = admin.parent
		if user == "Administrator" or not frappe.db.get_value("User", user, "enabled"):
			continue

		try:
			frappe.sendmail(
				recipients=[user],
				subject=subject,
				message=message,
				now=True,
			)
		except Exception as e:
			frappe.log_error("eTIMS: Notification error", str(e))
			pass  # Don't break on email errors
