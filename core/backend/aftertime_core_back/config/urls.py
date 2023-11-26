from django.contrib import admin
from django.urls import path, include

from rest_framework.authtoken.views import ObtainAuthToken

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v2/', include("core__REST_FRONT_USER.urls_v2")),
    path('api/v1/balance/', include('core__REST_FRONT_USER.urls')),
    path('api/v1/back/', include('core__REST_BACK.urls')),
    path("api-token-auth/", ObtainAuthToken.as_view()),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]