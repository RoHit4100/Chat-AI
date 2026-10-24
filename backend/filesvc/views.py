import os
from urllib.parse import quote
from django.db import connection
from django.http import FileResponse
from rest_framework import permissions, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from chat.models import Thread, UploadedFile
from chat.serializers import UploadedFileSerializer
from filesvc.service import file_service
from filesvc.storage import storage
from filesvc.throttles import UploadRateThrottle
from filesvc.validators import (
    MAX_REQUEST_SIZE_BYTES,
    MAX_FILE_SIZE_BYTES,
    validate_uploaded_file,
    sanitize_filename,
    is_dangerous_inline_file,
)

class ThreadFilesView(APIView):
    """List or upload files associated with a specific thread."""
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UploadRateThrottle]

    def get(self, request, thread_id):
        """List all uploaded files belonging to the thread (verifying ownership)."""
        thread = Thread.objects.filter(id=thread_id, user=request.user).first()
        if not thread:
            return Response({"detail": "Thread not found."}, status=status.HTTP_404_NOT_FOUND)

        files = thread.uploaded_files.all()
        return Response(UploadedFileSerializer(files, many=True).data)

    def post(self, request, thread_id):
        """Upload one or many files to a thread, validating limits and running threadpool parsers."""
        thread = Thread.objects.filter(id=thread_id, user=request.user).first()
        if not thread:
            return Response({"detail": "Thread not found."}, status=status.HTTP_404_NOT_FOUND)

        files = request.FILES.getlist("files") or list(request.FILES.values())
        if not files:
            return Response({"detail": "No files provided for upload."}, status=status.HTTP_400_BAD_REQUEST)

        # Enforce total request size limit
        total_request_size = sum(f.size for f in files)
        if total_request_size > MAX_REQUEST_SIZE_BYTES:
            return Response(
                {"detail": f"Total request size ({total_request_size} bytes) exceeds limit of {MAX_REQUEST_SIZE_BYTES} bytes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        uploaded_records = []
        for file_obj in files:
            clean_name = sanitize_filename(file_obj.name)

            # Validate extension, file size, and real MIME
            try:
                ext, detected_mime = validate_uploaded_file(file_obj, clean_name)
                # Save raw file using random UUID filename
                saved_path, written_size = storage.save_raw(file_obj, ext)

                uf = UploadedFile.objects.create(
                    thread=thread,
                    name=clean_name,
                    mime=detected_mime,
                    size=written_size,
                    path=saved_path,
                    status="pending",
                )

                # Parse in threadpool executor so event loop is not blocked (or directly under SQLite tests)
                if connection.vendor == "sqlite":
                    uf = file_service.parse_file_sync(uf.id)
                else:
                    future = file_service.parse_in_threadpool(uf.id)
                    try:
                        uf = future.result(timeout=30)
                    except Exception as exc:
                        uf.status = "failed"
                        uf.error = f"Parsing timed out or failed: {str(exc)}"
                        uf.save(update_fields=["status", "error"])

            except Exception as exc:
                error_msg = str(getattr(exc, "detail", exc))
                if isinstance(error_msg, list):
                    error_msg = error_msg[0]
                uf = UploadedFile.objects.create(
                    thread=thread,
                    name=clean_name,
                    mime="application/octet-stream",
                    size=getattr(file_obj, "size", 0),
                    path="",
                    status="failed",
                    error=str(error_msg),
                )

            uploaded_records.append(uf)

        return Response(UploadedFileSerializer(uploaded_records, many=True).data, status=status.HTTP_201_CREATED)

class FileDownloadView(APIView):
    """Authenticated endpoint to download uploaded files with security headers."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, file_id):
        """Download file verifying ownership, setting nosniff, and preventing inline HTML/SVG execution."""
        uf = UploadedFile.objects.filter(id=file_id).select_related("thread").first()
        if not uf or uf.thread.user_id != request.user.id:
            return Response({"detail": "File not found."}, status=status.HTTP_404_NOT_FOUND)

        if not uf.path or not os.path.exists(uf.path):
            return Response({"detail": "File data not found on disk."}, status=status.HTTP_404_NOT_FOUND)

        safe_name = sanitize_filename(uf.name)

        # Never render HTML/SVG inline in the browser to prevent XSS
        if is_dangerous_inline_file(uf.mime, uf.name):
            content_type = "application/octet-stream"
        else:
            content_type = uf.mime or "application/octet-stream"

        file_handle = open(uf.path, "rb")
        response = FileResponse(file_handle, content_type=content_type, as_attachment=True, filename=safe_name)
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{quote(safe_name)}'
        return response

class GeneratedFileDownloadView(APIView):
    """Authenticated endpoint to download generated files with security headers."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, file_id):
        """Download generated file verifying ownership, setting nosniff, and preventing inline execution."""
        from chat.models import GeneratedFile
        from filesvc.validators import detect_mime

        gf = GeneratedFile.objects.filter(id=file_id).select_related("thread").first()
        if not gf or gf.thread.user_id != request.user.id:
            return Response({"detail": "Generated file not found."}, status=status.HTTP_404_NOT_FOUND)

        if not gf.path or not os.path.exists(gf.path):
            return Response({"detail": "File data not found on disk."}, status=status.HTTP_404_NOT_FOUND)

        safe_name = sanitize_filename(gf.name)
        with open(gf.path, "rb") as f:
            header = f.read(4096)
        mime = detect_mime(header)

        if is_dangerous_inline_file(mime, gf.name):
            content_type = "application/octet-stream"
        else:
            content_type = mime or "application/octet-stream"

        file_handle = open(gf.path, "rb")
        response = FileResponse(file_handle, content_type=content_type, as_attachment=True, filename=safe_name)
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{quote(safe_name)}'
        return response
