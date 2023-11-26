import math
import uuid as lib_uuid
import datetime
import decimal

from django.db import models
from django.db.models import signals
from django.db.models import Avg, Count, Min, Sum, F
from django.dispatch import receiver

from .modelships import *

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.structures.objects.obj_ship import Ship as ObjShip


class ManagerShipLocation(models.Manager):
    @staticmethod
    def get_track(uuid_ship):
        ship = ModelShips.objects.get_by_uuid(uuid_ship)
        return ModelShipLocation.objects.filter(ship=ship)

    @staticmethod
    def get_track_by_mt(id_mt):
        ship = ModelShips.objects.get_by_id_mt(id_mt)
        return ModelShipLocation.objects.filter(ship=ship)

    def get_by_uuid_ship(self, uuid_ship: str):
        ship_entry = ModelShips.objects.get_by_uuid(uuid=uuid_ship)
        return self.filter(ship=ship_entry).prefetch_related('ship')

    def check_needs_update(self, origin_entity):
        last_entry = self.filter(ship=origin_entity.entry).order_by("-moment").first()

        if last_entry is not None:
            origin_ch = origin_entity.characteristics_in_space
            # origin_place = origin_ch.earth_place

            if (last_entry.lat == origin_ch.lat and
                last_entry.lon == origin_ch.lon and
                last_entry.heading == origin_ch.heading and
                last_entry.speed == origin_ch.speed and
                last_entry.course == origin_ch.course
            ):

                # We do not update data without change with time marker less than 5-minutes
                if (origin_entity.moment-last_entry.moment).total_seconds() > 5*60:
                    return True
                else:
                    return False
            else:
                # Greater than last position
                if (origin_entity.moment-last_entry.moment).total_seconds() > 0:
                    return True
                else:
                    # TODO Register log incident (try register data less then last position)
                    return False
        else:
            return True

    def get_all(self):
        return self.all()


    def get_ships_on_region_entries(self, lat, lon, square_radius):
        # self.all.all()
        # ship_entry = self.filter(lat__lte=round(lat+square_radius, 5)).values("ship")
        # return self.filter(ship=ship_entry).prefetch_related('ship')
        # return ship_entry
        return None

    def get_on_approx_moment(self,
                      moment = None,
                      ship_entry: object = None,
                      ship_id_mt: int = None,
                      ship_uuid: str = None,
                      **kwargs):

        if ship_entry is not None:
            if moment is not None:
                result_query = self.filter(ship=ship_entry, moment__lte=moment).order_by('-moment')[:1]
            else:
                result_query = self.filter(ship=ship_entry).order_by('-moment')[:1]

            if len(result_query) == 1:
                return result_query[0]
            else:
                return None

        elif ship_id_mt is not None:
            # TODO debt by code make variants to id_mt
            raise Exception("Debt by code.")
        elif ship_uuid is not None:
            # TODO debt by code make variants to id_mt
            raise Exception("Debt by code.")
        else:
            return None

    def get_on_moment(self,
                      moment,
                      ship_entry: object = None,
                      ship_id_mt: int = None,
                      ship_uuid: str = None,
                      **kwargs):

        if ship_entry is not None:
            result_query = self.filter(ship=ship_entry, moment=moment)
            result_query_size = len(result_query)
            if result_query_size == 1:
                return result_query[0]
            elif result_query_size == 0:
                return None
            else:
                # TODO make registration coruption of db
                raise Exception("Double of ship location.")

        elif ship_id_mt is not None:
            # TODO debt by code make variants to id_mt
            raise Exception("Debt by code.")
        elif ship_uuid is not None:
            # TODO debt by code make variants to id_mt
            raise Exception("Debt by code.")
        else:
            return None


class ModelShipLocation(models.Model):
    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(default=lib_uuid.uuid4, editable=False)
    # id_location = models.IntegerField(null=False)
    moment = models.DateTimeField(null=False)
    # ship = models.ForeignKey(ModelShips, verbose_name='uuid_ships', db_column='uuid_ships', to_field='uuid', on_delete=models.CASCADE)
    ship = models.ForeignKey(ModelShips, on_delete=models.CASCADE)

    type_location = models.IntegerField(null=False)
    lat = models.FloatField(null=True)
    lon = models.FloatField(null=True)

    course = models.IntegerField(null=True)
    heading = models.IntegerField(null=True)
    speed = models.IntegerField(null=True)

    # count = models.BigIntegerField()

    # Registration change
    # moment_create = models.DateTimeField(auto_now_add=True, null=True)
    # moment_update = models.DateTimeField(auto_now=True, null=True)
    # moment_sync = models.DateTimeField(null=True)
    # ---------------------------------------------------------------------
    objects = ManagerShipLocation()

    @staticmethod
    def create(entity: 'ObjShip'):
        ship_location = ModelShipLocation.objects.get_on_moment(
            id_mt=entity.id_mt,
            moment=entity.moment
        )

        if ship_location is None:
            new_ship_location = ModelShipLocation()
            new_ship_location.ship = entity.entry
            new_ship_location.moment = entity.moment
            new_ship_location.type_location = 1
            #TODO Append check characterisc in space mayby in other palace
            new_ship_location.lat = entity.characteristics_in_space.lat
            new_ship_location.lon = entity.characteristics_in_space.lon
            new_ship_location.course = entity.characteristics_in_space.course
            new_ship_location.heading = entity.characteristics_in_space.heading
            new_ship_location.speed = entity.characteristics_in_space.speed
            #TODO Debt code append all other properties
            new_ship_location.save()

            # region Update last ship location
            last_moment = ModelShipLocation.objects.get_on_approx_moment(ship_entry=entity.entry)
            if new_ship_location.moment == last_moment.moment:
                entity.entry.update_cur_location(lat=new_ship_location.lat, lon=new_ship_location.lon)
            # endregion

            return new_ship_location


        else:
            #TODO Make log event: Unexpected condition, code logic needs to be checked
            return ship_location

    @staticmethod
    def add():
        pass
        #     substance: (Substances, str, lib_uuid),
        #     location: (Locations, str, lib_uuid),
        #     count: int,
        #     uuid: (lib_uuid, str) = None,
        #     **kwargs):
        # new_element = BalanceSubstances()
        #
        # if uuid is not None:
        #     if isinstance(uuid, lib_uuid.UUID):
        #         new_element.uuid = uuid
        #     else:
        #         new_element.uuid = lib_uuid.UUID(str(uuid))
        #
        # if isinstance(substance, str):
        #     new_element.substance = Substances.objects.get_by_uuid(substance)
        # elif isinstance(substance, Substances):
        #     new_element.substance = substance
        #
        # if isinstance(location, str):
        #     new_element.location = Locations.objects.get_by_uuid(location)
        # elif isinstance(location, Locations):
        #     new_element.location = location
        #
        # new_element.count = count
        #
        # new_element.save()
        #
        # return new_element
