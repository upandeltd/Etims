<div align="center">
<h1>Coale Tax — Kenya eTIMS Compliance</h1>
<p><strong>ERPNext integration with Kenya Revenue Authority's electronic Tax Invoice Management System</strong></p>

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](license.txt)
[![Frappe Framework](https://img.shields.io/badge/Frappe-v15+-blue)](https://frappeframework.com)
[![ERPNext](https://img.shields.io/badge/ERPNext-v15+-green)](https://erpnext.com)
[![Python](https://img.shields.io/badge/Python-3.10+-yellow)](https://python.org)
</div>

---

## Overview

**Coale Tax** (formerly Kenya eTIMS Compliance) is a Frappe/ERPNext app that integrates with KRA's **eTIMS** (electronic Tax Invoice Management System). It automates tax-compliant invoicing, stock tracking, item registration, and invoice verification — mandatory for all VAT-registered businesses in Kenya.

The app hooks into ERPNext's core doctypes (Sales Invoice, Purchase Invoice, Stock Entry, Item, Payment Entry) to automatically sync transactions with the KRA eTIMS servers, generate QR codes, and enforce compliance at every step.

### Key Features

| Feature | Description |
|---|---|
| **Sales Invoice Sync** | Auto-submits sales transactions to eTIMS on invoice submission with QR code generation |
| **Purchase Invoice Sync** | Syncs purchase transactions and validates supplier invoices against KRA records |
| **Invoice Checker API** | Verifies supplier invoices against KRA eTIMS before payment processing |
| **Stock Movement Tracking** | Reports stock entries, transfers, and releases to eTIMS |
| **Item Registration** | Registers and syncs item master data with eTIMS classification codes |
| **Payment Validation** | Blocks payments on unverified Purchase Invoices (2026 compliance) |
| **Role-Based Access Control** | 7 custom roles with granular permissions and branch isolation |
| **Dual API Mode** | Supports both Production and Sandbox KRA environments |
| **Configurable Settings** | Central settings DocType for API URLs, timeouts, retry logic, and feature toggles |
| **Error Logging** | Comprehensive API error logging and audit trail |

---

## Installation

### Prerequisites

- [Frappe Bench](https://frappeframework.com/docs/user/en/bench) (v5.x+)
- [Frappe Framework](https://frappeframework.com) (v15+)
- [ERPNext](https://erpnext.com) (v15+)
- Python 3.10+

### Install

```bash
# Get the app
bench get-app https://github.com/CoaleTech/Coale-Tax.git

# Install on your site
bench --site <site-name> install-app kenya_etims_compliance

# Run migrations
bench --site <site-name> migrate
```

The app automatically creates the required eTIMS roles during installation.

---

## Configuration

### 1. Company PIN Setup

1. Navigate to the **Company** DocType (Accounting workspace or search bar).
2. Set the company **KRA PIN** in the **Tax ID** field.

### 2. Device Initialization

1. Go to **TIS Device Initialization** in the eTIMS Compliance workspace.
2. Select the company — PIN auto-populates.
3. Set the **Tax Branch Office**, **device serial**, and **environment** (Sandbox or Production).
4. Click **Initialize Device** to register with KRA.

Once initialized, the app stores the authenticated OSCU device information (communication key, branch ID) used for all subsequent API calls.

### 3. eTIMS Settings (Optional)

Access **eTIMS Settings** to configure:

| Setting | Default | Description |
|---|---|---|
| API Timeout | 30s | Request timeout (max 300s) |
| Retry Enabled | Yes | Auto-retry failed API calls |
| Max Retry Attempts | 3 | Number of retries |
| Retry Delay | 2s | Delay between retries |
| Default SAR Type (Sales) | 11 | Stock Adjustment Reason for sales |
| Default SAR Type (Purchase) | 02 | Stock Adjustment Reason for purchases |
| Default SAR Type (Stock Entry) | 06 | Stock Adjustment Reason for stock entries |
| RBAC Enabled | Yes | Role-based access control |
| Branch Isolation | Yes | Restrict users to their branch |
| Invoice Verification | Yes | Enforce invoice verification before payment |

---

## How It Works

### Document Event Hooks

The app hooks into ERPNext document events to sync data with eTIMS automatically:

| ERPNext DocType | Events | What Happens |
|---|---|---|
| **Sales Invoice** | before_save, before_submit, on_update, on_submit | Validates invoice numbers, submits to eTIMS, generates QR code, updates stock bins |
| **Purchase Invoice** | before_save, before_submit, on_update, on_change, on_submit | Validates invoice numbers, submits to eTIMS, auto-adds tax templates, updates stock bins |
| **Stock Entry** | before_validate, before_submit, on_submit | Calculates tax rates, syncs stock movements to eTIMS |
| **Item** | before_save | Auto-fills eTIMS classification info |
| **Payment Entry** | before_submit | Blocks payment on unverified purchase invoices |

### Client-Side Integrations

Custom JavaScript is injected into: **Item**, **Customer**, **BOM**, **Sales Invoice**, **Purchase Invoice**, **Supplier** — adding eTIMS action buttons and field validations.

---

## DocTypes

### Core Configuration
- **eTIMS Settings** — Central configuration (API URLs, timeouts, retry logic, RBAC toggles)
- **TIS Device Initialization** — Device registration with KRA (PIN, branch ID, communication key)
- **TIS Communication Key** — Stores API authentication keys
- **Tax Branch Office** — Branch office management

### Transaction Tracking
- **eTIMS Sales Receipt** — Sales transaction records
- **eTIMS Purchase Invoice** / **Purchase Item** / **Purchase Information** — Purchase records
- **eTIMS Purchase Order Tracking** — Purchase order compliance tracking
- **eTIMS Stock Movement** / **Stock Item** / **Stock Information** — Stock movement records
- **eTIMS Stock Release Number** — SAR number management

### Master Data
- **eTIMS Customer** — Customer registration with KRA
- **eTIMS Registered Items** / **Item Information** / **Item Classification** — Item master
- **eTIMS Import Item** / **Import Item Information** — Imported goods tracking
- **eTIMS BOM Item** — Bill of materials composition
- **eTIMS Insurance** / **Notice** / **Notice Item** — Insurance and notices

### Reference Data
- **eTIMS Code Information** / **Code Classification** — KRA code lists
- **eTIMS Country** / **Quantity Unit** / **Packing Unit** — Reference tables

### Branch Management
- **eTIMS Branch Information** / **Branch Item** / **Branch User** — Branch-level data

---

## Roles and Permissions

The app creates **7 custom roles** during installation:

| Role | Access Level | Description |
|---|---|---|
| **eTIMS Administrator** | Full | All eTIMS functions, settings, and configuration |
| **eTIMS Manager** | Branch-level full | Full operations within assigned branch |
| **eTIMS Operator** | Create/Write | Day-to-day operations, no delete permission |
| **eTIMS Auditor** | Read-only | Audit and review access (export, print, report) |
| **eTIMS Sales Clerk** | Sales-scoped | Sales Invoice sync and item search |
| **eTIMS Purchase Clerk** | Purchase-scoped | Purchase Invoice sync and item search |
| **eTIMS Store Keeper** | Stock-scoped | Stock Entry and Stock Release Number management |

**Key rules:**
- Only Admin, Manager, and Operator can sync data to eTIMS
- Auditors have strictly read-only access
- Branch isolation prevents cross-branch operations (configurable)
- Permission decorator `@require_etims_role()` is available for custom API endpoints

> See [ROLE_BASED_ACCESS_CONTROL_GUIDE.md](ROLE_BASED_ACCESS_CONTROL_GUIDE.md) for full details.

---

## API Integration

The app communicates with KRA via 13+ API endpoints:

| Endpoint | Purpose |
|---|---|
| itemSaveReq | Register/update items |
| searchItem / selectItem | Search and retrieve items |
| trnsSalesSaveWrReq | Submit sales transactions |
| trnsPurchaseSaveReq | Submit purchase transactions |
| searchTrns / selectTrnsSalesInfo / selectTrnsPurchaseInfo | Search transactions |
| stockReleaseNoSaveReq | Submit stock release numbers |
| searchStockMove / searchStockReleaseNo / selectStockReleaseNoList | Search stock data |
| invoiceCheckerReq | Verify supplier invoices |
| selectNoticeInfo / selectOrgUsrInfo | Retrieve notices and user info |

**API modes:**
- **Production**: `https://etims-api.kra.go.ke/etims-api/`
- **Sandbox**: `https://etims-api-sbx.kra.go.ke/etims-api/`

> See [ETIMS_API_V2_ENDPOINTS.md](ETIMS_API_V2_ENDPOINTS.md) for complete API documentation.

---

## Project Structure

```
kenya_etims_compliance/
├── custom_methods/          # Document event handlers
│   ├── sales_invoice.py     # Sales Invoice eTIMS sync
│   ├── purchase_invoice.py  # Purchase Invoice eTIMS sync
│   ├── stock.py             # Stock Entry eTIMS sync
│   ├── item.py              # Item registration
│   ├── payment_entry.py     # Payment validation
│   ├── invoice_checker.py   # KRA invoice verification
│   ├── stock_release.py     # Stock release numbers
│   └── *.js                 # Client-side scripts
├── installation/
│   └── etims_roles.py       # Role creation on install
├── kenya_etims_compliance/
│   └── doctype/             # 35 custom DocTypes
├── utils/
│   ├── etims_utils.py       # Core eTIMS API client
│   └── permissions.py       # RBAC utilities
├── hooks.py                 # Frappe hooks configuration
└── ...
```

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| [segno](https://pypi.org/project/segno/) | ~=1.6.1 | QR code generation for eTIMS receipts |
| [stripe](https://pypi.org/project/stripe/) | ~=2.56.0 | Payment processing |

---

## Documentation

- [eTIMS API V2 Endpoints](ETIMS_API_V2_ENDPOINTS.md) — Complete API reference
- [Role-Based Access Control Guide](ROLE_BASED_ACCESS_CONTROL_GUIDE.md) — Permissions and roles
- [Hardcoded Values Analysis](HARDCODED_VALUES_ANALYSIS.md) — Configuration analysis
- [Frappe Framework Docs](https://frappeframework.com/docs/user/en/introduction)
- [ERPNext Documentation](https://docs.erpnext.com/)

---

## Usage Guide

### Sales Invoicing
1. Create a **Sales Invoice** in the Accounting workspace.
2. Fill in items, customer, and tax details.
3. **Save** — the app validates and assigns eTIMS invoice numbers.
4. **Submit** — the invoice is sent to eTIMS and a QR code is generated.

### Purchase Invoicing
1. Create a **Purchase Invoice** in the Accounting workspace.
2. Fill in supplier, items, and tax details.
3. **Save** — auto-validates and adds tax templates.
4. **Submit** — syncs with eTIMS.

### Invoice Verification
1. Before processing payment, the app checks supplier invoices against KRA.
2. Unverified invoices block Payment Entry submission.
3. Manual override available with logging for authorized users.

### Stock Management
1. Create **Stock Entry** (Material Receipt, Transfer, etc.).
2. On submission, stock movements are automatically reported to eTIMS.
3. **Stock Release Numbers** can be managed via the dedicated DocType.

### Item Registration
1. Create an **Item** in the Stock workspace.
2. Check **"Update Item to TIMS"** and save.
3. Fill in eTIMS classification fields and click **"Register Item"**.

---

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'feat: add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the **MIT License** — see [license.txt](license.txt) for details.

Originally developed by [Upande Ltd](https://upande.com). Extended and maintained by [CoaleTech](https://github.com/CoaleTech).
