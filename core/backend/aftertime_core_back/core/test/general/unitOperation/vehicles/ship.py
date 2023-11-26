import uuid as lib_uuid
import json


from core.test.general.dataTemplates.vehicles import ships as data_template
from core.api.structures.objects import api_ships as api


def add_template(self):
    appended_elements = []
    template = data_template.data()
    for cur_data in template:
        new_element = api.update_by_json(json.dumps(cur_data))
        cur_data["uuid"] = new_element.entry.uuid
        appended_elements.append(cur_data)
    return appended_elements
