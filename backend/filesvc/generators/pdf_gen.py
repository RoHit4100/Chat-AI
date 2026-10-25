import os
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from filesvc.generators.base import BaseGenerator
from filesvc.generators.specs import validate_spec_for_kind

# Register DejaVu Unicode fonts for UTF-8 support
_FONT_FAMILY = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"

def _setup_fonts() -> tuple[str, str]:
    """Register DejaVu TrueType fonts if available on the system."""
    global _FONT_FAMILY, _FONT_BOLD
    candidate_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    bold_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]

    regular_path = next((p for p in candidate_paths if os.path.exists(p)), None)
    bold_path = next((p for p in bold_candidates if os.path.exists(p)), None)

    if regular_path:
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSans", regular_path))
            if bold_path:
                pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold_path))
                pdfmetrics.registerFontFamily(
                    "DejaVuSans",
                    normal="DejaVuSans",
                    bold="DejaVuSans-Bold",
                    italic="DejaVuSans",
                    boldItalic="DejaVuSans-Bold",
                )
            _FONT_FAMILY = "DejaVuSans"
            _FONT_BOLD = "DejaVuSans-Bold" if bold_path else "DejaVuSans"
        except Exception:
            pass
    return _FONT_FAMILY, _FONT_BOLD

_setup_fonts()

class PdfGenerator(BaseGenerator):
    """High-quality PDF generator with Unicode support, ATS resume formatting, and rich document elements."""
    default_extension = ".pdf"

    def validate_spec(self, spec: dict) -> None:
        super().validate_spec(spec)
        validate_spec_for_kind("pdf", spec)

    def generate(self, spec: dict, output_path: str) -> None:
        self.validate_spec(spec)

        # Determine page size and margins
        page_size_name = str(spec.get("page_size", "A4")).upper()
        page_size = letter if page_size_name == "LETTER" else A4

        margins_spec = spec.get("margins")
        if isinstance(margins_spec, dict):
            top_m = float(margins_spec.get("top", 36))
            bottom_m = float(margins_spec.get("bottom", 36))
            left_m = float(margins_spec.get("left", 36))
            right_m = float(margins_spec.get("right", 36))
        elif isinstance(margins_spec, (int, float)):
            top_m = bottom_m = left_m = right_m = float(margins_spec)
        else:
            # 36pt (0.5 in) default for clean ATS-friendly resume margins
            top_m = bottom_m = left_m = right_m = 36.0

        doc = SimpleDocTemplate(
            output_path,
            pagesize=page_size,
            leftMargin=left_m,
            rightMargin=right_m,
            topMargin=top_m,
            bottomMargin=bottom_m,
        )

        font_norm, font_bold = _setup_fonts()
        content_width = page_size[0] - left_m - right_m

        # Build paragraph styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=17,
            leading=21,
            alignment=1,  # Center
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=2,
        )
        subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=10.5,
            leading=14,
            alignment=1,  # Center
            textColor=colors.HexColor("#334155"),
            spaceAfter=3,
        )
        contact_style = ParagraphStyle(
            "DocContact",
            parent=styles["Normal"],
            fontName=font_norm,
            fontSize=8.5,
            leading=12,
            alignment=1,  # Center
            textColor=colors.HexColor("#475569"),
            spaceAfter=4,
        )
        heading_style = ParagraphStyle(
            "DocHeading",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=7,
            spaceAfter=2,
            keepWithNext=True,
        )
        body_style = ParagraphStyle(
            "DocBody",
            parent=styles["Normal"],
            fontName=font_norm,
            fontSize=9,
            leading=12.5,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=3,
        )
        group_style = ParagraphStyle(
            "DocGroup",
            parent=styles["Normal"],
            fontName=font_norm,
            fontSize=9,
            leading=12.5,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=2,
        )
        bullet_style = ParagraphStyle(
            "DocBullet",
            parent=styles["Normal"],
            fontName=font_norm,
            fontSize=9,
            leading=12.5,
            leftIndent=12,
            firstLineIndent=-8,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=2,
        )
        entry_title_style = ParagraphStyle(
            "EntryTitle",
            parent=styles["Normal"],
            fontName=font_bold,
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#0F172A"),
        )
        entry_date_style = ParagraphStyle(
            "EntryDate",
            parent=styles["Normal"],
            fontName=font_norm,
            fontSize=8.5,
            leading=13,
            alignment=2,  # Right-aligned
            textColor=colors.HexColor("#475569"),
        )
        entry_subtitle_style = ParagraphStyle(
            "EntrySubtitle",
            parent=styles["Normal"],
            fontName=font_norm,
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#334155"),
            spaceAfter=2,
        )

        story = []

        # Document Title / Candidate Name
        title = spec.get("title")
        if title:
            story.append(Paragraph(str(title), title_style))

        # Subtitle / Target Role
        subtitle = spec.get("subtitle")
        if subtitle:
            story.append(Paragraph(str(subtitle), subtitle_style))

        # Header / Contact lines
        header = spec.get("header") or spec.get("contact")
        if header:
            if isinstance(header, list):
                contact_line = "  •  ".join(str(item).strip() for item in header if str(item).strip())
                story.append(Paragraph(contact_line, contact_style))
            elif isinstance(header, dict):
                parts = [f"{k}: {v}" for k, v in header.items() if v]
                story.append(Paragraph("  •  ".join(parts), contact_style))
            elif isinstance(header, str):
                story.append(Paragraph(header, contact_style))

        # Author or Description if present
        author = spec.get("author")
        if author:
            story.append(Paragraph(f"Author: {author}", contact_style))
        description = spec.get("description")
        if description:
            story.append(Paragraph(str(description), body_style))
            story.append(Spacer(1, 4))

        # Top-level simple paragraphs
        for p in spec.get("paragraphs", []):
            story.append(Paragraph(str(p), body_style))

        # Render sections
        for sec in spec.get("sections", []):
            if isinstance(sec, str):
                story.append(Paragraph(sec, body_style))
                continue
            if not isinstance(sec, dict):
                continue

            heading = sec.get("heading") or sec.get("title")
            if heading:
                story.append(Paragraph(str(heading).upper(), heading_style))
                story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#CBD5E1"), spaceBefore=1, spaceAfter=4))

            # Section content / paragraph
            content = sec.get("content") or sec.get("paragraph")
            if content:
                story.append(Paragraph(str(content), body_style))

            # Section paragraphs list
            for p in sec.get("paragraphs", []):
                story.append(Paragraph(str(p), body_style))

            # Grouped items (e.g. Technical Skills categorized)
            for grp in sec.get("groups", []):
                if isinstance(grp, dict):
                    label = grp.get("label") or grp.get("name") or ""
                    items = grp.get("items") or grp.get("value") or grp.get("skills") or ""
                    if isinstance(items, list):
                        items_str = ", ".join(str(i) for i in items)
                    else:
                        items_str = str(items)
                    grp_text = f"<b>{label}</b> {items_str}" if label else items_str
                    story.append(Paragraph(grp_text, group_style))
                elif isinstance(grp, str):
                    story.append(Paragraph(grp, group_style))

            # Detailed entries (Work Experience, Projects, Education)
            for entry in sec.get("entries", []):
                if isinstance(entry, dict):
                    e_title = entry.get("title", "")
                    e_sub = entry.get("subtitle") or entry.get("company") or entry.get("organization") or ""
                    e_date = entry.get("date") or entry.get("dates") or ""
                    e_loc = entry.get("location", "")
                    e_desc = entry.get("description") or entry.get("content") or ""
                    e_bullets = entry.get("bullets", [])

                    # Row 1: Title on left, Date on right
                    if e_title or e_date:
                        left_w = content_width * 0.72
                        right_w = content_width * 0.28
                        title_cell = Paragraph(f"<b>{e_title}</b>", entry_title_style)
                        date_cell = Paragraph(str(e_date), entry_date_style)
                        row_tbl = Table([[title_cell, date_cell]], colWidths=[left_w, right_w])
                        row_tbl.setStyle(TableStyle([
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, -1), 1),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                        ]))
                        story.append(row_tbl)

                    # Row 2: Subtitle / Organization & Location
                    sub_parts = [p for p in [e_sub, e_loc] if p]
                    if sub_parts:
                        story.append(Paragraph("  |  ".join(sub_parts), entry_subtitle_style))

                    # Row 3: Description if present
                    if e_desc:
                        story.append(Paragraph(str(e_desc), body_style))

                    # Row 4: Bullets under entry
                    for b in e_bullets:
                        story.append(Paragraph(f"&bull;&nbsp; {b}", bullet_style))

                    story.append(Spacer(1, 2))
                elif isinstance(entry, str):
                    story.append(Paragraph(entry, body_style))

            # Section top-level bullets
            for bullet in sec.get("bullets", []):
                story.append(Paragraph(f"&bull;&nbsp; {bullet}", bullet_style))

            # Key-values
            kvs = sec.get("key_values", [])
            if isinstance(kvs, dict):
                kvs = [{k: v} for k, v in kvs.items()]
            for kv in kvs:
                if isinstance(kv, dict):
                    for k, v in kv.items():
                        story.append(Paragraph(f"<b>{k}:</b> {v}", group_style))

            # Embedded tables inside section
            for tbl in sec.get("tables", []):
                self._render_table(tbl, story, content_width)

        # Top-level tables
        for tbl in spec.get("tables", []):
            self._render_table(tbl, story, content_width)

        doc.build(story)

    def _render_table(self, tbl: dict, story: list, content_width: float) -> None:
        """Helper to render styled tables."""
        headers = tbl.get("headers", [])
        rows = tbl.get("rows", [])
        table_data = []
        if headers:
            table_data.append([str(h) for h in headers])
        for r in rows:
            table_data.append([str(c) for c in (r if isinstance(r, (list, tuple)) else [r])])

        if table_data:
            col_count = len(table_data[0])
            col_w = content_width / max(1, col_count)
            t = Table(table_data, colWidths=[col_w] * col_count)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ]))
            story.append(t)
            story.append(Spacer(1, 6))

    def summarize_spec(self, spec: dict) -> str:
        title = spec.get("title") or "Document"
        sections = len(spec.get("sections", [])) + len(spec.get("paragraphs", []))
        return f"PDF '{title}' ({sections} section(s))"
