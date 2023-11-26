import json

from rest_framework import generics, mixins, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.structures.objects import api_ships
from core.models.vehicles.modelships import ManagerShips
from core.models.vehicles.modelShipLocation import ModelShipLocation
from core.models.vehicles.modelShipLocation import ManagerShipLocation
from core__REST_BACK import serializers

import json as lib_json


class ShipPosition(APIView):
    permission_classes = (AllowAny,)
    http_method_names = ["get", "post"]

    # serializer_class
    # queryset

    def post(self, request):

        # tmp_data = json.loads(request.data)
        # print(tmp_data['vehicle_name'], tmp_data['sync_moment'], tmp_data['position_lat'])

        if isinstance(request.data, dict):
            new_ship = api_ships.update_by_json(request.data)
        else:
            new_ship = api_ships.update_by_json(request.data)

        content = {
            'message': None,
            'data': {
                'uuid': str(new_ship.uuid)
            }
        }

        return Response(content, status=status.HTTP_200_OK)

    def get(self, request, *args, **kwargs):
        if 'uuid_ship' in request.query_params:
            ship_position_json = api_ships.get_ship_position_json(uuid_ship=request.query_params['uuid_ship'])

        content = {
            'message': None,
            'data': ship_position_json
        }

        status_response = status.HTTP_200_OK

        return Response(content, status=status_response)


class ShipTrack(generics.GenericAPIView,
                mixins.ListModelMixin, ):
    # permission_classes = [IsAuthenticated]
    permission_classes = (AllowAny,)

    # pagination_class = CustomPaginator
    # queryset = balance_substances.get_all()

    def get(self, request, *args, **kwargs):
        if 'uuid_ship' in request.query_params:
            self.queryset = ManagerShipLocation.get_track(uuid_ship=request.query_params['uuid_ship'])
        elif 'id_mt' in request.query_params:
            self.queryset = ManagerShipLocation.get_track_by_mt(id_mt=request.query_params['id_mt'])

        self.serializer_class = serializers.ShipTrackItem

        return self.list(request, *args, **kwargs)

        # queryset = balance_substances.get_balances_by_substances()
        # queryset = balance_substances.get_balances_by_substances()
        # queryset = balance_substances.substance_residues()
        # serializer_class = serializers.BalanceSubstancesSerializerItem
        #
        # # try:
        # #     returnResponse = self.list(request, *args, **kwargs)
        # # except BaseException as e:
        # #     pass
        #
        # self.serializer_class = serializer_class
        # self.queryset = queryset
        #
        # # ser = serializer_class(queryset, many=True)
        # # return Response(ser.data)
        #
        # ser = serializer_class(queryset, many=True)
        # return self.list(request, *args, **kwargs)


class ShipsOnMap(generics.GenericAPIView,
                 mixins.ListModelMixin, ):
    # permission_classes = [IsAuthenticated]
    permission_classes = (AllowAny,)

    # pagination_class = CustomPaginator
    # queryset = balance_substances.get_all()

    def get(self, request, *args, **kwargs):
        if 'c_lat' in request.query_params and \
                'c_lon' in request.query_params and \
                'c_zoom' in request.query_params:
            self.queryset = ManagerShips.get_ships_on_map(
                lat=float(request.query_params['c_lat']),
                lon=float(request.query_params['c_lon']),
                zoom=int(request.query_params['c_zoom']))
            self.serializer_class = serializers.ShipsOnMapItem

            return self.list(request, *args, **kwargs)
        else:
            content = {'message': 'No required parameters'}
            status_resp = status.HTTP_400_BAD_REQUEST

            return Response(content, status=status_resp)

        # queryset = balance_substances.get_balances_by_substances()
        # queryset = balance_substances.get_balances_by_substances()
        # queryset = balance_substances.substance_residues()
        # serializer_class = serializers.BalanceSubstancesSerializerItem
        #
        # # try:
        # #     returnResponse = self.list(request, *args, **kwargs)
        # # except BaseException as e:
        # #     pass
        #
        # self.serializer_class = serializer_class
        # self.queryset = queryset
        #
        # # ser = serializer_class(queryset, many=True)
        # # return Response(ser.data)
        #
        # ser = serializer_class(queryset, many=True)
        # return self.list(request, *args, **kwargs)
