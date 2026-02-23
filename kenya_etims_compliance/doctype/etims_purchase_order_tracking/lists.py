# Copyright (c) 2026, Upande Ltd and contributors
# For license information, please see license.txt

def get_list_context(context):
    return {
        "title": "eTIMS Purchase Order Tracking",
        "show_sidebar": True,
        "show_search": True,
        "toolbar": [
            {
                "label": "Refresh",
                "href": "#",
                "onclick": "location.reload();"
            }
        ]
    }
