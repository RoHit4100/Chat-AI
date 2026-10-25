import base64
import hashlib
import io
import logging
import os
from pathlib import Path
from PIL import Image
from langchain_core.messages import HumanMessage
from rest_framework.exceptions import ValidationError
from agent.llm import get_llm

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
SUPPORTED_PIL_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}
MAX_IMAGE_DIMENSION = 2000

def downscale_image(img: Image.Image, max_longest_side: int = MAX_IMAGE_DIMENSION) -> Image.Image:
    """Downscale image so its longest side is at most max_longest_side, preserving aspect ratio."""
    width, height = img.size
    longest = max(width, height)
    if longest > max_longest_side:
        scale = max_longest_side / float(longest)
        new_width = max(1, int(round(width * scale)))
        new_height = max(1, int(round(height * scale)))
        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    return img

def validate_and_prepare_image(file_path: str, original_filename: str = "") -> tuple[Image.Image, str, str]:
    """Validate image format, handle multi-frame GIFs, downscale if needed, and return (PIL Image, format, mime)."""
    target_name = original_filename or Path(file_path).name
    ext = Path(target_name).suffix.lower()
    if not ext and target_name.startswith("."):
        ext = target_name.lower()
    if ext not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValidationError(f"Unsupported image format '{ext}'. Supported formats are PNG, JPEG, WEBP, and GIF.")

    try:
        img = Image.open(file_path)
        img.load()
    except Exception as exc:
        raise ValidationError(f"Corrupt or invalid image file '{original_filename or Path(file_path).name}': {str(exc)}")

    fmt = (img.format or "").upper()
    if fmt == "JPG":
        fmt = "JPEG"

    if fmt not in SUPPORTED_PIL_FORMATS:
        raise ValidationError(f"Unsupported image format '{fmt}'. Supported formats are PNG, JPEG, WEBP, and GIF.")

    # Handle multi-frame GIF: extract the first frame
    if fmt == "GIF":
        try:
            img.seek(0)
        except Exception:
            pass

    # Downscale so the longest side is at most MAX_IMAGE_DIMENSION (2000 px)
    img = downscale_image(img, MAX_IMAGE_DIMENSION)

    mime = "image/png" if fmt in ("PNG", "GIF") else ("image/webp" if fmt == "WEBP" else "image/jpeg")
    return img, fmt, mime

def encode_image_to_base64(img: Image.Image, fmt: str) -> tuple[str, str]:
    """Encode PIL image to base64 string without persisting base64 in state. Returns (b64_str, mime)."""
    buf = io.BytesIO()
    if fmt in ("JPEG", "JPG"):
        # JPEG requires RGB mode
        if img.mode in ("RGBA", "LA", "P"):
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            rgb_img.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
            rgb_img.save(buf, format="JPEG", quality=90)
        else:
            img.convert("RGB").save(buf, format="JPEG", quality=90)
        mime = "image/jpeg"
    elif fmt == "WEBP":
        img.save(buf, format="WEBP", quality=90)
        mime = "image/webp"
    else:
        # Default to PNG
        img.save(buf, format="PNG")
        mime = "image/png"

    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
    return b64_str, mime

def perform_ocr_fallback(img: Image.Image, filename: str = "") -> str:
    """Fall back to local OCR extraction with pytesseract when vision model is unavailable."""
    try:
        import pytesseract
        ocr_text = pytesseract.image_to_string(img)
        cleaned = ocr_text.strip()
        if cleaned:
            return (
                f"[Note: Analyzed using OCR text extraction because the visual model is unavailable.]\n\n"
                f"Extracted Text:\n{cleaned}"
            )
        return ""
    except Exception as exc:
        logger.warning("OCR fallback failed on %s: %s", filename, exc)
        return ""

def analyze_image_with_vision(
    file_path: str,
    original_filename: str = "",
    question: str | None = None,
    is_summary: bool = False,
) -> tuple[str, str]:
    """Analyze image using configured LLM vision capabilities, falling back to OCR if unsupported.
    Returns (description_text, source) where source is 'vision', 'ocr', or 'error'.
    """
    try:
        img, fmt, _ = validate_and_prepare_image(file_path, original_filename)
    except ValidationError as ve:
        err_msg = ve.detail[0] if isinstance(ve.detail, list) else str(ve.detail)
        return f"Error: {err_msg}", "error"
    except Exception as exc:
        return f"Error: Failed to process image '{original_filename}': {str(exc)}", "error"

    # Check if vision is explicitly disabled via env
    vision_disabled = os.getenv("LLM_SUPPORTS_VISION", "1").strip().lower() in ("0", "false")
    vision_error_reason = "LLM_SUPPORTS_VISION=0 is configured" if vision_disabled else None

    if not vision_disabled:
        try:
            llm = get_llm()

            b64_str, mime = encode_image_to_base64(img, fmt)

            if is_summary:
                prompt_text = (
                    "Provide a concise 1-2 sentence factual summary of this image for a document index.\n"
                    "Identify the image type (chart, screenshot, photo, document, diagram) and the main subject or key takeaway."
                )
            else:
                prompt_text = (
                    "You are an expert visual analysis assistant. Provide a detailed, comprehensive description of this image.\n"
                    "- Transcribe all visible text, numbers, labels, legends, titles, and annotations exactly as they appear.\n"
                    "- If this is a chart, graph, diagram, or table, transcribe all axes, axis titles, categories, data points, and numerical values.\n"
                    "- Describe the layout, colors, structure, and any visual relationships."
                )
                if question:
                    prompt_text += f"\n\nUser Question/Focus: {question}"

            msg = HumanMessage(
                content=[
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64_str}"}},
                ]
            )

            # Invoke configured LLM
            response = llm.invoke([msg])
            content = getattr(response, "content", "")
            if isinstance(content, list):
                text_pieces = []
                for p in content:
                    if isinstance(p, dict) and "text" in p:
                        text_pieces.append(str(p["text"]))
                    elif isinstance(p, str):
                        text_pieces.append(p)
                content = "".join(text_pieces)

            cleaned_content = str(content).strip()
            if cleaned_content:
                return cleaned_content, "vision"
            else:
                vision_error_reason = "Vision model returned empty text response"

        except Exception as exc:
            logger.warning("LLM vision analysis failed on %s: %s", original_filename, exc)
            vision_error_reason = str(exc)

    # Fallback to OCR with pytesseract
    ocr_result = perform_ocr_fallback(img, original_filename)
    if ocr_result:
        return ocr_result, "ocr"

    # Both vision and OCR failed or produced no text
    fn = original_filename or Path(file_path).name
    return (
        f"Error: The image '{fn}' could not be analysed. "
        f"The vision model failed ({vision_error_reason or 'unknown error'}) and OCR extracted no readable text.",
        "error",
    )
