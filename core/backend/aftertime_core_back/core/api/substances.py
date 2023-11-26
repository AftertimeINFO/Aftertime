import uuid
from core.models import substances


def add(**kwargs):
    """

    :param kwargs:
        description: str
    :return:
    """
    return substances.Substances.add(**kwargs)


def get_by_uuid(**kwargs):
    return substances.Substances.objects.get_by_uuid(**kwargs)


def get_all():
    return substances.Substances.objects.get_all()
