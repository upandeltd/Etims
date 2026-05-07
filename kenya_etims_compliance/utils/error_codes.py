# kenya_etims_compliance/utils/error_codes.py
"""KRA eTIMS Error Code Mapping (TIS Spec 21.3, 21.6.3).

Maps result codes from the OSCU/VSCU API responses to human-readable
messages and recommended actions.
"""

# Result code -> (message, recommended_action)
KRA_ERROR_CODES = {
    "000": ("Success", ""),
    "001": ("Saved successfully", ""),
    "010": ("No data found", "Verify the request parameters are correct."),
    "020": ("Duplicate data", "This transaction has already been submitted. Check for duplicate invoice numbers."),
    "030": ("Invalid request", "Review the payload structure and required fields."),
    "031": ("Missing required field", "Ensure all mandatory fields are populated."),
    "032": ("Invalid field value", "Check field values match KRA expected formats and code lists."),
    "033": ("Invalid date format", "Dates must be in YYYYMMDDHHmmss format."),
    "034": ("Invalid number format", "Verify numeric fields contain valid numbers."),
    "040": ("Authentication failed", "Check TIN, branch ID, and communication key in TIS Device Initialization."),
    "041": ("Authorization failed", "This operation is not authorized for this device/user."),
    "042": ("Communication key expired", "Re-initialize the device to obtain a new communication key."),
    "043": ("Device not registered", "Register this OSCU/VSCU device with KRA before use."),
    "044": ("Device suspended", "Contact KRA — this device has been suspended."),
    "045": ("Branch not registered", "Register this branch with KRA."),
    "050": ("Item not registered", "Register the item with KRA using the Item Registration API before selling."),
    "051": ("Item classification not found", "Check the item classification code against KRA code list."),
    "052": ("Invalid tax type code", "Verify the tax type code (A/B/C/D/E) is correct."),
    "053": ("Invalid packaging unit code", "Check the packaging unit code against KRA code list."),
    "054": ("Invalid quantity unit code", "Check the quantity unit code against KRA code list."),
    "060": ("Invoice number mismatch", "The invoice number sequence is incorrect. Check the last invoice number."),
    "061": ("Receipt number error", "Receipt numbering issue — contact KRA support if persistent."),
    "062": ("Stock release number error", "SAR number issue — verify SAR sequence."),
    "070": ("Server error", "KRA server error — retry the request after a short delay."),
    "071": ("Service unavailable", "KRA service is temporarily unavailable. Retry later."),
    "080": ("Timeout", "The KRA server did not respond in time. Retry the request."),
    "090": ("Data integrity error", "Data validation failed on KRA side. Review all field values."),
    "099": ("Unknown error", "An unexpected error occurred. Check KRA error logs for details."),
    # Authentication / header errors
    "900": ("Missing API headers", "No active TIS Device Initialization found for this branch. Check that the device is registered and active."),
    # Device installation / re-initialization codes
    "902": ("Device already installed", "This device is already registered with KRA. No re-initialization needed. Verify device is online using selectOrgUsrInfo."),
}

# Warning codes (Spec 21.6.4) — memory capacity warnings
KRA_WARNING_CODES = {
    0: ("Normal operation", "No action required."),
    1: ("Memory capacity low", "OSCU/VSCU memory is running low. Plan for maintenance."),
    2: ("Memory capacity critical", "OSCU/VSCU memory is critically low. Immediate maintenance required."),
}


def get_error_message(result_cd):
    """Look up a KRA result code and return (message, action) tuple.

    Args:
        result_cd: The resultCd string from the KRA API response.

    Returns:
        tuple: (human_readable_message, recommended_action)
    """
    if result_cd in KRA_ERROR_CODES:
        return KRA_ERROR_CODES[result_cd]
    return (f"Unrecognized error code: {result_cd}", "Contact KRA support or check the TIS specification.")


def get_warning_message(warning_cd):
    """Look up a KRA warning code and return (message, action) tuple.

    Args:
        warning_cd: The warning code integer (0-2) from the KRA API response.

    Returns:
        tuple: (message, action)
    """
    warning_cd = int(warning_cd) if warning_cd is not None else 0
    if warning_cd in KRA_WARNING_CODES:
        return KRA_WARNING_CODES[warning_cd]
    return (f"Unknown warning code: {warning_cd}", "Check the TIS specification.")
