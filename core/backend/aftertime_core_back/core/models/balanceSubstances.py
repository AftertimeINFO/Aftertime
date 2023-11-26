import uuid as lib_uuid
import datetime
import decimal

from .directRequest import direct_request
from django.db import models
from django.db.models import signals
from django.db.models import Avg, Count, Min, Sum, F
from django.dispatch import receiver
from .substances import *
from .locations import *


class BalanceSubstancesManager(models.Manager):
    def get_all(self):
        return self.all()

    def get_balances_by_substances(self):
        return (self.all()
                .values(
                        uuid_substance=F('substance'),
                        sub_descr=F('substance__description'))
                .annotate(sum_count=Sum('count')))

    def substance_residues(self, **kwargs):
        sql = """
            select 
                all_balance.uuid_substances,
                core_substances.name as substance_name,
                core_substances.description as substance_description,
                all_balance.start_sum as amount_start,
                all_balance.end_sum as amount_end,
                all_balance.difference as amount_difference
                from (select 
                    start_balance.uuid_substances, 
                    start_balance.sum as start_sum, 
                    end_balance.sum as end_sum,
                    end_balance.sum - start_balance.sum  as difference 
                from (
                    select 
                        uuid_substances, 
                        SUM(count) 
                    from core_balancesubstances  
                    where moment <= %(start_moment)s  
                    GROUP BY uuid_substances
                    ) as start_balance
                LEFT JOIN (
                    select 
                        uuid_substances, 
                        SUM(count) 
                    from core_balancesubstances 
                    where moment <= %(end_moment)s
                    GROUP BY uuid_substances
                    ) as end_balance
                on start_balance.uuid_substances = end_balance.uuid_substances) as all_balance
            LEFT JOIN core_substances
            ON core_substances.uuid = all_balance.uuid_substances
        """

        cur_date = datetime.datetime.now()

        start_moment = cur_date.date().replace(month=1, day=1)
        end_moment = start_moment.replace(year=start_moment.year + 1)

        parameters = {
            'start_moment': start_moment,
            'end_moment': end_moment
        }

        result = direct_request(sql, parameters)

        for row in result:
            row['amount_difference_per_sec'] = round(row['amount_difference']/365/24/60/60)
            cur_moment = datetime.datetime.now()
            row['current_moment'] = cur_moment
            start_moment = cur_moment.replace(month=1,day=1,hour=0,minute=0,second=0,microsecond=0)
            dif_moment = cur_moment - start_moment
            dif_seconds = round(dif_moment.total_seconds())
            row['amount_current'] = row['amount_start'] + row['amount_difference_per_sec']*dif_seconds

        return result


class BalanceSubstances(models.Model):
    uuid = models.UUIDField(default=lib_uuid.uuid4, editable=False, primary_key=True)
    # id_location = models.IntegerField(null=False)
    moment = models.DateField(null=True)
    substance = models.ForeignKey(Substances, verbose_name='uuid_substances', db_column='uuid_substances', to_field='uuid', on_delete=models.CASCADE)
    location = models.ForeignKey(Locations, verbose_name='uuid_locations', db_column='uuid_locations', to_field='uuid', on_delete=models.CASCADE)

    count = models.BigIntegerField()

    # Registration change
    moment_create = models.DateTimeField(auto_now_add=True, null=True)
    moment_update = models.DateTimeField(auto_now=True, null=True)
    # moment_sync = models.DateTimeField(null=True)
    # ---------------------------------------------------------------------
    objects = BalanceSubstancesManager()

    @staticmethod
    def add(
            substance: (Substances, str, lib_uuid),
            location: (Locations, str, lib_uuid),
            count: int,
            uuid: (lib_uuid, str) = None,
            **kwargs):
        new_element = BalanceSubstances()

        if uuid is not None:
            if isinstance(uuid, lib_uuid.UUID):
                new_element.uuid = uuid
            else:
                new_element.uuid = lib_uuid.UUID(str(uuid))

        if isinstance(substance, str):
            new_element.substance = Substances.objects.get_by_uuid(substance)
        elif isinstance(substance, Substances):
            new_element.substance = substance

        if isinstance(location, str):
            new_element.location = Locations.objects.get_by_uuid(location)
        elif isinstance(location, Locations):
            new_element.location = location

        new_element.count = count

        new_element.save()

        return new_element
