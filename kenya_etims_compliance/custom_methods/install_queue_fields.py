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


def install_queue_fields():
    create_custom_fields(QUEUE_STATUS_FIELDS, update=True)
    create_custom_fields(RECEIPT_TYPE_FIELDS, update=True)
    create_custom_fields(TIS_DEVICE_FIELDS, update=True)
