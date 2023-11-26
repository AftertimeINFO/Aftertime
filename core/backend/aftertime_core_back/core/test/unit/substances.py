from django.test import TestCase

import core.api.locations
from core.models import locations
from core.test.general.unitOperation import substances
# Create your tests here.


class Test001Operation(TestCase):
    def setUp(self):
        substances.add_template(self)

    def test_001_AddLocation(self):
        print('test')
        pass

    def test_001_GetLocation(self):
        # new_location = core.api.locations.add(description="USA")

        # result = locations.Locations.objects.all() LocationsManager().get_all()
        # result = locations.Locations() .Locations().objects.all()
        pass