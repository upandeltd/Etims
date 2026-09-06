"""ESC/POS raw command helpers for thermal (raw_printing) print formats.

Exposed to print-format Jinja via the ``jinja`` hook in hooks.py. These are
pure functions and MUST never raise during print rendering — every public
helper degrades to an empty string on any problem so the template can fall
back to plain text. (A raised exception here would break print rendering for
every doctype, since the jinja hook is site-global.)

Byte-safety note
----------------
Frappe raw printing sends the rendered string to QZ Tray, whose default config
uses ``encoding: null`` → the desktop app encodes with the JVM-default charset.
Under that default, bytes 128-255 are NOT guaranteed to survive (UTF-8 turns
them into multibyte sequences and corrupts the command); bytes 0-127 are
identical under every charset. The QR "store data" command's length prefix is
two bytes (pL, pH forming a little-endian uint16), and EITHER byte can land in
128-255 depending on the payload length — we therefore only emit the command
while BOTH length bytes stay below 128. Because pL wraps every 256 bytes, this
leaves safe/unsafe length "islands" (e.g. data length 0-124 is safe, 125-252
is NOT, 253-380 is safe again, ...) — a realistic KRA receipt-verification URL
(~114-140 chars depending on the issued signature's length) can land in an
unsafe island. When that happens we log it via frappe.log_error instead of
silently dropping it, so an oversized URL is diagnosable. The real fix for the
unsafe islands is on the print pipeline, not here: have the QZ Tray raw-print
call request explicit ``encoding: 'ISO-8859-1'`` (Latin-1 maps byte values
0-255 to code points 1:1, so no re-encode corruption is possible for ANY byte)
instead of relying on the JVM-default charset.
"""

import frappe

# GS ( k — ESC/POS QR code (function 165) command prefix
_GS_K = "\x1d\x28\x6b"

# Error-correction selectors for the "set EC level" sub-command (48-51)
_EC_LEVELS = {"L": "\x30", "M": "\x31", "Q": "\x32", "H": "\x33"}


def _safe_length_bytes(store_len):
	"""Return ``(pL, pH)`` for ``store_len``, or None if either byte would be >= 128."""
	pL = store_len & 0xFF
	pH = (store_len >> 8) & 0xFF
	if pL >= 128 or pH >= 128:
		return None
	return pL, pH


def escpos_qr(data, module_size=6, ec_level="M"):
	"""Return an ESC/POS QR-code command string for ``data``.

	Returns "" when there is no data, or when the length prefix would need a
	byte >= 128 (the caller should then print the URL as plain text instead —
	the print format's ``{% if _qr %}`` fallback already handles this). Unlike
	the previous behavior, the length-cap case is logged via frappe.log_error
	rather than failing silently, since it can trip on legitimate, KRA-issued
	verification URLs.
	"""
	try:
		if not data:
			return ""

		data = str(data)
		store_len = len(data) + 3
		length_bytes = _safe_length_bytes(store_len)
		if length_bytes is None:
			frappe.log_error(
				title="eTIMS: QR code omitted",
				message=(
					f"escpos_qr: {len(data)}-char payload (store_len={store_len}) needs a "
					"length-prefix byte >= 128, which is not byte-safe for raw ESC/POS "
					"printing under the default JVM charset. QR omitted; the plain-text "
					f"URL still prints. Data: {data}"
				),
			)
			return ""
		pL, pH = length_bytes

		try:
			module_size = int(module_size)
		except (TypeError, ValueError):
			module_size = 6
		if not 1 <= module_size <= 16:
			module_size = 6

		ec = _EC_LEVELS.get(str(ec_level).upper(), _EC_LEVELS["M"])

		select_model = _GS_K + "\x04\x00\x31\x41\x32\x00"  # model 2
		set_size = _GS_K + "\x03\x00\x31\x43" + chr(module_size)
		set_ec = _GS_K + "\x03\x00\x31\x45" + ec
		store = _GS_K + chr(pL) + chr(pH) + "\x31\x50\x30" + data
		print_symbol = _GS_K + "\x03\x00\x31\x51\x30"

		return select_model + set_size + set_ec + store + print_symbol
	except Exception:
		# Never break print rendering — fall back to plain text.
		return ""
