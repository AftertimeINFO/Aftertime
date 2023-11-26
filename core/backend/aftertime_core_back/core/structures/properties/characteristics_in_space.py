import json

from core.structures.properties.locations import EarthPlace


class CharacteristicsInSpace:

    __slots__ = (
        "earth_place",
        "course",
        "heading",
        "speed",
        "lat",
        "lon",
        "moment",
    )

    def __init__(self,
                 course,
                 heading,
                 speed,
                 moment,
                 lat: (str, float) = None,
                 lon: (str, float) = None,
                 earth_place: EarthPlace = None):
        self.earth_place = earth_place
        # ==================================================
        if course is not None:
            self.course = int(course)
        else:
            self.course = None
        # ==================================================
        if heading is not None:
            self.heading = int(heading)
        else:
            self.heading = None
        # ==================================================
        if speed is not None:
            self.speed = int(speed)
        else:
            self.speed = None
        # ==================================================
        self.lat = lat
        self.lon = lon
        self.moment = moment

    def get_json(self):
        structure = {
            "lat": self.lat,
            "lon": self.lon,
            "speed": self.speed,
            "heading": self.heading,
            "course": self.course,
            "moment": self.moment
        }

        return json.dumps(structure)
