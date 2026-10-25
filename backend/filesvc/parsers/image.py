import hashlib
import logging
from filesvc.parsers.base import BaseParser, ParsedResult
from filesvc.image_vision import (
    validate_and_prepare_image,
    analyze_image_with_vision,
)

logger = logging.getLogger(__name__)

class ImageParser(BaseParser):
    """Parser for images extracting dimensions, validating formats, and creating vision summary."""

    def parse(self, file_path: str, original_filename: str) -> ParsedResult:
        # Validate format (png, jpg/jpeg, webp, gif), downscale if >2000px, handle animated gif
        img, fmt, _ = validate_and_prepare_image(file_path, original_filename)
        width, height = img.size
        mode = img.mode

        image_info = {
            "width": width,
            "height": height,
            "format": fmt,
            "mode": mode,
            "file_path": file_path,
        }

        # Attempt upload-time summary using vision call; do not fail upload if vision call fails
        vision_cache = {}
        summary = f"Image '{original_filename}': {fmt} ({width}x{height} px, {mode})."
        text_content = f"Image '{original_filename}': {width}x{height} px, format {fmt}, mode {mode}."

        try:
            desc_text, source = analyze_image_with_vision(
                file_path,
                original_filename=original_filename,
                is_summary=True,
            )
            if source in ("vision", "ocr") and desc_text:
                q_hash = hashlib.sha256(b"").hexdigest()[:16]
                vision_cache[q_hash] = desc_text
                # Compact 1-sentence summary for file manifest
                first_line = desc_text.split("\n")[0].strip()
                summary = f"Image '{original_filename}': {first_line[:160]}"
                text_content = desc_text
        except Exception as exc:
            logger.warning("Upload-time vision call failed on %s: %s", original_filename, exc)

        return ParsedResult(
            text=text_content,
            summary=summary,
            metadata=image_info,
            structured_data={
                "width": width,
                "height": height,
                "format": fmt,
                "mode": mode,
                "image_info": image_info,
                "vision_cache": vision_cache,
            },
            image_info=image_info,
        )
