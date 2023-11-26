import json
from datetime import datetime
from django.test import TestCase

import core.api.locations
from core.models import locations
from core.test.general.unitOperation.vehicles import ship
# Create your tests here.

from core.test.general.dataTemplates.vehicles import ships as data_template
from core.api.structures.objects import api_ships as api

import json as lib_json


class Test001Operation(TestCase):
    ships = []

    def setUp(self):
        self.ships = ship.add_template(self)

    def test_001_UpdateData(self):
        # region Check write equal data with no changes saving
        template = data_template.data_no_changes()
        for cur_data in template:
            result_element = api.update_by_json(lib_json.dumps(cur_data))
            ship_position_json = api.get_ship_position_json(id_mt=str(cur_data["id_mt"]))
            ship_position_dict = json.loads(ship_position_json)

            self.assertNotEqual(datetime.strptime(ship_position_dict["moment"], '%Y-%m-%d %H:%M:%S'),
                                datetime.strptime(cur_data["sync_moment"], '%Y-%m-%d %H:%M:%S'),
                                "Unexpected data update")
            pass
        # endregion

        # region Check write now position
        template = data_template.data_update()
        for cur_data in template:
            result_element = api.update_by_json(lib_json.dumps(cur_data))
            ship_position_json = api.get_ship_position_json(id_mt=str(cur_data["id_mt"]))
            ship_position_dict = json.loads(ship_position_json)

            self.assertEqual(datetime.strptime(ship_position_dict["moment"], '%Y-%m-%d %H:%M:%S'),
                             datetime.strptime(cur_data["sync_moment"], '%Y-%m-%d %H:%M:%S'),
                             "Data was not updated")

            self.assertEqual(ship_position_dict["lat"],
                             float(cur_data["position_lat"]),
                             "New Latitude position was not saved")

            self.assertEqual(ship_position_dict["lon"],
                             float(cur_data["position_lon"]),
                             "New Longitude position was not saved")
        # endregion

    def test_002_get_position(self):
        for cur_ship in self.ships:
            ship_json = api.get_ship_position_json(uuid_ship=str(cur_ship["uuid"]))
            ship_data = json.loads(ship_json)
            self.assertEqual(ship_data["name"], cur_ship["vehicle_name"], "Incorrect name save in DB")

    def test_003_get_ships_on_region(self):
        ship_locations = data_template.data_update()
        for cur_data in ship_locations:
            api.update_by_json(lib_json.dumps(cur_data))
        ships = api.get_ships_on_region_entryes(45.3, 28.9, 0.1)
