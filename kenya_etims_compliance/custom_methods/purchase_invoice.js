frappe.ui.form.on("Purchase Invoice",{
    is_return:function(frm){
        if(frm.doc.is_return == 1){
            is_return_doc(frm)

        }else{
            frm.doc.custom_receipt_type_code = "P"
            frm.doc.custom_purchase_status_code = "02"
        }

        refresh_field("custom_receipt_type_code")
        refresh_field("custom_purchase_status_code")
    },

    onload:function(frm){
        if(frm.doc.is_return == 1){
            is_return_doc(frm)

            refresh_field("custom_receipt_type_code")
            refresh_field("custom_purchase_status_code")
        }
       
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

function is_return_doc(frm){
   
    frm.doc.custom_receipt_type_code = "R"
    frm.doc.custom_purchase_status_code = "05"
   
}