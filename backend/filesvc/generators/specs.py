"""Pydantic specifications and validators for file generators."""
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator

class GroupSpec(BaseModel):
    """A labeled group of items (e.g. for skills: label='Backend', items='Django, DRF, PostgreSQL')."""
    label: str = Field(description="Group category or title, e.g. 'Backend'")
    items: Union[str, List[str]] = Field(description="List of skills or comma-separated string")

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Support aliases like 'name' -> 'label', 'value' -> 'items'
            if "label" not in data and "name" in data:
                data["label"] = data["name"]
            if "items" not in data and "value" in data:
                data["items"] = data["value"]
            if "items" not in data and "skills" in data:
                data["items"] = data["skills"]
        return data

class EntrySpec(BaseModel):
    """An experience, project, or education entry with date, organization, and bullet points."""
    title: str = Field(description="Job title, project name, or degree")
    subtitle: Optional[str] = Field(default=None, description="Company, organization, or institution")
    organization: Optional[str] = Field(default=None, description="Alternative to subtitle")
    date: Optional[str] = Field(default=None, description="Date range, e.g. 'Sept 2024 - Present'")
    dates: Optional[str] = Field(default=None, description="Alternative to date")
    location: Optional[str] = Field(default=None, description="City, State or Remote")
    description: Optional[str] = Field(default=None, description="Short summary of role or project")
    bullets: Optional[List[str]] = Field(default_factory=list, description="List of achievements or responsibilities")

    @model_validator(mode="before")
    @classmethod
    def normalize_entry(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("subtitle") and data.get("company"):
                data["subtitle"] = data["company"]
            if not data.get("subtitle") and data.get("organization"):
                data["subtitle"] = data["organization"]
            if not data.get("date") and data.get("dates"):
                data["date"] = data["dates"]
            if not data.get("description") and data.get("content"):
                data["description"] = data["content"]
        return data

class TableSpec(BaseModel):
    """Table structure with optional headers and 2D row data."""
    headers: Optional[List[str]] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)

class SectionSpec(BaseModel):
    """Structured section of a document (heading, paragraphs, bullets, groups, entries, tables)."""
    heading: str = Field(description="Section heading, e.g. 'SUMMARY' or 'WORK EXPERIENCE'")
    level: Optional[int] = Field(default=1, description="Heading level (1=H1, 2=H2)")
    content: Optional[str] = Field(default=None, description="Single text block")
    paragraph: Optional[str] = Field(default=None, description="Alias for content")
    paragraphs: Optional[List[str]] = Field(default=None, description="List of paragraphs")
    bullets: Optional[List[str]] = Field(default=None, description="List of bullet points")
    groups: Optional[List[GroupSpec]] = Field(default=None, description="Grouped items, e.g. categorized skills")
    entries: Optional[List[EntrySpec]] = Field(default=None, description="List of experience/project/education entries")
    key_values: Optional[Union[List[Dict[str, str]], Dict[str, str]]] = Field(default=None, description="Key-value pairs")
    tables: Optional[List[TableSpec]] = Field(default=None, description="Embedded tables")

    @model_validator(mode="before")
    @classmethod
    def normalize_section(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"heading": data, "content": ""}
        if isinstance(data, dict):
            if not data.get("heading") and data.get("title"):
                data["heading"] = data["title"]
            if not data.get("content") and data.get("paragraph"):
                data["content"] = data["paragraph"]
        return data

    @model_validator(mode="after")
    def validate_has_content(self) -> "SectionSpec":
        has_items = any([
            bool(self.content and self.content.strip()),
            bool(self.paragraph and self.paragraph.strip()),
            bool(self.paragraphs and any(str(p).strip() for p in self.paragraphs)),
            bool(self.bullets and len(self.bullets) > 0),
            bool(self.groups and len(self.groups) > 0),
            bool(self.entries and len(self.entries) > 0),
            bool(self.key_values),
            bool(self.tables and len(self.tables) > 0),
        ])
        if not has_items and not self.heading:
            raise ValueError(f"Section '{self.heading}' must contain at least one content item (paragraphs, bullets, groups, or entries).")
        return self

class DocumentSpec(BaseModel):
    """Comprehensive specification for PDF and DOCX document generators."""
    title: Optional[str] = Field(default=None, description="Document title or candidate name")
    subtitle: Optional[str] = Field(default=None, description="Document subtitle or candidate target role")
    header: Optional[Union[str, List[str], Dict[str, Any]]] = Field(default=None, description="Contact lines, links, email, phone")
    contact: Optional[Union[str, List[str]]] = Field(default=None, description="Direct contact info string or list")
    author: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    page_size: Optional[str] = Field(default="A4", description="Page size: 'A4' or 'LETTER'")
    margins: Optional[Union[float, int, Dict[str, Union[float, int]]]] = Field(default=None, description="Margin in pt or dict with top, bottom, left, right")
    sections: Optional[List[SectionSpec]] = Field(default_factory=list, description="Document sections")
    paragraphs: Optional[List[str]] = Field(default_factory=list, description="Top-level paragraphs")
    tables: Optional[List[TableSpec]] = Field(default_factory=list, description="Top-level tables")
    compact: Optional[bool] = Field(default=None, description="Optimize for 1-page compact layout")

    @model_validator(mode="after")
    def validate_document(self) -> "DocumentSpec":
        has_content = (
            bool(self.title and self.title.strip()) or
            bool(self.sections and len(self.sections) > 0) or
            bool(self.paragraphs and len(self.paragraphs) > 0) or
            bool(self.tables and len(self.tables) > 0)
        )
        if not has_content:
            raise ValueError("Document spec must contain a 'title' or at least one 'sections', 'paragraphs', or 'tables' item.")
        return self

class CellSpec(BaseModel):
    """Specification for an individual spreadsheet cell with typed formatting and optional formula."""
    value: Optional[Any] = Field(default=None, description="Computed scalar value (e.g. numeric total, percentage, string)")
    number_format: Optional[str] = Field(default=None, description="Format string, e.g. '#,##0' for currency/counts, '0.0%' for percentages")
    bold: Optional[bool] = Field(default=False, description="Whether cell text is bold")
    formula: Optional[str] = Field(default=None, description="Optional Excel formula string, e.g. '=SUM(B2:B13)'")

    @model_validator(mode="before")
    @classmethod
    def normalize_cell(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            if isinstance(data, str) and data.startswith("="):
                return {"formula": data, "value": None}
            return {"value": data}
        return data

class SheetSpec(BaseModel):
    """Specification for a single sheet in an Excel workbook."""
    name: Optional[str] = Field(default="Sheet1")
    headers: Optional[List[str]] = Field(default_factory=list)
    rows: Optional[List[List[Union[CellSpec, Any]]]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_sheet(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("headers") and data.get("columns"):
                cols = data.get("columns")
                if isinstance(cols, list):
                    headers = []
                    for c in cols:
                        if isinstance(c, dict):
                            headers.append(str(c.get("header") or c.get("name") or c.get("title") or ""))
                        else:
                            headers.append(str(c))
                    data["headers"] = headers
            elif isinstance(data.get("headers"), list):
                headers = []
                for h in data["headers"]:
                    if isinstance(h, dict):
                        headers.append(str(h.get("header") or h.get("name") or h.get("title") or ""))
                    else:
                        headers.append(str(h))
                data["headers"] = headers
        return data

class SpreadsheetSpec(BaseModel):
    """Specification for XLSX and CSV generators."""
    sheet_name: Optional[str] = Field(default="Data")
    headers: Optional[List[str]] = Field(default_factory=list)
    rows: Optional[List[List[Union[CellSpec, Any]]]] = Field(default_factory=list)
    sheets: Optional[List[SheetSpec]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_spreadsheet_data(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("headers") and data.get("columns"):
                cols = data.get("columns")
                if isinstance(cols, list):
                    headers = []
                    for c in cols:
                        if isinstance(c, dict):
                            headers.append(str(c.get("header") or c.get("name") or c.get("title") or ""))
                        else:
                            headers.append(str(c))
                    data["headers"] = headers
            elif isinstance(data.get("headers"), list):
                headers = []
                for h in data["headers"]:
                    if isinstance(h, dict):
                        headers.append(str(h.get("header") or h.get("name") or h.get("title") or ""))
                    else:
                        headers.append(str(h))
                data["headers"] = headers
        return data

    @model_validator(mode="after")
    def validate_spreadsheet(self) -> "SpreadsheetSpec":
        has_simple = bool(self.headers or self.rows)
        has_sheets = bool(self.sheets and len(self.sheets) > 0)
        if not has_simple and not has_sheets:
            raise ValueError("Spreadsheet spec must contain 'headers'/'rows' or 'sheets'.")
        return self

class SlideSpec(BaseModel):
    """Specification for a slide in a PowerPoint presentation."""
    title: Optional[str] = Field(default="")
    content: Optional[str] = Field(default=None)
    bullets: Optional[List[str]] = Field(default_factory=list)

class PresentationSpec(BaseModel):
    """Specification for PPTX presentation generator."""
    title: Optional[str] = Field(default=None)
    subtitle: Optional[str] = Field(default=None)
    slides: Optional[List[Union[SlideSpec, str, Dict[str, Any]]]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_presentation(self) -> "PresentationSpec":
        if not self.title and not self.slides:
            raise ValueError("Presentation spec must contain 'title' or 'slides'.")
        return self

class ChartSpec(BaseModel):
    """Specification for PNG chart generator."""
    chart_type: str = Field(default="bar")
    title: Optional[str] = Field(default="")
    x_label: Optional[str] = Field(default="")
    y_label: Optional[str] = Field(default="")
    x: Optional[List[Any]] = Field(default=None)
    y: Optional[List[Any]] = Field(default=None)
    labels: Optional[List[Any]] = Field(default=None)
    values: Optional[List[Any]] = Field(default=None)
    grid: Optional[bool] = Field(default=True)

    @field_validator("chart_type")
    @classmethod
    def check_chart_type(cls, v: str) -> str:
        allowed = {"bar", "line", "pie", "scatter"}
        if v.lower() not in allowed:
            raise ValueError(f"Unsupported chart_type '{v}'. Allowed types: {sorted(allowed)}.")
        return v.lower()

    @model_validator(mode="after")
    def validate_chart(self) -> "ChartSpec":
        has_x = bool(self.x or self.labels)
        has_y = bool(self.y or self.values)
        if not has_x and not has_y:
            raise ValueError("Chart spec must contain data points ('x'/'labels' and 'y'/'values').")
        return self

class MarkdownSpec(BaseModel):
    """Specification for Markdown document generator."""
    content: Optional[str] = Field(default=None)
    title: Optional[str] = Field(default=None)
    sections: Optional[List[Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_md(self) -> "MarkdownSpec":
        if not self.content and not self.title and not self.sections:
            raise ValueError("Markdown spec must contain 'content', 'title', or 'sections'.")
        return self

class CodeSpec(BaseModel):
    """Specification for source code generator."""
    code: Optional[str] = Field(default=None)
    content: Optional[str] = Field(default=None)
    language: Optional[str] = Field(default=None)

    @model_validator(mode="after")
    def validate_code(self) -> "CodeSpec":
        if not self.code and not self.content:
            raise ValueError("Code spec must contain 'code' or 'content'.")
        return self

SPEC_MODELS: Dict[str, type[BaseModel]] = {
    "pdf": DocumentSpec,
    "docx": DocumentSpec,
    "xlsx": SpreadsheetSpec,
    "csv": SpreadsheetSpec,
    "pptx": PresentationSpec,
    "chart": ChartSpec,
    "png": ChartSpec,
    "md": MarkdownSpec,
    "markdown": MarkdownSpec,
    "code": CodeSpec,
    "py": CodeSpec,
    "js": CodeSpec,
    "sql": CodeSpec,
}

def validate_spec_for_kind(kind: str, spec: dict) -> dict:
    """Validate a raw spec dict against its corresponding Pydantic model.
    Raises ValueError with formatted, actionable error descriptions on failure.
    """
    clean_kind = (kind or "").strip().lower().lstrip(".")
    model_cls = SPEC_MODELS.get(clean_kind)
    if not model_cls:
        return spec

    try:
        validated = model_cls.model_validate(spec)
        return validated.model_dump(exclude_unset=False)
    except Exception as exc:
        raise ValueError(f"Spec validation failed for '{kind}': {str(exc)}")
