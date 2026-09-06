import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

QUEUE_STATUS_FIELDS = {
	"Sales Invoice": [
		dict(
			fieldname="custom_etims_queue_status",
			label="eTIMS Queue Status",
			fieldtype="Select",
			options="\nQueued\nProcessing\nSent\nFailed",
			insert_after="custom_update_sales_to_etims",
			read_only=1,
			no_copy=1,
			print_hide=1,
		),
		dict(
			fieldname="custom_etims_retry_count",
			label="eTIMS Retry Count",
			fieldtype="Int",
			insert_after="custom_etims_queue_status",
			read_only=1,
			no_copy=1,
			hidden=1,
		),
		dict(
			fieldname="custom_etims_last_error",
			label="eTIMS Last Error",
			fieldtype="Small Text",
			insert_after="custom_etims_retry_count",
			read_only=1,
			no_copy=1,
			hidden=1,
		),
		dict(
			fieldname="custom_etims_queue_entry",
			label="eTIMS Queue Entry",
			fieldtype="Link",
			options="eTIMS Invoice Queue",
			insert_after="custom_etims_last_error",
			read_only=1,
			no_copy=1,
			hidden=1,
		),
	],
	"Purchase Invoice": [
		dict(
			fieldname="custom_etims_queue_status",
			label="eTIMS Queue Status",
			fieldtype="Select",
			options="\nQueued\nProcessing\nSent\nFailed",
			insert_after="custom_item_updated_in_tims",
			read_only=1,
			no_copy=1,
			print_hide=1,
		),
		dict(
			fieldname="custom_etims_retry_count",
			label="eTIMS Retry Count",
			fieldtype="Int",
			insert_after="custom_etims_queue_status",
			read_only=1,
			no_copy=1,
			hidden=1,
		),
		dict(
			fieldname="custom_etims_last_error",
			label="eTIMS Last Error",
			fieldtype="Small Text",
			insert_after="custom_etims_retry_count",
			read_only=1,
			no_copy=1,
			hidden=1,
		),
		dict(
			fieldname="custom_etims_queue_entry",
			label="eTIMS Queue Entry",
			fieldtype="Link",
			options="eTIMS Invoice Queue",
			insert_after="custom_etims_last_error",
			read_only=1,
			no_copy=1,
			hidden=1,
		),
	],
	"Stock Entry": [
		dict(
			fieldname="custom_etims_queue_status",
			label="eTIMS Queue Status",
			fieldtype="Select",
			options="\nQueued\nProcessing\nSent\nFailed",
			insert_after="custom_updated_in_etims",
			read_only=1,
			no_copy=1,
			print_hide=1,
		),
		dict(
			fieldname="custom_etims_retry_count",
			label="eTIMS Retry Count",
			fieldtype="Int",
			insert_after="custom_etims_queue_status",
			read_only=1,
			no_copy=1,
			hidden=1,
		),
		dict(
			fieldname="custom_etims_last_error",
			label="eTIMS Last Error",
			fieldtype="Small Text",
			insert_after="custom_etims_retry_count",
			read_only=1,
			no_copy=1,
			hidden=1,
		),
		dict(
			fieldname="custom_etims_queue_entry",
			label="eTIMS Queue Entry",
			fieldtype="Link",
			options="eTIMS Invoice Queue",
			insert_after="custom_etims_last_error",
			read_only=1,
			no_copy=1,
			hidden=1,
		),
	],
}


TIS_DEVICE_FIELDS = {
	"TIS Device Initialization": [
		dict(
			fieldname="custom_last_z_report_date",
			label="Last Z Report Date",
			fieldtype="Date",
			insert_after="column_break_fwpl",
			read_only=1,
			description="Date when the last Z (end-of-day) report was generated for this branch",
		),
	],
}

RECEIPT_TYPE_FIELDS = {
	"Sales Invoice": [
		dict(
			fieldname="custom_receipt_copy_count",
			label="Receipt Copy Count",
			fieldtype="Int",
			insert_after="custom_etims_queue_entry",
			read_only=1,
			no_copy=1,
			description="Number of copy receipts printed (Spec 4.1.2)",
		),
		dict(
			fieldname="custom_receipt_label",
			label="Receipt Label",
			fieldtype="Data",
			insert_after="custom_receipt_copy_count",
			read_only=1,
			no_copy=1,
			description="Receipt type label: NS, NC, CS, CC, TS, TC, PS (Spec 4.3)",
		),
	],
}

# Purchase-invoice verification chain (`verify_supplier_invoice`,
# `mark_invoice_as_manually_verified`, `payment_entry.validate_payment_for_etims_invoice`)
# reads and writes these. They were only ever declared in the orphaned
# `custom_fields/*.json` data files, which nothing in the app loads — `fixtures`
# exports Custom Field by module, so a definition that was never inserted is
# never exported either. Result: every write raised
# OperationalError 1054 "Unknown column", and the payment gate read a missing
# field as falsy and hard-blocked every Payment Entry with no working override.
# `no_copy` keeps verification state from surviving into an amended invoice.
VERIFICATION_FIELDS = {
	"Purchase Invoice": [
		dict(
			fieldname="custom_etims_verification_section",
			label="eTIMS Invoice Verification",
			fieldtype="Section Break",
			insert_after="terms_section_break",
			collapsible=1,
		),
		dict(
			fieldname="custom_supplier_cu_invoice_no",
			label="Supplier CU Invoice No",
			fieldtype="Data",
			insert_after="custom_etims_verification_section",
			description=(
				"Control-unit invoice number from the supplier's fiscal receipt. "
				"eTIMS format '<CU_ID>/<seq>' (e.g. KRACU0400003494/5) or a TIMS "
				"numeric receipt. Used to verify when the trader invoice number differs."
			),
		),
		dict(
			fieldname="custom_invoice_verified",
			label="Invoice Verified",
			fieldtype="Check",
			default="0",
			insert_after="custom_supplier_cu_invoice_no",
			read_only=1,
			no_copy=1,
			description="Invoice was matched against KRA's purchase register",
		),
		dict(
			fieldname="custom_verification_date",
			label="Verification Date",
			fieldtype="Datetime",
			insert_after="custom_invoice_verified",
			read_only=1,
			no_copy=1,
		),
		dict(
			fieldname="column_break_etims_verify",
			fieldtype="Column Break",
			insert_after="custom_verification_date",
		),
		dict(
			fieldname="custom_kra_invoice_number",
			label="KRA Invoice Number",
			fieldtype="Data",
			insert_after="column_break_etims_verify",
			read_only=1,
			no_copy=1,
			description="Supplier invoice number as KRA recorded it",
		),
		dict(
			fieldname="custom_supplier_pin_verified",
			label="Verified Supplier PIN",
			fieldtype="Data",
			insert_after="custom_kra_invoice_number",
			read_only=1,
			no_copy=1,
		),
		dict(
			fieldname="custom_qr_code",
			label="QR Code",
			fieldtype="Small Text",
			insert_after="custom_supplier_pin_verified",
			read_only=1,
			no_copy=1,
		),
		dict(
			fieldname="custom_verification_override_reason",
			label="Manual Verification Reason",
			fieldtype="Small Text",
			insert_after="custom_qr_code",
			read_only=1,
			no_copy=1,
			description="Why this invoice was accepted without a KRA match",
		),
		dict(
			fieldname="custom_kra_acceptance_reason",
			label="KRA Reconciliation Acceptance Reason",
			fieldtype="Small Text",
			insert_after="custom_verification_override_reason",
			read_only=1,
			no_copy=1,
			description="Why this invoice was accepted as an unmatched reconciliation exception",
		),
	],
	"Supplier": [
		dict(
			fieldname="custom_registered_in_etims",
			label="Registered in eTIMS",
			fieldtype="Check",
			default="0",
			insert_after="custom_branch_id",
			description="Supplier is registered in KRA eTIMS and transmits invoices",
		),
		dict(
			fieldname="custom_auto_verify_invoices",
			label="Auto-Verify Invoices",
			fieldtype="Check",
			default="0",
			insert_after="custom_registered_in_etims",
			description="Verify this supplier's invoices automatically (requires Registered in eTIMS)",
		),
		dict(
			fieldname="custom_verification_notes",
			label="Verification Notes",
			fieldtype="Small Text",
			insert_after="custom_auto_verify_invoices",
		),
	],
}


def install_queue_fields():
	create_custom_fields(QUEUE_STATUS_FIELDS, update=True)
	create_custom_fields(RECEIPT_TYPE_FIELDS, update=True)
	create_custom_fields(TIS_DEVICE_FIELDS, update=True)
	create_custom_fields(VERIFICATION_FIELDS, update=True)
