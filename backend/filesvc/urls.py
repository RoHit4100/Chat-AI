from django.urls import path
from filesvc.views import (
    ThreadFilesView,
    ThreadGeneratedFilesView,
    FileDownloadView,
    GeneratedFileDownloadView,
    GeneratedFilePreviewView,
)

urlpatterns = [
    path("threads/<uuid:thread_id>/files/", ThreadFilesView.as_view(), name="thread-files"),
    path("threads/<uuid:thread_id>/files", ThreadFilesView.as_view(), name="thread-files-noslash"),
    path("threads/<uuid:thread_id>/generated/", ThreadGeneratedFilesView.as_view(), name="thread-generated-files"),
    path("threads/<uuid:thread_id>/generated", ThreadGeneratedFilesView.as_view(), name="thread-generated-files-noslash"),
    path("files/<str:file_id>/download/", FileDownloadView.as_view(), name="file-download"),
    path("files/<str:file_id>/download", FileDownloadView.as_view(), name="file-download-noslash"),
    path("generated/<str:file_id>/download/", GeneratedFileDownloadView.as_view(), name="generated-download"),
    path("generated/<str:file_id>/download", GeneratedFileDownloadView.as_view(), name="generated-download-noslash"),
    path("generated/<str:file_id>/preview/", GeneratedFilePreviewView.as_view(), name="generated-preview"),
    path("generated/<str:file_id>/preview", GeneratedFilePreviewView.as_view(), name="generated-preview-noslash"),
]
