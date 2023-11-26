from rest_framework import serializers
from core import models
# from pullgerReflection.com_linkedin import models


# class BalanceSubstancesSerializer(serializers.ModelSerializer):
#
#     class Meta:
#         model = models.BalanceSubstances
#         fields = '__all__'

class BalanceSubstancesSerializerItem(serializers.Serializer):
    substance_name = serializers.CharField(max_length=250)
    substance_description = serializers.CharField(max_length=250)
    amount_start = serializers.CharField(max_length=250)
    amount_end = serializers.CharField(max_length=250)
    amount_current = serializers.CharField(max_length=250)
    amount_difference = serializers.CharField(max_length=250)
    amount_difference_per_sec = serializers.CharField(max_length=250)
    current_moment = serializers.DateTimeField()


class BalanceSubstancesSerializer(serializers.Serializer):
    items = BalanceSubstancesSerializerItem(many=True)
    # class Meta:
    #     model = models.BalanceSubstances
    #     fields = '__all__'

# class BalanceSubstancesSerializer(serializers.ModelSerializer):
#     sub_descr = serializers.CharField(max_length=250)
#
#     class Meta:
#         model = models.BalanceSubstances
#         fields = ('sub_descr')


# class CompaniesModifySerializer(serializers.ModelSerializer):
#
#     class Meta:
#         model = models.Companies
#         fields = '__all__'
