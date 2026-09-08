frappe.listview_settings["Item"] = {
    onload: function(listview) {
        listview.page.add_action_item(__("Register to eTIMS"), function() {
            const selected = listview.get_checked_items();

            if (!selected.length) {
                frappe.msgprint(__("Please select at least one item."));
                return;
            }

            const etims_item_doc_names = selected.map(item => item.name).filter(name => name);
            console.log(etims_item_doc_names);
            if (!etims_item_doc_names.length) {
                frappe.msgprint(__("None of the selected items have an eTIMS item linked."));
                return;
            }

            frappe.confirm(
                `Are you sure you want to register ${etims_item_doc_names.length} item(s) to eTIMS?`,
                () => {
                    frappe.call({
                        method: "kenya_etims_compliance.custom_methods.item.bulk_item_save_req",
                        args: { doc_names: etims_item_doc_names },
                        freeze: true,
                        freeze_message: __("Registering items to eTIMS..."),
                        callback: function(r) {
                            if (!r.message) return;

                            const { success, errors } = r.message;

                            let msg = "";

                            if (success.length) {
                                msg += `<p><b style="color: green;">✔ ${success.length} item(s) registered successfully:</b></p><ul>`;
                                success.forEach(s => {
                                    msg += `<li>${s.doc_name}: ${s.message}</li>`;
                                });
                                msg += "</ul>";
                            }

                            if (errors.length) {
                                msg += `<p><b style="color: red;">✘ ${errors.length} item(s) failed:</b></p><ul>`;
                                errors.forEach(e => {
                                    msg += `<li>${e.doc_name}: ${e.message}</li>`;
                                });
                                msg += "</ul>";
                            }

                            frappe.msgprint({
                                title: __("eTIMS Registration Results"),
                                indicator: errors.length ? "red" : "green",
                                message: msg
                            });

                            listview.refresh();
                        }
                    });
                }
            );
        });
    }
};