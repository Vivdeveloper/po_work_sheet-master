frappe.ui.form.on("Item", {
    validate:function(frm,cdt,cdn){
            for (var i = 0; i < frm.doc.custom_moving_section.length; i++) {
                for (var j = i + 1; j <frm.doc.custom_moving_section.length; j++) {
                    if (frm.doc.custom_moving_section[i].branch_wh == frm.doc.custom_moving_section[j].branch_wh) {
                        frappe.throw(__("Can't repeat same branch in the Moving section " + frm.doc.custom_moving_section[j].branch_wh));
                    }
                }
                if(frm.doc.custom_moving_section[i].fms==''){
                    var row=i+1
                    frappe.throw(__("Please enter the values in the Row "+ row+" of Moving section"))
                }

            }
        }
})