import uuid as lib_uuid

from core.test.general.dataTemplates import locations as data_template
from core.api import locations as api


def add_template(self):
    template = data_template.data()
    for cur_data in template:
        new_element = api.add(**cur_data)

        add_element = api.get_by_uuid(uuid=new_element.uuid)

        for (key, value) in cur_data.items():
            check_value = getattr(add_element, key)

            if isinstance(check_value, lib_uuid.UUID):
                check_value = str(check_value)

            self.assertEqual(check_value, value, "Incorrect compare DATA in new object")

