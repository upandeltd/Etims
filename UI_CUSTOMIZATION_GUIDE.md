# UI Customization Guide: Adding Custom Buttons to eTIMS Forms

This guide explains how to add custom buttons to enable the new eTIMS v2.0 functionality in your ERPNext forms.

---

## Method 1: Using Client Scripts (Recommended)

The client script handlers have already been created. You need to add the custom buttons through the "Customize Form" feature.

---

## 1. Item Form - "Search in eTIMS" Button

### Option A: Via Customize Form (UI)

1. Go to **Item** list
2. Click on **Menu (three dots)** → **Customize Form**
3. Add a new **Custom Action**:
   - **Label:** `Search in eTIMS`
   - **Action:** `custom_search_item_in_etims`
   - **Action Type:** `Client Action`

Or add a Button field:
- **Field Name:** `search_item_in_etims`
- **Label:** `Search in eTIMS`
- **Field Type:** `Button`
- **Insert After:** `item_code`

### Option B: Via Client Script (Already Created)

The handler is already in `custom_methods/item.js`. To activate:

1. Go to **Home** → **Customization** → **Client Scripts**
2. Click **New**
3. Fill in:
   - **DocType:** `Item`
   - **Module:** `Kenya eTIMS Compliance`
4. Paste the following code:

```javascript
frappe.ui.form.on('Item', {
    refresh: function(frm) {
        if (frm.doc.custom_item_code || frm.doc.custom_item_name) {
            frm.add_custom_button(__('Search in eTIMS'), function() {
                frappe.call({
                    method: "kenya_etims_compliance.custom_methods.item.searchItemReq",
                    args: {
                        "item_code": frm.doc.custom_item_code || null,
                        "item_name": frm.doc.custom_item_name || null
                    },
                    freeze: true,
                    callback: function(r) {
                        let keys = Object.keys(r.message)
                        let values = Object.values(r.message)
                        frappe.msgprint({
                            title: __(keys[0]),
                            indicator: keys[0] === 'Success' ? 'green' : 'red',
                            message: __(JSON.stringify(values[0], null, 2))
                        });
                    }
                })
            }, __('Actions'));
        }
    },

    custom_search_item_in_etims: function(frm) {
        // Same handler as above
    }
});
```

---

## 2. Sales Invoice Form - "Search Transaction" Button

### Via Client Script

1. Go to **Home** → **Customization** → **Client Scripts**
2. Click **New**
3. Fill in:
   - **DocType:** `Sales Invoice`
   - **Module:** `Kenya eTIMS Compliance`
4. Paste the following code:

```javascript
frappe.ui.form.on("Sales Invoice", {
    refresh: function(frm) {
        if (frm.doc.custom_invoice_number) {
            frm.add_custom_button(__('Search Transaction'), function() {
                frappe.call({
                    method: "kenya_etims_compliance.custom_methods.sales_invoice.searchSalesTrnsReq",
                    args: {
                        "invoice_no": frm.doc.custom_invoice_number || null
                    },
                    freeze: true,
                    callback: function(r) {
                        let keys = Object.keys(r.message)
                        let values = Object.values(r.message)
                        frappe.msgprint({
                            title: __(keys[0]),
                            indicator: keys[0] === 'Success' ? 'green' : 'red',
                            message: __(JSON.stringify(values[0], null, 2))
                        });
                    }
                })
            }, __('Actions'));
        }
    },

    custom_search_sales_transaction: function(frm) {
        // Handler for button action
    }
});
```

---

## 3. Purchase Invoice Form - "Search Purchase" Button

### Via Client Script

1. Go to **Home** → **Customization** → **Client Scripts**
2. Click **New**
3. Fill in:
   - **DocType:** `Purchase Invoice`
   - **Module:** `Kenya eTIMS Compliance`
4. Paste the following code:

```javascript
frappe.ui.form.on("Purchase Invoice", {
    refresh: function(frm) {
        if (frm.doc.custom_invoice_number) {
            frm.add_custom_button(__('Search Purchase'), function() {
                frappe.call({
                    method: "kenya_etims_compliance.custom_methods.purchase_invoice.searchPurchaseTrnsReq",
                    args: {
                        "invoice_no": frm.doc.custom_invoice_number || null
                    },
                    freeze: true,
                    callback: function(r) {
                        let keys = Object.keys(r.message)
                        let values = Object.values(r.message)
                        frappe.msgprint({
                            title: __(keys[0]),
                            indicator: keys[0] === 'Success' ? 'green' : 'red',
                            message: __(JSON.stringify(values[0], null, 2))
                        });
                    }
                })
            }, __('Actions'));
        }
    },

    custom_search_purchase_transaction: function(frm) {
        // Handler for button action
    }
});
```

---

## 4. TIS Device Initialization - "Refresh Org Info" Button

### Via Client Script

1. Go to **Home** → **Customization** → **Client Scripts**
2. Click **New**
3. Fill in:
   - **DocType:** `TIS Device Initialization`
   - **Module:** `Kenya eTIMS Compliance**
4. Paste the following code:

```javascript
frappe.ui.form.on("TIS Device Initialization", {
    refresh: function(frm) {
        if (frm.doc.active && frm.doc.communication_key) {
            frm.add_custom_button(__('Refresh Org Info'), function() {
                frappe.call({
                    method: "refresh_org_info",
                    doc: frm.doc,
                    freeze: true,
                    callback: function(r) {
                        let keys = Object.keys(r.message)
                        let values = Object.values(r.message)
                        frappe.msgprint({
                            title: __(keys[0]),
                            indicator: keys[0] === 'Success' ? 'green' : 'red',
                            message: __(JSON.stringify(values[0], null, 2))
                        });
                    }
                })
            }, __('Actions'));
        }
    },

    refresh_org_info: function(frm) {
        // Handler for button action
    }
});
```

---

## 5. eTIMS Stock Release Number - "Sync to eTIMS" Button

This is already handled by the client script at `doctype/etims_stock_release_number/etims_stock_release_number.js`.

The buttons will automatically appear:
- **"Sync to eTIMS"** - Appears when document is submitted but not synced
- **"Search in eTIMS"** - Appears in draft mode when SR number exists

---

## Method 2: Via Python Console (Bulk Creation)

Alternatively, you can create all client scripts via the Frappe console:

```python
# Scripts to create via Frappe Console

# Item Client Script
item_script = '''
frappe.ui.form.on('Item', {
    refresh: function(frm) {
        if (frm.doc.custom_item_code || frm.doc.custom_item_name) {
            frm.add_custom_button(__('Search in eTIMS'), function() {
                frappe.call({
                    method: "kenya_etims_compliance.custom_methods.item.searchItemReq",
                    args: {
                        "item_code": frm.doc.custom_item_code || null,
                        "item_name": frm.doc.custom_item_name || null
                    },
                    freeze: true,
                    callback: function(r) {
                        let keys = Object.keys(r.message)
                        let values = Object.values(r.message)
                        frappe.msgprint({
                            title: __(keys[0]),
                            indicator: keys[0] === 'Success' ? 'green' : 'red',
                            message: __(JSON.stringify(values[0], null, 2))
                        });
                    }
                })
            }, __('Actions'));
        }
    }
});
'''

# Sales Invoice Client Script  
sales_script = '''
frappe.ui.form.on("Sales Invoice", {
    refresh: function(frm) {
        if (frm.doc.custom_invoice_number) {
            frm.add_custom_button(__('Search Transaction'), function() {
                frappe.call({
                    method: "kenya_etims_compliance.custom_methods.sales_invoice.searchSalesTrnsReq",
                    args: {"invoice_no": frm.doc.custom_invoice_number},
                    freeze: true,
                    callback: function(r) {
                        let keys = Object.keys(r.message)
                        let values = Object.values(r.message)
                        frappe.msgprint({
                            title: __(keys[0]),
                            indicator: keys[0] === 'Success' ? 'green' : 'red',
                            message: __(JSON.stringify(values[0], null, 2))
                        });
                    }
                })
            }, __('Actions'));
        }
    }
});
'''

# Purchase Invoice Client Script
purchase_script = '''
frappe.ui.form.on("Purchase Invoice", {
    refresh: function(frm) {
        if (frm.doc.custom_invoice_number) {
            frm.add_custom_button(__('Search Purchase'), function() {
                frappe.call({
                    method: "kenya_etims_compliance.custom_methods.purchase_invoice.searchPurchaseTrnsReq",
                    args: {"invoice_no": frm.doc.custom_invoice_number},
                    freeze: true,
                    callback: function(r) {
                        let keys = Object.keys(r.message)
                        let values = Object.values(r.message)
                        frappe.msgprint({
                            title: __(keys[0]),
                            indicator: keys[0] === 'Success' ? 'green' : 'red',
                            message: __(JSON.stringify(values[0], null, 2))
                        });
                    }
                })
            }, __('Actions'));
        }
    }
});
'''

# TIS Device Initialization Client Script
tis_script = '''
frappe.ui.form.on("TIS Device Initialization", {
    refresh: function(frm) {
        if (frm.doc.active && frm.doc.communication_key) {
            frm.add_custom_button(__('Refresh Org Info'), function() {
                frappe.call({
                    method: "refresh_org_info",
                    doc: frm.doc,
                    freeze: true,
                    callback: function(r) {
                        let keys = Object.keys(r.message)
                        let values = Object.values(r.message)
                        frappe.msgprint({
                            title: __(keys[0]),
                            indicator: keys[0] === 'Success' ? 'green' : 'red',
                            message: __(JSON.stringify(values[0], null, 2))
                        });
                    }
                })
            }, __('Actions'));
        }
    }
});
'''

# Create the scripts
scripts = [
    {"dt": "Item", "script": item_script, "name": "Item eTIMS Search"},
    {"dt": "Sales Invoice", "script": sales_script, "name": "Sales Invoice eTIMS Search"},
    {"dt": "Purchase Invoice", "script": purchase_script, "name": "Purchase Invoice eTIMS Search"},
    {"dt": "TIS Device Initialization", "script": tis_script, "name": "TIS Device eTIMS Refresh"},
]

for s in scripts:
    if not frappe.db.exists("Client Script", s["name"]):
        doc = frappe.new_doc("Client Script")
        doc.name = s["name"]
        doc.dt = s["dt"]
        doc.module = "Kenya eTIMS Compliance"
        doc.applicable_doctypes = [{"dt": s["dt"]}]
        doc.script = s["script"]
        doc.is_standard = 1
        doc.insert()
        print(f"Created client script: {s['name']}")
    else:
        print(f"Client script already exists: {s['name']}")
```

---

## Verification Steps

After adding the buttons, verify they appear correctly:

1. **Item Form:**
   - Open any Item
   - Check for "Actions" menu in the form toolbar
   - "Search in eTIMS" button should be visible when `custom_item_code` or `custom_item_name` is filled

2. **Sales Invoice:**
   - Open any Sales Invoice
   - "Search Transaction" button should appear when `custom_invoice_number` exists

3. **Purchase Invoice:**
   - Open any Purchase Invoice
   - "Search Purchase" button should appear when `custom_invoice_number` exists

4. **TIS Device Initialization:**
   - Open TIS Device Initialization
   - "Refresh Org Info" button should appear when device is active

5. **eTIMS Stock Release Number:**
   - Open any Stock Release Number record
   - "Sync to eTIMS" button appears on submitted records
   - "Search in eTIMS" button appears on draft records

---

## Troubleshooting

### Buttons Not Appearing

1. Clear browser cache and reload
2. Check that `bench build` was run after code changes
3. Verify the client script is active:
   - Go to **Customization** → **Client Scripts**
   - Find the script and ensure it's enabled

### Buttons Grayed Out

This is expected behavior - buttons only appear when:
- **Item:** `custom_item_code` or `custom_item_name` is filled
- **Invoices:** `custom_invoice_number` exists
- **TIS Device:** Device is `active` and has `communication_key`
- **Stock Release:** Based on document status

### API Errors

1. Check **Error Logging** doctype for detailed error messages
2. Verify **API Mode** (Sandbox vs Production)
3. Ensure **Communication Key** is valid
4. Check **TIS Device Initialization** settings

---

## Quick Setup via Bench Console

For quick setup, run this in your bench console:

```bash
bench --site [site-name] console
```

Then paste the Python code from Method 2 above.

---

## Summary

| Form | Button | Handler | Function |
|------|--------|---------|----------|
| Item | Search in eTIMS | `custom_search_item_in_etims` | Search items in KRA eTIMS |
| Sales Invoice | Search Transaction | `custom_search_sales_transaction` | Search sales transactions |
| Purchase Invoice | Search Purchase | `custom_search_purchase_transaction` | Search purchase transactions |
| TIS Device Initialization | Refresh Org Info | `refresh_org_info` | Get organization info |
| Stock Release Number | Sync to eTIMS | `sync_to_etims` | Sync SAR to KRA |
| Stock Release Number | Search in eTIMS | `search_in_etims` | Search SAR in KRA |
