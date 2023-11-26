import time

from rest_framework import status
from rest_framework.views import APIView
from rest_framework import generics, mixins, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework import authentication, permissions
from django.http import JsonResponse
# from .. import serializers
# ----------------------------


class Ping(APIView):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = (AllowAny,)

    def get(self, request, format=None):
        # content = {'message': 'Pong: Reflection LinkedIN'}
        # status_resp = status.HTTP_200_OK
        from pympler.classtracker import ClassTracker
        from pympler.classtracker_stats import HtmlStats

        ct = ClassTracker()
        ct.create_snapshot(description="start")
        time.sleep(60)
        ct.create_snapshot(description="end")
        ct.stats.dump_stats("pympler_stats.out")
        html_stats = HtmlStats(ct)
        html_stats.create_html("html_stats.html")
        # html_stats.tracked_classes
        ct.close()
        return Response("pong CORE__DEBUG__REST_BACK")


class PingJSON(APIView):
    authentication_classes = [authentication.TokenAuthentication]
    permission_classes = (AllowAny,)

    def get(self, request, format=None):
        content = [
            {
                'id': "2234234",
                # 'avatarUrl': _mock.image.avatar(index),
                'name': 'test name',
                'email': 'sdf@sdf.sd',
                # phoneNumber: _mock.phoneNumber(index),
                'address': '908 Jack Locks',
                'country': 'test country',
                'state': 'Virginia',
                'city': 'Rancho Cordova',
                'zipCode': '85807',
                'company': 'company',
                'isVerified': False,
                'status': 'active',
                'role': 'AAAA'
            }
        ]
        # status_resp = status.HTTP_200_OK

        # return Response(content, status=status.HTTP_200_OK)
        response = Response(content, status=status.HTTP_200_OK)

        # response = JsonResponse(content, safe=False, status=status.HTTP_200_OK)
        # response["Access-Control-Allow-Origin"] = "*"

        return response
