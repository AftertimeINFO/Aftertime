from django.test import TestCase

from core.test.general.unitOperation import balance_substances
from core.test.general.unitOperation import substances
from core.test.general.unitOperation import locations

from core.api import locations as api_locations
from core.api import substances as api_substances
from core.api import balance_substances as api_balance_substances


class TestBalanceSubstances(TestCase):
    def setUp(self):
        substances.add_template(self)
        locations.add_template(self)
        balance_substances.add_template(self)

    def test_001_sum_by_substances(self):
        api_balance_substances.get_all()
        api_balance_substances.get_balances_by_substances()
        # api_locations.get_all()
        print('test')
        pass

    def test_001_GetLocation(self):
        # new_location = core.api.locations.add(description="USA")

        # result = locations.Locations.objects.all() LocationsManager().get_all()
        # result = locations.Locations() .Locations().objects.all()
        pass