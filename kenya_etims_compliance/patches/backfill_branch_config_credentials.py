import frappe


def execute():
    '''Copy eTIMS credentials from TIS Device Initialization onto existing Tax Branch Configurations.'''
    frappe.db.sql("""
        UPDATE `tabTax Branch Configurations` AS tbc
        JOIN `tabTIS Device Initialization` AS tdi
            ON tdi.name = tbc.tis_device_initialization
        SET
            tbc.pin = tdi.pin,
            tbc.branch_id = tdi.branch_id,
            tbc.communication_key = tdi.communication_key,
            tbc.api_mode = tdi.api_mode
    """)
