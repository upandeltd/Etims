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
identical under every charset. The only QR command byte that can exceed 127 is
the data-store length byte, and only once the payload reaches ~125 chars. We
therefore emit the QR command ONLY while every byte stays below 128.
"""

# GS ( k — ESC/POS QR code (function 165) command prefix
_GS_K = "\x1d\x28\x6b"

# Error-correction selectors for the "set EC level" sub-command (48-51)
_EC_LEVELS = {"L": "\x30", "M": "\x31", "Q": "\x32", "H": "\x33"}

# storeLen = len(data) + 3 must stay < 128 so the length byte is single-byte safe
_MAX_SINGLE_BYTE_STORE_LEN = 128


def escpos_qr(data, module_size=6, ec_level="M"):
	"""Return an ESC/POS QR-code command string for ``data``.

	Returns "" when there is no data, or when the command would need a byte
	above 127 (the caller should then print the URL as plain text instead).
	"""
	try:
		if not data:
			return ""

		data = str(data)
		store_len = len(data) + 3
		if store_len >= _MAX_SINGLE_BYTE_STORE_LEN:
			# Length byte would exceed 127 — not byte-safe under default QZ encoding.
			return ""

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
		store = _GS_K + chr(store_len & 0xFF) + "\x00" + "\x31\x50\x30" + data
		print_symbol = _GS_K + "\x03\x00\x31\x51\x30"

		return select_model + set_size + set_ec + store + print_symbol
	except Exception:
		# Never break print rendering — fall back to plain text.
		return ""
