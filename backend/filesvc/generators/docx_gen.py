import docx
from filesvc.generators.base import BaseGenerator

class DocxGenerator(BaseGenerator):
    """Generator for Microsoft Word (.docx) documents from structured spec."""
    default_extension = ".docx"

    def validate_spec(self, spec: dict) -> None:
        super().validate_spec(spec)
        if not spec.get("title") and not spec.get("sections") and not spec.get("paragraphs") and not spec.get("tables"):
            raise ValueError("DOCX spec must contain at least 'title', 'sections', 'paragraphs', or 'tables'.")

    def generate(self, spec: dict, output_path: str) -> None:
        self.validate_spec(spec)
        doc = docx.Document()

        title = spec.get("title")
        if title:
            doc.add_heading(str(title), level=0)

        description = spec.get("description")
        if description:
            doc.add_paragraph(str(description))

        # Handle simple paragraphs list
        for p in spec.get("paragraphs", []):
            doc.add_paragraph(str(p))

        # Handle structured sections with headings and bullets
        for sec in spec.get("sections", []):
            if isinstance(sec, dict):
                heading = sec.get("heading")
                if heading:
                    doc.add_heading(str(heading), level=sec.get("level", 1))
                content = sec.get("content")
                if content:
                    doc.add_paragraph(str(content))
                for bullet in sec.get("bullets", []):
                    doc.add_paragraph(str(bullet), style="List Bullet")
            elif isinstance(sec, str):
                doc.add_paragraph(sec)

        # Handle tables
        for tbl in spec.get("tables", []):
            headers = tbl.get("headers", [])
            rows = tbl.get("rows", [])
            if headers or rows:
                col_count = len(headers) if headers else (len(rows[0]) if rows else 0)
                table = doc.add_table(rows=0, cols=col_count)
                table.style = "Table Grid"
                if headers:
                    hdr_cells = table.add_row().cells
                    for i, h in enumerate(headers):
                        hdr_cells[i].text = str(h)
                for r in rows:
                    row_cells = table.add_row().cells
                    for i, cell_val in enumerate(r[:col_count]):
                        row_cells[i].text = str(cell_val)

        doc.save(output_path)

    def summarize_spec(self, spec: dict) -> str:
        title = spec.get("title") or "Document"
        sections = len(spec.get("sections", [])) + len(spec.get("paragraphs", []))
        tables = len(spec.get("tables", []))
        return f"DOCX '{title}' ({sections} section(s), {tables} table(s))"
