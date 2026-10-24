import json
import os
import uuid
from pathlib import Path
from django.conf import settings

class LocalStorage:
    """Storage wrapper saving files to local volume using random UUIDs."""

    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir or settings.MEDIA_ROOT).resolve()
        self.raw_dir = self.base_dir / "uploads"
        self.parsed_dir = self.base_dir / "parsed"
        self.generated_dir = self.base_dir / "generated"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.parsed_dir.mkdir(parents=True, exist_ok=True)
        self.generated_dir.mkdir(parents=True, exist_ok=True)

    def save_raw(self, file_obj, extension: str = "") -> tuple[str, int]:
        """Save raw uploaded stream to disk with a random UUID filename. Returns (filepath, size)."""
        clean_ext = f".{extension.lstrip('.')}" if extension else ""
        random_name = f"{uuid.uuid4().hex}{clean_ext}"
        destination = self.raw_dir / random_name

        total_bytes = 0
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)

        with open(destination, "wb") as f:
            if hasattr(file_obj, "chunks"):
                for chunk in file_obj.chunks():
                    f.write(chunk)
                    total_bytes += len(chunk)
            elif hasattr(file_obj, "read"):
                while True:
                    chunk = file_obj.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    total_bytes += len(chunk)
            elif isinstance(file_obj, (bytes, bytearray)):
                f.write(file_obj)
                total_bytes = len(file_obj)
            else:
                raise ValueError("Unsupported file object type for saving.")

        return str(destination.resolve()), total_bytes

    def save_parsed(self, file_id: str, data: dict) -> str:
        """Write parsed text and metadata JSON for an uploaded file."""
        filename = f"{file_id}.json"
        destination = self.parsed_dir / filename
        with open(destination, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return str(destination.resolve())

    def get_generated_path(self, filename: str) -> str:
        """Create a randomized safe path within generated_dir."""
        random_prefix = uuid.uuid4().hex
        ext = Path(filename).suffix.lower()
        destination = self.generated_dir / f"{random_prefix}{ext}"
        return str(destination.resolve())

    def read_parsed(self, parsed_path: str) -> dict:
        """Read and return parsed JSON data from disk."""
        if not parsed_path or not os.path.exists(parsed_path):
            return {}
        with open(parsed_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def read_bytes(self, path: str) -> bytes:
        """Read raw binary contents from file path."""
        with open(path, "rb") as f:
            return f.read()

    def delete(self, path: str) -> bool:
        """Delete file safely if it exists."""
        try:
            if path and os.path.exists(path):
                os.remove(path)
                return True
        except Exception:
            pass
        return False

# Global storage instance
storage = LocalStorage()
