from rest_framework import generics, mixins, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

# from pullgerReflection.com_linkedin import models
# from pullgerReflection.com_linkedin import api

# from pullgerInternalControl.pullgerReflection.REST.logging import logger

from .. import serializers
# from .general import CustomPaginator
from core.api import balance_substances


class BalanceListView(generics.GenericAPIView,
                   mixins.ListModelMixin,):

    # permission_classes = [IsAuthenticated]
    permission_classes = (AllowAny,)
    # pagination_class = CustomPaginator
    # queryset = balance_substances.get_all()


    def get(self, request, *args, **kwargs):
        # queryset = balance_substances.get_balances_by_substances()
        # queryset = balance_substances.get_balances_by_substances()
        queryset = balance_substances.substance_residues()
        serializer_class = serializers.BalanceSubstancesSerializerItem

        # try:
        #     returnResponse = self.list(request, *args, **kwargs)
        # except BaseException as e:
        #     pass

        self.serializer_class = serializer_class
        self.queryset = queryset

        # ser = serializer_class(queryset, many=True)
        # return Response(ser.data)

        # ser = serializer_class(queryset, many=True)
        return self.list(request, *args, **kwargs)
