# kenya_etims_compliance/custom_methods/receipt_labels.py
"""Receipt label generation per TIS Spec 4.3.

Labels encode the receipt type and transaction type:
  NS = Normal Sale,     NC = Normal Credit
  CS = Copy Sale,       CC = Copy Credit
  TS = Training Sale,   TC = Training Credit
  PS = Proforma Sale
"""

import frappe


def get_receipt_label(doc):
	"""Determine the receipt label for a Sales Invoice.

	Args:
	    doc: Sales Invoice document

	Returns:
	    str: Two-character receipt label (NS, NC, CS, CC, TS, TC, PS)
	"""
	from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
		get_etims_settings,
	)

	settings = get_etims_settings()
	is_credit = doc.is_return == 1
	is_training = settings.get("training_mode", 0)
	is_copy = (doc.custom_receipt_copy_count or 0) > 0
	is_draft = doc.docstatus == 0

	if is_draft:
		return "PS"  # Proforma Sale

	if is_training:
		return "TC" if is_credit else "TS"

	if is_copy:
		return "CC" if is_credit else "CS"

	return "NC" if is_credit else "NS"
