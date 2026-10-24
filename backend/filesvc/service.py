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

# Global service instance
file_service = FileService()
