import os
import re
from django.core.exceptions import ValidationError

# Pattern for safe filename characters: alphanumeric, dashes, underscores, and dots
SAFE_FILENAME_REGEX = re.compile(r"^[\w,\s-]+\.[A-Za-z0-9]+$")

def validate_safe_filename(name: str):
    """Validate that filename contains no path traversal sequences or illegal characters."""
    if not name or not isinstance(name, str):
        raise ValidationError("File name must be a non-empty string.")
    clean_name = os.path.basename(name)
    if clean_name != name or ".." in name or "/" in name or "\\" in name:
        raise ValidationError("Invalid filename: path traversal sequences are not allowed.")
    if len(name) > 255:
        raise ValidationError("Filename exceeds maximum length of 255 characters.")
    return name
