frappe.ui.form.on("Sales Invoice",{
    is_return:function(frm){
        if(frm.doc.is_return == 1){
            frm.doc.custom_receipt_type_code = "R"
            frm.doc.custom_invoice_status_code = "05"
            frm.doc.custom_credit_note_reason_code = "06"
        }else{
            frm.doc.custom_receipt_type_code = "S"
            frm.doc.custom_invoice_status_code = "02"
            frm.doc.custom_credit_note_reason_code = ""
        }
        refresh_field("custom_receipt_type_code")
        refresh_field("custom_invoice_status_code")
        refresh_field("custom_credit_note_reason_code")
    },
    // custom_check:function(frm){
    //     frappe.call({
    //         "method": "kenya_etims_compliance.custom_methods.sales_invoice.trnsSalesSaveWrReq?doc_name=" + frm.doc.name,
    //         freeze: true,
    //         callback: function(r)   {
    //            return
    //         }		
    //     })
    // }
})
