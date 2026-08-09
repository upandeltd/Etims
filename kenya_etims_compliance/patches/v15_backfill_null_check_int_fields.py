# """Backfill NULL values in this app's Check/Int custom fields to 0.

# Several eTIMS custom fields (fieldtype Check/Int, e.g. Item.custom_update_item_to_tims)
# were added via fixture on long-lived sites without backfilling rows that already
# existed when the column was added, leaving them NULL instead of 0.

# Frappe always declares these columns `int(...) NOT NULL DEFAULT 0`. When the
# Custom Field fixture is re-synced, schema sync issues `ALTER TABLE ... MODIFY
# <field> int(...) not null default 0`. If the column still has NULL rows, MariaDB
# has to coerce NULL -> 0 implicitly; under strict sql_mode (STRICT_TRANS_TABLES /
# STRICT_ALL_TABLES, as on Frappe Cloud) that coercion is promoted from a warning
# to a hard error:

#     pymysql.err.DataError: (1265, "Data truncated for column '<field>' at row 1")

# This patch runs BEFORE schema sync (pre_model_sync) and backfills NULL -> 0 for
# every Check/Int custom field this app ships, on every doctype where the table and
# column already exist. Safe to re-run.

# Note: Sales Invoice.custom_invoice_number / custom_original_invoice_number are
# intentionally NOT included here — on at least one site those columns hold
# free-text supplier invoice numbers (same issue previously found on Purchase
# Invoice), which NULL-backfill alone can't fix. Verify that data before assuming
# this patch covers them.
# """

# import frappe

# CHECK_INT_FIELDS = (
# 	("BOM Item", "custom_updated_in_etims"),
# 	("BOM", "custom_updated_to_etims"),
# 	("Customer", "custom_is_registered"),
# 	("Item Group", "custom_etims_item_type_code"),
# 	("Item", "custom_registered_in_tims"),
# 	("Item", "custom_update_item_to_tims"),
# 	("Item", "custom_is_import_item"),
# 	("Item", "reading_required"),
# 	("Purchase Invoice Item", "custom_stock_master_updated"),
# 	("Purchase Invoice Item", "custom_maintain_stock"),
# 	("Purchase Invoice", "custom_update_purchase_in_tims"),
# 	("Purchase Invoice", "custom_item_updated_in_tims"),
# 	("Purchase Invoice", "custom_purchase_is_from_etims"),
# 	("Sales Invoice Item", "custom_stock_master_updated"),
# 	("Sales Invoice Item", "custom_maintain_stock"),
# 	("Sales Invoice", "custom_update_sales_to_etims"),
# 	("Sales Invoice", "custom_update_invoice_in_tims"),
# 	("Sales Invoice", "custom_item_count"),
# 	("Sales Invoice", "custom_sr_number"),
# 	("Stock Entry Detail", "custom_stock_master_updated"),
# 	("Stock Entry", "custom_send_stock_info_to_etims"),
# 	("Stock Entry", "custom_updated_in_etims"),
# 	("Stock Entry", "custom_update_both_branches"),
# 	("Stock Entry", "custom_is_import_stock"),
# 	("Stock Entry", "custom_is_return"),
# )


# def execute():
# 	for doctype, fieldname in CHECK_INT_FIELDS:
# 		if not frappe.db.table_exists(doctype):
# 			continue
# 		if not frappe.db.has_column(doctype, fieldname):
# 			continue

# 		table = f"tab{doctype}"
# 		frappe.db.sql(
# 			f"UPDATE `{table}` SET `{fieldname}` = 0 WHERE `{fieldname}` IS NULL"  # nosemgrep: trusted table/column names from static allowlist
# 		)
# 		frappe.db.commit()
