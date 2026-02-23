# KRA eTIMS API v2.0 Endpoints Documentation

This document describes the new API endpoints added to achieve full compliance with KRA TIS Technical Specifications v2.0.

## Table of Contents

- [Phase 1: Search Endpoints](#phase-1-search-endpoints)
- [Phase 2: Stock Release Number Management](#phase-2-stock-release-number-management)
- [Phase 3: Detail Query Endpoints](#phase-3-detail-query-endpoints)
- [Phase 4: Organization & Notice Endpoints](#phase-4-organization--notice-endpoints)
- [Error Handling](#error-handling)
- [Usage Examples](#usage-examples)

---

## Phase 1: Search Endpoints

### 1.1 Search Items

**Python Method:** `eTIMS.searchItem(item_code=None, item_name=None, last_req_dt=None)`

**Whitelisted Wrapper:** `searchItemReq(item_code=None, item_name=None, last_req_dt=None)`

**Endpoint:** `/searchItem`

**Section:** 7.13

**Parameters:**
- `item_code` (optional): eTIMS item code
- `item_name` (optional): Item name
- `last_req_dt` (optional): Last request datetime for incremental updates

**Response:**
```python
{
    "Success": [
        {
            "itemCd": "KE...",
            "itemClsCd": "...",
            "itemNm": "Item Name",
            ...
        }
    ]
}
```

### 1.2 Search Stock Movements

**Python Method:** `eTIMS.searchStockMove(sar_no=None, last_req_dt=None)`

**Whitelisted Wrapper:** `searchStockMoveReq(sar_no=None, last_req_dt=None)`

**Endpoint:** `/searchStockMove`

**Section:** 7.15

**Parameters:**
- `sar_no` (optional): Stock release number
- `last_req_dt` (optional): Last request datetime for incremental updates

### 1.3 Search Sales Transactions

**Python Method:** `eTIMS.searchTrns(invoice_no=None, last_req_dt=None, trns_type='sales')`

**Whitelisted Wrapper:** `searchSalesTrnsReq(invoice_no=None, last_req_dt=None)`

**Endpoint:** `/searchTrnsSales`

**Section:** 7.14

### 1.4 Search Purchase Transactions

**Python Method:** `eTIMS.searchTrns(invoice_no=None, last_req_dt=None, trns_type='purchase')`

**Whitelisted Wrapper:** `searchPurchaseTrnsReq(invoice_no=None, last_req_dt=None)`

**Endpoint:** `/searchTrnsPurchase`

**Section:** 7.20

---

## Phase 2: Stock Release Number Management

### 2.1 Save Stock Release Number

**Python Method:** `eTIMS.stockReleaseNoSaveReq(sar_no, org_sar_no=0, sar_type='11')`

**Whitelisted Wrapper:** `sync_stock_release_number(sar_no, org_sar_no=0, sar_type='11')`

**Endpoint:** `/stockReleaseNoSaveReq`

**Section:** 7.16

**SAR Type Codes:**
- `11` - Sales stock release
- `02` - Purchase stock release
- `03` - Sales return (full)
- `04` - Stock transfer (in)
- `06` - Material receipt
- `12` - Purchase return
- `13` - Inter-branch transfer (out)

### 2.2 Search Stock Release Numbers

**Python Method:** `eTIMS.searchStockReleaseNo(sar_no=None, last_req_dt=None)`

**Whitelisted Wrapper:** `search_stock_release_no(sar_no=None, last_req_dt=None)`

**Endpoint:** `/searchStockReleaseNo`

**Section:** 7.17

### 2.3 Get Stock Release Number List

**Python Method:** `eTIMS.selectStockReleaseNoList(last_req_dt=None)`

**Whitelisted Wrapper:** `get_stock_release_list(last_req_dt=None)`

**Endpoint:** `/selectStockReleaseNoList`

**Section:** 7.18

---

## Phase 3: Detail Query Endpoints

### 3.1 Get Item Details

**Python Method:** `eTIMS.selectItem(item_code)`

**Whitelisted Wrapper:** `selectItemReq(item_code)`

**Endpoint:** `/selectItem`

**Section:** 7.9

**Response:**
```python
{
    "Success": {
        "itemCd": "KE...",
        "itemClsCd": "...",
        "itemNm": "Item Name",
        "itemTyCd": "...",
        "pkgUnitCd": "...",
        "qtyUnitCd": "...",
        "taxTyCd": "...",
        ...
    }
}
```

### 3.2 Get Sales Transaction Details

**Python Method:** `eTIMS.selectTrnsSalesInfo(invoice_no)`

**Whitelisted Wrapper:** `selectSalesTrnsInfoReq(invoice_no)`

**Endpoint:** `/selectTrnsSalesInfo`

**Section:** 7.21

### 3.3 Get Purchase Transaction Details

**Python Method:** `eTIMS.selectTrnsPurchaseInfo(invoice_no)`

**Whitelisted Wrapper:** `selectPurchaseTrnsInfoReq(invoice_no)`

**Endpoint:** `/selectTrnsPurchaseInfo`

**Section:** 7.21

---

## Phase 4: Organization & Notice Endpoints

### 4.1 Get Notice Details

**Python Method:** `eTIMS.selectNoticeInfo(notice_no)`

**Whitelisted Wrapper:** `eTIMSCodeInformation.noticeInfoReq(notice_no)`

**Endpoint:** `/selectNoticeInfo`

**Section:** 7.23

### 4.2 Get Organization/User Information

**Python Method:** `eTIMS.selectOrgUsrInfo()`

**Whitelisted Wrapper:** `get_org_user_info()`

**Endpoint:** `/selectOrgUsrInfo`

**Section:** 7.5

**Doctype Method:** `TISDeviceInitialization.refresh_org_info()`

---

## Error Handling

All API responses are processed through the `handle_api_response()` method which maps KRA result codes:

| Result Code | Meaning | Handling |
|-------------|---------|----------|
| `000` | Success | Returns data in "Success" key |
| `400` | Bad Request | Logs error, returns error message |
| `401` | Unauthorized | Logs error, returns error message |
| `500` | Server Error | Logs error, returns error message |
| Other | Unknown Error | Returns error with code |

---

## Usage Examples

### Example 1: Search an Item

```python
from kenya_etims_compliance.utils.etims_utils import eTIMS

# Search by item code
result = eTIMS.searchItem(item_code="KE1123456789")

if "Success" in result:
    items = result["Success"]
    for item in items:
        print(f"Item: {item['itemNm']}")
else:
    print(f"Error: {result['Error']}")
```

### Example 2: Get Stock Release List

```python
from kenya_etims_compliance.custom_methods.stock_release import get_stock_release_list

result = get_stock_release_list()

if "Success" in result:
    sar_list = result["Success"]
    print(f"Found {len(sar_list)} stock release numbers")
```

### Example 3: Sync Stock Release Number on Submit

```python
# In eTIMS Stock Release Number doctype
class eTIMSStockReleaseNumber(Document):
    def on_submit(self):
        from kenya_etims_compliance.custom_methods.stock_release import sync_stock_release_number
        
        result = sync_stock_release_number(
            self.sr_number,
            self.orginal_sr_number or 0,
            '11'  # SAR type for sales
        )
        
        if result.get("Error"):
            frappe.throw(result.get("Error"))
```

### Example 4: Get Organization Info from Frappe Client

```javascript
// Client script to refresh organization info
frappe.call({
    method: "kenya_etims_compliance.custom_methods.organization.get_org_user_info",
    callback: function(r) {
        if (r.message.Success) {
            console.log("Organization Info:", r.message.Success);
        } else {
            frappe.msgprint("Error: " + r.message.Error);
        }
    }
});
```

---

## Testing

Run the test suite:

```bash
bench --site [site-name] run-tests --app kenya_etims_compliance --module kenya_etims_compliance.test_etims_api
```

---

## API Mode Configuration

Ensure proper API mode is set in **TIS Device Initialization**:

- **Sandbox**: `https://etims-api-sbx.kra.go.ke/etims-api/`
- **Production**: `https://etims-api.kra.go.ke/etims-api/`

---

## Changelog

### Version 2.0 (2026-02-03)

- Added 15+ new API endpoints per KRA TIS v2.0 specifications
- Enhanced error handling with proper result code mapping
- Added stock release number lifecycle management
- Added search functionality for items, transactions, and stock movements
- Added detail query endpoints for items and transactions
- Added organization/user info retrieval
- Added notice detail inquiry
- Created comprehensive test suite
- Added client script handlers for UI integration

---

## Support

For issues or questions:
1. Check Error Logging doctype for detailed error messages
2. Verify API mode (Sandbox vs Production)
3. Ensure communication key is valid
4. Check TIS Device Initialization settings
