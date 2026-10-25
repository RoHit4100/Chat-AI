import os
import re
from pathlib import Path
from django.conf import settings
from rest_framework.exceptions import ValidationError

# Limits from settings / env
MAX_FILE_SIZE_BYTES = getattr(settings, "MAX_FILE_SIZE_BYTES", 25 * 1024 * 1024)
MAX_REQUEST_SIZE_BYTES = getattr(settings, "MAX_REQUEST_SIZE_BYTES", 100 * 1024 * 1024)
MAX_ZIP_MEMBERS = getattr(settings, "MAX_ZIP_MEMBERS", 100)
MAX_ZIP_UNCOMPRESSED_SIZE = getattr(settings, "MAX_ZIP_UNCOMPRESSED_SIZE", 50 * 1024 * 1024)

# Prohibited archive extensions inside ZIP archives
NESTED_ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz", ".tgz"}

# Allowed extensions and their acceptable MIME types
ALLOWED_EXTENSIONS = {
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
    },
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
    },
    ".csv": {"text/csv", "text/plain", "application/csv"},
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
    },
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".gif": {"image/gif"},
    ".webp": {"image/webp"},
    ".bmp": {"image/bmp", "image/x-ms-bmp"},
    ".svg": {"image/svg+xml", "text/xml", "text/plain", "application/xml"},
    ".txt": {"text/plain"},
    ".md": {"text/plain", "text/markdown"},
    ".py": {"text/plain", "text/x-python", "text/x-script.python"},
    ".js": {"text/plain", "application/javascript", "text/javascript"},
    ".jsx": {"text/plain", "application/javascript", "text/javascript"},
    ".ts": {"text/plain", "application/typescript", "video/mp2t"},
    ".tsx": {"text/plain", "application/typescript"},
    ".html": {"text/html", "text/plain"},
    ".css": {"text/css", "text/plain"},
    ".json": {"application/json", "text/plain"},
    ".zip": {"application/zip", "application/x-zip-compressed", "application/x-zip", "application/octet-stream"},
    ".yaml": {"text/plain", "text/yaml", "application/x-yaml"},
    ".yml": {"text/plain", "text/yaml", "application/x-yaml"},
    ".sh": {"text/plain", "text/x-shellscript"},
    ".sql": {"text/plain", "application/sql", "text/x-sql"},
}

def detect_mime(header_bytes: bytes) -> str:
    """Detect MIME type from initial file header bytes using python-magic."""
    try:
        import magic
        mime = magic.from_buffer(header_bytes, mime=True)
        return mime or "application/octet-stream"
    except Exception:
        return "application/octet-stream"

def sanitize_filename(filename: str) -> str:
    """Sanitize filename by removing directory traversal, quotes, and control characters."""
    if not filename:
        return "unnamed_file"
    # Take basename only
    clean = os.path.basename(filename)
    # Strip dangerous characters
    clean = re.sub(r'[\r\n\t"\';\\/\0]', "", clean).strip()
    return clean or "unnamed_file"

def validate_uploaded_file(file_obj, filename: str) -> tuple[str, str]:
    """Validate extension, size, and real MIME type. Returns (ext, mime)."""
    safe_name = sanitize_filename(filename)
    ext = Path(safe_name).suffix.lower()

    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"File extension '{ext}' is not permitted.")

    # Validate file size
    size = getattr(file_obj, "size", None)
    if size is None:
        pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
        file_obj.seek(0, os.SEEK_END)
        size = file_obj.tell()
        file_obj.seek(pos)

    if size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(f"File size ({size} bytes) exceeds limit of {MAX_FILE_SIZE_BYTES} bytes.")

    # Read header bytes to detect real MIME type
    pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
    file_obj.seek(0)
    header = file_obj.read(4096)
    file_obj.seek(pos)

    detected_mime = detect_mime(header)
    allowed_mimes = ALLOWED_EXTENSIONS[ext]

    # Check MIME match
    if detected_mime not in allowed_mimes and "text/plain" not in allowed_mimes:
        raise ValidationError(f"MIME type '{detected_mime}' does not match expected extension '{ext}'.")

    return ext, detected_mime

def validate_zip_safety(zip_file) -> None:
    """Ensure zip archive conforms to member count, size, and security constraints."""
    infolist = zip_file.infolist()

    # Cap member count
    if len(infolist) > MAX_ZIP_MEMBERS:
        raise ValidationError(f"ZIP file exceeds maximum limit of {MAX_ZIP_MEMBERS} members.")

    # Cap total uncompressed size to prevent zip bombs
    total_uncompressed = sum(info.file_size for info in infolist)
    if total_uncompressed > MAX_ZIP_UNCOMPRESSED_SIZE:
        raise ValidationError(f"ZIP uncompressed size ({total_uncompressed} bytes) exceeds limit of {MAX_ZIP_UNCOMPRESSED_SIZE} bytes.")

    for info in infolist:
        member_name = info.filename
        # Reject absolute paths and drive letters
        if member_name.startswith("/") or member_name.startswith("\\") or re.match(r"^[a-zA-Z]:", member_name):
            raise ValidationError(f"ZIP contains illegal absolute path: {member_name}")

        # Reject directory traversal
        norm = os.path.normpath(member_name)
        if norm.startswith("..") or "/../" in member_name or "\\..\\" in member_name:
            raise ValidationError(f"ZIP contains directory traversal path: {member_name}")

        # Reject nested archives
        ext = Path(member_name).suffix.lower()
        if ext in NESTED_ARCHIVE_EXTENSIONS:
            raise ValidationError(f"ZIP contains forbidden nested archive: {member_name}")

def is_dangerous_inline_file(mime: str, filename: str) -> bool:
    """Check if file must never be rendered inline in a browser (e.g. HTML, SVG)."""
    mime_lower = (mime or "").lower()
    ext_lower = Path(filename or "").suffix.lower()
    return (
        "html" in mime_lower
        or "svg" in mime_lower
        or ext_lower in (".html", ".htm", ".svg", ".xhtml")
    )
