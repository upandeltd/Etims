# Settings Implementation Summary - KRA eTIMS Compliance

## Overview

This document summarizes all hardcoded values that have been identified and moved to the **eTIMS Settings** doctype for better configurability and maintainability.

---

## New eTIMS Settings Doctype

### Location
`/doctype/etims_settings/`

### Files Created
1. `etims_settings.py` - Controller with helper functions
2. `etims_settings.json` - Doctype configuration
3. `test_etims_settings.py` - Test cases
4. `__init__.py` - Package init

---

## Settings Configuration

### General Settings Tab

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| **Default SAR Type - Sales** | Select | `11` | Default SAR type for Sales transactions (11=Sales) |
| **Default SAR Type - Purchase** | Select | `02` | Default SAR type for Purchase transactions (02=Purchase) |
| **Default SAR Type - Stock Entry** | Select | `06` | Default SAR type for Stock Entry (06=Material Receipt) |
| **Enable Auto Sync** | Check | `1` | Automatically sync Stock Release Numbers on submit |

### API Settings Tab

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| **API Timeout** | Int | `30` | Request timeout in seconds (max: 300) |
| **Production API URL** | Data | `https://etims-api.kra.go.ke/etims-api/` | KRA Production endpoint |
| **Sandbox API URL** | Data | `https://etims-api-sbx.kra.go.ke/etims-api/` | KRA Sandbox endpoint |

### Retry Settings Tab

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| **Enable Retry Logic** | Check | `1` | Automatically retry failed API requests |
| **Max Retry Attempts** | Int | `3` | Maximum number of retry attempts |
| **Retry Delay** | Int | `2` | Delay between retries in seconds |

### Search Settings Tab

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| **Default Search Limit** | Int | `100` | Default number of search results |
| **Max Search Limit** | Int | `1000` | Maximum allowed search results |

### Error Handling Tab

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| **Enable Error Logging** | Check | `1` | Log API errors to Error Logging doctype |
| **Error Notification Email** | Data | - | Send error notifications to this email |

---

## Code Changes Summary

### 1. API URLs - Now Configurable ✅

**Before:**
```python
# utils/etims_utils.py:85-88 (HARDCODED)
if settings_docs[0].api_mode == "Production":
    t_base_url = 'https://etims-api.kra.go.ke/etims-api/'
elif settings_docs[0].api_mode == "Sandbox":
    t_base_url = 'https://etims-api-sbx.kra.go.ke/etims-api/'
```

**After:**
```python
# utils/etims_utils.py:76-88
def tims_base_url():
    from kenya_etims_compliance.doctype.etims_settings.etims_settings import get_api_url
    
    if settings_docs:
        api_mode = settings_docs[0].api_mode
        t_base_url = get_api_url(api_mode)  # From settings
        return t_base_url
```

---

### 2. Default SAR Type - Now Configurable ✅

**Before:**
```python
# utils/etims_utils.py:425 (HARDCODED)
def stockReleaseNoSaveReq(sar_no, org_sar_no=0, sar_type='11'):

# custom_methods/stock_release.py:9 (HARDCODED)
def sync_stock_release_number(sar_no, org_sar_no=0, sar_type='11'):
```

**After:**
```python
# utils/etims_utils.py:430-442
def stockReleaseNoSaveReq(sar_no, org_sar_no=0, sar_type=None):
    if sar_type is None:
        from kenya_etims_compliance.doctype.etims_settings.etims_settings import get_etims_settings
        settings = get_etims_settings()
        sar_type = settings.get("default_sar_type_sales", "11")

# custom_methods/stock_release.py:9-21
def sync_stock_release_number(sar_no, org_sar_no=0, sar_type=None):
    if sar_type is None:
        from kenya_etims_compliance.doctype.etims_settings.etims_settings import get_etims_settings
        settings = get_etims_settings()
        sar_type = settings.get("default_sar_type_sales", "11")
```

---

### 3. Error Logging - Now Configurable ✅

**Before:**
```python
# utils/etims_utils.py:114-119
def log_errors(title, description):
    new_doc = frappe.new_doc("Error Logging")
    new_doc.title = title
    new_doc.description = description
    new_doc.insert()  # Always logs
```

**After:**
```python
# utils/etims_utils.py:112-124
def log_errors(title, description):
    from kenya_etims_compliance.doctype.etims_settings.etims_settings import get_etims_settings
    
    settings = get_etims_settings()
    if not settings.get("enable_error_logging", 1):
        return  # Check settings first
    
    new_doc = frappe.new_doc("Error Logging")
    new_doc.title = title
    new_doc.description = description
    new_doc.insert()
```

---

### 4. Auto Sync - Now Configurable ✅

**Added to doctype/etims_stock_release_number/etims_stock_release_number.py:**
```python
def on_submit(self):
    from kenya_etims_compliance.doctype.etims_settings.etims_settings import get_etims_settings
    
    settings = get_etims_settings()
    if not settings.get("enable_auto_sync", 1):
        return  # Skip sync if disabled
```

---

### 5. SAR Type per Doctype - Now Configurable ✅

**Added to etims_stock_release_number.py:23-24:**
```python
# Use SAR type from doctype, or get default based on reference type
sar_type = self.sar_type or get_sar_type_for_doctype(self.reference_type)
```

**Helper function in etims_settings.py:**
```python
def get_sar_type_for_doctype(doctype):
    settings = get_etims_settings()
    
    sar_type_mapping = {
        "Sales Invoice": settings.get("default_sar_type_sales", "11"),
        "Purchase Invoice": settings.get("default_sar_type_purchase", "02"),
        "Stock Entry": settings.get("default_sar_type_stock_entry", "06"),
    }
    
    return sar_type_mapping.get(doctype, "11")
```

---

## Helper Functions Added

### `get_etims_settings()`
Returns all settings with defaults applied.

```python
settings = get_etims_settings()
# Returns dict with all configuration values
```

### `get_api_timeout()`
Returns the API timeout in seconds.

```python
timeout = get_api_timeout()  # Default: 30
```

### `get_sar_type_for_doctype(doctype)`
Returns the default SAR type for a given doctype.

```python
sar_type = get_sar_type_for_doctype("Sales Invoice")  # Returns: "11"
```

### `get_retry_settings()`
Returns retry configuration.

```python
retry_settings = get_retry_settings()
# Returns: {"enabled": 1, "max_attempts": 3, "delay": 2}
```

### `get_api_url(api_mode)`
Returns the API URL for the specified mode.

```python
url = get_api_url("Production")  # Returns production URL from settings
```

---

## Settings Validation

The eTIMS Settings doctype includes validation for:

1. **API Timeout:** Must be positive (≥1 second), warning if >300 seconds
2. **Retry Settings:** Max attempts must be ≥1, delay cannot be negative
3. **Search Limits:** Default limit cannot exceed max limit

---

## Accessing eTIMS Settings

### Via UI
1. Go to **Home** → **eTIMS Settings**
2. Modify settings as needed
3. Save

### Via Python Console
```python
from kenya_etims_compliance.doctype.etims_settings.etims_settings import get_etims_settings

settings = get_etims_settings()
print(settings)
```

### Via Client Script
```javascript
frappe.call({
    method: "kenya_etims_compliance.doctype.etims_settings.etims_settings.get_etims_settings",
    callback: function(r) {
        console.log(r.message);
    }
})
```

---

## SAR Type Codes Reference

| Code | Description | Used For |
|------|-------------|----------|
| `11` | Sales Stock Release | Sales Invoice |
| `02` | Purchase Stock Release | Purchase Invoice |
| `03` | Sales Return (Full) | Sales Returns |
| `04` | Stock Transfer (In) | Inter-branch Transfers |
| `06` | Material Receipt | Stock Entry - Material Receipt |
| `12` | Purchase Return | Purchase Returns |
| `13` | Inter-Branch Transfer (Out) | Stock Transfers Out |

---

## Migration Notes

### For Existing Installations

1. Run `bench migrate` to create the eTIMS Settings doctype
2. The first time eTIMS Settings is accessed, it will be created with default values
3. Review and adjust settings according to your requirements

### Default Values Applied

If settings don't exist, the following defaults are used:
- API Timeout: 30 seconds
- Production URL: `https://etims-api.kra.go.ke/etims-api/`
- Sandbox URL: `https://etims-api-sbx.kra.go.ke/etims-api/`
- Retry: Enabled, 3 attempts, 2 second delay
- Search Limits: Default 100, Max 1000
- Error Logging: Enabled
- Auto Sync: Enabled
- SAR Types: Sales=11, Purchase=02, Stock Entry=06

---

## Files Modified

| File | Changes |
|------|---------|
| `utils/etims_utils.py` | - Updated `tims_base_url()` to use settings<br>- Updated `log_errors()` to check settings<br>- Updated `stockReleaseNoSaveReq()` to use settings default |
| `custom_methods/stock_release.py` | - Updated `sync_stock_release_number()` to use settings |
| `doctype/etims_stock_release_number/etims_stock_release_number.py` | - Added auto-sync check<br>- Added per-doctype SAR type logic |

---

## Files Created

| File | Purpose |
|------|---------|
| `doctype/etims_settings/etims_settings.py` | Settings controller and helper functions |
| `doctype/etims_settings/etims_settings.json` | Doctype configuration |
| `doctype/etims_settings/test_etims_settings.py` | Test cases |
| `doctype/etims_settings/__init__.py` | Package initialization |
| `HARDCODED_VALUES_ANALYSIS.md` | Analysis document |
| `SETTINGS_IMPLEMENTATION_SUMMARY.md` | This document |

---

## Testing

Run the settings tests:
```bash
bench --site [site-name] run-tests --app kenya_etims_compliance --module kenya_etims_compliance.doctype.etims_settings
```

---

## Next Steps (Optional Future Enhancements)

1. **Add timeout to all API requests** - Currently not implemented, can use `get_api_timeout()`
2. **Add retry logic with exponential backoff** - Use `get_retry_settings()`
3. **Add search limit parameters** - Use `get_etims_settings()["default_search_limit"]`
4. **Add email notifications** - Implement using `error_notification_email` setting

---

## Summary

| Category | Hardcoded Values | Status |
|----------|-----------------|--------|
| API URLs | Production/Sandbox URLs | ✅ Moved to Settings |
| Default SAR Types | '11', '02', '06' | ✅ Moved to Settings |
| Error Logging | Always enabled | ✅ Made configurable |
| Auto Sync | Always enabled | ✅ Made configurable |
| API Timeout | Not set (infinite) | ⏳ Settings created, implementation pending |
| Retry Logic | Not implemented | ⏳ Settings created, implementation pending |
| Search Limits | Not implemented | ⏳ Settings created, implementation pending |
| Date/Time Formats | KRA/TIMS formats | ✅ Keep as-is (specification) |
| Error Codes | HTTP status codes | ✅ Keep as-is (standard) |
| API Endpoints | Endpoint names | ✅ Keep as-is (specification) |
