# Role-Based Access Control (RBAC) Implementation Guide

## Overview

This guide explains the implemented Role-Based Access Control (RBAC) system for the Kenya eTIMS Compliance application, including role definitions, permission structures, and usage instructions.

---

## Table of Contents

1. [New eTIMS Roles](#new-etims-roles)
2. [Permission Structure](#permission-structure)
3. [Configuration](#configuration)
4. [Usage Examples](#usage-examples)
5. [Migration Steps](#migration-steps)
6. [Troubleshooting](#troubleshooting)

---

## New eTIMS Roles

### Role Definitions

| Role | Description | Can Delete | Access Level |
|------|-------------|------------|-------------|
| **eTIMS Administrator** | Full system control, settings management | ✅ All | System-wide |
| **eTIMS Manager** | Branch-level oversight, all operations per branch | ✅ All | Per-branch |
| **eTIMS Operator** | Daily operations - create/view, no delete | ❌ No | Per-branch |
| **eTIMS Auditor** | Read-only access for audit | ❌ No | Read-only |
| **eTIMS Sales Clerk** | Sales Invoice sync, item search | ❌ No | Sales only |
| **eTIMS Purchase Clerk** | Purchase Invoice sync, item search | ❌ No | Purchase only |
| **eTIMS Store Keeper** | Stock Entry, Stock Release Numbers | ❌ No | Inventory only |

### Role Hierarchy

```
eTIMS Administrator
├── Full system access
└── Can manage all branches

eTIMS Manager
├── All operations within assigned branch
├── Can cross-branch operations (if enabled)
└── Cannot modify system settings

eTIMS Operator
├── Create and modify documents
├── Cannot delete records
└── Cannot sync critical data

eTIMS Auditor
├── Read-only access to all data
└── Cannot modify anything

eTIMS Clerks (Sales/Purchase/Store)
├── Limited to their domain
└── Cannot delete records
```

---

## Permission Structure

### Permission Matrix by Doctype

| Doctype | Admin | Manager | Operator | Auditor | Sales Clerk | Purchase Clerk | Store Keeper |
|---------|-------|--------|---------|--------|-------------|----------------|--------------|
| **TIS Device Initialization** | ✅ All | ✅ All | ❌ | ✅ Read | ❌ | ❌ | ❌ |
| **Tax Branch Office** | ✅ All | ✅ All | ❌ | ✅ Read | ❌ | ❌ | ❌ |
| **TIS Communication Key** | ✅ All | ❌ | ❌ | ✅ Read | ❌ | ❌ | ❌ |
| **eTIMS Stock Release Number** | ✅ All | ✅ All | ❌ Write | ❌ | ❌ | ✅ Write | ❌ |
| **eTIMS Sales Receipt** | ✅ All | ✅ All | ❌ Write | ❌ | ✅ Write | ❌ | ❌ |
| **eTIMS Settings** | ✅ All | ❌ | ❌ | ✅ Read | ❌ | ❌ | ❌ |
| **eTIMS Code Information** | ✅ All | ✅ All | ✅ Read | ✅ Read | ✅ Read | ✅ Read | ✅ Read |
| **Sales Invoice** | ✅ All | ✅ All | ✅ Write | ❌ | ✅ Write | ❌ | ❌ |
| **Purchase Invoice** | ✅ All | ✅ All | ✅ Write | ❌ | ❌ | ✅ Write | ❌ |
| **Stock Entry** | ✅ All | ✅ All | ✅ Write | ❌ | ❌ | ❌ | ✅ Write |

---

## Configuration

### 1. Enable/Disable RBAC

Navigate to: **eTIMS Settings** → **Role Based Access Control** section

| Setting | Default | Description |
|---------|---------|-------------|
| **Enable RBAC** | `1` (checked) | Enable role-based access control |
| **Enforce Branch Isolation** | `1` (checked) | Users can only access their assigned branch |
| **Allow Cross-Branch Operations** | `0` (unchecked) | Managers can operate across all branches |

### 2. Enable Permission Logging

Navigate to: **eTIMS Settings** → **Error Handling** section

| Setting | Default | Description |
|---------|---------|-------------|
| **Enable Permission Logging** | `1` (checked) | Log all permission checks to Error Logging doctype |

---

## Usage Examples

### Check Permissions in Python Code

```python
from kenya_etims_compliance.utils.permissions import (
    is_etims_admin,
    is_etims_manager,
    can_sync_to_etims,
    can_delete_doctype,
    validate_branch_access
)

# Example: Check if user can sync
if can_sync_to_etims(None):
    # Proceed with sync
    result = sync_to_etims()

# Example: Check if user can delete
if can_delete_doctype("eTIMS Stock Release Number"):
    # Allow delete operation
    doc.delete()
else:
    frappe.throw("Permission Denied")

# Example: Validate branch access
validate_branch_access(doc)  # Throws if no access
```

### Permission Decorators

```python
from kenya_etims_compliance.utils.permissions import (
    require_admin,
    require_manager,
    require_sync_permission
)

# Require administrator
@require_admin
def update_api_credentials():
    # Only eTIMS Administrator can run this
    pass

# Require manager or administrator
@require_manager
def approve_manual_sync():
    # Only eTIMS Manager or Administrator can run this
    pass

# Require sync permission
@require_sync_permission()
def sync_item_to_kra():
    # Only users with sync permission can run this
    pass
```

### Client-Side Permission Checks

```javascript
// Check if user has specific role
frappe.call({
    method: "kenya_etims_compliance.utils.permissions.has_etims_role",
    args: {
        role_name: "eTIMS Administrator"
    },
    callback: function(r) {
        if (r.message) {
            // User is admin
        } else {
            frappe.msgprint("Access Denied");
        }
    }
});
```

---

## Migration Steps

### Step 1: Run Bench Migration

```bash
cd /Users/mac/ERPNext/supermarket
bench migrate
```

This will:
- Create all eTIMS roles
- Update doctype permissions
- Install new fields in eTIMS Settings

### Step 2: Build and Restart

```bash
bench build
bench restart
```

### Step 3: Assign eTIMS Roles to Users

1. Go to **User** list
2. Select a user → **User → Roles**
3. Add appropriate eTIMS role:
   - System administrators: **eTIMS Administrator**
   - Branch managers: **eTIMS Manager**
   - Sales staff: **eTIMS Sales Clerk**
   - Purchase staff: **eTIMS Purchase Clerk**
   - Store keepers: **eTIMS Store Keeper**
   - Auditors: **eTIMS Auditor**

### Step 4: Assign Branch Access

1. Go to **User** → **Permissions → Add**
2. Set:
   - **Allow:** Tax Branch Office
   - **Value:** [Branch ID]
   - **Is Default:** ✅

### Step 5: Configure Settings

1. Go to **eTIMS Settings**
2. Configure RBAC settings as needed
3. Save

---

## Testing Permissions

### Test Script: Permission Verification

```python
# Run in Frappe Console
from kenya_etims_compliance.utils.permissions import *

# Test role checks
print(f"Is Admin: {is_etims_admin()}")
print(f"Is Manager: {is_etims_manager()}")
print(f"Can Sync: {can_sync_to_etims(None)}")
print(f"Can Delete SAR: {can_delete_doctype('eTIMS Stock Release Number')}")

# Test branch access
try:
    validate_branch_access(test_doc)
    print("Branch access: OK")
except Exception as e:
    print(f"Branch access denied: {e}")
```

### Test by Role

| Test | Admin | Manager | Operator | Auditor | Clerk |
|------|-------|--------|---------|--------|-------|
| Create SAR | ✅ | ✅ | ✅ | ❌ | ✅ |
| Delete SAR | ✅ | ✅ | ❌ | ❌ | ❌ |
| Sync to KRA | ✅ | ✅ | ✅ | ❌ | ❌ |
| View Settings | ✅ | ❌ | ❌ | ✅ | ❌ |
| Modify Device Init | ✅ | ✅ | ❌ | ❌ | ❌ |

---

## Troubleshooting

### Issue: Users Cannot Access Documents

**Symptom:** Users get "Permission Denied" errors

**Solution:**

1. Check if RBAC is enabled in eTIMS Settings
2. Verify user has assigned eTIMS role
3. Confirm user has assigned Tax Branch Office
4. Check doctype permissions for the user's role

### Issue: Sync Not Working

**Symptom:** Stock Release Numbers not syncing to KRA

**Solution:**

1. Check eTIMS Settings → Enable Auto Sync
2. Verify user has sync permission (Admin, Manager, or Operator)
3. Check Error Logging for specific error messages
4. Ensure branch has valid TIS Device Initialization

### Issue: Cannot Delete Records

**Symptom:** Delete button is visible but operation is denied

**Solution:**

This is expected behavior! Only Admin and Manager can delete critical records. This prevents accidental data loss.

### Issue: Branch Access Errors

**Symptom:** Users get "Permission Denied: You do not have access to branch X"

**Solution:**

1. Check User Permissions for Tax Branch Office assignment
2. Verify the assigned branch matches the document's branch
3. For Admin/Manager with cross-branch operations, ensure "Allow Cross-Branch Operations" is checked

---

## Files Modified/Created

| File | Changes |
|------|---------|
| `hooks.py` | Added before_install hook for role creation |
| `installation/etims_roles.py` | Role creation script |
| `utils/permissions.py` | Permission helper functions and decorators |
| `doctype/etims_settings/etims_settings.py` | Added role-related settings getters |
| `doctype/etims_settings/etims_settings.json` | Added RBAC configuration fields |
| `doctype/etims_stock_release_number/etims_stock_release_number.py` | Added permission checks, branch validation |
| `doctype/etims_stock_release_number/etims_stock_release_number.json` | Updated permissions with eTIMS roles |
| `doctype/tis_device_initialization/tis_device_initialization.json` | Updated permissions with eTIMS roles |

---

## Security Best Practices

### 1. Principle of Least Privilege

- Only give users the minimum permissions they need
- Use Clerk roles for regular staff
- Use Manager roles for supervisors
- Use Administrator role sparingly

### 2. Branch Isolation

- Each user should have exactly one default branch
- Enable cross-branch operations only for managers
- Regularly audit branch access

### 3. Audit Trail

- Enable permission logging to track all permission checks
- Review Error Logging doctype regularly
- Monitor failed permission attempts

### 4. Role Assignment

- Assign roles based on job function, not hierarchy
- Remove eTIMS roles from users who change roles
- Regularly review and update role assignments

---

## Quick Reference: Permission Checks

| Function | Returns True When... |
|----------|---------------------|
| `is_etims_admin()` | User has eTIMS Administrator role |
| `is_etims_manager()` | User has eTIMS Manager role |
| `is_etims_operator()` | User has eTIMS Operator role |
| `is_etims_auditor()` | User has eTIMS Auditor role |
| `can_sync_to_etims()` | User is Admin, Manager, or Operator |
| `can_delete_doctype(doctype)` | User is Admin or Manager for critical doctypes |
| `validate_branch_access(doc)` | User has access to document's branch (or is Admin/Manager with cross-branch) |
| `can_manage_settings()` | User is eTIMS Administrator |

---

## Summary

The RBAC implementation provides:

✅ **7 new eTIMS-specific roles** with clear hierarchy
✅ **Permission checks** enforced at multiple levels
✅ **Branch isolation** for data security
✅ **Audit logging** for compliance
✅ **Backward compatible** - works with or without RBAC enabled
✅ **Configurable** - can be toggled via settings

For questions or issues, refer to the troubleshooting section or check the Error Logging doctype.
