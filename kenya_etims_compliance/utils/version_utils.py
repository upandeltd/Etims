# kenya_etims_compliance/utils/version_utils.py
import frappe

_cached_version = None

def get_frappe_major_version():
    """Return major version number as int (e.g. 15, 16). Cached per process."""
    global _cached_version
    if _cached_version is None:
        _cached_version = int(frappe.__version__.split('.')[0])
    return _cached_version

def is_v16_or_later():
    return get_frappe_major_version() >= 16

def is_v15():
    return get_frappe_major_version() == 15
