import uuid as lib_uuid

from django.db import models
from django.db.models import signals
from django.dispatch import receiver


class LocationsManager(models.Manager):

    def get_all(self):
        return self.all()

    def get_by_uuid(self, uuid: (lib_uuid, str)):
        res = self.filter(uuid=str(uuid))
        if len(res) == 1:
            return res[0]
        else:
            return None


class Locations(models.Model):
    uuid = models.UUIDField(default=lib_uuid.uuid4, editable=False, primary_key=True)
    # id_location = models.IntegerField(null=False)
    description = models.CharField(max_length=250, blank=False, null=False)

    # Registration change
    moment_create = models.DateTimeField(auto_now_add=True, null=True)
    moment_update = models.DateTimeField(auto_now=True, null=True)
    # moment_sync = models.DateTimeField(null=True)
    # ---------------------------------------------------------------------
    objects = LocationsManager()

    @staticmethod
    def add(uuid: (lib_uuid, str) = None, description: str = None, **kwargs):
        new_location = Locations()

        if uuid is not None:
            if isinstance(uuid, lib_uuid.UUID):
                new_location.uuid = uuid
            else:
                new_location.uuid = lib_uuid.UUID('{' + str(uuid) + '}')

        new_location.description = description
        new_location.save()

        return new_location

