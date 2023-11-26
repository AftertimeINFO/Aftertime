import uuid as lib_uuid

from django.db import models
from django.db.models import signals
from django.dispatch import receiver


class ManagerShips(models.Manager):

    def get_all(self):
        return self.all()

    def get_by_uuid(self, uuid: (lib_uuid, str)):
        res = self.filter(uuid=str(uuid))
        if len(res) == 1:
            return res[0]
        elif len(res) > 1:
            # TODO register core exception
            raise Exception("DB broke. Double uuid in Ship model.")
        else:
            return None

    def get_by_id_mt(self, id_mt: int):
        res = self.filter(id_mt=id_mt)
        if len(res) == 1:
            return res[0]
        elif len(res) > 1:
            # TODO register core exception
            raise Exception("DB broke. Double id_me in Ship model.")
        else:
            return None

    @staticmethod
    def get_ships_on_map(lat: float, lon: float, zoom: int):
        mlat = 1
        mlon = 1
        if zoom == 6:
            mlat = 14
            mlon = 40
        elif zoom == 6:
            mlat = 7
            mlon = 20
        elif zoom == 7:
            mlat = 3.5
            mlon = 10
        elif zoom == 8:
            mlat = 2
            mlon = 5
        elif zoom == 9:
            mlat = 1
            mlon = 2.5
        elif zoom == 10:
            mlat = 0.5
            mlon = 1.5


        return ModelShips.objects.filter(lat__gte=lat-mlat, lat__lte=lat+mlat, lon__gte=lon-mlon, lon__lte=lon+mlon)
         # self.all()


class ModelShips(models.Model):
    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(default=lib_uuid.uuid4, editable=False)
    id_mt = models.IntegerField(null=False)

    name = models.CharField(max_length=250, blank=False, null=False)
    type = models.IntegerField(null=False)
    flag = models.CharField(max_length=2, blank=False, null=False)

    lat = models.FloatField(null=True)
    lon = models.FloatField(null=True)

    course = models.IntegerField(null=True)
    heading = models.IntegerField(null=True)
    speed = models.IntegerField(null=True)

    moment = models.DateTimeField(null=True)

    # Registration change
    moment_create = models.DateTimeField(auto_now_add=True, null=True)
    moment_update = models.DateTimeField(auto_now=True, null=True)
    # moment_sync = models.DateTimeField(null=True)
    # ---------------------------------------------------------------------
    objects = ManagerShips()

    def update_cur_location(self, lat, lon, **kwargs):
        self.lat = lat
        self.lon = lon
        pass

    @staticmethod
    def create(entity):
        if entity.entry == None:
            if entity.id_mt != None:
                new_ship = ModelShips()
                new_ship.id_mt = entity.id_mt
                new_ship.name = entity.name
                new_ship.type = entity.type
                new_ship.save()

                return new_ship
            else:
               raise Exception("Ship entity does not contain ")
        else:
            # TODO Registration incorrect call of method
            return entity.entry

    @staticmethod
    def add(uuid: (lib_uuid, str) = None, description: str = None, **kwargs):
        pass
        # new_location = Locations()
        #
        # if uuid is not None:
        #     if isinstance(uuid, lib_uuid.UUID):
        #         new_location.uuid = uuid
        #     else:
        #         new_location.uuid = lib_uuid.UUID('{' + str(uuid) + '}')
        #
        # new_location.description = description
        # new_location.save()
        #
        # return new_location

    def update_cur(self):
        ModelShips.update(ship=self)

    def update_location(self, ship_obj):
        self.lat = ship_obj.characteristics_in_space.lat
        self.lon = ship_obj.characteristics_in_space.lon
        self.course = ship_obj.characteristics_in_space.course
        self.heading = ship_obj.characteristics_in_space.heading
        self.speed = ship_obj.characteristics_in_space.speed
        self.save()

    @staticmethod
    def update(
            ship: (object, str, lib_uuid),
    ):
        isinstance(ship, ModelShips)
        # ModelShips().objects.get_by_id_mt()

        pass
