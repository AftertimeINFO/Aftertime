import json
from core.structures.properties.characteristics_in_space import CharacteristicsInSpace

from core.models.vehicles.modelships import ModelShips
from core.models.vehicles.modelships import ManagerShips
from core.models.vehicles.modelShipLocation import ModelShipLocation
from core.models.vehicles.modelShipLocation import ManagerShipLocation
from core.structures.properties.locations import EarthPlace

from datetime import datetime as lib_datetime, timezone as lib_timezone


class Ship:
    __slots__ = (
        "entry",
        "entry_characteristic_in_space",
        "uuid",
        "id_mt",
        "name",
        "type",
        "country",
        "place",  # properties.location
        "characteristics_in_space",
        "moment",
        "changed",
        "changed_characteristics_in_space"
    )

    def __del__(self):
        del self.characteristics_in_space
        del self.entry
        del self.entry_characteristic_in_space
        pass

    def __init__(self, **kwargs):
        self.entry = None
        self.entry_characteristic_in_space = None

        self.uuid = None
        self.id_mt = None
        self.name = None

        self.type = None
        self.country = None

        self.place = None
        self.characteristics_in_space = None
        self.moment = None
        self.changed = None
        self.changed_characteristics_in_space = None

    def create(self):
        pass

    def capture_entry(self):
        if self.uuid is not None:
            self.entry = ModelShips.objects.get_by_uuid(uuid=self.uuid)
        elif self.id_mt is not None:
            self.entry = ModelShips.objects.get_by_id_mt(id_mt=self.id_mt)
        else:
            raise Exception("No any identification in input data.")

    def capture_entry_characteristic_in_space(self):
        if self.entry is not None:
            self.entry_characteristic_in_space = ModelShipLocation.objects.get_on_approx_moment(
                moment=self.moment,
                ship_entry=self.entry)

    def __update_entry(self, entry):
        self.entry = entry
        # self.capture_entry_characteristic_in_space()

    def __update_entry_characteristic_in_space(self, entry_characteristic_in_space):
        self.entry_characteristic_in_space = entry_characteristic_in_space
        pass

    def get_json(self):
        if self.characteristics_in_space is not None:
            structure = json.loads(self.characteristics_in_space.get_json())
        else:
            structure = {
                "lat": None,
                "lon": None,
                "speed": None,
                "heading": None,
                "course": None
            }

        structure["uuid"] = self.uuid
        structure["id_mt"] = self.id_mt
        structure["name"] = self.name
        structure["place"] = self.place
        structure["type"] = self.type
        structure["moment"] = self.moment.strftime('%Y-%m-%d %H:%M:%S')

        return json.dumps(structure)

    def __fill(self):
        self.capture_entry()

        if self.entry is not None:
            self.uuid = self.entry.uuid
            self.id_mt = self.id_mt
            self.name = self.entry.name
            # self.country = self.entry.country
            self.type = self.entry.type
            self.changed = False

            self.capture_entry_characteristic_in_space()

            if self.entry_characteristic_in_space is not None:
                self.moment = self.entry_characteristic_in_space.moment
                self.update_characteristics_in_space(
                    lat=self.entry_characteristic_in_space.lat,
                    lon=self.entry_characteristic_in_space.lon,
                    heading=self.entry_characteristic_in_space.heading,
                    speed=self.entry_characteristic_in_space.speed,
                    course=self.entry_characteristic_in_space.speed,
                    moment=self.entry_characteristic_in_space.moment,
                    salent=True
                )
                self.changed_characteristics_in_space = False
            else:
                self.changed_characteristics_in_space = None

        else:
            self.changed = None
            self.changed_characteristics_in_space = None

    def set_properties(self,
                       uuid: str = None,
                       id_mt: int = None,
                       vehicle_name: str = None,
                       vehicle_type: (str, int) = None,
                       vehicle_flag: str = None,
                       position_lat: (str, float) = None,
                       position_lon: (str, float) = None,
                       position_course: (str, int) = None,
                       position_heading: (str, int) = None,
                       position_speed: (str, int) = None,
                       sync_moment: str = None,
                       **kwargs):
        # -------------------------------------------------
        id_mt = int(id_mt) if isinstance(id_mt, type("str")) or isinstance(id_mt, type("int")) else None
        vehicle_type = int(vehicle_type) if isinstance(vehicle_type, type("str")) or isinstance(vehicle_type, type("int")) else None

        if sync_moment is not None:
            if sync_moment.find(".") != -1:
                moment = lib_datetime.strptime(sync_moment[0:sync_moment.find(".")], '%Y-%m-%d %H:%M:%S').replace(
                    tzinfo=lib_timezone.utc)
            else:
                moment = lib_datetime.strptime(sync_moment, '%Y-%m-%d %H:%M:%S').replace(tzinfo=lib_timezone.utc)
        else:
            moment = None
        # -------------------------------------------------
        if uuid is not None and self.uuid is None:
            self.uuid = uuid
        if id_mt is not None and self.id_mt is None:
            self.id_mt = id_mt

        if self.uuid is not None or self.id_mt is not None:
            self.__fill()

        if self.id_mt != id_mt:
            self.changed = True

        # TODO append update field
        if moment is not None:
            self.moment = moment

        if vehicle_name is not None:
            if self.name != vehicle_name:
                self.changed = True
            self.name = vehicle_name

        if vehicle_type is not None:
            if self.type != vehicle_type:
                self.changed = True
            self.type = vehicle_type

        # if self.country != vehicle_flag:
        #     self.changed = True
        self.country = vehicle_flag

        self.changed_characteristics_in_space = self.update_characteristics_in_space(
            lat=position_lat,
            lon=position_lon,
            course=position_course,
            heading=position_heading,
            speed=position_speed,
            moment=self.moment
        )

    def update_characteristics_in_space(
            self,
            lat,
            lon,
            course,
            heading,
            speed,
            moment,
            **kwargs):

        if (lat is not None
                and lon is not None
                and course is not None
                and heading is not None
                and speed is not None
                and moment is not None):

            lat = float(lat)
            lon = float(lon)
            course = int(course)
            heading = int(heading)
            speed = int(speed)

            if ((self.characteristics_in_space is None) or
                    (self.characteristics_in_space.lat != lat or
                     self.characteristics_in_space.lon != lon or
                     self.characteristics_in_space.course != course or
                     self.characteristics_in_space.heading != heading or
                     self.characteristics_in_space.speed != speed or
                     self.characteristics_in_space.moment != moment)
                ):
                self.characteristics_in_space = CharacteristicsInSpace(
                    lat=lat,
                    lon=lon,
                    course=course,
                    heading=heading,
                    speed=speed,
                    moment=moment
                )
                if self.characteristics_in_space is None:
                    return False
                else:
                    return True
            else:
                return False
        else:
            return False

    @staticmethod
    def get_entry(uuid_ship: str):
        ModelShipLocation.objects.get_by_uuid_ship(uuid=uuid_ship)

    @staticmethod
    def get_from_json(json_data: (str, dict)):
        if isinstance(json_data, dict):
            json_parse = json_data
        else:
            json_parse = json.loads(json_data)

        new_ship = Ship()
        new_ship.set_properties(**json_parse)

        return new_ship

    @staticmethod
    def get_entity(uuid: str):
        return ManagerShips.get_by_uuid(uuid)

    @staticmethod
    def get_by_uuid(uuid: str):
        ship = Ship()
        ship.set_properties(uuid=uuid)
        return ship

    @staticmethod
    def get_ships_on_region_entryes(lat, lon, square_radius):
        return ModelShipLocation.objects.get_ships_on_region_entries(lat, lon, square_radius)

    @staticmethod
    def get_by_id_mt(id_mt: str):
        ship = Ship()
        ship.set_properties(id_mt=id_mt)
        return ship

    def renew_general(self):
        if self.changed:
            if self.entry is None:
                new_ship = ModelShips.create(self)
                self.__update_entry(new_ship)
            else:
                self.__update_entry(self.entry)
            self.uuid = self.entry.uuid

    def renew_space_characteristics(self):
        if self.entry is not None:
            if self.changed_characteristics_in_space:
                if ModelShipLocation.objects.check_needs_update(self):
                    new_ship_location = ModelShipLocation.create(self)
                    self.entry.update_location(self)
                    self.__update_entry_characteristic_in_space(new_ship_location)
        else:
            # TODO Make log error: The call should not occur
            pass
        pass
