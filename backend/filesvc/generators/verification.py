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
            wb_data = openpyxl.load_workbook(file_path, data_only=True)
            wb_raw = openpyxl.load_workbook(file_path, data_only=False)
        except Exception as exc:
            raise ValueError(f"Verification failed: could not open XLSX workbook ({str(exc)}).")

        sheets = wb_data.sheetnames
        if not sheets:
            raise ValueError("Verification failed: XLSX workbook contains no sheets.")

        ws_data = wb_data.active
        ws_raw = wb_raw.active

        # 1. Header row present and matches spec
        expected_headers = spec.get("headers") or []
        if not expected_headers and spec.get("sheets"):
            first_s = spec["sheets"][0]
            if isinstance(first_s, dict):
                expected_headers = first_s.get("headers") or []

        if ws_data.max_row < 1:
            raise ValueError("Verification failed: generated XLSX has 0 rows.")

        computed_cols = spec.get("computed_columns") or (spec.get("sheets") and spec["sheets"][0].get("computed_columns")) or []
        extra_cols = [c.get("header") for c in computed_cols if isinstance(c, dict) and c.get("header") and c.get("header") not in expected_headers]
        all_expected_headers = list(expected_headers) + extra_cols

        if all_expected_headers:
            for idx, h in enumerate(all_expected_headers, start=1):
                cell_h = ws_data.cell(1, idx).value
                if cell_h is None or str(cell_h).strip() != str(h).strip():
                    raise ValueError(f"Verification failed: header row missing or column {idx} mismatch (expected '{h}', got '{cell_h}').")

        # 2. Row and column counts match the spec
        expected_rows = spec.get("rows") or []
        if not expected_rows and spec.get("sheets"):
            first_s = spec["sheets"][0]
            if isinstance(first_s, dict):
                expected_rows = first_s.get("rows") or []

        has_total_spec = bool(spec.get("total_row") or (spec.get("sheets") and spec["sheets"][0].get("total_row")))
        has_total_in_rows = any(isinstance(r, (list, tuple)) and len(r) > 0 and str(r[0].get("value") if isinstance(r[0], dict) else r[0]).strip().lower() == "total" for r in expected_rows)

        total_row_added = (has_total_spec and not has_total_in_rows)
        expected_row_count = len(expected_rows) + (1 if all_expected_headers else 0) + (1 if total_row_added else 0)
        expected_col_count = len(all_expected_headers) if all_expected_headers else (len(expected_rows[0]) if expected_rows else 0)

        if ws_data.max_row != expected_row_count:
            raise ValueError(f"Verification failed: row count mismatch (expected {expected_row_count} rows, found {ws_data.max_row}).")
        if expected_col_count and ws_data.max_column != expected_col_count:
            raise ValueError(f"Verification failed: column count mismatch (expected {expected_col_count} columns, found {ws_data.max_column}).")

        # 3. Check for #REF! or formula errors and unexpectedly empty cells
        for r in range(1, ws_data.max_row + 1):
            for c in range(1, ws_data.max_column + 1):
                cv = str(ws_data.cell(r, c).value or "")
                raw_v = str(ws_raw.cell(r, c).value or "")
                coord = ws_data.cell(r, c).coordinate
                if "#REF!" in cv or "#REF!" in raw_v:
                    raise ValueError(f"Verification failed: cell {coord} contains '#REF!'.")
                if any(err in cv for err in ["#VALUE!", "#NAME?", "#N/A", "#DIV/0!"]):
                    raise ValueError(f"Verification failed: cell {coord} contains error '{cv}'.")

        # Check no cell is unexpectedly empty
        for r in range(2, ws_data.max_row + 1):
            is_last_row = (r == ws_data.max_row and str(ws_data.cell(r, 1).value or "").strip().lower() == "total")
            for c in range(1, ws_data.max_column + 1):
                col_h = str(ws_data.cell(1, c).value or "").lower()
                is_growth_col = "growth" in col_h or "%" in col_h
                val = ws_data.cell(r, c).value
                coord = ws_data.cell(r, c).coordinate

                if is_growth_col:
                    if r == 2:
                        # First data row must be blank
                        if val is not None and str(val).strip() not in ("", "-"):
                            raise ValueError(f"Verification failed: first period growth cell {coord} must be blank.")
                    elif is_last_row:
                        # Total row must be blank
                        if val is not None and str(val).strip() not in ("", "-"):
                            raise ValueError(f"Verification failed: total row growth cell {coord} must be blank.")
                    else:
                        if val is None or str(val).strip() == "":
                            raise ValueError(f"Verification failed: cell {coord} is unexpectedly empty.")
                else:
                    if val is None or str(val).strip() == "":
                        raise ValueError(f"Verification failed: cell {coord} is unexpectedly empty.")

        # 4. Total row verification (totals equal sum of data rows)
        totals_summary = []
        if ws_data.max_row >= 3:
            last_row_first = ws_data.cell(ws_data.max_row, 1).value
            if last_row_first and str(last_row_first).strip().lower() == "total":
                for c in range(2, ws_data.max_column + 1):
                    col_header = str(ws_data.cell(1, c).value or f"Col{c}")
                    col_h_lower = col_header.lower()

                    if "growth" in col_h_lower or "%" in col_h_lower:
                        continue

                    # Sum numeric data rows (rows 2 to max_row - 1, including January!)
                    data_nums = []
                    for r in range(2, ws_data.max_row):
                        cv = ws_data.cell(r, c).value
                        if isinstance(cv, (int, float)):
                            data_nums.append(float(cv))
                        elif cv is None or cv == "":
                            continue
                        else:
                            try:
                                data_nums.append(float(str(cv).replace(",", "").replace("$", "").replace("₹", "")))
                            except ValueError:
                                data_nums = []
                                break

                    if data_nums:
                        sum_data = sum(data_nums)
                        tot_val = ws_data.cell(ws_data.max_row, c).value
                        coord = ws_data.cell(ws_data.max_row, c).coordinate
                        if tot_val is None or str(tot_val).strip() == "":
                            raise ValueError(f"Verification failed: total row cell {coord} for '{col_header}' is empty.")

                        try:
                            tot_num = float(str(tot_val).replace(",", "").replace("$", "").replace("₹", ""))
                        except ValueError:
                            tot_num = None

                        if tot_num is not None:
                            if abs(tot_num - sum_data) > 0.05:
                                raise ValueError(f"Verification failed: total for '{col_header}' ({tot_val}) does not match sum of data rows ({sum_data:.2f}).")
                            fmt_tot = f"{int(tot_num):,}" if tot_num.is_integer() else f"{tot_num:,.2f}"
                            totals_summary.append(f"{col_header}: {fmt_tot}")

        # 5. Build precise summary for the assistant
        sample_cells = []
        for r in range(2, min(5, ws_data.max_row + 1)):
            row_items = [str(ws_data.cell(r, c).value) for c in range(1, min(4, ws_data.max_column + 1))]
            sample_cells.append(f"Row {r-1}: [{', '.join(row_items)}]")

        tot_text = ", ".join(totals_summary) if totals_summary else "N/A"
        summary = (
            f"Verified XLSX: {ws_data.max_row - 2} data row(s), {ws_data.max_column} column(s). "
            f"Total row: ({tot_text}). "
            f"Sample: {'; '.join(sample_cells)}"
        )

        return {
            "pages": 1,
            "sections": len(sheets),
            "words": len(expected_rows),
            "rows": len(expected_rows),
            "columns": ws_data.max_column,
            "total": tot_text,
            "sample_cells": sample_cells,
            "summary": summary,
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
