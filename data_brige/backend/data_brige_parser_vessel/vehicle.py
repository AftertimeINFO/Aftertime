import json
from datetime import datetime, timedelta
class Vehicle:
    __slots__ = (
        'id_mt', #
        'vehicle_name', # Vehicle name
        'vehicle_type', # Vehicle type
        'vehicle_flag',  # Vehicle flag
        'position_lat', # Latitude of vehicle position
        'position_lon', # Longitude of vehicle position
        'position_course', # Course of vehicle
        'position_heading', # Heading of vehicle
        'position_speed', # Speed of vehicle
        'sync_reverse_stamp',
        'sync_moment' # Synchronization moment
    )

    def __init__(self,
                 sync_elapsed: int,
                 load_moment: datetime,
                 id: str,
                 name: str,
                 type: int,
                 flag: str,
                 lat: int,
                 lon: int,
                 course: int,
                 heading: int = None,
                 speed: int = None
                 ):
        self.id_mt = id
        self.vehicle_name = name
        self.vehicle_type = type
        self.vehicle_flag = flag
        self.position_lat = lat
        self.position_lon = lon
        self.position_course = course
        self.position_heading = heading
        self.position_speed = speed
        self.sync_reverse_stamp = sync_elapsed
        self.sync_moment = (load_moment - timedelta(minutes=int(sync_elapsed))).replace(second=0)

    def get_json(self):
        serizlized = {
            'id_mt': self.id_mt,
            'vehicle_name': self.vehicle_name,
            'vehicle_type': self.vehicle_type,
            'vehicle_flag': self.vehicle_flag,
            'position_lat': self.position_lat,
            'position_lon': self.position_lon,
            'position_course': self.position_course,
            'position_heading': self.position_heading,
            'position_speed': self.position_speed,
            'sync_reverse_stamp': int(self.sync_reverse_stamp),
            'sync_moment': str(self.sync_moment)
        }
        return json.dumps(serizlized)
