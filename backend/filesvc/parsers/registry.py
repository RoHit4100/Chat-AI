from pathlib import Path
from filesvc.parsers.base import BaseParser
from filesvc.parsers.pdf import PdfParser
from filesvc.parsers.docx import DocxParser
from filesvc.parsers.spreadsheet import SpreadsheetParser
from filesvc.parsers.pptx import PptxParser
from filesvc.parsers.image import ImageParser
from filesvc.parsers.json_parser import JsonParser
from filesvc.parsers.zip_parser import ZipParser
from filesvc.parsers.text_code import TextCodeParser

PARSER_MAP: dict[str, type[BaseParser]] = {
    ".pdf": PdfParser,
    ".docx": DocxParser,
    ".xlsx": SpreadsheetParser,
    ".xls": SpreadsheetParser,
    ".csv": SpreadsheetParser,
    ".pptx": PptxParser,
    ".png": ImageParser,
    ".jpg": ImageParser,
    ".jpeg": ImageParser,
    ".gif": ImageParser,
    ".webp": ImageParser,
    ".svg": TextCodeParser,
    ".json": JsonParser,
    ".zip": ZipParser,
    ".txt": TextCodeParser,
    ".md": TextCodeParser,
    ".py": TextCodeParser,
    ".js": TextCodeParser,
    ".jsx": TextCodeParser,
    ".ts": TextCodeParser,
    ".tsx": TextCodeParser,
    ".html": TextCodeParser,
    ".css": TextCodeParser,
    ".yaml": TextCodeParser,
    ".yml": TextCodeParser,
    ".sh": TextCodeParser,
    ".sql": TextCodeParser,
}

def get_parser_for_file(filename: str, mime: str = "") -> BaseParser:
    """Resolve the parser instance for a given file name and MIME type."""
    ext = Path(filename).suffix.lower()
    parser_cls = PARSER_MAP.get(ext)
    if not parser_cls:
        if (mime or "").startswith("image/"):
            parser_cls = ImageParser
        elif (mime or "").startswith("text/"):
            parser_cls = TextCodeParser
        else:
            raise ValueError(f"No parser available for extension '{ext}' (MIME: {mime}).")
    return parser_cls()
