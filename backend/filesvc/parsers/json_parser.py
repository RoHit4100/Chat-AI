import json
from filesvc.parsers.base import BaseParser, ParsedResult

class JsonParser(BaseParser):
    """Parser for JSON files with validation and schema inspection."""

    def parse(self, file_path: str, original_filename: str) -> ParsedResult:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        formatted_text = json.dumps(data, indent=2, ensure_ascii=False)
        if isinstance(data, dict):
            keys = list(data.keys())
            preview_keys = ", ".join(str(k) for k in keys[:5]) + ("..." if len(keys) > 5 else "")
            summary = f"JSON object '{original_filename}': {len(keys)} key(s) [{preview_keys}]."
            metadata = {"type": "object", "keys": keys, "key_count": len(keys)}
        elif isinstance(data, list):
            summary = f"JSON array '{original_filename}': {len(data)} item(s)."
            metadata = {"type": "array", "item_count": len(data)}
        else:
            summary = f"JSON primitive '{original_filename}': {type(data).__name__}."
            metadata = {"type": type(data).__name__}

        return ParsedResult(
            text=formatted_text,
            summary=summary,
            metadata=metadata,
            structured_data=data,
        )
