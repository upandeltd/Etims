# eTIMS Wait-Before-Print (Option B default) — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Coale POS receipt wait briefly for KRA eTIMS signing to land (so the first receipt carries the verification QR), falling back to a provisional receipt + reload-robust auto-reprint when KRA is slow — as the default, with a kill-switch.

**Architecture:** A configurable wait is gated at the single `ReceiptSendDialog` print chokepoint in the `coale_pos` Vue SPA. It races a site-broadcast realtime event (`etims_invoice_signed`, emitted by the `kenya_etims_compliance` queue worker after the QR is written) against a timeout, with a read-only status endpoint as backstop. On timeout the receipt prints provisional and the invoice is queued for auto-reprint (localStorage-persisted, reconciled on mount, print-then-remove ordering).

**Tech Stack:** Frappe/ERPNext v15 (Python, `FrappeTestCase`/unittest, `frappe.publish_realtime`), Vue 3 SPA (`window.frappe.realtime`, QZ Tray printing), Vitest (added here for the pure gate logic).

**Spec:** `apps/kenya_etims_compliance/docs/superpowers/specs/2026-06-09-etims-wait-before-print-design.md`

**Conventions:**
- Python tests run with `bench --site <site> run-tests --module <dotted.module>` (or `--app kenya_etims_compliance`). Substitute the bench site (this bench serves on port 8045).
- All custom field names are pre-existing and verified: `custom_update_invoice_in_tims`, `custom_etims_queue_status`, `custom_update_sales_to_etims`, `custom_receipt_qr_url`, `custom_invoice_number`.
- Commit after every task (TDD: red → green → commit).

---

## File Structure

**`kenya_etims_compliance` (server):**
- Modify: `.../doctype/etims_settings/etims_settings.json` — add 2 fields.
- Modify: `.../doctype/etims_settings/etims_settings.py` — add 2 defaults in `get_etims_settings`.
- Create: `.../custom_methods/etims_status.py` — `get_etims_signing_status` (read-only, whitelisted) + `get_etims_print_settings` (whitelisted settings read for the SPA).
- Modify: `.../custom_methods/queue_processor.py` — 1 realtime emit in `_handle_sales_invoice_success`.
- Test: `.../tests/test_etims_wait_before_print.py` (new).

**`coale_pos` (frontend):**
- Modify: `frontend/package.json` + create `frontend/vitest.config.js` — add Vitest.
- Create: `frontend/src/services/etimsGate.js` — `waitForEtimsSigned` + invoice-filtered listener + localStorage pending-reprint helpers.
- Create: `frontend/src/services/etimsGate.test.js` (flat path; matches the vitest glob `src/**/*.test.js`).
- Modify: `frontend/src/components/pos/ReceiptSendDialog.vue` — gate the auto-print watch; disable manual controls while pending.
- Modify: `frontend/src/pages/pos/Retail.vue` — session-level auto-reprint listener + reconcile-on-mount; pass settings to the dialog.

---

## Chunk 1: Server — settings, status endpoint, realtime emit

### Task 1: Add wait settings to eTIMS Settings + defaults

**Files:**
- Modify: `kenya_etims_compliance/kenya_etims_compliance/kenya_etims_compliance/doctype/etims_settings/etims_settings.json`
- Modify: `kenya_etims_compliance/kenya_etims_compliance/kenya_etims_compliance/doctype/etims_settings/etims_settings.py`
- Test: `kenya_etims_compliance/kenya_etims_compliance/tests/test_etims_wait_before_print.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_etims_wait_before_print.py
from unittest.mock import MagicMock, patch
from frappe.tests.utils import FrappeTestCase
from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
    get_etims_settings,
)


class TestEtimsWaitSettings(FrappeTestCase):
    @patch("kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings.frappe.get_single")
    def test_wait_defaults_present_when_unset(self, get_single):
        # Single doc returns None for the new fields -> defaults must apply
        doc = MagicMock()
        doc.as_dict.return_value = {}
        doc.get.side_effect = lambda k, d=None: None
        get_single.return_value = doc
        settings = get_etims_settings()
        self.assertEqual(settings["wait_for_etims_before_print"], 1)
        self.assertEqual(settings["etims_print_wait_seconds"], 6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site <site> run-tests --module kenya_etims_compliance.kenya_etims_compliance.tests.test_etims_wait_before_print`
Expected: FAIL (KeyError / missing keys).

- [ ] **Step 3: Add the defaults**

In `etims_settings.py`, extend `_defaults` with:

```python
        "wait_for_etims_before_print": 1,
        "etims_print_wait_seconds": 6,
```

Ensure the merge logic that overlays the Single doc values treats `None`/unset as "use default" (do not let a blank Single field overwrite the default with `None`). If the existing merge does `value if value is not None else default`, that already holds; otherwise guard these two keys explicitly.

- [ ] **Step 4: Add the two fields to the doctype JSON**

Append to `field_order` and `fields` in `etims_settings.json` (place under an existing section, e.g. after the queue fields):

```json
{
  "fieldname": "wait_for_etims_before_print",
  "fieldtype": "Check",
  "label": "Wait for eTIMS before printing receipt",
  "default": "1",
  "description": "POS waits briefly for KRA signing so the first receipt carries the QR. Turn off to print immediately."
},
{
  "fieldname": "etims_print_wait_seconds",
  "fieldtype": "Int",
  "label": "eTIMS print wait (seconds)",
  "default": "6",
  "depends_on": "wait_for_etims_before_print"
}
```

Add both fieldnames to `field_order`.

- [ ] **Step 5: Run test to verify it passes**

Run: `bench --site <site> run-tests --module kenya_etims_compliance.kenya_etims_compliance.tests.test_etims_wait_before_print`
Expected: PASS.

- [ ] **Step 6: Migrate + commit**

```bash
bench --site <site> migrate
git add kenya_etims_compliance/kenya_etims_compliance/kenya_etims_compliance/doctype/etims_settings/ kenya_etims_compliance/kenya_etims_compliance/tests/test_etims_wait_before_print.py
git commit -m "feat(etims): add wait-before-print settings with defaults"
```

---

### Task 2: `get_etims_signing_status` read-only endpoint

**Files:**
- Create: `kenya_etims_compliance/kenya_etims_compliance/custom_methods/etims_status.py`
- Test: `kenya_etims_compliance/kenya_etims_compliance/tests/test_etims_wait_before_print.py`

- [ ] **Step 1: Write the failing tests**

```python
from kenya_etims_compliance.custom_methods import etims_status


class TestSigningStatus(FrappeTestCase):
    @patch("kenya_etims_compliance.custom_methods.etims_status.frappe")
    def test_returns_signed_payload(self, frappe_mock):
        frappe_mock.db.get_value.return_value = {
            "custom_update_invoice_in_tims": 1,
            "custom_etims_queue_status": "Sent",
            "custom_update_sales_to_etims": 1,
            "custom_receipt_qr_url": "https://etims.kra.go.ke/...",
            "custom_invoice_number": 42,
        }
        out = etims_status.get_etims_signing_status("SINV-0001")
        self.assertTrue(out["signing_enabled"])
        self.assertTrue(out["signed"])
        self.assertEqual(out["status"], "Sent")
        self.assertEqual(out["invoice_number"], 42)
        frappe_mock.has_permission.assert_called_once()

    @patch("kenya_etims_compliance.custom_methods.etims_status.frappe")
    def test_unsigned_invoice(self, frappe_mock):
        frappe_mock.db.get_value.return_value = {
            "custom_update_invoice_in_tims": 1,
            "custom_etims_queue_status": "Queued",
            "custom_update_sales_to_etims": 0,
            "custom_receipt_qr_url": None,
            "custom_invoice_number": None,
        }
        out = etims_status.get_etims_signing_status("SINV-0002")
        self.assertFalse(out["signed"])
        self.assertIsNone(out["qr_url"])

    @patch("kenya_etims_compliance.custom_methods.etims_status.frappe")
    def test_missing_invoice_returns_disabled(self, frappe_mock):
        frappe_mock.db.get_value.return_value = None
        out = etims_status.get_etims_signing_status("NOPE")
        self.assertFalse(out["signing_enabled"])
        self.assertFalse(out["signed"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `bench --site <site> run-tests --module kenya_etims_compliance.kenya_etims_compliance.tests.test_etims_wait_before_print`
Expected: FAIL (module `etims_status` not found).

- [ ] **Step 3: Implement**

```python
# custom_methods/etims_status.py
import frappe

_FIELDS = [
    "custom_update_invoice_in_tims",
    "custom_etims_queue_status",
    "custom_update_sales_to_etims",
    "custom_receipt_qr_url",
    "custom_invoice_number",
]


@frappe.whitelist()
def get_etims_signing_status(invoice_name):
    """Read-only signing status for the POS wait-gate. Permission-checked."""
    frappe.has_permission("Sales Invoice", "read", doc=invoice_name, throw=True)
    row = frappe.db.get_value("Sales Invoice", invoice_name, _FIELDS, as_dict=True)
    if not row:
        return {"signing_enabled": False, "status": None, "signed": False,
                "qr_url": None, "invoice_number": None}
    return {
        "signing_enabled": bool(row.get("custom_update_invoice_in_tims")),
        "status": row.get("custom_etims_queue_status"),
        "signed": bool(row.get("custom_update_sales_to_etims")),
        "qr_url": row.get("custom_receipt_qr_url"),
        "invoice_number": row.get("custom_invoice_number"),
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: same module command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add kenya_etims_compliance/kenya_etims_compliance/custom_methods/etims_status.py kenya_etims_compliance/kenya_etims_compliance/tests/test_etims_wait_before_print.py
git commit -m "feat(etims): add get_etims_signing_status read endpoint for POS wait-gate"
```

---

### Task 3: Emit `etims_invoice_signed` after the QR commit

**Files:**
- Modify: `kenya_etims_compliance/kenya_etims_compliance/custom_methods/queue_processor.py` (`_handle_sales_invoice_success`, immediately after the `frappe.db.commit()` that follows `doc.save` — ~line 426)
- Test: `kenya_etims_compliance/kenya_etims_compliance/tests/test_etims_wait_before_print.py`

- [ ] **Step 1: Write the failing test**

```python
class TestRealtimeEmit(FrappeTestCase):
    @patch("kenya_etims_compliance.custom_methods.queue_processor.frappe")
    def test_emit_after_qr_written(self, frappe_mock):
        # Arrange a doc whose QR is set; call the private helper directly.
        from kenya_etims_compliance.custom_methods import queue_processor as qp
        doc = MagicMock()
        doc.name = "SINV-0009"
        doc.custom_receipt_qr_url = "https://etims.kra.go.ke/...sig"
        doc.posting_date = "2026-06-09"
        frappe_mock.get_doc.return_value = doc
        # Patch the eTIMS date helpers too so the test exercises only the emit, not real
        # date parsing of the sdcDateTime literal.
        with patch.object(qp, "eTIMS") as etims_mock, \
             patch.object(qp, "create_qr_code", return_value=("f.png", "https://etims.kra.go.ke/...sig")), \
             patch.object(qp, "create_attachment", return_value="/private/files/f.png"), \
             patch.object(qp, "create_sales_receipt"), \
             patch.object(qp, "stockIOSaveReq"), \
             patch.object(qp, "KRAClient"):
            etims_mock.strp_datetime_object.return_value = None
            etims_mock.strp_date_object.return_value = None
            etims_mock.strp_time_object.return_value = None
            etims_mock.strf_date_object.return_value = "20260609"
            qp._handle_sales_invoice_success("SINV-0009", {"sdcDateTime": "20260609120000", "rcptSign": "sig"}, MagicMock(branch_id=""))
        # Assert a publish_realtime call for our event/invoice happened
        calls = [c for c in frappe_mock.publish_realtime.call_args_list
                 if c.args and c.args[0] == "etims_invoice_signed"]
        self.assertTrue(calls, "expected etims_invoice_signed emit")
        payload = calls[0].args[1] if len(calls[0].args) > 1 else calls[0].kwargs.get("message")
        self.assertEqual(payload["invoice"], "SINV-0009")
        self.assertTrue(calls[0].kwargs.get("after_commit"))
```

> Note: `create_qr_code`, `create_attachment`, `create_sales_receipt`, `stockIOSaveReq`, `KRAClient` are imported **inside** `_handle_sales_invoice_success` today. Either (a) hoist those imports to module top so `patch.object(qp, ...)` works, or (b) patch their source modules. Prefer (a) — a small, safe refactor that also makes the function testable. Do the hoist as part of Step 3.

- [ ] **Step 2: Run to verify it fails**

Run: same module command. Expected: FAIL (no emit).

- [ ] **Step 3: Implement the emit (and hoist imports)**

Hoist the local imports in `_handle_sales_invoice_success` to module top. Then, immediately after the existing `frappe.db.commit()` that follows `doc.save(...)` (the point where `doc.custom_receipt_qr_url` is persisted), add:

```python
        # Notify any waiting POS terminal that this invoice is now signed.
        # Site-wide broadcast (no room/user args) — frontend filters by `invoice`.
        frappe.publish_realtime(
            "etims_invoice_signed",
            {
                "invoice": doc.name,
                "status": "Sent",
                "qr_url": doc.custom_receipt_qr_url,
            },
            after_commit=True,
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: same module command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add kenya_etims_compliance/kenya_etims_compliance/custom_methods/queue_processor.py kenya_etims_compliance/kenya_etims_compliance/tests/test_etims_wait_before_print.py
git commit -m "feat(etims): broadcast etims_invoice_signed after QR is written"
```

---

### Task 4: Surface wait settings to the SPA

**Files:**
- Modify: `coale_pos/coale_pos/api/pos.py` (`get_pos_profile_details`, ~line 1196-1230 where `custom_enable_etims_signing` is already returned)
- Test: extend the server test module (cross-app import is fine; or add a focused test in coale_pos tests if present)

> **IMPORTANT (verified):** `get_pos_profile_details` returns a **nested** dict
> `{"success": True, "profile": {...}}` and `custom_enable_etims_signing` lives **inside
> `profile`**. The two new keys MUST go inside `profile` (that's where the SPA reads them).
> The settings getter is imported function-locally, so the test must patch it at its
> **source module**, not on `coale_pos.api.pos`.

- [ ] **Step 1: Write the failing test**

```python
# Add to the same test module (imports coale_pos):
class TestPosProfileEtimsSettings(FrappeTestCase):
    @patch("kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings.get_etims_settings")
    @patch("coale_pos.api.pos.frappe")
    def test_profile_details_include_wait_settings(self, frappe_mock, settings_mock):
        from coale_pos.api import pos
        profile = MagicMock()
        profile.custom_enable_etims_signing = 1
        frappe_mock.get_doc.return_value = profile
        settings_mock.return_value = {"wait_for_etims_before_print": 1, "etims_print_wait_seconds": 6}
        out = pos.get_pos_profile_details("Main POS")
        self.assertEqual(out["profile"]["etims_wait_before_print"], 1)
        self.assertEqual(out["profile"]["etims_print_wait_seconds"], 6)
```

> If `get_pos_profile_details` is hard to unit-test as-is (heavy doc access), assert only the
> two added keys via a thin extraction helper, or mark this as a manual-verification task and
> keep the production change minimal. Do not over-mock.

- [ ] **Step 2: Run to verify it fails.** Expected: KeyError on the new keys inside `profile`.

- [ ] **Step 3: Implement**

In `get_pos_profile_details`, read the eTIMS settings (guard with try/except so coale_pos
still works if the eTIMS app is absent), then add the two keys **inside the `profile` dict
that is returned**:

```python
        try:
            from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
                get_etims_settings,
            )
            _etims = get_etims_settings()
        except ImportError:
            _etims = {}
        # ... inside the profile dict that gets returned:
        "etims_wait_before_print": _etims.get("wait_for_etims_before_print", 0),
        "etims_print_wait_seconds": _etims.get("etims_print_wait_seconds", 6),
```

- [ ] **Step 4: Run to verify it passes.** Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add coale_pos/coale_pos/api/pos.py kenya_etims_compliance/kenya_etims_compliance/tests/test_etims_wait_before_print.py
git commit -m "feat(pos): surface eTIMS wait-before-print settings to the SPA"
```

---

## Chunk 2: Frontend — Vitest tooling + gate service

### Task 5: Add Vitest

**Files:**
- Modify: `coale_pos/frontend/package.json`
- Create: `coale_pos/frontend/vitest.config.js`

- [ ] **Step 1: Add devDependency + script**

`package.json`: add `"test": "vitest run"` and `"test:watch": "vitest"` to `scripts`; add `vitest` (and `happy-dom`) to `devDependencies`.

- [ ] **Step 2: Create `vitest.config.js`**

```js
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.test.js'],
    globals: true,
  },
})
```

- [ ] **Step 3: Install + verify the runner boots**

Run: `cd apps/coale_pos/frontend && yarn install && yarn test`
Expected: Vitest runs, reports "no test files found" or passes (no tests yet).

- [ ] **Step 4: Commit**

```bash
git add coale_pos/frontend/package.json coale_pos/frontend/vitest.config.js coale_pos/frontend/yarn.lock
git commit -m "chore(pos): add vitest for frontend unit tests"
```

---

### Task 6: `etimsGate.js` — `waitForEtimsSigned`

**Files:**
- Create: `coale_pos/frontend/src/services/etimsGate.js`
- Test: `coale_pos/frontend/src/services/etimsGate.test.js`

- [ ] **Step 1: Write the failing tests**

```js
// src/services/etimsGate.test.js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { waitForEtimsSigned } from './etimsGate'

function makeRealtime() {
  const handlers = {}
  return {
    on: (ev, cb) => { (handlers[ev] ||= []).push(cb) },
    off: (ev, cb) => { handlers[ev] = (handlers[ev] || []).filter(h => h !== cb) },
    emit: (ev, payload) => (handlers[ev] || []).forEach(h => h(payload)),
  }
}

beforeEach(() => { globalThis.window = { frappe: { realtime: makeRealtime() } } })

describe('waitForEtimsSigned', () => {
  it('skips immediately when signing disabled', async () => {
    const r = await waitForEtimsSigned('SINV-1', { signingEnabled: false, timeoutMs: 50 })
    expect(r).toEqual({ signed: false, skip: true })
  })

  it('resolves signed on matching realtime event', async () => {
    const p = waitForEtimsSigned('SINV-2', { signingEnabled: true, timeoutMs: 1000, statusFetcher: vi.fn() })
    window.frappe.realtime.emit('etims_invoice_signed', { invoice: 'SINV-2', status: 'Sent' })
    expect(await p).toMatchObject({ signed: true })
  })

  it('ignores events for a different invoice', async () => {
    const statusFetcher = vi.fn().mockResolvedValue({ signed: false })
    const p = waitForEtimsSigned('SINV-3', { signingEnabled: true, timeoutMs: 60, statusFetcher })
    window.frappe.realtime.emit('etims_invoice_signed', { invoice: 'OTHER', status: 'Sent' })
    const r = await p
    expect(r.signed).toBe(false)
    expect(r.timedOut).toBe(true)
  })

  it('on timeout does one status read that can confirm signed', async () => {
    const statusFetcher = vi.fn().mockResolvedValue({ signed: true })
    const r = await waitForEtimsSigned('SINV-4', { signingEnabled: true, timeoutMs: 30, statusFetcher })
    expect(statusFetcher).toHaveBeenCalledOnce()
    expect(r.signed).toBe(true)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/coale_pos/frontend && yarn test`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```js
// src/services/etimsGate.js
const EVENT = 'etims_invoice_signed'

/**
 * Wait briefly for a Sales Invoice to be signed by KRA eTIMS.
 * Resolves { signed, skip?, timedOut? } and never throws.
 *
 * opts:
 *  - signingEnabled: bool   (skip the wait entirely when false)
 *  - timeoutMs: number      (e.g. settings.etims_print_wait_seconds * 1000)
 *  - statusFetcher: (invoiceName) => Promise<{signed:boolean}>  (backstop on timeout)
 */
export function waitForEtimsSigned(invoiceName, opts = {}) {
  const { signingEnabled = false, timeoutMs = 6000, statusFetcher = null } = opts
  if (!signingEnabled || !invoiceName) {
    return Promise.resolve({ signed: false, skip: true })
  }

  const rt = window?.frappe?.realtime
  return new Promise((resolve) => {
    let done = false
    const finish = (result) => {
      if (done) return
      done = true
      if (rt) rt.off(EVENT, onSigned)
      clearTimeout(timer)
      resolve(result)
    }
    const onSigned = (payload) => {
      if (payload && payload.invoice === invoiceName) finish({ signed: true })
    }
    if (rt) rt.on(EVENT, onSigned)

    const timer = setTimeout(async () => {
      // Backstop: one status read absorbs a dropped realtime event.
      if (statusFetcher) {
        try {
          const s = await statusFetcher(invoiceName)
          if (s && s.signed) return finish({ signed: true })
        } catch (_) { /* fall through to timedOut */ }
      }
      finish({ signed: false, timedOut: true })
    }, timeoutMs)
  })
}
```

- [ ] **Step 4: Run to verify it passes.** Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add coale_pos/frontend/src/services/etimsGate.js coale_pos/frontend/src/services/etimsGate.test.js
git commit -m "feat(pos): add waitForEtimsSigned gate (realtime + timeout backstop)"
```

---

### Task 7: localStorage pending-reprint helpers + reconcile

**Files:**
- Modify: `coale_pos/frontend/src/services/etimsGate.js`
- Modify: `coale_pos/frontend/src/services/etimsGate.test.js`

- [ ] **Step 1: Write the failing tests**

```js
import { addPendingReprint, getPendingReprints, removePendingReprint, reconcilePendingReprints } from './etimsGate'

describe('pending reprint set', () => {
  beforeEach(() => { globalThis.localStorage = (() => {
    let s = {}; return { getItem: k => s[k] ?? null, setItem: (k, v) => { s[k] = String(v) }, removeItem: k => { delete s[k] } }
  })() })

  it('adds and lists pending invoices', () => {
    addPendingReprint('SINV-1')
    expect(getPendingReprints().map(e => e.invoice)).toContain('SINV-1')
  })

  it('removePendingReprint drops the entry', () => {
    addPendingReprint('SINV-2'); removePendingReprint('SINV-2')
    expect(getPendingReprints().map(e => e.invoice)).not.toContain('SINV-2')
  })

  it('reconcile reprints a now-signed invoice exactly once (print-then-remove)', async () => {
    addPendingReprint('SINV-3')
    const statusFetcher = vi.fn().mockResolvedValue({ signed: true })
    const reprint = vi.fn().mockResolvedValue()
    await reconcilePendingReprints({ statusFetcher, reprint })
    expect(reprint).toHaveBeenCalledWith('SINV-3')
    expect(getPendingReprints()).toHaveLength(0)
  })

  it('reconcile keeps a still-queued invoice pending', async () => {
    addPendingReprint('SINV-4')
    await reconcilePendingReprints({ statusFetcher: vi.fn().mockResolvedValue({ signed: false }), reprint: vi.fn() })
    expect(getPendingReprints().map(e => e.invoice)).toContain('SINV-4')
  })

  it('reconcile expires entries older than TTL', async () => {
    addPendingReprint('SINV-5', { now: 0 })
    await reconcilePendingReprints({ statusFetcher: vi.fn().mockResolvedValue({ signed: false }), reprint: vi.fn(), now: 999999999, ttlMs: 1 })
    expect(getPendingReprints().map(e => e.invoice)).not.toContain('SINV-5')
  })
})
```

- [ ] **Step 2: Run to verify it fails.** Expected: FAIL (helpers not exported).

- [ ] **Step 3: Implement (append to `etimsGate.js`)**

```js
const PENDING_KEY = 'etims_pending_reprints'
const DEFAULT_TTL_MS = 30 * 60 * 1000 // 30 min

function _read() {
  try { return JSON.parse(localStorage.getItem(PENDING_KEY) || '[]') } catch { return [] }
}
function _write(list) { localStorage.setItem(PENDING_KEY, JSON.stringify(list)) }

export function addPendingReprint(invoice, { now } = {}) {
  if (!invoice) return
  const list = _read().filter(e => e.invoice !== invoice)
  list.push({ invoice, at: now ?? Date.now() })
  _write(list)
}
export function getPendingReprints() { return _read() }
export function removePendingReprint(invoice) { _write(_read().filter(e => e.invoice !== invoice)) }

/**
 * Reprint QR copies for invoices that became signed while we weren't listening.
 * print-then-remove ordering: prints first, then drops the entry. A crash between
 * yields at most one benign duplicate on the next mount (never a lost QR).
 */
export async function reconcilePendingReprints({ statusFetcher, reprint, now, ttlMs = DEFAULT_TTL_MS } = {}) {
  const tnow = now ?? Date.now()
  for (const entry of _read()) {
    if (tnow - entry.at > ttlMs) { removePendingReprint(entry.invoice); continue }
    let signed = false
    try { signed = (await statusFetcher(entry.invoice))?.signed } catch { signed = false }
    if (!signed) continue
    try { await reprint(entry.invoice) } catch { continue } // keep pending on print failure
    removePendingReprint(entry.invoice) // print-then-remove
  }
}
```

- [ ] **Step 4: Run to verify it passes.** Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add coale_pos/frontend/src/services/etimsGate.js coale_pos/frontend/src/services/etimsGate.test.js
git commit -m "feat(pos): reload-robust pending-reprint set with print-then-remove reconcile"
```

---

## Chunk 3: Frontend wiring + acceptance

### Task 8: Gate the `ReceiptSendDialog` auto-print + disable manual controls while pending

**Files:**
- Modify: `coale_pos/frontend/src/components/pos/ReceiptSendDialog.vue` (open watch ~187-224; print handlers `handlePrintReceipt` ~246, `onPrinterMappingSaved` ~231; browser fallback ~256)

- [ ] **Step 1: Add props + a `finalizing` ref**

Props passed from `Retail.vue`: `etimsWaitEnabled: Boolean` (already ANDed with the
kill-switch in `Retail.vue` — see Task 9 Step 5), `etimsWaitMs: Number`. Add
`const finalizing = ref(false)`.

> **Kill-switch consumption (spec §3):** the gate must wait only when signing is on **AND**
> `wait_for_etims_before_print` is on. That AND is computed in `Retail.vue` and passed as the
> single `etimsWaitEnabled` prop, so this component gates on one boolean. With the kill-switch
> off, `etimsWaitEnabled` is false → no wait → today's behavior (satisfies Task 10's
> kill-switch acceptance check).

- [ ] **Step 2: Gate the auto-print watch**

In the `watch` that fires on open, before calling `printViaQzTray`, insert:

```js
import { waitForEtimsSigned } from '@/services/etimsGate'
import { getEtimsSigningStatus, registerProvisionalReprint } from '@/services/etimsReprint' // thin wrappers (Task 9)

// inside the open handler, after invoiceName is known:
if (props.etimsWaitEnabled) {
  finalizing.value = true
  const res = await waitForEtimsSigned(props.invoiceName, {
    signingEnabled: true,
    timeoutMs: props.etimsWaitMs || 6000,
    statusFetcher: getEtimsSigningStatus,
  })
  finalizing.value = false
  if (res.timedOut) registerProvisionalReprint(props.invoiceName) // provisional now, reprint later
}
// existing printViaQzTray(...) call proceeds (re-renders server-side → QR if present)
```

- [ ] **Step 3: Disable manual controls while `finalizing`**

Bind `:disabled="finalizing"` on the print/send buttons and early-return in `handlePrintReceipt`, `onPrinterMappingSaved`, and the browser-print fallback when `finalizing.value` is true. Show a "Finalizing eTIMS…" label while pending.

- [ ] **Step 4: Manual verification (no unit test for the Vue component)**

Build the SPA: `cd apps/coale_pos/frontend && yarn build`. Expected: build succeeds, no import errors. Component behavior is covered by the acceptance checklist (Task 10).

- [ ] **Step 5: Commit**

```bash
git add coale_pos/frontend/src/components/pos/ReceiptSendDialog.vue
git commit -m "feat(pos): gate receipt print on eTIMS signing; lock manual controls while waiting"
```

---

### Task 9: Session listener + reconcile-on-mount in `Retail.vue` (+ thin wrappers)

**Files:**
- Create: `coale_pos/frontend/src/services/etimsReprint.js` (thin wrappers: `getEtimsSigningStatus(invoice)` → server call; `registerProvisionalReprint(invoice)` → `addPendingReprint`; `reprintQrCopy(invoice)` → `printViaQzTray` with the eTIMS format)
- Modify: `coale_pos/frontend/src/pages/pos/Retail.vue` (`onMounted` ~1265; existing `window.frappe.realtime.on` usage ~1293)
- Test: `coale_pos/frontend/src/services/etimsReprint.test.js` (only the pure mapping bits; the realtime/print I/O is verified manually)

> **VERIFIED:** the SPA imports `call` from `'frappe-ui'` (see `printService.js:9`), and
> `call(...)` returns the **already-unwrapped** result (no `.message` envelope). Do NOT use
> `@/utils/api` (does not exist) or `r?.message`.

- [ ] **Step 1: Write a small failing test for the wrapper mapping**

```js
// src/services/etimsReprint.test.js
import { describe, it, expect, vi } from 'vitest'

vi.mock('frappe-ui', () => ({ call: vi.fn() }))
vi.mock('./printService', () => ({ printViaQzTray: vi.fn(), getQzPrintFormat: vi.fn() }))
import { call } from 'frappe-ui'
import { getEtimsSigningStatus } from './etimsReprint'

describe('getEtimsSigningStatus', () => {
  it('calls the server method and returns its (unwrapped) result', async () => {
    call.mockResolvedValue({ signed: true, status: 'Sent' })
    const out = await getEtimsSigningStatus('SINV-1')
    expect(call).toHaveBeenCalledWith(
      'kenya_etims_compliance.custom_methods.etims_status.get_etims_signing_status',
      { invoice_name: 'SINV-1' },
    )
    expect(out).toEqual({ signed: true, status: 'Sent' })
  })
})
```

- [ ] **Step 2: Run to verify it fails.** Expected: FAIL (module not found).

- [ ] **Step 3: Implement `etimsReprint.js`**

```js
import { call } from 'frappe-ui'
import { addPendingReprint, removePendingReprint, reconcilePendingReprints } from './etimsGate'
import { printViaQzTray } from './printService'

export async function getEtimsSigningStatus(invoice) {
  // call() returns the unwrapped result (no .message envelope), matching printService.js usage.
  return await call('kenya_etims_compliance.custom_methods.etims_status.get_etims_signing_status', {
    invoice_name: invoice,
  })
}
export function registerProvisionalReprint(invoice) { addPendingReprint(invoice) }
export async function reprintQrCopy(invoice, posProfile) { return printViaQzTray(invoice, posProfile) }
export { reconcilePendingReprints, removePendingReprint }
```

- [ ] **Step 4: Run to verify it passes.** Expected: PASS.

- [ ] **Step 5: Bind dialog props (incl. kill-switch AND) in `Retail.vue` template**

Compute the gate-enable flag from the profile in the store (signing ON **AND** wait
kill-switch ON) and the wait window in ms, then pass both to the single `<ReceiptSendDialog>`:

```js
// in <script setup>, near other computed:
const etimsWaitEnabled = computed(() =>
  !!(posStore.posProfileDetails?.custom_enable_etims_signing && posStore.posProfileDetails?.etims_wait_before_print)
)
const etimsWaitMs = computed(() => (posStore.posProfileDetails?.etims_print_wait_seconds || 6) * 1000)
```

```html
<!-- add to the existing <ReceiptSendDialog ...> (Retail.vue ~253) -->
<ReceiptSendDialog
  v-model="showReceiptSendDialog"
  :invoice-name="lastInvoiceName"
  :etims-wait-enabled="etimsWaitEnabled"
  :etims-wait-ms="etimsWaitMs"
  ... />
```

> The store exposes the profile as `posStore.posProfileDetails` (ref at `stores/pos.js:21`,
> assigned the whole `profileResult.profile` at ~line 248). Task 4 places
> `custom_enable_etims_signing` / `etims_wait_before_print` / `etims_print_wait_seconds`
> inside that `profile` dict, so they are available on `posStore.posProfileDetails`.

- [ ] **Step 6: Wire the session listener + reconcile in `Retail.vue`**

In `onMounted`, after the existing realtime setup:

```js
import {
  reconcilePendingReprints, getPendingReprints,
} from '@/services/etimsGate'
import {
  getEtimsSigningStatus, reprintQrCopy, removePendingReprint,
} from '@/services/etimsReprint'

const onEtimsSigned = async (payload) => {
  const inv = payload?.invoice
  if (!inv) return
  if (!getPendingReprints().some(e => e.invoice === inv)) return // filter: only ours, only pending
  // Re-confirm via the status endpoint before printing (spec Unit 6).
  try {
    const s = await getEtimsSigningStatus(inv)
    if (!s?.signed) return
    await reprintQrCopy(inv, posStore.posProfileDetails)
    removePendingReprint(inv) // print-then-remove
  } catch (_) { /* keep pending; reconcile-on-mount will retry */ }
}
window.frappe?.realtime?.on('etims_invoice_signed', onEtimsSigned)

// reload-robustness: reprint anything that signed while we were away
reconcilePendingReprints({
  statusFetcher: getEtimsSigningStatus,
  reprint: (inv) => reprintQrCopy(inv, posStore.posProfileDetails),
})
```

Remove the listener in `onUnmounted` (`window.frappe?.realtime?.off('etims_invoice_signed', onEtimsSigned)`).

- [ ] **Step 7: Build + commit**

```bash
cd apps/coale_pos/frontend && yarn build && cd -
git add coale_pos/frontend/src/services/etimsReprint.js coale_pos/frontend/src/services/etimsReprint.test.js coale_pos/frontend/src/pages/pos/Retail.vue
git commit -m "feat(pos): session reprint listener + reconcile-on-mount for eTIMS QR copies"
```

---

### Task 10: Acceptance checklist (manual, on a worker-scaled bench)

**Prerequisite (operational, not code):** the wait only succeeds reliably when the queue drains fast. On this bench's single dev worker the wait will usually time out; for a realistic test, run production workers or temporarily set `background_workers` ≥ 3 and run a dedicated `short`-queue worker. Document this in the PR.

- [ ] Healthy KRA, signing ON → first receipt shows a **scannable QR** (normal sale).
- [ ] Same for a **return/credit-note** sale.
- [ ] Throttled/slow KRA → provisional prints immediately, **QR copy auto-prints** within seconds when `Sent`.
- [ ] **Reload** the POS between provisional and `Sent` → QR copy prints on next load (reconcile).
- [ ] **Two tills** signing concurrently → neither resolves/reprints the other's invoice.
- [ ] **Offline** sale → offline notice only, no dialog, no stuck wait.
- [ ] **Kill-switch** (`wait_for_etims_before_print` = 0) → behaves exactly as today (no wait).
- [ ] Manual print/send buttons are **disabled** during "Finalizing eTIMS…".

- [ ] **Final commit / PR**

```bash
git add -A && git commit -m "test(etims): acceptance checklist for wait-before-print"
```

---

## Rollout notes

- Ship with the kill-switch ON by default; a site with under-provisioned workers can set `wait_for_etims_before_print = 0` to disable the wait without a deploy.
- The real unlock for "QR on the *first* receipt" is worker scaling (`bench setup production` / dedicated eTIMS queue) — call this out in the PR as the operational follow-up.
- No change to submit / queue insert / idempotency barrier / per-branch number allocation.
- **Backstop scope (intentional):** the spec mentioned a "low-frequency safety poll"; this
  plan deliberately implements only the **on-timeout status read** (`waitForEtimsSigned`) plus
  **reconcile-on-mount**. Realtime + those two cover the failure modes (dropped event, reload)
  without a periodic poll — adding one would be YAGNI. If field data later shows missed
  reprints, a periodic reconcile timer is the natural follow-up.
