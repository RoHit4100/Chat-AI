import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from chat.models import UploadedFile
from filesvc.storage import storage
from filesvc.parsers.registry import get_parser_for_file

logger = logging.getLogger(__name__)

class FileService:
    """Orchestrates file saving, background parsing, and manifest generation."""

    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="filesvc_parser")

    def parse_file_sync(self, file_id: int) -> UploadedFile:
        """Synchronously parse an uploaded file, write parsed data, and update DB status."""
        try:
            uploaded_file = UploadedFile.objects.get(id=file_id)
        except UploadedFile.DoesNotExist:
            logger.error("UploadedFile with id=%s not found.", file_id)
            return None

        try:
            parser = get_parser_for_file(uploaded_file.name, uploaded_file.mime)
            result = parser.parse(uploaded_file.path, uploaded_file.name)

            # Persist parsed content and metadata
            parsed_path = storage.save_parsed(str(uploaded_file.id), result.to_dict())

            uploaded_file.parsed_path = parsed_path
            uploaded_file.summary = result.summary
            uploaded_file.status = "ready"
            uploaded_file.error = ""
            uploaded_file.save(update_fields=["parsed_path", "summary", "status", "error"])
            logger.info("Successfully parsed file %s (%s)", uploaded_file.id, uploaded_file.name)
        except Exception as exc:
            logger.exception("Failed to parse file %s: %s", uploaded_file.id, exc)
            uploaded_file.status = "failed"
            uploaded_file.error = f"Parsing failed: {str(exc)}"
            uploaded_file.save(update_fields=["status", "error"])

        return uploaded_file

    def parse_in_threadpool(self, file_id: int):
        """Submit parsing task to the background threadpool so the main loop is not blocked."""
        return self.executor.submit(self.parse_file_sync, file_id)

    async def parse_file_async(self, file_id: int) -> UploadedFile:
        """Asynchronously run file parsing offloaded to a worker thread."""
        return await asyncio.to_thread(self.parse_file_sync, file_id)

    def cleanup_orphaned_uploads(self, older_than_hours: int = 24, dry_run: bool = False) -> dict:
        """Find and clean up uploaded files never attached to a message beyond the cutoff age."""
        import os
        from datetime import timedelta
        from django.utils import timezone

        cutoff = timezone.now() - timedelta(hours=older_than_hours)
        orphans = list(UploadedFile.objects.filter(message__isnull=True, created_at__lte=cutoff))

        count = 0
        bytes_freed = 0
        details = []

        for uf in orphans:
            file_size = uf.size or 0
            details.append({"id": uf.id, "name": uf.name, "size": file_size, "path": uf.path})
            if not dry_run:
                if uf.path and os.path.exists(uf.path):
                    try:
                        os.remove(uf.path)
                    except Exception as exc:
                        logger.warning("Failed to delete raw orphan file %s: %s", uf.path, exc)
                if uf.parsed_path and os.path.exists(uf.parsed_path):
                    try:
                        os.remove(uf.parsed_path)
                    except Exception as exc:
                        logger.warning("Failed to delete parsed orphan file %s: %s", uf.parsed_path, exc)
                uf.delete()
            count += 1
            bytes_freed += file_size

        logger.info(
            "Orphaned uploads cleanup (%s): %s files, %s bytes freed",
            "dry-run" if dry_run else "executed",
            count,
            bytes_freed,
        )
        return {"count": count, "bytes_freed": bytes_freed, "files": details, "dry_run": dry_run}

# Global service instance
file_service = FileService()

def cleanup_orphaned_uploads(older_than_hours: int = 24, dry_run: bool = False) -> dict:
    """Convenience module function for cleaning up orphaned uploads."""
    return file_service.cleanup_orphaned_uploads(older_than_hours=older_than_hours, dry_run=dry_run)

