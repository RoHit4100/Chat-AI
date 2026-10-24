from pypdf import PdfReader
from filesvc.parsers.base import BaseParser, ParsedResult

class PdfParser(BaseParser):
    """Parser for PDF files using pypdf."""

    def parse(self, file_path: str, original_filename: str) -> ParsedResult:
        reader = PdfReader(file_path)
        page_count = len(reader.pages)
        pages_text = []
        for i, page in enumerate(reader.pages):
            txt = page.extract_text() or ""
            if txt.strip():
                pages_text.append(f"--- Page {i + 1} ---\n{txt.strip()}")

        full_text = "\n\n".join(pages_text).strip()
        preview = (full_text[:200].replace("\n", " ").strip()) if full_text else "No extractable text"
        summary = f"PDF document '{original_filename}': {page_count} page(s). Preview: {preview}"
        return ParsedResult(
            text=full_text,
            summary=summary,
            metadata={"page_count": page_count, "pages": len(pages_text)},
        )
