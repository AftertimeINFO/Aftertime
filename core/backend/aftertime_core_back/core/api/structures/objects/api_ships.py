import time

from core.models.vehicles import modelships
from core.structures.objects import obj_ship

import time as lib_time


def update_by_json(data: (str, dict)):
    ship = obj_ship.Ship.get_from_json(data)
    ship.renew_general()
    ship.renew_space_characteristics()

    return ship


def get_ship_position_json(id_mt: str = None, uuid_ship: str = None):
    if id_mt is not None:
        ship = obj_ship.Ship.get_by_id_mt(id_mt=id_mt)
    else:
        ship = obj_ship.Ship.get_by_uuid(uuid=uuid_ship)

    return ship.get_json()


def get_ships_on_region_entryes(lat, lon, square_radius):
    obj_ship.Ship.get_ships_on_region_entryes(lat, lon, square_radius)
    pass


