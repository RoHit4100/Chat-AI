from django.urls import path, re_path, include
from rest_framework.routers import DefaultRouter
from chat.views import (
    MeView,
    ThreadViewSet,
    stream_thread_view,
    regenerate_thread_view,
)

router = DefaultRouter()
router.register(r"threads", ThreadViewSet, basename="thread")

urlpatterns = [
    re_path(r"^me/?$", MeView.as_view(), name="me"),
    path("threads/<uuid:id>/stream", stream_thread_view, name="thread-stream"),
    path("threads/<uuid:id>/stream/", stream_thread_view, name="thread-stream-slash"),
    path("threads/<uuid:id>/regenerate", regenerate_thread_view, name="thread-regenerate"),
    path("threads/<uuid:id>/regenerate/", regenerate_thread_view, name="thread-regenerate-slash"),
    path("", include(router.urls)),
]
