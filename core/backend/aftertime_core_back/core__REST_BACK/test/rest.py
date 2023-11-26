import json
import json as lib_json

from rest_framework.test import APITestCase
from core.test.general.dataTemplates.vehicles import ships

class Test_000_REST(APITestCase):

    def setUp(self):
        result_get = self.client.get("/api/v1/back/ping")
        self.assertEqual(result_get.status_code, 200, "General API Critical error.")

    def test_001(self):
        # json_sent = json.dumps(ships.data())

        for cur_ship in ships.data():
            result_get = self.client.post("/api/v1/back/vehicle/ship", json.dumps(cur_ship), content_type="application/json")
            self.assertEqual(result_get.status_code, 200, "REST API Append Ship position error.")
            self.assertIsInstance(result_get.data, dict, "Incorrect response")
            self.assertIn("data", result_get.data, "Incorrect response dict structure")
            self.assertIn("uuid", result_get.data["data"],  "Incorrect response dict structure")

            result_ship_get = self.client.get(
                f"/api/v1/back/vehicle/ship?uuid_ship={result_get.data['data']['uuid']}")

            self.assertEqual(result_ship_get.status_code, 200, "General API Critical error.")
            self.assertIsInstance(result_ship_get.data, dict, "Incorrect response")
            self.assertIn("data", result_ship_get.data, "Incorrect response dict structure")
            self.assertIsInstance(result_ship_get.data["data"], str, "Incorrect data responce")

            json_dict = json.loads(result_ship_get.data["data"])
            self.assertIn("lat", json_dict, "Incorrect response dict structure")
            self.assertIn("lon", json_dict, "Incorrect response dict structure")
            self.assertEqual(float(json_dict["lat"]), float(cur_ship["position_lat"]), "Incorrect ship creation")

        # -------------- Get Ships on Map

        for cur in ships.map_positions():
            request_url = f"/api/v1/back/vehicle/map/ships?" \
                                         f"c_lat={cur['c_lat']}&" \
                                         f"c_lon={cur['c_lon']}&" \
                                         f"c_zoom={cur['c_zoom']}"
            result_get = self.client.get(request_url)
            pass
