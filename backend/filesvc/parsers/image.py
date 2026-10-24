from PIL import Image
from filesvc.parsers.base import BaseParser, ParsedResult

class ImageParser(BaseParser):
    """Parser for images extracting dimensions and preparing vision model context."""

    def parse(self, file_path: str, original_filename: str) -> ParsedResult:
        with Image.open(file_path) as img:
            width, height = img.size
            fmt = img.format or "UNKNOWN"
            mode = img.mode

        image_info = {
            "width": width,
            "height": height,
            "format": fmt,
            "mode": mode,
            "file_path": file_path,
        }

        summary = f"Image '{original_filename}': {fmt} ({width}x{height} px, {mode})."
        text = (
            f"Image metadata:\n"
            f"File: {original_filename}\n"
            f"Format: {fmt}\n"
            f"Dimensions: {width} x {height} pixels\n"
            f"Color Mode: {mode}"
        )

        return ParsedResult(
            text=text,
            summary=summary,
            metadata=image_info,
            image_info=image_info,
        )
