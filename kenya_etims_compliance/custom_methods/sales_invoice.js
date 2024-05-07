frappe.ui.form.on("Sales Invoice",{
    is_return:function(frm){
        updateSalesType(frm)

        refresh_field("custom_receipt_type_code")
        refresh_field("custom_invoice_status_code")
        refresh_field("custom_credit_note_reason_code")
    },
    onload:function(frm){
        updateSalesType(frm)

        refresh_field("custom_receipt_type_code")
        refresh_field("custom_invoice_status_code")
        refresh_field("custom_credit_note_reason_code")
    },

    after_save:function(frm){
        if(frm.doc.update_stock == 1){
            if(frm.doc.set_warehouse){
                // console.log(frm.doc.set_warehouse)
                frm.fields_dict.items.grid.grid_rows.forEach((row) => {
                    if (row){
                        row.doc.warehouse = frm.doc.set_warehouse
                    }
                })
            }
        }
    }
})

function updateSalesType(frm){
    if(frm.doc.is_return == 1){
        frm.doc.custom_receipt_type_code = "R"
        frm.doc.custom_invoice_status_code = "05"
        frm.doc.custom_credit_note_reason_code = "06"
    }else{
        frm.doc.custom_receipt_type_code = "S"
        frm.doc.custom_invoice_status_code = "02"
        frm.doc.custom_credit_note_reason_code = ""
    }
}