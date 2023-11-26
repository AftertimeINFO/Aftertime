class EarthPlace:
    __slots__=(
        "lat",
        "lon"
    )

    def __init__(self, lat: (str, float), lon: (str, float), **kwargs):
        self.lat = float(lat)
        self.lon = float(lon)
