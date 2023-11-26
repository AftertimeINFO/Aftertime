from core.models import locations


def add(**kwargs):
    """

    :param kwargs:
        description: str
    :return:
    """
    return locations.Locations.add(**kwargs)

class tt:
    pass

def get_by_uuid(**kwargs):
    return locations.Locations.objects.get_by_uuid(**kwargs)


def get_all():
    return locations.Locations.objects.get_all()
