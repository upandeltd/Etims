import frappe


def run():
	"""Verify queue status after processing all invoices."""
	frappe.connect()

	# Check remaining queued entries
	queued = frappe.db.count("eTIMS Invoice Queue", filters={"status": "Queued"})
	failed = frappe.db.count("eTIMS Invoice Queue", filters={"status": "Failed"})
	sent = frappe.db.count("eTIMS Invoice Queue", filters={"status": "Sent"})
	processing = frappe.db.count("eTIMS Invoice Queue", filters={"status": "Processing"})

	print("\n" + "=" * 60)
	print(" eTIMS INVOICE QUEUE STATUS")
	print("=" * 60)
	print(f"  Queued:     {queued}")
	print(f"  Processing: {processing}")
	print(f"  Sent:       {sent}")
	print(f"  Failed:     {failed}")
	print("=" * 60)

	if queued == 0:
		print("\n  Queue is now clear. All invoices have been processed.")
	else:
		print(f"\n  WARNING: {queued} invoices still in queue.")
