# """Repair child tables missing the standard parent/parentfield/parenttype columns.

# Several eTIMS child doctypes were created as regular tables and only later marked
# ``istable = 1``. Frappe adds the child-table columns (parent, parentfield,
# parenttype) ONLY in the CREATE TABLE path — never in the sync/alter path
# (`frappe/database/schema.py:get_columns_from_docfields`). So those pre-existing
# tables permanently lack the columns, and any parent document that loads them
# crashes with ``OperationalError (1054, "Unknown column 'parent'")``.

# This patch adds the missing columns idempotently across every child (istable)
# doctype in the module. It is safe to re-run.
# """

# import frappe

# CHILD_COLUMNS = ("parent", "parentfield", "parenttype")


# def execute():
# 	doctypes = frappe.get_all(
# 		"DocType",
# 		filters={"istable": 1, "module": "Kenya Etims Compliance"},
# 		pluck="name",
# 	)

# 	for dt in doctypes:
# 		if not frappe.db.table_exists(dt):
# 			continue

# 		table = f"tab{dt}"
# 		# Read the physical schema directly. has_column()/get_table_columns() are
# 		# cached and can report standard child columns as present for an istable
# 		# doctype even when the actual table is missing them.
# 		existing = {
# 			row[0]
# 			for row in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")  # nosemgrep: trusted table name from DocType query
# 		}
# 		missing = [c for c in CHILD_COLUMNS if c not in existing]
# 		if not missing:
# 			continue

# 		col_defs = ", ".join(
# 			f"ADD COLUMN `{c}` varchar({frappe.db.VARCHAR_LEN})" for c in missing
# 		)
# 		frappe.db.sql_ddl(f"ALTER TABLE `{table}` {col_defs}")  # nosemgrep: DDL on trusted table name

# 		if "parent" in missing:
# 			try:
# 				frappe.db.add_index(dt, ["parent"], index_name="parent")
# 			except Exception:
# 				# Index may already exist; not fatal.
# 				pass

# 		frappe.db.commit()
# 		frappe.logger().info(f"eTIMS: repaired child columns {missing} on {table}")
