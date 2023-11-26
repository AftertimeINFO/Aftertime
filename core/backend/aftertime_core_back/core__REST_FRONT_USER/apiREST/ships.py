from core.models.vehicles import ModelShips
from rest_framework import authentication, permissions, serializers, viewsets
from rest_framework.permissions import AllowAny


class ShipsSerializer(serializers.ModelSerializer):
    model = ModelShips

    class Meta:
        model = ModelShips
        fields = ("id", "name")


class ShipsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ModelShips.objects.all()
    serializer_class = ShipsSerializer
    search_fields = ["name"]
    permission_classes = [AllowAny, ]