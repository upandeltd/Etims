# Role Management Analysis - Kenya eTIMS Compliance App

## Executive Summary

The Kenya eTIMS Compliance app uses a **hybrid role-based access control (RBAC) system** combining:
1. **Standard ERPNext roles** (System Manager, Sales User, Purchase User, Stock User)
2. **Branch-based permissions** via Tax Branch Office
3. **User-level permissions** via User Permission doctype

---

## Current Role Structure

### Standard Roles Used

| Role | Purpose | Access Level |
|------|---------|--------------|
| **System Manager** | Full access to all eTIMS doctypes | All permissions (create, read, write, delete, export, etc.) |
| **Sales User** | Sales operations access | Most eTIMS doctypes (limited to no delete) |
| **Purchase User** | Purchase operations access | Purchase-related doctypes |
| **Stock User** | Inventory operations access | Warehouse/Stock doctypes |

### Doctype Permission Pattern

Most eTIMS doctypes follow this permission structure:

```json
"permissions": [
  {
    "create": 1,
    "delete": 1,
    "email": 1,
    "export": 1,
    "print": 1,
    "read": 1,
    "report": 1,
    "role": "System Manager",
    "share": 1,
    "write": 1
  },
  {
    "create": 1,
    "delete": 1,  // Note: Sales User can delete
    "email": 1,
    "export": 1,
    "print": 1,
    "read": 1,
    "report": 1,
    "role": "Sales User",
    "share": 1,
    "write": 1
  }
]
```

---

## Branch-Based Permission System

### How It Works

The app implements **multi-branch support** using:

1. **Tax Branch Office** doctype - Represents physical branches
2. **User Permission** doctype - Links users to branches
3. **TIS Device Initialization** - Per-branch device configuration

### Key Function: `get_user_branch_id()`

**Location:** `utils/etims_utils.py:224-232`

```python
def get_user_branch_id():
    current_user = frappe.session.user
    
    # Get user's default tax branch
    tax_branch_perms = frappe.db.get_all(
        "User Permission", 
        filters={
            "user": current_user, 
            "allow": "Tax Branch Office", 
            "is_default": 1
        }, 
        fields=["for_value"]
    )
    
    if tax_branch_perms:
        return tax_branch_perms[0].get("for_value")
```

### Usage Pattern

Users are assigned to branches via **User Permission**:

1. Navigate to: **User → Permissions → Add**
2. Select: **Allow = "Tax Branch Office"**
3. Select: **Value = [Branch ID]** (e.g., "001", "002")
4. Check: **Is Default**

This ensures:
- API calls use the correct branch credentials
- Transactions are tagged with the correct branch
- Data isolation between branches

---

## Permission Flow for API Operations

### 1. Authentication Headers

```python
def get_headers():
    branch_id = eTIMS.get_user_branch_id()  # Get user's branch
    
    # Get branch-specific credentials
    header_docs = frappe.db.get_all(
        "TIS Device Initialization", 
        filters={"branch_id": branch_id, "active": 1}, 
        fields=["pin", "branch_id", "communication_key"]
    )
    
    if header_docs:
        return {
            "tin": header_docs[0].get("pin"),
            "bhfId": header_docs[0].get("branch_id"),
            "cmcKey": header_docs[0].get("communication_key"),
        }
```

### 2. Data Isolation

| Data Type | Isolation Method |
|-----------|-----------------|
| API Credentials | Per-branch TIS Device Initialization |
| Stock Release Numbers | Filtered by `tax_branch_office` |
| Transactions | Tagged with `custom_tax_branch_office` |
| Device Communication | Per-branch communication keys |

---

## Current Issues & Gaps

### 1. Over-Permissive Sales User

**Issue:** Sales User has `delete: 1` permission on most doctypes

**Risk:** Accidental deletion of critical eTIMS data

**Example:** `etims_stock_release_number.json`
```json
{
  "role": "Sales User",
  "delete": 1,  // Should be 0 for critical data
  ...
}
```

### 2. No Dedicated eTIMS Roles

**Issue:** Using generic ERPNext roles instead of eTIMS-specific roles

**Impact:** 
- Cannot differentiate between eTIMS managers and regular users
- All Sales Users have same access level
- No audit trail for who performed eTIMS operations

### 3. No Role Hierarchy

**Issue:** No supervisor/manager role for approvals

**Missing:**
- eTIMS Manager role for approving critical operations
- eTIMS Auditor role for read-only access
- eTIMS Operator role for day-to-day operations

### 4. Lack of Field-Level Permissions

**Issue:** All users with a role see all fields

**Missing:**
- Hide sensitive fields (Communication Key) from operators
- Restrict editing of synced fields
- Control access to device initialization

### 5. No Branch Transfer Restrictions

**Issue:** Users with multiple branch permissions can switch freely

**Risk:** 
- Data inconsistency
- Unauthorized cross-branch operations

---

## Recommended Role Structure

### Proposed eTIMS-Specific Roles

| Role | Description | Permissions |
|------|-------------|-------------|
| **eTIMS Administrator** | Full eTIMS system access | All operations + settings management |
| **eTIMS Manager** | Branch-level oversight | All operations per branch, approve sync |
| **eTIMS Operator** | Daily operations | Create transactions, view data, no delete |
| **eTIMS Auditor** | Read-only audit access | View all, no modifications |
| **eTIMS Sales Clerk** | Sales transactions only | Sales Invoice sync, item search |
| **eTIMS Purchase Clerk** | Purchase transactions only | Purchase Invoice sync, item search |
| **eTIMS Store Keeper** | Inventory operations only | Stock Entry, Stock Release Numbers |

### Permission Matrix

| Doctype | Admin | Manager | Operator | Auditor | Sales Clerk | Purchase Clerk | Store Keeper |
|---------|-------|--------|---------|--------|-------------|----------------|--------------|
| TIS Device Initialization | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Tax Branch Office | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| eTIMS Stock Release Number | ✅ | ✅ | R | ✅ | ❌ | ❌ | W |
| eTIMS Sales Receipt | ✅ | ✅ | R | ✅ | R | ❌ | ❌ |
| eTIMS Code Information | ✅ | ✅ | R | ✅ | R | R | R |
| eTIMS Settings | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

**Legend:** ✅ = All, R = Read, W = Write, ❌ = None

---

## Implementation Plan

### Phase 1: Create eTIMS-Specific Roles

```python
# Add to hooks.py or install script
etims_roles = [
    {
        "doctype": "Role",
        "role_name": "eTIMS Administrator",
        "desk_access": 1,
        "is_custom": 1,
    },
    {
        "doctype": "Role",
        "role_name": "eTIMS Manager",
        "desk_access": 1,
        "is_custom": 1,
    },
    {
        "doctype": "Role",
        "role_name": "eTIMS Operator",
        "desk_access": 1,
        "is_custom": 1,
    },
    {
        "doctype": "Role",
        "role_name": "eTIMS Auditor",
        "desk_access": 0,
        "is_custom": 1,
    },
    {
        "doctype": "Role",
        "role_name": "eTIMS Sales Clerk",
        "desk_access": 1,
        "is_custom": 1,
    },
    {
        "doctype": "Role",
        "role_name": "eTIMS Purchase Clerk",
        "desk_access": 1,
        "is_custom": 1,
    },
    {
        "doctype": "Role",
        "role_name": "eTIMS Store Keeper",
        "desk_access": 1,
        "is_custom": 1,
    },
]
```

### Phase 2: Update Doctype Permissions

Update key doctypes with granular permissions:

**Example: eTIMS Stock Release Number**

```json
"permissions": [
  {
    "role": "eTIMS Administrator",
    "create": 1, "delete": 1, "email": 1, "export": 1,
    "print": 1, "read": 1, "report": 1, "share": 1, "write": 1
  },
  {
    "role": "eTIMS Manager",
    "create": 1, "delete": 1, "email": 1, "export": 1,
    "print": 1, "read": 1, "report": 1, "share": 1, "write": 1
  },
  {
    "role": "eTIMS Store Keeper",
    "create": 1, "delete": 0, "email": 1, "export": 1,
    "print": 1, "read": 1, "report": 1, "share": 1, "write": 1
  },
  {
    "role": "eTIMS Auditor",
    "create": 0, "delete": 0, "email": 0, "export": 1,
    "print": 1, "read": 1, "report": 1, "share": 0, "write": 0
  }
]
```

### Phase 3: Add Permission Helpers

Create `utils/permissions.py`:

```python
import frappe

def has_etims_role(role_name):
    """Check if current user has specific eTIMS role"""
    return frappe.has_permission("eTIMS Settings", "write")

def is_etims_admin():
    """Check if user is eTIMS Administrator"""
    return "eTIMS Administrator" in frappe.get_roles()

def is_etims_manager():
    """Check if user is eTIMS Manager"""
    return "eTIMS Manager" in frappe.get_roles()

def can_modify_synced_data():
    """Check if user can modify synced records"""
    return is_etims_admin() or is_etims_manager()

def can_delete_doctype(doctype):
    """Check if user can delete from doctype"""
    if is_etims_admin():
        return True
    # Add doctype-specific rules
    restricted_doctypes = [
        "eTIMS Stock Release Number",
        "eTIMS Sales Receipt",
        "TIS Device Initialization",
    ]
    if doctype in restricted_doctypes:
        return is_etims_manager()
    return True
```

### Phase 4: Add Field-Level Permissions

```python
# In doctype controllers
def has_permission(self, ptype, user=None):
    """Override permissions for specific fields"""
    if ptype == "write":
        field = self.get("fieldname")
        protected_fields = {
            "communication_key": ["eTIMS Administrator", "eTIMS Manager"],
            "device_id": ["eTIMS Administrator", "eTIMS Manager"],
            "synced_to_etims": ["eTIMS Administrator"],
        }
        if field in protected_fields:
            user_roles = frappe.get_roles()
            if not any(role in user_roles for role in protected_fields[field]):
                return False
    return super().has_permission(ptype, user)
```

---

## Branch-Based Access Control Enhancement

### Current: User Permission Based

```
User → User Permission → Tax Branch Office → Branch ID
```

### Proposed: Add User-Branch Mapping Doctype

**New Doctype:** `eTIMS User Branch Mapping`

| Field | Type | Description |
|-------|------|-------------|
| `user` | Link to User | User to assign |
| `branch_office` | Link to Tax Branch Office | Branch to assign |
| `is_primary` | Check | Primary branch for user |
| `is_active` | Check | Whether assignment is active |
| `role_in_branch` | Select | Role level in this branch |

### Benefits

- Single user can access multiple branches
- Different role levels per branch
- Audit trail of branch access
- Easier branch transfers

---

## Best Practices Recommendations

### 1. Principle of Least Privilege

```python
# Bad: All Sales Users can delete
"permissions": [{"role": "Sales User", "delete": 1}]

# Good: Only Managers can delete
"permissions": [
  {"role": "eTIMS Manager", "delete": 1},
  {"role": "eTIMS Operator", "delete": 0},
  {"role": "Sales User", "delete": 0}
]
```

### 2. Branch Isolation

```python
# Always filter by user's branch
def get_list(self, args):
    user_branch = eTIMS.get_user_branch_id()
    args['filters']['tax_branch_office'] = user_branch
    return super().get_list(args)
```

### 3. Audit Trail

```python
# Log critical operations
def on_submit(self):
    frappe.db.set_value(
        self.doctype, self.name, "modified_by",
        frappe.session.user,
        update_modified=False
    )
    frappe.db.set_value(
        self.doctype, self.name, "modified_from_branch",
        eTIMS.get_user_branch_id(),
        update_modified=False
    )
```

---

## Security Checklist

- [ ] Remove delete permission from Sales User for critical doctypes
- [ ] Create eTIMS-specific roles
- [ ] Implement branch-based data filtering in all doctypes
- [ ] Add field-level permissions for sensitive data
- [ ] Add audit trail for all eTIMS operations
- [ ] Implement permission checks in custom methods
- [ ] Add user activity logging
- [ ] Document role assignments
- [ ] Regular permission audits

---

## Summary

| Aspect | Current State | Recommended |
|--------|---------------|--------------|
| **Roles** | Generic ERPNext roles | eTIMS-specific roles |
| **Delete Permissions** | Sales User can delete | Managers only |
| **Branch Access** | User Permission doctype | Enhanced mapping doctype |
| **Field Permissions** | None implemented | Sensitive field protection |
| **Audit Trail** | Basic modified_by tracking | Comprehensive activity logging |
| **Role Hierarchy** | Flat structure | Admin > Manager > Operator |

---

## Files Requiring Updates

| File | Changes Needed |
|------|----------------|
| All doctype JSON files | Add eTIMS-specific role permissions |
| `hooks.py` | Add role creation in `before_install` |
| `utils/permissions.py` | Create new permission helpers |
| `custom_methods/*.py` | Add permission checks |
| `etims_settings.py` | Add role-based settings |
