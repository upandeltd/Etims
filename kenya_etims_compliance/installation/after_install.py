import os

import frappe


def after_install():
    """Run after app installation to create required single DocType records."""
    create_etims_settings()


def create_etims_settings():
    """Create eTIMS Settings single record if it doesn't exist."""
    if not frappe.db.exists("eTIMS Settings"):
        frappe.get_doc({"doctype": "eTIMS Settings"}).insert(ignore_permissions=True)
        frappe.db.commit()


def setup_workspace_sidebar():
    """Idempotently set up Workspace Sidebar fixtures (v16+ only).

    Deletes the existing module sidebar so the shipped JSON is re-imported on
    every migrate. This ensures title/logo changes land on production.
    """
    if not frappe.db.exists("DocType", "Workspace Sidebar"):
        return

    from kenya_etims_compliance.utils.version_utils import is_v16_or_later

    if not is_v16_or_later():
        return

    try:
        from frappe.modules.import_file import import_file_by_path

        sidebar_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "kenya_etims_compliance",
            "workspace_sidebar",
            "etims_compliance.json",
        )
        if not os.path.exists(sidebar_path):
            return

        # Remove the existing sidebar so the JSON re-import updates title/logo.
        existing = frappe.get_all(
            "Workspace Sidebar", filters={"module": "Kenya Etims Compliance"}, pluck="name"
        )
        for name in existing:
            frappe.delete_doc("Workspace Sidebar", name, force=True, ignore_permissions=True)

        import_file_by_path(sidebar_path)
    except ImportError:
        pass  # import_file_by_path not available on this Frappe version
    except Exception as e:
        frappe.log_error(title="eTIMS: Workspace sidebar import failed", message=str(e))
        pass  # Not critical - workspace JSON handles navigation


def setup_desktop_icon():
    """Idempotently update the v15 Desktop Icon label to 'eTIMS'.

    Frappe only reads desktop_icon/ JSON on install, so the label can stay
    stale on production. This migrate hook forces the label to 'eTIMS'.
    """
    if not frappe.db.exists("DocType", "Desktop Icon"):
        return

    for name in frappe.get_all(
        "Desktop Icon", filters={"app": "kenya_etims_compliance"}, pluck="name"
    ):
        doc = frappe.get_doc("Desktop Icon", name)
        if doc.label != "eTIMS":
            doc.label = "eTIMS"
            doc.logo_url = "/assets/kenya_etims_compliance/images/etims-icon.jpg"
            doc.save(ignore_permissions=True)
            frappe.db.commit()
