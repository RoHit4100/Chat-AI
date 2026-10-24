from filesvc.parsers.base import BaseParser, ParsedResult

class TextCodeParser(BaseParser):
    """Parser for plain text, markdown, configuration, and source code files."""

    def parse(self, file_path: str, original_filename: str) -> ParsedResult:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="latin-1", errors="replace") as f:
                content = f.read()

        lines = content.splitlines()
        line_count = len(lines)
        char_count = len(content)

        preview = (content[:200].replace("\n", " ").strip()) if content else "Empty file"
        summary = f"Text/Code file '{original_filename}': {line_count} lines ({char_count} chars). Preview: {preview}"

        return ParsedResult(
            text=content,
            summary=summary,
            metadata={
                "line_count": line_count,
                "char_count": char_count,
            },
        )
