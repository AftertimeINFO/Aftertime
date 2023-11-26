import json as lib_json

from rest_framework.test import APITestCase
from core.test.general.dataTemplates.vehicles import ships
from core.test.general.unitOperation.vehicles import ship


class Test_000_REST(APITestCase):
    def setUp(self):
        pass

    def test_001(self):
        template_vehicles = ship.add_template(self)

        resultGet = self.client.get("/api/v1/back/ping")
        self.assertEqual(resultGet.status_code, 200, "General API Critical error.")

        # json_sent = json.dumps(ships.data())

        resultGet = self.client.get(f"/api/v1/back/vehicle/ship/track?uuid_ship={str(template_vehicles[0])}")
        # result_get = self.client.post("/api/v1/back/vehicle/ship", ships.data()[0])
        line1 = resultGet.data
        pass

    # def test_001_Smoke(self):
    #     resultGet = self.client.get("/pullgerAM/api/ping/")
    #     self.assertEqual(resultGet.status_code, 200, "General API Critical error.")
    #
    #     self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token)
    #     resultGet = self.client.get("/pullgerAM/api/pingAuth/")
    #
    #     self.assertEqual(resultGet.status_code, 200, "General API Critical error with authentification.")

    # def test_000_AccountAddforLinkedIN(self):
    #     unitOperationsAMRest.add_account_for_linkedin(self)