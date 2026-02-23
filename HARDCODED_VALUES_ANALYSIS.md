# Hardcoded Values Analysis - KRA eTIMS Compliance App

This document lists all hardcoded values that should be moved to settings for better maintainability and configurability.

---

## 1. API URLs (HIGH PRIORITY)

### Current Location: `utils/etims_utils.py:85-88`

```python
# HARDCODED - Should be in Settings
t_base_url = 'https://etims-api.kra.go.ke/etims-api/'  # Production
t_base_url = 'https://etims-api-sbx.kra.go.ke/etims-api/'  # Sandbox
```

**Recommendation:** Already configurable via `api_mode` field in TIS Device Initialization, but URLs should also be stored in settings for flexibility.

---

## 2. Default SAR Type Codes (HIGH PRIORITY)

### Current Locations:

**`utils/etims_utils.py:425`**
```python
def stockReleaseNoSaveReq(sar_no, org_sar_no=0, sar_type='11'):  # '11' is hardcoded
```

**`custom_methods/stock_release.py:9`**
```python
def sync_stock_release_number(sar_no, org_sar_no=0, sar_type='11'):  # '11' is hardcoded
```

**`doctype/etims_stock_release_number/etims_stock_release_number.json:54`**
```json
{
  "default": "11",  // Hardcoded default SAR type
  "fieldname": "sar_type",
  ...
}
```

**Recommendation:** Create a Settings doctype with configurable default SAR types for different reference types.

---

## 3. Request Timeout Values (MEDIUM PRIORITY)

### Current Location: Throughout the codebase

**Issue:** No timeout is specified in `requests.request()` calls.

**Example in `utils/etims_utils.py:294`:**
```python
response = requests.request(
    "POST", 
    eTIMS.tims_base_url() + 'saveItem', 
    json = payload,
    headers=headers
    # NO TIMEOUT SPECIFIED - Could hang indefinitely
)
```

**Recommendation:** Add configurable timeout setting (default: 30 seconds).

---

## 4. API Endpoint Paths (LOW PRIORITY)

### Current Location: `utils/etims_utils.py`

**Hardcoded endpoint names:**
- `'saveItem'`
- `'updateImportItem'`
- `'searchItem'`
- `'searchStockMove'`
- `'searchTrnsSales'`
- `'searchTrnsPurchase'`
- `'stockReleaseNoSaveReq'`
- `'searchStockReleaseNo'`
- `'selectStockReleaseNoList'`
- `'selectItem'`
- `'selectTrnsSalesInfo'`
- `'selectTrnsPurchaseInfo'`
- `'selectNoticeInfo'`
- `'selectOrgUsrInfo'`

**Recommendation:** These are KRA API specification endpoints and should remain as-is, but could be documented in a constants file for reference.

---

## 5. Error Code Messages (LOW PRIORITY)

### Current Location: `utils/etims_utils.py:128-141`

```python
def handle_api_response(response_json):
    result_cd = response_json.get("resultCd")
    result_msg = response_json.get("resultMsg", "Unknown error")

    if result_cd == '000':
        return {"Success": response_json.get("data")}
    elif result_cd == '400':
        error_msg = f"Bad Request: {result_msg}"  # "Bad Request" is hardcoded
        ...
    elif result_cd == '401':
        error_msg = f"Unauthorized: {result_msg}"  # "Unauthorized" is hardcoded
        ...
    elif result_cd == '500':
        error_msg = f"Server Error: {result_msg}"  # "Server Error" is hardcoded
```

**Recommendation:** Error messages are standard HTTP status codes and should remain as-is.

---

## 6. Date/Time Format Strings (LOW PRIORITY)

### Current Location: `utils/etims_utils.py`

```python
# KRA/TIMS specific formats - should NOT be changed
'%Y-%m-%d %H:%M:%S'     # KRA datetime format
'%Y%m%d%H%M%S'          # TIMS datetime format
'%Y-%m-%d'              # Date format
'%Y%m%d'                # TIMS date format
'%H:%M:%S'              # Time format
'%H%M%S'                # TIMS time format
```

**Recommendation:** These are KRA/TIMS specification formats and MUST remain hardcoded.

---

## 7. Search Result Limits (MEDIUM PRIORITY)

### Current Location: Search endpoints

**Issue:** No pagination or result limits specified for search endpoints.

**Recommendation:** Add configurable default and maximum result limits.

---

## 8. Retry Logic Configuration (MEDIUM PRIORITY)

### Current Location: Not implemented

**Issue:** No retry logic for failed API requests.

**Recommendation:** Add configurable retry settings:
- Max retry attempts (default: 3)
- Retry delay in seconds (default: 2)

---

## Summary of Required Changes

### High Priority (Should be in Settings)

| Setting | Current Value | Description |
|---------|---------------|-------------|
| Default SAR Type (Sales) | `'11'` | Default SAR type for sales transactions |
| Default SAR Type (Purchase) | `'02'` | Default SAR type for purchase transactions |
| Default SAR Type (Stock Entry) | `'06'` | Default SAR type for material receipts |
| API Timeout | `None` | Request timeout in seconds |
| Max Retry Attempts | `None` | Number of retry attempts for failed requests |
| Retry Delay | `None` | Delay between retries in seconds |
| Max Search Results | `None` | Maximum results to return from search |

### Already Configurable (No Changes Needed)

| Setting | Location | Configurable Via |
|---------|----------|------------------|
| API Mode (Sandbox/Production) | TIS Device Initialization | `api_mode` field |
| Production URL | Code | Should add to Settings |
| Sandbox URL | Code | Should add to Settings |

---

## Proposed Solution: eTIMS Settings Doctype

Create a new **eTIMS Settings** doctype with the following fields:

### General Settings
- **Default SAR Type - Sales** (Select, default: "11")
- **Default SAR Type - Purchase** (Select, default: "02")
- **Default SAR Type - Stock Entry** (Select, default: "06")
- **Enable Auto Sync** (Check, default: 1)

### API Settings
- **API Timeout** (Int, default: 30, unit: seconds)
- **Production API URL** (Data, default: "https://etims-api.kra.go.ke/etims-api/")
- **Sandbox API URL** (Data, default: "https://etims-api-sbx.kra.go.ke/etims-api/")
- **Enable Retry Logic** (Check, default: 1)
- **Max Retry Attempts** (Int, default: 3)
- **Retry Delay** (Int, default: 2, unit: seconds)

### Search Settings
- **Default Search Limit** (Int, default: 100)
- **Max Search Limit** (Int, default: 1000)

### Error Handling
- **Enable Error Logging** (Check, default: 1)
- **Error Notification Email** (Data)

---

## Implementation Priority

1. **Phase 1** (High Priority - Implement Now)
   - Create eTIMS Settings doctype
   - Add API timeout configuration
   - Add default SAR type configuration
   - Update code to use settings values

2. **Phase 2** (Medium Priority - Implement Later)
   - Add retry logic
   - Add search result limits
   - Add error notification settings

3. **Phase 3** (Low Priority - Optional)
   - API endpoint override capability
   - Custom error message templates
