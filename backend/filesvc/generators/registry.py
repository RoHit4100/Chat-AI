from pathlib import Path
from filesvc.generators.base import BaseGenerator
from filesvc.generators.docx_gen import DocxGenerator
from filesvc.generators.pdf_gen import PdfGenerator
from filesvc.generators.xlsx_gen import XlsxGenerator
from filesvc.generators.csv_gen import CsvGenerator
from filesvc.generators.pptx_gen import PptxGenerator
from filesvc.generators.chart_gen import ChartGenerator
from filesvc.generators.md_gen import MarkdownGenerator
from filesvc.generators.code_gen import CodeGenerator

GENERATOR_MAP: dict[str, type[BaseGenerator]] = {
    "docx": DocxGenerator,
    "pdf": PdfGenerator,
    "xlsx": XlsxGenerator,
    "csv": CsvGenerator,
    "pptx": PptxGenerator,
    "chart": ChartGenerator,
    "png": ChartGenerator,
    "md": MarkdownGenerator,
    "markdown": MarkdownGenerator,
    "code": CodeGenerator,
    "py": CodeGenerator,
    "js": CodeGenerator,
    "sql": CodeGenerator,
}

def get_generator(kind: str) -> BaseGenerator:
    """Resolve and return generator instance for the specified file kind."""
    clean_kind = (kind or "").strip().lower().lstrip(".")
    gen_cls = GENERATOR_MAP.get(clean_kind)
    if not gen_cls:
        allowed = sorted(set(GENERATOR_MAP.keys()))
        raise ValueError(f"Unknown generator kind '{kind}'. Allowed kinds: {allowed}.")
    return gen_cls()

def get_default_extension(kind: str, name: str = "") -> str:
    """Get the appropriate extension for kind or keep existing extension from name."""
    if name and Path(name).suffix:
        return Path(name).suffix.lower()
    gen = get_generator(kind)
    return gen.default_extension

def summarize_spec(kind: str, spec: dict) -> str:
    """Produce a concise summary of the spec for the agent manifest."""
    try:
        gen = get_generator(kind)
        return gen.summarize_spec(spec)
    except Exception:
        return f"{kind.upper()} file specification"
