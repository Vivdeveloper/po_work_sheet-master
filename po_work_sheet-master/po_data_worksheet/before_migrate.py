import frappe

#Remove purge fields which does not contain module name.
def remove_purge_custom_fields():
    custom_field_list=['Item-moving_section']
    name_list = ", ".join(["%s" % frappe.db.escape(d) for d in custom_field_list])
    frappe.db.sql(
        """DELETE from `tabCustom Field` where 
        name in ({0})  and ISNULL(module) """.format(name_list))