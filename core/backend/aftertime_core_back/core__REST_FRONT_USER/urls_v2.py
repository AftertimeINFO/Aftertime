from rest_framework.routers import DefaultRouter, SimpleRouter
from core__REST_FRONT_USER.apiREST import ShipsViewSet

router = SimpleRouter()

router.register("ships", ShipsViewSet)


urlpatterns = router.urls