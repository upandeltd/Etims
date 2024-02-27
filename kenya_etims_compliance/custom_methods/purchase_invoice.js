frappe.ui.form.on("Purchase Invoice",{
    is_return:function(frm){
        if(frm.doc.is_return == 1){
            frm.doc.custom_receipt_type_code = "R"
            frm.doc.custom_purchase_status_code = "05"
        }else{
            frm.doc.custom_receipt_type_code = "P"
            frm.doc.custom_purchase_status_code = "02"
        }
        refresh_field("custom_receipt_type_code")
        refresh_field("custom_purchase_status_code")
    }
})