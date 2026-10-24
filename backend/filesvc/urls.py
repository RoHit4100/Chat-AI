from django.urls import path
from filesvc.views import ThreadFilesView, FileDownloadView

urlpatterns = [
    path("threads/<uuid:thread_id>/files/", ThreadFilesView.as_view(), name="thread-files"),
    path("threads/<uuid:thread_id>/files", ThreadFilesView.as_view(), name="thread-files-noslash"),
    path("files/<str:file_id>/download/", FileDownloadView.as_view(), name="file-download"),
    path("files/<str:file_id>/download", FileDownloadView.as_view(), name="file-download-noslash"),
]
