# eTIMS "Wait-for-Sent before print" as the default POS receipt flow

- **Date:** 2026-06-09
- **Status:** Approved design — spec reviewed ✅ (3 HIGH issues resolved + advisories folded in)
- **Apps touched:** `kenya_etims_compliance` (server, settings, realtime), `coale_pos` (frontend)
- **Owner doctype:** `eTIMS Settings`

---

## 1. Problem

On a Coale POS retail sale, KRA eTIMS signing runs **asynchronously** by default
(`eTIMS Settings.enable_queue = 1`). The KRA receipt signature (`rcptSign`) — and
therefore the verification **QR** — only exists *after* the background queue worker
(`process_queue_entry` → `_handle_sales_invoice_success`) gets KRA's response, which
happens **seconds after** `create_pos_invoice` returns and commits.

The thermal receipt is re-rendered server-side at print time (`printService.js` →
`get_rendered_raw_commands` for the `Kenya eTIMS POS Receipt` format), so it reflects
whatever eTIMS fields exist **at the moment Print is clicked**. Today nothing makes the
POS wait for signing to finish, so under any real load the first receipt frequently
prints with **no scannable QR** (the `escpos_qr` Jinja helper degrades to URL-text).

A valid QR cannot be produced earlier: it encodes
`…indexEtimsReceiptData?Data=<PIN><bhfId><rcptSign>`, and `rcptSign` is only in KRA's
response. So the only way to get a QR on the *first* receipt without blocking the till
on KRA is to **briefly wait for the signing to land, then print** — falling back to a
provisional receipt (and auto-reprinting the QR copy) when KRA is slow.

## 2. Goal

Make **wait-for-Sent-then-print** the default POS receipt behavior, with:

- a short, **configurable** wait window before falling back,
- a **kill-switch** so a deployment can disable it without a code change,
- a **provisional-now + auto-reprint-when-Sent** fallback on timeout,
- **offline sales** bypassing the wait entirely (no KRA to reach yet).

Non-goals: changing the submit / queue / invoice-number-allocation core; changing
synchronous mode (`enable_queue = 0`); altering KRA payloads or compliance fields.

## 3. Decisions (locked with the user)

| Decision | Choice |
|---|---|
| Wait window | ~**6 s** default, **configurable** |
| Activation | **Default ON**, with a kill-switch toggle |
| Timeout fallback | **Provisional now + auto-reprint when Sent** |
| Offline sales | **Skip the wait**, print provisional |
| Wait mechanism | **Hybrid**: realtime primary + one status-poll backstop |

### Why hybrid (mechanism C)

`window.frappe.realtime` already powers `ContactlessPayment.vue`, so realtime is a
reused dependency, not a new one. Realtime alone is fast but a dropped event (socket
reconnect on a busy floor) would force a false timeout every time; poll-only is correct
but chatty and adds latency. Hybrid uses the realtime event for the instant happy path
and a single `get_etims_signing_status` read (on timeout, plus a low-frequency safety
poll) as the correctness backstop.

## 4. Architecture

```
create_pos_invoice (commit)            background worker
        │                          process_queue_entry
        │  invoice_name                     │
        ▼                                   ▼
  handlePaymentComplete            _handle_sales_invoice_success
  (4 signing-eligible branches      writes QR/rcptSign, commit
   open the SAME dialog)                  │
        │                                 │
        ▼                                 │
  ReceiptSendDialog (open) ◄── single print chokepoint
        │  await waitForEtimsSigned(invoiceName)
        │   ├─ realtime etims_invoice_signed (filter: invoice==me) ◄─ publish_realtime(after_commit, site room)
        │   └─ on timeout: one get_etims_signing_status read
        ▼
   signed? ── yes ─► printViaQzTray  (QR present)
        │
        └─ timed out ─► print provisional NOW
                         └─ add invoice to localStorage pending-reprint set
                                  │
   Retail.vue session listener  ◄──┘  (also reconciles this set on mount)
        on etims_invoice_signed (filter: invoice in set) → confirm Sent → reprint QR copy once

  offline branch: never opens dialog → no gate, no print (notice only)
```

### Units (each independently testable)

1. **`eTIMS Settings` fields** — `wait_for_etims_before_print` (Check, default 1),
   `etims_print_wait_seconds` (Int, default 6). Exposed through `get_etims_settings()`.
2. **`get_etims_signing_status(invoice_name)`** (server, whitelisted, read-only) →
   `{ signing_enabled, status, signed, qr_url, invoice_number }`. Permission-checked on
   Sales Invoice read. Does **not** extend `get_invoice_details` (kept lean).
3. **Realtime emit** — one line in `_handle_sales_invoice_success` after the QR commit
   (`queue_processor.py` ~line 426):
   `frappe.publish_realtime("etims_invoice_signed", {invoice, status:"Sent", qr_url}, after_commit=True)`.
   **Targeting:** this call passes no `room`/`user`/`doctype`, so per
   `frappe/realtime.py` it resolves to `get_site_room()` — a **site-wide broadcast to
   every Desk/SPA session**, not just the originating till. This is the same pattern the
   existing `qr_payment_completed` emit uses (validated-by-precedent: the coale_pos SPA
   already receives that broadcast), so it is safe to reach a POS browser session. The
   consequence — every terminal receives every terminal's event — is handled by **strict
   per-`invoice` filtering on both frontend listeners** (see Units 4 and 6). Targeting was
   deliberately left as broadcast-with-filter to reuse the proven contactless pattern
   rather than introduce per-invoice rooms the SPA would have to join/leave.
4. **`etimsGate.js`** (frontend service) — `waitForEtimsSigned(invoiceName, opts)`:
   short-circuits → `{signed:false, skip:true}` on `!signingEnabled`; otherwise races a
   realtime `etims_invoice_signed` listener **(which MUST ignore any event whose payload
   `invoice` ≠ this `invoiceName`)** vs `timeoutMs`, with one `get_etims_signing_status`
   read on timeout to absorb a dropped event. Pure, no UI. (Offline sales never reach
   this gate — see Unit 5.)
5. **Gate at the print chokepoint — `ReceiptSendDialog.vue`** (NOT per-branch in
   `Retail.vue`). `handlePaymentComplete` opens this one dialog from **four** signing-
   eligible branches — normal sale (Retail.vue:761), exchange/credit-note (717),
   outstanding payment (705), finalized draft (730) — and returns/credit-notes go through
   the *same* eTIMS signing queue, so they have the identical QR race. Gating inside the
   dialog's open→print sequence covers all four uniformly with one insertion point: when
   the dialog opens with an `invoiceName`, `await waitForEtimsSigned(...)` (showing a
   transient "Finalizing eTIMS…" state) before the existing `printViaQzTray` call. The
   **offline** branch (Retail.vue:753–757) shows a notice and never opens the dialog, so
   it is naturally excluded — no gate, no print, QR arrives later via the normal
   synced-sale signing path.
   - **Disable manual print/send controls while the wait is pending.** The dialog has
     other live print entry points besides the auto-print watch — `handlePrintReceipt`
     (~line 246), `onPrinterMappingSaved` (~231), the browser-print fallback (~256). While
     `waitForEtimsSigned` is pending, these MUST be disabled so a user cannot trigger an
     ungated print mid-wait; they re-enable once the gate resolves (signed or timed out).
   - **Exchange document assumption.** The exchange branch passes `result.sales_invoice_name`
     (Retail.vue:715); an exchange also produces a separately-signed credit note, but the
     gate tracks **the sales invoice** and the exchange receipt renders that document's QR.
     Credit-note receipt *content* is out of scope for this wait-gate.
6. **Auto-reprint listener** (session-level, mounted in `Retail.vue`, independent of the
   dialog's lifetime) — holds a set of provisionally-printed invoice names; on
   `etims_invoice_signed` it **filters by payload `invoice`**, confirms `signed` via the
   status endpoint, calls `printViaQzTray` once, then drops the entry. The set is
   **persisted to `localStorage`** and **reconciled on `Retail.vue` mount** (re-check each
   pending invoice's status, reprint any now-`Sent`, expire entries older than a bounded
   TTL). This makes auto-reprint **eventually-once** rather than losing the reprint on a
   page reload between provisional-print and the `Sent` event (see §7).

## 5. Data flow / contracts

- **Settings → frontend:** the two new fields ride the existing POS profile/boot details
  read (alongside `custom_enable_etims_signing`); no extra round-trip at sale time.
- **`get_etims_signing_status` response:**
  - `signing_enabled: bool` — `custom_update_invoice_in_tims` on the invoice.
  - `status: str` — `custom_etims_queue_status` (`Queued|Processing|Sent|Failed|null`).
  - `signed: bool` — `custom_update_sales_to_etims == 1`.
  - `qr_url: str|null` — `custom_receipt_qr_url`.
  - `invoice_number: int|null` — `custom_invoice_number`.
- **Realtime event `etims_invoice_signed`:** `{ invoice: str, status: "Sent", qr_url: str }`,
  emitted `after_commit` from the worker as a **site-wide broadcast**. Both frontend
  listeners (the `waitForEtimsSigned` race listener and the auto-reprint listener) **must
  match on the payload `invoice`** and ignore events for other tills' invoices. This is a
  hard requirement, not an optimization: without it, one cashier's signing would resolve
  another cashier's wait / trigger an unrelated reprint.

## 6. Behavior matrix

Applies to **all four signing-eligible branches** that open `ReceiptSendDialog` (normal
sale, exchange/credit-note, outstanding payment, finalized draft), since each runs the
same gated open→print sequence. Returns/credit-notes are explicitly **in scope** — they
hit the same signing queue and QR race.

| Situation | Gate result | What prints |
|---|---|---|
| Signing disabled on profile | skip (immediate) | normal receipt, no wait |
| Offline / unsynced sale | gate not reached | **no receipt today** — offline notice shown (Retail.vue:753–757); QR-bearing receipt available later once the synced sale signs (existing path) |
| KRA healthy (signed < timeout) | signed | receipt **with QR** (happy path) |
| KRA slow (timeout) | timed out | provisional now → **auto-reprint QR** on Sent (eventually-once, §7) |
| Realtime event dropped, signed in time | signed via status read on timeout | receipt with QR |
| Signing fails (queue Failed) | timed out | provisional; no auto-reprint (no Sent event); manual "Print Copy"/"Retry eTIMS" remains |
| Page reload between provisional print and Sent | timed out earlier | reconcile-on-mount reprints the QR copy when it finds the invoice now Sent (§7) |

## 7. Error handling

- The gate **never throws into checkout** — the sale is already committed and
  fiscalization is durable via the queue. Any error/timeout falls through to provisional
  print.
- Realtime listeners are registered on mount and removed on unmount; the auto-reprint set
  is bounded and self-cleaning (entry dropped after one reprint).
- `get_etims_signing_status` is permission-checked and read-only; returns
  `signing_enabled:false` for non-eTIMS invoices so the gate short-circuits.
- **Auto-reprint guarantee is "eventually at-most-once", not "exactly once".** The live
  tracked set guards against double-printing within a session. But the set is JS state: a
  page reload between the provisional print and the `Sent` event would, on its own, lose
  the reprint. The `localStorage` persistence + reconcile-on-mount (Unit 6) recovers it —
  on next mount the still-pending invoice is re-checked and the QR copy printed if it is
  now `Sent`. Net property: the QR copy prints **at most once and, barring permanent
  signing failure, eventually once**; entries expire after a bounded TTL so the set never
  grows unbounded. If signing never reaches `Sent` (queue `Failed`), no auto-reprint
  occurs and the operator falls back to the desk-form "Print Copy"/"Retry eTIMS" actions.
- **Reprint ordering (print-then-remove).** A single `localStorage` flag with non-atomic
  print-then-persist cannot guarantee *both* "at most once" and "eventually once": removing
  the entry before printing loses the reprint on a crash in between (the original bug);
  printing before removing risks a duplicate on remount. We choose **print-then-remove**
  and accept the rare benign failure — a crash in the gap yields at most one **duplicate
  QR copy** on the next mount, which is far less harmful than a missing QR. (A later
  hardening option, out of scope here, is a server-side "QR-copy-already-printed" flag for
  true idempotency.)

## 8. Testing

**Server (python):**
- `get_etims_signing_status` for: signing disabled, queued/unsigned, sent/signed,
  non-existent → permission error.
- Realtime emit fires after the success commit (assert `publish_realtime` called with
  `after_commit=True` and correct payload).

**Frontend (unit):**
- `waitForEtimsSigned`: signed-fast (realtime), timeout→`timedOut`, disabled-skip,
  realtime-dropped-but-status-read-confirms, **ignores an event for a different invoice**.
- Auto-reprint listener: reprints once on Sent; filters by payload `invoice`; ignores
  invoices not in the set; no double reprint.
- Reconcile-on-mount: a pending invoice that became `Sent` while unmounted reprints once;
  a still-`Queued` one stays pending; an expired (past-TTL) entry is dropped.

**Manual (acceptance):**
- Healthy KRA → QR on first receipt (normal sale **and** a return/credit-note).
- Throttled/slow KRA → provisional first, QR copy auto-prints on Sent.
- Reload between provisional and Sent → QR copy prints on next POS load (reconcile).
- Two tills signing concurrently → neither resolves/reprints the other's invoice.
- Offline sale → offline notice only, no dialog, no false-timeout wait.
- Kill-switch off → behaves exactly as today (no wait).

## 9. Rollout / config dependency

Option B's benefit depends on the queue draining within the wait window. This bench
currently runs a **single all-queue `bench worker`** (dev Procfile, `background_workers=1`,
no `supervisor.conf`). For the wait to usually succeed on a busy floor, deploy production
workers (`bench setup production` / raise `background_workers`, ideally a dedicated eTIMS
queue). This is an operational prerequisite, documented but out of code scope; the
kill-switch lets a site disable the wait if its workers are under-provisioned.

**Stakes under the current single worker:** with `background_workers=1`, concurrent
sales serialize through one KRA call at a time, so the ~6 s wait will **frequently time
out** under real load. That makes provisional-print + auto-reprint the **common** path,
not the exception — which is exactly why the reload-robust, `localStorage`-backed
reconcile-on-mount (Unit 6 / §7) is part of the core design rather than a nice-to-have.
Until workers are scaled, expect the QR to land on the auto-reprinted copy more often
than on the first receipt.

## 10. Files touched

- `kenya_etims_compliance/.../doctype/etims_settings/etims_settings.json` (+2 fields),
  `etims_settings.py` (`get_etims_settings` returns the 2 fields).
- `kenya_etims_compliance/.../custom_methods/sales_invoice.py` or a small new module:
  `get_etims_signing_status`.
- `kenya_etims_compliance/.../custom_methods/queue_processor.py`: 1-line realtime emit in
  `_handle_sales_invoice_success`.
- `coale_pos/frontend/src/services/etimsGate.js` (new) — `waitForEtimsSigned`, the
  invoice-filtered realtime listener, and the `localStorage` pending-reprint helpers.
- `coale_pos/frontend/src/components/pos/ReceiptSendDialog.vue` — gate the open→print
  sequence (single chokepoint for all four signing-eligible branches).
- `coale_pos/frontend/src/pages/pos/Retail.vue` — mount the session-level auto-reprint
  listener + reconcile-on-mount; pass `signingEnabled`/`timeoutMs` through to the dialog.
- Small read of the 2 settings via existing profile/boot details (no new round-trip).

No change to submit, queue insert, idempotency barrier, or per-branch number allocation.
