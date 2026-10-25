import io
from pypdf import PdfReader
from filesvc.parsers.base import BaseParser, ParsedResult

class PdfParser(BaseParser):
    """Parser for PDF files using pypdf, AcroForm extraction, and image OCR fallback."""

    def parse(self, file_path: str, original_filename: str) -> ParsedResult:
        reader = PdfReader(file_path)
        page_count = len(reader.pages)
        pages_text = []

        for i, page in enumerate(reader.pages):
            txt = (page.extract_text() or "").strip()

            # If page has little or no text (< 50 chars) but contains images, run OCR on images
            if len(txt) < 50 and len(page.images) > 0:
                ocr_pieces = []
                for img in page.images:
                    try:
                        import pytesseract
                        from PIL import Image as PILImage
                        pil_img = PILImage.open(io.BytesIO(img.data))
                        ocr_res = pytesseract.image_to_string(pil_img).strip()
                        if ocr_res:
                            ocr_pieces.append(ocr_res)
                    except Exception:
                        pass
                if ocr_pieces:
                    ocr_text = "\n".join(ocr_pieces)
                    txt = f"{txt}\n{ocr_text}".strip() if txt else ocr_text

            if txt:
                pages_text.append(f"--- Page {i + 1} ---\n{txt}")

        # Extract AcroForm fields if present and merge as "label: value"
        form_lines = []
        try:
            fields = reader.get_fields()
            if fields and isinstance(fields, dict):
                for name, field in fields.items():
                    val = getattr(field, "value", None)
                    if val is None and isinstance(field, dict):
                        val = field.get("/V", "")
                    if val is not None and str(val).strip():
                        form_lines.append(f"{name}: {str(val).strip()}")
        except Exception:
            pass

        if form_lines:
            pages_text.append("--- Form Fields ---\n" + "\n".join(form_lines))

        full_text = "\n\n".join(pages_text).strip()
        preview = (full_text[:200].replace("\n", " ").strip()) if full_text else "No extractable text"
        summary = f"PDF document '{original_filename}': {page_count} page(s). Preview: {preview}"
        return ParsedResult(
            text=full_text,
            summary=summary,
            metadata={
                "page_count": page_count,
                "pages": len(pages_text),
                "has_form_fields": bool(form_lines),
            },
        )
