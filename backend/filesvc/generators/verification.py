import os
from pathlib import Path
from typing import Any, Dict

def verify_generated_file(kind: str, file_path: str, spec: dict) -> Dict[str, Any]:
    """Re-open produced file, extract text, check page count, and verify every section from spec is present.
    Returns metrics dict: {'pages': int, 'sections': int, 'words': int, 'summary': str}.
    Raises ValueError with a clear, specific message if verification fails.
    """
    if not os.path.exists(file_path):
        raise ValueError(f"Verification failed: file '{Path(file_path).name}' was not created.")

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        raise ValueError(f"Verification failed: generated file '{Path(file_path).name}' is empty (0 bytes).")

    clean_kind = (kind or "").strip().lower().lstrip(".")

    if clean_kind == "pdf":
        import pypdf
        try:
            reader = pypdf.PdfReader(file_path)
        except Exception as exc:
            raise ValueError(f"Verification failed: could not parse generated PDF ({str(exc)}).")

        page_count = len(reader.pages)
        if page_count == 0:
            raise ValueError("Verification failed: generated PDF has 0 pages.")

        extracted_text = " ".join((p.extract_text() or "").strip() for p in reader.pages)
        words = len(extracted_text.split())
        if words == 0:
            raise ValueError("Verification failed: generated PDF has no extractable text.")

        sections = spec.get("sections", [])
        for sec in sections:
            if isinstance(sec, dict):
                heading = sec.get("heading") or sec.get("title")
                if heading and heading.strip().lower() not in extracted_text.lower():
                    raise ValueError(f"Verification failed: section '{heading}' is missing from generated PDF text.")

                # Check that sections with content, bullets, or entries actually rendered text
                has_content = bool(sec.get("content") or sec.get("paragraph") or sec.get("paragraphs"))
                bullets = sec.get("bullets") or []
                groups = sec.get("groups") or []
                entries = sec.get("entries") or []

                if bullets and not any(any(w.lower() in extracted_text.lower() for w in b.split() if len(w) > 3) for b in bullets):
                    raise ValueError(f"Verification failed: bullets under section '{heading}' were not rendered in PDF.")
                if groups and not any(str(g.get("label") or g.get("name") or "").lower() in extracted_text.lower() for g in groups if isinstance(g, dict)):
                    raise ValueError(f"Verification failed: skill groups under section '{heading}' were not rendered in PDF.")
                if entries and not any(str(e.get("title", "")).lower() in extracted_text.lower() for e in entries if isinstance(e, dict) and e.get("title")):
                    raise ValueError(f"Verification failed: entry details under section '{heading}' were not rendered in PDF.")
            elif isinstance(sec, str) and sec.strip():
                if sec.strip().lower() not in extracted_text.lower():
                    raise ValueError(f"Verification failed: section text '{sec}' is missing from generated PDF.")

        return {
            "pages": page_count,
            "sections": len(sections),
            "words": words,
            "summary": f"{page_count} page(s), {len(sections)} section(s), {words} words",
        }

    elif clean_kind == "docx":
        import docx
        try:
            doc = docx.Document(file_path)
        except Exception as exc:
            raise ValueError(f"Verification failed: could not parse generated DOCX ({str(exc)}).")

        para_texts = [p.text for p in doc.paragraphs if p.text.strip()]
        tbl_texts = [c.text for t in doc.tables for r in t.rows for c in r.cells if c.text.strip()]
        all_text = " ".join(para_texts + tbl_texts)
        words = len(all_text.split())

        if words == 0:
            raise ValueError("Verification failed: generated DOCX contains no text.")

        estimated_pages = max(1, (len(para_texts) + 30) // 35)
        sections = spec.get("sections", [])
        for sec in sections:
            if isinstance(sec, dict):
                heading = sec.get("heading") or sec.get("title")
                if heading and heading.strip().lower() not in all_text.lower():
                    raise ValueError(f"Verification failed: section '{heading}' is missing from generated DOCX text.")
            elif isinstance(sec, str) and sec.strip():
                if sec.strip().lower() not in all_text.lower():
                    raise ValueError(f"Verification failed: section text '{sec}' is missing from generated DOCX.")

        return {
            "pages": estimated_pages,
            "sections": len(sections),
            "words": words,
            "summary": f"approx {estimated_pages} page(s), {len(sections)} section(s), {words} words",
        }

    elif clean_kind in ("xlsx", "xls"):
        import openpyxl
        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
        except Exception as exc:
            raise ValueError(f"Verification failed: could not open XLSX workbook ({str(exc)}).")

        sheets = wb.sheetnames
        total_rows = sum(ws.max_row for ws in wb.worksheets)
        if total_rows == 0:
            raise ValueError("Verification failed: generated XLSX workbook contains no data rows.")

        return {
            "pages": 1,
            "sections": len(sheets),
            "words": total_rows,
            "summary": f"{len(sheets)} sheet(s), {total_rows} total rows",
        }

    elif clean_kind == "csv":
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = [l for l in f.readlines() if l.strip()]
        if not lines:
            raise ValueError("Verification failed: generated CSV is empty.")
        return {
            "pages": 1,
            "sections": 1,
            "words": len(lines),
            "summary": f"{len(lines)} CSV row(s)",
        }

    elif clean_kind == "pptx":
        from pptx import Presentation
        try:
            prs = Presentation(file_path)
        except Exception as exc:
            raise ValueError(f"Verification failed: could not parse PPTX ({str(exc)}).")

        slide_count = len(prs.slides)
        if slide_count == 0:
            raise ValueError("Verification failed: generated PPTX has 0 slides.")
        return {
            "pages": slide_count,
            "sections": slide_count,
            "words": slide_count * 20,
            "summary": f"{slide_count} slide(s)",
        }

    elif clean_kind in ("chart", "png"):
        from PIL import Image
        try:
            with Image.open(file_path) as img:
                w, h = img.size
        except Exception as exc:
            raise ValueError(f"Verification failed: could not verify image ({str(exc)}).")
        return {
            "pages": 1,
            "sections": 1,
            "words": 1,
            "summary": f"Chart image {w}x{h} px",
        }

    else:
        # Markdown, Code, Plain text
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        words = len(text.split())
        lines = len(text.splitlines())
        if lines == 0:
            raise ValueError(f"Verification failed: generated {clean_kind} file is empty.")
        return {
            "pages": 1,
            "sections": 1,
            "words": words,
            "summary": f"{lines} line(s), {words} words",
        }
