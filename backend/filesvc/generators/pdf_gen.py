from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from filesvc.generators.base import BaseGenerator

class PdfGenerator(BaseGenerator):
    """Generator for PDF documents from structured spec using ReportLab."""
    default_extension = ".pdf"

    def validate_spec(self, spec: dict) -> None:
        super().validate_spec(spec)
        if not spec.get("title") and not spec.get("sections") and not spec.get("paragraphs") and not spec.get("tables"):
            raise ValueError("PDF spec must contain at least 'title', 'sections', 'paragraphs', or 'tables'.")

    def generate(self, spec: dict, output_path: str) -> None:
        self.validate_spec(spec)
        doc = SimpleDocTemplate(output_path, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
        styles = getSampleStyleSheet()

        bullet_style = ParagraphStyle(
            "BulletStyle",
            parent=styles["Normal"],
            leftIndent=20,
            firstLineIndent=-10,
            spaceAfter=4,
        )

        story = []

        title = spec.get("title")
        if title:
            story.append(Paragraph(str(title), styles["Title"]))
            story.append(Spacer(1, 14))

        author = spec.get("author")
        if author:
            story.append(Paragraph(f"Author: {author}", styles["Italic"]))
            story.append(Spacer(1, 10))

        # Handle simple paragraphs
        for p in spec.get("paragraphs", []):
            story.append(Paragraph(str(p), styles["Normal"]))
            story.append(Spacer(1, 8))

        # Handle sections
        for sec in spec.get("sections", []):
            if isinstance(sec, dict):
                heading = sec.get("heading")
                if heading:
                    story.append(Paragraph(str(heading), styles["Heading2"]))
                    story.append(Spacer(1, 6))
                content = sec.get("content")
                if content:
                    story.append(Paragraph(str(content), styles["Normal"]))
                    story.append(Spacer(1, 8))
                for bullet in sec.get("bullets", []):
                    story.append(Paragraph(f"&bull; {bullet}", bullet_style))
                story.append(Spacer(1, 6))
            elif isinstance(sec, str):
                story.append(Paragraph(sec, styles["Normal"]))
                story.append(Spacer(1, 8))

        # Handle tables
        for tbl in spec.get("tables", []):
            headers = tbl.get("headers", [])
            rows = tbl.get("rows", [])
            table_data = []
            if headers:
                table_data.append([str(h) for h in headers])
            for r in rows:
                table_data.append([str(c) for c in r])

            if table_data:
                t = Table(table_data)
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B3A42")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]))
                story.append(t)
                story.append(Spacer(1, 12))

        doc.build(story)

    def summarize_spec(self, spec: dict) -> str:
        title = spec.get("title") or "Document"
        sections = len(spec.get("sections", [])) + len(spec.get("paragraphs", []))
        return f"PDF '{title}' ({sections} section(s))"
