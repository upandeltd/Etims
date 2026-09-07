# Kenya eTIMS Compliance App -- Change Audit

**Baseline:** `/Users/mac/ERPNext/GBIWholesale/apps/kenya_etims_compliance`
**Modified:** `/Users/mac/ERPNext/ssmv16/apps/kenya_etims_compliance`
**Audit Date:** 2026-03-28

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Changes](#2-architecture-changes)
3. [New Modules and Files](#3-new-modules-and-files)
4. [Modified Files](#4-modified-files)
5. [Removed Files and DocTypes](#5-removed-files-and-doctypes)
6. [DocType Schema Changes](#6-doctype-schema-changes)
7. [Security and Permissions](#7-security-and-permissions)
8. [Scheduled Tasks](#8-scheduled-tasks)
9. [Reports](#9-reports)
10. [Breaking Changes](#10-breaking-changes)
11. [Post-Audit Fixes (2026-07-29)](#11-post-audit-fixes-2026-07-29)
12. [Workspace Sidebar & Desk Icon Fix (2026-07-29)](#12-workspace-sidebar--desk-icon-fix-2026-07-29)
13. [Role Profiles (2026-07-29)](#13-role-profiles-2026-07-29)
14. [Number Card Dashboard Fixes (2026-09-06)](#14-number-card-dashboard-fixes-2026-09-06)
15. [Purchase-Side Reconciliation Engine (2026-09-06)](#15-purchase-side-reconciliation-engine-2026-09-06)

---

## 1. Executive Summary

The modified app represents a **major architectural overhaul** of the Kenya eTIMS Compliance application. The changes can be grouped into five strategic themes:

| Theme | Description |
|-------|-------------|
| **API Client Centralization** | All raw `requests.post()` calls replaced with a centralized `KRAClient` class featuring circuit breaker, retry logic, timeout, and audit trail |
| **Invoice Queue System** | Synchronous eTIMS API calls replaced with an asynchronous queue (`eTIMS Invoice Queue` DocType) with background processing and retry |
| **Purchase Compliance Pipeline** | New end-to-end purchase compliance: supplier PIN verification, invoice checking, payment validation, purchase reconciliation |
| **Reporting and Scoring** | Nine new Script Reports, monthly compliance scoring, supplier scoring, and a dashboard with Number Cards and Charts |
| **v16 Compatibility and RBAC** | Frappe v16 compatibility layer, seven new eTIMS roles, fixture-based deployment, and a centralized `eTIMS Settings` Single DocType |

**By the numbers:**

- **18 new Python modules** in `custom_methods/`
- **8 new DocTypes** (eTIMS Settings, Invoice Queue, Compliance Score, Reconciliation Log, Credit Note Reason, Purchase Register Entry, Stock Register Entry, Purchase Order Tracking)
- **9 new Script Reports** (X/Z Daily, PLU, VAT Return Preview, Purchase Reconciliation, Stock Reconciliation, Supplier Compliance, Payment Reconciliation, Income/Expense Validation)
- **4 new utility modules** (kra_client, error_codes, permissions, version_utils)
- **7 new roles** (Administrator, Manager, Operator, Auditor, Sales Clerk, Purchase Clerk, Store Keeper)
- **3 removed DocTypes** (eTIMS Sales Invoice, eTIMS Item, eTIMS Item Group, eTIMS Tax Account, eTIMS Tax Configuration, Tax Branch Configurations)

---

## 2. Architecture Changes

### 2.1 KRA API Client Centralization

**File:** `kenya_etims_compliance/utils/kra_client.py` (NEW -- 180+ lines)

**Purpose:** Every file in the original app made direct `requests.post()` calls to KRA, each with its own error handling (or lack thereof). The new `KRAClient` class centralizes all HTTP communication with the KRA eTIMS API.

**Key features:**
- **Circuit breaker:** Blocks requests after 5 consecutive failures; auto-resets after 5 minutes. Prevents cascading timeouts.
- **Configurable retry:** Reads `max_retry_attempts` and `retry_delay` from eTIMS Settings.
- **Timeout:** Configurable via eTIMS Settings (default 30 seconds).
- **Audit trail:** Logs every API call (endpoint, reference document, result code, status) via `frappe.log_error()`.
- **Connection error handling:** Increments circuit breaker counter on `requests.ConnectionError`.
- **Empty/invalid response handling:** Detects empty response bodies and JSON decode errors.

**Impact:** All modules that previously imported `requests` directly (`sales_invoice.py`, `purchase_invoice.py`, `stock.py`, `customer.py`, `bom.py`, `item.py`, and all DocType controllers) now use `KRAClient().post(endpoint, payload)` instead.

### 2.2 eTIMS Settings Single DocType

**File:** `kenya_etims_compliance/kenya_etims_compliance/doctype/etims_settings/` (NEW)

**Purpose:** The original app had settings scattered across `Tax Branch Configurations` and `TIS Device Initialization`. The new `eTIMS Settings` Single DocType centralizes all app-wide configuration.

**Settings include:**
- Default SAR type codes (sales, purchase, stock)
- API timeout, retry logic toggle, max retries, retry delay
- Production and sandbox API URLs
- Search limits (default and max)
- Error logging toggle
- Auto-sync and queue toggles
- Queue max retries and retry interval
- Invoice verification enforcement
- Training mode flag

**Helper function:** `get_etims_settings()` returns a dict with sensible defaults even if the Single record has not been created yet.

### 2.3 Invoice Queue System

**Files:**
- `kenya_etims_compliance/custom_methods/queue_processor.py` (NEW -- 337 lines)
- `kenya_etims_compliance/kenya_etims_compliance/doctype/etims_invoice_queue/` (NEW DocType)

**Purpose:** The original app submitted invoices to KRA synchronously during `before_submit`, meaning a KRA timeout or error would block the user. The queue system decouples submission from the user action.

**How it works:**
1. During `before_submit`, a queue entry is created with the payload and enqueued as a background job.
2. Custom fields `custom_etims_queue_status` and `custom_etims_queue_entry` are set on the source document.
3. Background worker processes the entry via `KRAClient`.
4. On failure, the entry is retried up to `queue_max_retries` times.
5. A scheduler job (`*/5 * * * *`) retries failed entries.
6. The Sales Invoice JS shows the queue status in the dashboard headline with a "Retry eTIMS" button for failed entries.

### 2.4 Version Compatibility Layer

**File:** `kenya_etims_compliance/utils/version_utils.py` (NEW -- 17 lines)

**Purpose:** The modified app targets Frappe v16 but maintains backward compatibility with v15. The module provides `is_v16_or_later()` and `is_v15()` helpers used by installation scripts to conditionally set up Workspace Sidebar (v16 only).

---

## 3. New Modules and Files

### 3.1 Custom Methods (Business Logic)

| File | Lines | Purpose |
|------|-------|---------|
| `queue_processor.py` | 337 | Invoice queue management: enqueue, process, retry, status updates |
| `bulk_operations.py` | 128 | Bulk item registration and invoice submission for batch operations |
| `compliance_scoring.py` | 200 | Monthly compliance scorecard (transmission 35%, reconciliation 25%, supplier health 15%, error rate 10%, filing timeliness 15%) |
| `dashboard.py` | 77 | Dashboard analytics: real-time stats for sales, purchases, queue status |
| `device_status.py` | 41 | OSCU/VSCU connection test; receipt copy counter (TIS Spec 4.1.2) |
| `import_workflow.py` | 157 | Automated import item processing: fetch from KRA, match to local items, create Stock Entry, confirm back to KRA |
| `invoice_checker.py` | 262 | Verify supplier invoices against KRA eTIMS (required for 2026 tax compliance -- all expenses must be eTIMS-compliant to be deductible) |
| `install_queue_fields.py` | 168 | Post-migrate hook: ensures `custom_etims_queue_status` and `custom_etims_queue_entry` fields exist on Sales Invoice, Purchase Invoice, Stock Entry |
| `notifications.py` | 80 | Email notifications: VAT filing deadline reminders (5-day and 1-day), queue failure alerts, KRA notice alerts |
| `organization.py` | 19 | Fetch organization/user info from KRA |
| `payment_entry.py` | 344 | Payment Entry validation: blocks payment for unverified Purchase Invoices (configurable via eTIMS Settings) |
| `purchase_order.py` | 353 | Purchase Order tracking for audit trail and invoice reconciliation |
| `receipt_labels.py` | 42 | Receipt label generation per TIS Spec 4.3 (NS/NC/CS/CC/TS/TC/PS codes) |
| `reconciliation.py` | 310 | Purchase reconciliation engine: matches KRA auto-populated purchase data against local Purchase Invoices |
| `setup_wizard.py` | 325 | eTIMS setup wizard page for initial configuration |
| `stock_reconciliation_etims.py` | 176 | Stock movement reconciliation: compares KRA stock records against ERPNext Stock Ledger |
| `stock_release.py` | 56 | Stock release number management helpers |
| `supplier_scoring.py` | 126 | Supplier compliance scoring: PIN verification (30%), eTIMS registration (25%), invoice transmission rate (25%), credit note ratio (10%), payment history (10%) |
| `supplier.js` | 190 | Supplier form: KRA PIN verification button, eTIMS status indicators, invoice statistics dialog, PIN format validation |
| `item_list.js` | NEW | Item list view customizations |

### 3.2 Utilities

| File | Lines | Purpose |
|------|-------|---------|
| `utils/kra_client.py` | ~180 | Centralized KRA API client (see Section 2.1) |
| `utils/error_codes.py` | ~80 | KRA error code mapping (TIS Spec 21.3, 21.6.3) with human-readable messages and recommended actions |
| `utils/permissions.py` | ~300 | Role-based permission helpers, decorators (`@require_admin`, `@require_sync_permission`), branch access validation |
| `utils/version_utils.py` | 17 | Frappe version detection for v15/v16 compatibility |

### 3.3 New DocTypes

| DocType | Type | Purpose |
|---------|------|---------|
| `eTIMS Settings` | Single | Centralized app configuration (API URLs, timeouts, retry, queue, search limits) |
| `eTIMS Invoice Queue` | Regular | Async invoice submission queue with status tracking and retry |
| `eTIMS Compliance Score` | Regular | Monthly compliance scorecard per branch (autoname: `{period}-{branch}`) |
| `eTIMS Reconciliation Log` | Regular | Audit log for purchase reconciliation runs |
| `eTIMS Credit Note Reason` | Regular | KRA credit note reason code master data |
| `eTIMS Purchase Register Entry` | Regular | Stores KRA auto-populated purchase data for reconciliation |
| `eTIMS Stock Register Entry` | Regular | Stores KRA stock movement data for reconciliation |
| `eTIMS Purchase Order Tracking` | Regular | PO-to-invoice audit trail (with separate api.py, controllers.py, lists.py) |

### 3.4 Reports (9 new)

| Report | Purpose |
|--------|---------|
| `eTIMS X Daily Report` | Interim daily report (TIS Spec 15) -- data since last Z Report |
| `eTIMS Z Daily Report` | Official end-of-day accounting record (TIS Spec 16) -- transactions by receipt type, tax rate, payment method |
| `eTIMS PLU Report` | Price Look-Up report -- items sold with quantities, amounts, tax codes |
| `eTIMS VAT Return Preview` | Pre-filing VAT return data grouped by tax code and category |
| `eTIMS Purchase Reconciliation` | KRA vs local Purchase Invoice comparison with variance analysis |
| `eTIMS Stock Reconciliation` | KRA vs ERPNext Stock Ledger comparison |
| `eTIMS Supplier Compliance` | Supplier compliance scores, PIN verification status, invoice transmission rates |
| `eTIMS Payment Reconciliation` | Payment Entry vs invoice verification status |
| `eTIMS Income/Expense Validation` | Tax deductibility check: flags non-eTIMS-compliant expenses |

### 3.5 Infrastructure

| File/Directory | Purpose |
|----------------|---------|
| `installation/after_install.py` | Creates eTIMS Settings Single record; sets up Workspace Sidebar (v16) |
| `installation/etims_roles.py` | Creates 7 eTIMS roles with granular permissions across all DocTypes |
| `tasks.py` | Scheduler task dispatcher: daily fetches, weekly verifications, monthly scoring |
| `setup_dashboard.py` | Creates Number Cards (6) and Dashboard Charts (3) for eTIMS workspace |
| `custom_fields/` | Custom field definitions directory |
| `fixtures/` | Fixture JSON files for deployment |
| `desktop_icon/` | Desktop icon for v16 app launcher |
| `public/icons/`, `public/icons.svg` | App icons |
| `public/images/` | App images (logo for v16 app screen) |
| `public/js/` | Client-side JS (etims_icons.js loaded globally) |
| `tests/test_etims_expense_compliance.py` | Test for expense compliance validation |
| `kenya_etims_compliance/test_etims_api.py` | API integration tests |
| `workspace_sidebar/` | v16 Workspace Sidebar definition |
| `page/etims_setup_wizard/` | Setup wizard page |
| `print_format/kenya_etims_pos_receipt/` | POS receipt print format |

---

## 4. Modified Files

### 4.1 hooks.py -- App Configuration

The hooks file is the central nervous system of a Frappe app. Nearly every section changed.

| Area | Original | Modified | Purpose |
|------|----------|----------|---------|
| **App screen** | Not present | `add_to_apps_screen` with logo, title, route | v16 desk home tile |
| **JS includes** | Commented out | `app_include_js = "etims_icons.js"` | Global icon loading |
| **doctype_js** | Sales Invoice, Item, Customer, BOM (Purchase Invoice commented out) | Added Purchase Invoice, Supplier | Enable PI and Supplier client scripts |
| **doctype_list_js** | Not present | `Item: "custom_methods/item_list.js"` | Item list view customizations |
| **Installation hooks** | Commented out | `before_install` (roles), `after_install` (settings), `after_migrate` (workspace sidebar, queue fields) | Automated setup on install/migrate |
| **doc_events - Sales Invoice** | `on_update` -> `insert_tax_details`, `before_submit` -> etims_sales_invoice DocType method | `before_save` -> `validate`, `before_submit` -> `trnsSalesSaveWrReq`, `on_update` -> `insert_invoice_number` | Direct submission without intermediate DocType |
| **doc_events - Stock Entry** | Had `before_save` -> `insert_tax_code` | Removed `before_save`; kept `before_submit` and added `on_submit` | Simplified; tax code inserted during validation |
| **doc_events - Item** | `before_save` -> `create_etims_item_data` | `before_save` -> `autofill_tims_info` | No longer creates separate eTIMS Item DocType |
| **doc_events - Purchase Invoice** | Entirely commented out | Fully enabled: `before_save`, `before_submit`, `on_update`, `on_change`, `on_submit` | Full purchase lifecycle integration |
| **doc_events - Payment Entry** | Not present | `before_submit` -> `validate_payment_for_etims_invoice` | Payment validation gate |
| **scheduler_events** | Single cron every 10 min (retry pending invoices) | 5-min cron (queue retry), daily (5 tasks), weekly (2 tasks), monthly (1 task) | Comprehensive automation |
| **fixtures** | Commented out | Custom Field, Workspace, Workspace Sidebar, Role, eTIMS Credit Note Reason | Deployment-ready fixtures |

### 4.2 sales_invoice.py -- Sales Invoice Backend

This is the most heavily modified file. Key changes:

| Change | Purpose |
|--------|---------|
| Removed `requests` import; added `KRAClient`, `get_etims_settings`, `get_receipt_label`, `enqueue_invoice` | Centralized API and queue integration |
| Added `searchSalesTrnsReq()` and `selectSalesTrnsInfoReq()` | New whitelisted endpoints for searching/viewing sales transactions in eTIMS |
| `validate()` now checks POS Profile for `custom_enable_etims_signing` | Auto-enable eTIMS from POS Profile (server-side fallback) |
| Removed `confirm_etims_sinv()`, `get_sinv_data()`, `get_etims_sinv_data()` | Eliminated dependency on eTIMS Sales Invoice DocType |
| `insert_tax_details()` renamed to `insert_invoice_number()` | Clearer naming; now sets invoice number, SCU, warehouse, tax amounts |
| Removed `get_sales_type_code()`, `get_rcpt_type_code()`, `get_payment_type_code()`, `get_sales_status_code()` | These code-to-value mappings are now stored directly on the Sales Invoice via custom fields |
| `create_etims_sinv()` and `auto_create_etims_sinv()` replaced by `trnsSalesSaveWrReq()` | Direct submission to KRA via queue instead of creating intermediate DocType |
| Added `etims_sale_item_list_stock()` | Separate item list for stock-maintaining items |
| Added `create_qr_code()` and `create_attachment()` | QR code generation per KRA spec with file attachment |
| Removed `create_etims_sales_invoice()` and `update_existing_etims_sinv()` (180+ lines) | Eliminated eTIMS Sales Invoice intermediate DocType entirely |
| Removed `get_etims_details()` SQL query | Settings now from `eTIMS Settings` and `TIS Device Initialization` |
| Bare `except:` clauses replaced with `except Exception as e:` with `frappe.throw(_(...))` | Proper error handling with translatable messages |
| Removed `frappe.db.commit()` calls | Frappe handles commits at the end of the request lifecycle |

### 4.3 sales_invoice.js -- Sales Invoice Frontend

| Change | Purpose |
|--------|---------|
| Added `is_return` and `onload` handlers for `updateSalesType()` | Dynamic receipt type and invoice status code based on return status |
| Added `pos_profile` handler | Auto-set eTIMS signing from POS Profile |
| Queue status dashboard headline with color coding | Visual feedback for eTIMS submission status |
| "Retry eTIMS" button for failed queue entries | Manual retry without resubmitting invoice |
| "Search Sales Transaction" button | Query KRA for transaction details |
| "Print Copy" button (TIS Spec 4.1.2) | Increments copy counter and prints with COPY watermark |
| Removed "Preview eTIMS Information" and "Create eTIMS Sales Invoice" buttons | No longer uses intermediate DocType |

### 4.4 purchase_invoice.py -- Purchase Invoice Backend

| Change | Purpose |
|--------|---------|
| Added `searchPurchaseTrnsReq()` and `selectPurchaseTrnsInfoReq()` | Whitelisted endpoints for purchase transaction search/details |
| Added `handle_reverse_invoice()` | Buyer-initiated invoicing for unregistered suppliers per KRA Reverse Invoicing Guidelines (March 2025) |
| `trnsPurchaseSaveReq()` now checks `custom_is_reverse_invoice` flag | Routes to reverse invoice handler when applicable |
| Submission uses queue (`enqueue_invoice()`) when `enable_queue` is set | Async submission matching sales invoice pattern |
| `requests.post()` replaced with `KRAClient().post()` | Centralized API client |
| Bare `except:` replaced with proper exception handling | Error messages are translatable and logged |

### 4.5 item.py -- Item Backend

| Change | Purpose |
|--------|---------|
| `create_etims_item_data()` replaced by `autofill_tims_info()` | No longer creates separate eTIMS Item DocType; populates custom fields directly on Item |
| Added `searchItemReq()` and `selectItemReq()` | Whitelisted endpoints for item search/details in eTIMS |
| Error responses now logged via `eTIMS.log_errors()` | Consistent error logging |
| `importItemUpdateReq()` uses `KRAClient().post()` | Centralized API client |
| Removed eTIMS Item DocType creation logic | Item data stored as custom fields on the Item doctype itself |
| `get_country_code()` removed | Simplified; country code handled differently |

### 4.6 stock.py -- Stock Entry Backend

| Change | Purpose |
|--------|---------|
| `insert_tax_code()` removed entirely | Tax code insertion moved to validation phase |
| `insert_tax_rate_and_amount()` simplified | Inline calculation instead of delegating to `insert_item_tax()` helper |
| Added `searchStockMoveReq()` | Whitelisted endpoint for stock movement search in eTIMS |
| `update_stock_to_etims()` now supports queue mode | Checks `enable_queue` setting; falls back to synchronous submission |
| `requests.post()` replaced with `KRAClient().post()` | Centralized API client |

### 4.7 customer.py -- Customer Backend

| Change | Purpose |
|--------|---------|
| `requests.post()` replaced with `KRAClient().post()` | Centralized API client |
| `print()` replaced with `frappe.logger().debug()` | Proper logging |
| Bare `except:` replaced with `except Exception as e:` with `frappe.log_error()` | Error traceability |

### 4.8 bom.py -- BOM Backend

| Change | Purpose |
|--------|---------|
| `requests.post()` replaced with `KRAClient().post()` | Centralized API client |
| Error logging uses `eTIMS.log_errors()` | Consistent error logging |

### 4.9 etims_utils.py -- Utility Class

| Change | Purpose |
|--------|---------|
| All methods decorated with `@staticmethod` | Proper Python class design; no implicit `self` parameter |
| `get_user_branch_id()` replaced raw SQL with `frappe.db.get_all()` | Cleaner ORM usage |
| `tims_base_url()` now delegates to `get_api_url()` from eTIMS Settings | URL configuration centralized |
| Added `verify_supplier_pin()` | Supplier PIN verification via KRA `selectCustomer` endpoint |
| Added `log_errors()` | Centralized error logging to Error Logging DocType (gated by eTIMS Settings) |
| Added `handle_api_response()` | Standardized API response handling with error code mapping |
| `itemSaveReq()` reads from Item DocType directly (not eTIMS Item) | Reflects elimination of eTIMS Item intermediate DocType |
| `type(x) == str` replaced with `isinstance(x, str)` | Pythonic type checking |
| Bare `except:` replaced with `except Exception as e:` | Error traceability |
| Removed `frappe.db.commit()` calls | Frappe handles commits |
| `get_list` changed to `get_all` in `get_headers()` | Consistent API usage |

### 4.10 etims_response.py -- Mock API Responses

| Change | Purpose |
|--------|---------|
| `@frappe.whitelist(allow_guest=True)` changed to `@frappe.whitelist()` | **Security fix:** Mock endpoints no longer accessible without authentication |
| Communication key reverted to original test value | Sandbox key alignment |

### 4.11 __init__.py -- App Init

| Change | Purpose |
|--------|---------|
| Added `check_app_permission()` | Permission gate for v16 app screen tile; blocks Website Users |

### 4.12 .github/workflows/ci.yml and README.md

Minor updates for CI configuration and documentation alignment.

---

## 5. Removed Files and DocTypes

### 5.1 Removed DocTypes (from baseline)

| DocType | Reason for Removal |
|---------|-------------------|
| `eTIMS Sales Invoice` | Replaced by direct submission from Sales Invoice via queue. The intermediate DocType added complexity without benefit. |
| `eTIMS Sales Invoice Item` | Child table of eTIMS Sales Invoice -- removed with parent |
| `eTIMS Item` | Item eTIMS data now stored as custom fields directly on the Item DocType. Eliminates data duplication. |
| `eTIMS Item Group` | Functionality absorbed into Item custom fields and classification codes |
| `eTIMS Tax Account` | Tax configuration consolidated into eTIMS Settings |
| `eTIMS Tax Configuration` | Tax configuration consolidated into eTIMS Settings |
| `Tax Branch Configurations` | Configuration consolidated into eTIMS Settings and TIS Device Initialization |

### 5.2 Removed Print Formats

| Print Format | Reason |
|--------------|--------|
| `eTIMS Compliant Invoice` | Replaced by updated print format system |
| `eTIMS Compliant Invoice (Sales Invoice)` | Replaced by updated print format system |

### 5.3 Removed Code Patterns

- All direct `import requests` usage in business logic modules
- All `frappe.db.commit()` calls within hooks (anti-pattern in Frappe)
- All bare `except:` clauses (replaced with `except Exception as e:`)
- All `print()` statements (replaced with `frappe.logger()`)
- All `type(x) == str` checks (replaced with `isinstance()`)
- `get_etims_details()` raw SQL query in sales_invoice.py

---

## 6. DocType Schema Changes

The following existing DocTypes had their JSON schemas modified (field additions, permission changes, or property updates). The modifications are primarily for v16 compatibility (migration hash updates, field ordering) and new custom fields.

### Modified DocType JSONs

| DocType | Nature of Change |
|---------|-----------------|
| `Error Logging` | Schema refresh for v16 |
| `eTIMS BOM Item` | Field updates |
| `eTIMS Branch Information` | Added JS controller, field updates, permission changes |
| `eTIMS Branch Item` | Field updates |
| `eTIMS Branch User` | Added JS controller, field updates, permission changes |
| `eTIMS Code Classification` / Item | Schema updates |
| `eTIMS Code Information` | Added JS controller, field updates |
| `eTIMS Country` | Schema updates |
| `eTIMS Customer` | Added `etims_customer.js` (client script) and `test_etims_customer.py`; schema updates |
| `eTIMS Import Item` | Field and controller updates |
| `eTIMS Import Item Information` | JS controller, field, and controller updates |
| `eTIMS Insurance` | JS controller, field, and controller updates |
| `eTIMS Item Classification` | Schema updates |
| `eTIMS Item Information` | JS controller, field, and controller updates |
| `eTIMS Notice` / Item | Schema updates |
| `eTIMS Packing Unit` | Schema updates |
| `eTIMS Purchase Information` | JS controller, field, and controller updates |
| `eTIMS Purchase Invoice` / Item | Field and controller updates |
| `eTIMS Quantity Unit` | Schema updates |
| `eTIMS Registered Items` | Schema updates |
| `eTIMS Sales Receipt` | Schema updates |
| `eTIMS Stock Information` | JS controller, field, and controller updates |
| `eTIMS Stock Item` | Field updates |
| `eTIMS Stock Movement` / Item | Field and controller updates |
| `eTIMS Stock Release Number` | JS controller, field, and controller updates |
| `Tax Branch Office` | Schema updates |
| `TIS Communication Key` | Schema updates |
| `TIS Device Initialization` | JS controller, field, and controller updates |

### Modified Custom Field JSONs

| Custom Field Set | Changes |
|-----------------|---------|
| `bom.json` | Updated field definitions for BOM eTIMS integration |
| `bom_item.json` | Updated child table fields |
| `item.json` | Major additions: eTIMS data now stored directly on Item (previously on eTIMS Item DocType) |
| `item_barcode.json` | Field updates |
| `purchase_invoice_item.json` | Added eTIMS-specific item fields |
| `sales_invoice.json` | Added queue status, receipt copy count, invoice number, sales type/receipt type/payment type code fields |
| `sales_invoice_item.json` | Updated item-level eTIMS fields |
| `sales_taxes_and_charges.json` | Tax code mapping fields |
| `stock_entry_detail.json` | eTIMS tax and item code fields |

---

## 7. Security and Permissions

### 7.1 Role-Based Access Control

**File:** `installation/etims_roles.py`

Seven granular roles replace the original approach of using standard ERPNext roles:

| Role | Desk Access | Description |
|------|-------------|-------------|
| eTIMS Administrator | Yes | Full access to all eTIMS functions and settings |
| eTIMS Manager | Yes | Branch-level oversight with full operations access |
| eTIMS Operator | Yes | Day-to-day operations -- create transactions, no delete |
| eTIMS Auditor | No | Read-only access for audit and review |
| eTIMS Sales Clerk | Yes | Sales Invoice sync and item search |
| eTIMS Purchase Clerk | Yes | Purchase Invoice sync and item search |
| eTIMS Store Keeper | Yes | Stock Entry and Stock Release Number management |

### 7.2 Permission Utilities

**File:** `utils/permissions.py`

Provides:
- Role check functions (`is_etims_admin()`, `can_modify_doctype()`, `can_sync_to_etims()`)
- Decorators (`@require_admin()`, `@require_manager()`, `@require_sync_permission()`)
- Branch access validation (`validate_branch_access()`)
- Permission audit logging (`log_permission_check()`)

### 7.3 Security Fixes

| Fix | Location | Impact |
|-----|----------|--------|
| `allow_guest=True` removed from mock API endpoints | `etims_response.py` | Prevents unauthenticated access to test data endpoints |
| `check_app_permission()` added | `__init__.py` | Blocks Website Users from accessing eTIMS app screen |
| `frappe.has_permission()` checks added | `bulk_operations.py`, `organization.py` | Explicit permission validation before operations |

---

## 8. Scheduled Tasks

### Original
```python
scheduler_events = {
    "cron": {
        "*/10 * * * *": ["...retry_pending_etims_invoices"]
    }
}
```

### Modified
```python
scheduler_events = {
    "cron": {
        "*/5 * * * *": ["...queue_processor.retry_failed_invoices"]
    },
    "daily": [
        "tasks.fetch_kra_notices",
        "tasks.fetch_purchase_transactions",
        "tasks.run_reconciliation_task",
        "tasks.fetch_import_items",
        "tasks.send_deadline_reminders",
    ],
    "weekly": [
        "tasks.verify_supplier_pins",
        "tasks.calculate_supplier_scores",
    ],
    "monthly": [
        "tasks.generate_compliance_score",
    ],
}
```

| Schedule | Task | Purpose |
|----------|------|---------|
| Every 5 min | `retry_failed_invoices` | Retry queued invoices that failed (was 10 min in original) |
| Daily | `fetch_kra_notices` | Download new KRA notices |
| Daily | `fetch_purchase_transactions` | Pull KRA purchase data for reconciliation |
| Daily | `run_reconciliation_task` | Run purchase reconciliation for previous month |
| Daily | `fetch_import_items` | Process pending import items from KRA |
| Daily | `send_deadline_reminders` | VAT filing deadline alerts (5 days and 1 day before 20th) |
| Weekly | `verify_supplier_pins` | Batch verify supplier KRA PINs (100 per run) |
| Weekly | `calculate_supplier_scores` | Recalculate supplier compliance scores |
| Monthly | `generate_compliance_score` | Generate monthly compliance scorecard |

---

## 9. Reports

All nine reports follow the standard Frappe Script Report pattern with `execute(filters)` returning columns, data, message, chart, and report_summary.

| Report | Data Sources | Chart Type |
|--------|-------------|------------|
| eTIMS Z Daily Report | Sales Invoice (grouped by receipt type, tax rate, payment method) | Bar |
| eTIMS X Daily Report | Same as Z Report but since last Z Report (does not reset counters) | Bar |
| eTIMS PLU Report | Sales Invoice Item (quantity sold, total amount, tax by item) | N/A |
| eTIMS VAT Return Preview | Sales Invoice + Purchase Invoice taxes by tax code | Bar |
| eTIMS Purchase Reconciliation | eTIMS Purchase Register Entry vs Purchase Invoice | Donut |
| eTIMS Stock Reconciliation | eTIMS Stock Register Entry vs Stock Ledger Entry | Bar |
| eTIMS Supplier Compliance | Supplier custom fields (score, PIN status, invoice stats) | Bar |
| eTIMS Payment Reconciliation | Payment Entry vs Purchase Invoice verification status | Donut |
| eTIMS Income/Expense Validation | Sales Invoice + Purchase Invoice (eTIMS compliance flag) | Bar |

---

## 10. Breaking Changes

### 10.1 DocType Removals

Any code, reports, or custom scripts referencing the following DocTypes will break:
- `eTIMS Sales Invoice`
- `eTIMS Sales Invoice Item`
- `eTIMS Item`
- `eTIMS Item Group`
- `eTIMS Tax Account`
- `eTIMS Tax Configuration`
- `Tax Branch Configurations`

**Migration path:** Data from `eTIMS Item` should be migrated to custom fields on `Item`. Data from `eTIMS Sales Invoice` is no longer needed as the source of truth is the Sales Invoice itself plus KRA's records.

### 10.2 API Endpoint Changes

- `create_etims_sinv` (whitelisted) -- REMOVED. Replace with `trnsSalesSaveWrReq` (called automatically on submit).
- `auto_create_etims_sinv` -- REMOVED. Queue handles automatic submission.
- `get_sinv_data`, `get_etims_sinv_data` -- REMOVED. Read from Sales Invoice directly.

### 10.3 Hook Method Changes

| Hook | Original Method | New Method |
|------|----------------|------------|
| Item before_save | `create_etims_item_data` | `autofill_tims_info` |
| SI on_update | `insert_tax_details` | `insert_invoice_number` |
| SI before_submit | `etims_sales_invoice.writeInvoiceToeTIMS` | `sales_invoice.trnsSalesSaveWrReq` |

### 10.4 Custom Field Dependencies

The modified app expects the following custom fields to exist (created by `install_queue_fields.py` after_migrate hook):
- `Sales Invoice.custom_etims_queue_status`
- `Sales Invoice.custom_etims_queue_entry`
- `Purchase Invoice.custom_etims_queue_status`
- `Purchase Invoice.custom_etims_queue_entry`
- `Stock Entry.custom_etims_queue_status`
- `Stock Entry.custom_etims_queue_entry`

### 10.5 Settings Dependency

The new `eTIMS Settings` Single DocType must exist for many features to work. The `after_install` hook creates it automatically, but manual installations need to create it.

---

## 11. Post-Audit Fixes (2026-07-29)

Roles/permissions audit and full non-destructive smoke test on production site `mbaguya` (frappe/erpnext v16). Findings remediated:

### 11.1 eTIMS Code Information -- missing role permissions (Medium)

`eTIMS Code Information` shipped with permissions for only `Sales User` and `System Manager`. The intended eTIMS-role grants lived in `installation/etims_roles.py::add_etims_role_permissions()`, which runs in `before_install` (before the app's own DocTypes exist, so every `frappe.db.exists("DocType", ...)` check is False) and is never re-run on migrate -- the grants therefore never applied. Added all seven eTIMS roles directly to `etims_code_information.json` (the durable source of truth): Administrator/Manager full CRUD; Operator/Sales Clerk/Purchase Clerk/Store Keeper create+write, no delete; Auditor read-only.

### 11.2 Removed dead install code (Low)

Deleted the no-op `update_existing_doctype_permissions()` and `add_etims_role_permissions()` from `installation/etims_roles.py`. Both targeted app DocTypes that do not exist at `before_install` time and were never called on migrate. `before_install()` now only calls `create_etims_roles()`. DocType JSON is the single source of truth for permissions.

### 11.3 Dashboard Number Card duplication on migrate (Low/Medium)

`setup_dashboard.py` inserted the "Sales Success Rate" card with `name="Sales Success Rate"` but `label="Sales Success Rate (%)"`. Number Cards autoname from their label, so the idempotency check `frappe.db.exists("Number Card", "Sales Success Rate")` never matched and a duplicate card was created on every `bench migrate`. Set the card `name` to `"Sales Success Rate (%)"` (matching label) and removed the accumulated duplicate on production.

### 11.4 Role fixture never exported (Low)

`hooks.py` declared a `Role` fixture for the seven eTIMS roles, but no `fixtures/role.json` existed, so `bench migrate` could not recreate roles if deleted (they were created only once at `before_install`). Added `fixtures/role.json` with the seven roles.

### 11.5 Verification

- `bench --site mbaguya migrate` runs clean (after_migrate hooks + patches, no errors).
- Live DB: eTIMS Code Information now carries 9 permission rows (including all 7 eTIMS roles); all 7 roles present; no dangling permission-to-role references; single `Sales Success Rate (%)` card.
- Full smoke test: 40/40 DocTypes instantiate, 9/9 Script Reports execute, 12/12 Number Cards + dashboard API compute, 5/6 charts (the 6th is an empty-state -- 0 matching rows, framework behaviour, not a defect), workspace + sidebar load, utility functions pass.

**Files changed:** `kenya_etims_compliance/kenya_etims_compliance/doctype/etims_code_information/etims_code_information.json`, `kenya_etims_compliance/installation/etims_roles.py`, `kenya_etims_compliance/setup_dashboard.py`, `kenya_etims_compliance/fixtures/role.json` (new).

---

## 12. Workspace Sidebar & Desk Icon Fix (2026-07-29)

Two production issues on `mbaguya`: the eTIMS workspace sidebar did not render, and the desk showed two "eTIMS" icons. Root causes were a workspace/sidebar name mismatch plus non-standard file structure; fixed by aligning to Frappe v16 conventions.

### 12.1 Root cause

- **Sidebar not rendering:** the desk resolves a workspace's `Workspace Sidebar` by matching the sidebar record's name to the workspace name (`frappe.boot.workspace_sidebar_item[<workspace>.toLowerCase()]`, see `frappe/public/js/frappe/ui/sidebar/sidebar.js` + `frappe/boot.py::get_sidebar_items`). The sidebar was named `eTIMS` but the workspace was `eTIMS Compliance` (route `/app/etims-compliance`), so no boot key matched and the custom sidebar never loaded.
- **Two desk icons:** `create_desktop_icons_from_workspace` (`frappe/desk/doctype/desktop_icon/desktop_icon.py`) hides the workspace-derived Link icon only when the workspace name equals `app_title`. `app_title` is `eTIMS` but the workspace was `eTIMS Compliance`, so the Link icon ("eTIMS Compliance") showed alongside the app's App icon -> duplicate.

### 12.2 Fix -- rename workspace to `eTIMS` and align structure

- Renamed the Workspace `eTIMS Compliance` -> `eTIMS` (name = `app_title` = sidebar name). Route is now `/app/etims`. This makes the sidebar resolve by direct name match AND makes Frappe auto-hide the duplicate workspace icon.
- Moved the Workspace to the standard folder-per-record path `kenya_etims_compliance/workspace/etims/etims.json` (synced via `IMPORTABLE_DOCTYPES`).
- Moved the Workspace Sidebar to the standard app-level path `workspace_sidebar/etims.json` (synced via the `app_level_folders` list in `frappe/model/sync.py`); removed the non-standard duplicates: `fixtures/workspace_sidebar.json`, the flat module-dir copy, and the `Workspace`/`Workspace Sidebar` fixture entries + v16 append block in `hooks.py`.
- Removed the legacy `desktop_icon/*.json` files (both copies); the app tile now comes solely from the standard v16 `add_to_apps_screen` hook (route updated to `/app/etims`).
- Removed the now-redundant `after_install.setup_workspace_sidebar` (and its `after_migrate` entry) -- the sidebar is synced by the standard mechanism.
- Updated the setup-wizard redirect + button to `/app/etims` / "Go to eTIMS".

### 12.3 Production remediation + verification

- Renamed the live Workspace doc `eTIMS Compliance` -> `eTIMS`; deleted the two stale Desktop Icons; ran `bench --site mbaguya migrate` (clean); regenerated icons via `create_desktop_icons()`.
- Live DB after fix: Workspace `eTIMS` present (old name gone), Workspace Sidebar `eTIMS` present (48 items, Home -> `eTIMS`), boot sidebar key `etims` present, exactly one visible desk icon `eTIMS` (-> `/app/etims`).
- Browser-verified on the running site: opening `/app/etims` renders the full custom sidebar (Getting Started, Daily Operations, Reconciliation, Reports, Monitoring) and shows a single `eTIMS` app icon.

**Files changed:** `hooks.py`, `installation/after_install.py`, `kenya_etims_compliance/page/etims_setup_wizard/etims_setup_wizard.js`, workspace moved to `kenya_etims_compliance/workspace/etims/etims.json`, sidebar at `workspace_sidebar/etims.json`; removed `fixtures/workspace_sidebar.json`, both `desktop_icon/kenya_etims_compliance.json`, and the flat `kenya_etims_compliance/workspace_sidebar/etims_compliance.json`.

---

## 13. Role Profiles (2026-07-29)

Added per-persona **Role Profiles** so an admin can grant eTIMS access in one field on the User form (`role_profile_name`) instead of assigning individual roles. Neither the `matoro` nor `alidav16` copy previously shipped any Role Profile.

### 13.1 What was added

- Seven Role Profiles, one per eTIMS role (least-privilege, eTIMS roles only -- no standard ERPNext roles bundled): `eTIMS Administrator`, `eTIMS Manager`, `eTIMS Operator`, `eTIMS Auditor`, `eTIMS Sales Clerk`, `eTIMS Purchase Clerk`, `eTIMS Store Keeper`. Each profile contains exactly its matching eTIMS role.
- Shipped as `fixtures/role_profile.json` and registered in `hooks.py` `fixtures` (filtered to the seven names), so they sync on install/migrate like `role.json`.

### 13.2 Note on migrate + background worker

`Role Profile.on_update` enqueues `update_all_users` on the `long` queue (it only runs synchronously under `in_install`/`in_test`) and locks the doc until the job runs. On a normal production server (workers running) this drains automatically. On a worker-less box, the queued action leaves a stale file lock in `sites/<site>/locks/` that blocks the next migrate with `DocumentLockedError` -- clear the locks and run a `bench worker` (long queue) to drain. Verified clean on `mbaguya` with a worker running: migrate succeeds, all seven profiles present with their roles, no residual locks.

**Files changed:** `hooks.py` (Role Profile fixture entry), `kenya_etims_compliance/fixtures/role_profile.json` (new).

---

## 14. Number Card Dashboard Fixes (2026-09-06)

Two independent bugs left the eTIMS workspace unable to render 8 of its 12 number cards.

### 14.1 Root cause

- Sum-type cards (`eTIMS Sales Amount Today`, `eTIMS Sales Amount This Month`) never set `aggregate_function_based_on`, which Number Card's own `validate()` requires whenever `function != "Count"`. Every insert failed with "Aggregate Field is required to create a number card".
- All 8 filtered cards used bareword `Today` / `This Month` inside `filters_json` instead of Frappe's `Timespan` operator (`["Sales Invoice", "posting_date", "Timespan", "today"]`), which crashes client-side the moment the workspace widget resolves the dynamic filter via `orjson.loads()`.

### 14.2 Fix and verification

Fixed both in `setup_dashboard.py`'s card definitions and re-synced `workspace/etims/etims.json` so the fixture matches. Verified live: `create_number_cards()` inserts all 12 rows with zero new Error Log entries, and the workspace renders real values end-to-end in browser (Sales Today: KES 3.00, Sales This Month: KES 17208.00, etc.).

**Files changed:** `kenya_etims_compliance/setup_dashboard.py`, `kenya_etims_compliance/kenya_etims_compliance/workspace/etims/etims.json`.

---

## 15. Purchase-Side Reconciliation Engine (2026-09-06)

Closes the "trust the till" gap on the purchase side: Purchase Invoices no longer need a human to mark them verified before payment can happen, and payment is never blocked on KRA state the payer doesn't control. Instead, a real reconciliation engine matches each local Purchase Invoice against KRA's own purchase register -- KES-tolerant, band-by-band (A-E) -- and enforcement moves from ad hoc invoice/payment gates to period close.

### 15.1 Reconciliation engine

**Files:** `custom_methods/reconciliation.py`, `tasks.py`

- New per-band comparison (`_get_band_mismatch_rows`) reconciling KRA's own A-E tax decomposition against the local eTIMS Purchase Invoice for every matched register entry, not just the header total.
- `run_reconciliation(period, branch)` is the single entry point used by both the scheduled job and the manual "Run Reconciliation" button; `close_period` now blocks on unresolved reconciliation exceptions instead of a payment-time verification flag.
- `fetch_purchase_transactions` fixed to advance a proper rolling high-water mark instead of an unbounded/self-widening lookback window; `eTIMS Purchase Information.upsert_purchase_invoice` dedup hardened.

### 15.2 New DocType: eTIMS Reconciliation Exception

Tracks Missing Locally / Not in KRA / Amount Mismatch (now including per-band mismatches) individually so each can be reviewed, accepted, or corrected before a period closes, instead of the old behavior of silently blocking or silently passing.

### 15.3 Payment Entry advisory gate

**File:** `custom_methods/payment_entry.py`

Replaced the hard block ("Cannot make payment for unverified invoices") with an advisory-only notice naming each unconfirmed invoice and its KRA match status, since KRA's purchase register is only populated once the *supplier* files -- routinely after the payment is already due. Blocking `check_payment_eligibility` replaced by reporting-only `get_payment_etims_status`.

### 15.4 Purchase Invoice

**Files:** `custom_methods/purchase_invoice.py`, `custom_methods/purchase_invoice.js`

Added `purchase_return_information` (debit-note counterpart to the existing sales-return logic), an `accept_not_in_kra` UI action for resolving reconciliation exceptions, and reworked `verify_supplier_invoice` / `get_last_inv_number` against the new verification/band fields.

### 15.5 Shared KRA tax-band handling

**File:** `utils/etims_utils.py`

`KRA_TAX_BANDS` and `_resolve_band_code` / `apply_tax_bands` are now the single source of truth for the A-E band breakdown that was previously duplicated ad hoc across sales and purchase payload builders. Propagated into `etims_vat_return_preview`, `etims_x_daily_report` / `etims_z_daily_report` (new shared `_filter_invoices` helper), and `etims_plu_report`. Also fixes `create_new_item_doctype` to auto-vivify a missing `custom_item_classification_code` Link target instead of throwing on first sync.

### 15.6 Settings and fixtures

Existing `enforce_invoice_verification` setting repurposed as the period-close gate (relabeled "Enforce Reconciliation at Period Close"); new `purchase_fetch_lookback_days` setting for the high-water-mark fetch. New Purchase Invoice verification/reconciliation custom fields installed via `install_queue_fields.py` and wired into `after_install.py` and `setup_wizard.py`.

### 15.7 Also

`escpos.py` QR code now checks both bytes of its little-endian length prefix (previously only one), and logs via `frappe.log_error` instead of silently dropping the code when a legitimate KRA verification URL lands in an unsafe length range; `kra_client.py` drops `select_trns_sales_info`/`select_trns_purchase_info` -- not real KRA endpoints (README corrected to match: KRA exposes list-only search, no per-invoice detail call). Test suite updated to match the advisory payment flow and the new reconciliation/band behavior.

### 15.8 Verification

`git status --short` clean after commit; two independent, file-disjoint commits pushed to `upstream/coale-v16` with zero new Error Log entries introduced.

**Files changed:** 42 files, +2251/-939. Primary: `custom_methods/reconciliation.py`, `tasks.py`, `custom_methods/payment_entry.py`, `custom_methods/purchase_invoice.py`/`.js`, `utils/etims_utils.py`, `utils/escpos.py`, `utils/kra_client.py`; new doctype `doctype/etims_reconciliation_exception/`; `doctype/etims_reconciliation_log/etims_reconciliation_log.js` (new); `doctype/etims_settings/`; reports `etims_vat_return_preview`, `etims_x_daily_report`, `etims_z_daily_report`, `etims_plu_report`, `etims_purchase_reconciliation`; `installation/after_install.py`; `custom_methods/install_queue_fields.py`; `fixtures/custom_field.json`; `custom_methods/setup_wizard.py`, `dashboard.py`, `sales_invoice.py`, `bulk_operations.py`, `queue_processor.py`, `stock_reconciliation_etims.py`; `doctype/etims_purchase_information/`, `etims_purchase_invoice/`, `etims_item_information/`; tests (`test_escpos.py` new, `test_etims_custom_methods.py`, `test_etims_expense_compliance.py`, `test_etims_utils.py`); `README.md`.

---

*End of audit document.*
