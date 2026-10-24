from django.urls import path, re_path, include
from rest_framework.routers import DefaultRouter
from chat.views import MeView, ThreadViewSet

router = DefaultRouter()
router.register(r"threads", ThreadViewSet, basename="thread")

urlpatterns = [
    # Support both /api/me and /api/me/
    re_path(r"^me/?$", MeView.as_view(), name="me"),
    path("", include(router.urls)),
]
