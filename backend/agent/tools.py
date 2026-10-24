import os
from pathlib import Path
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
import pandas as pd

from chat.models import UploadedFile
from filesvc.storage import storage

MAX_READ_CHUNK = int(os.getenv("MAX_READ_CHUNK", "4000"))

@tool
def search_web(query: str) -> str:
    """Search the web for up-to-date information on a given topic."""
    return f"Search results for: {query}. (Simulated placeholder output)"

@tool
def inspect_file(filename: str) -> str:
    """Inspect and retrieve summary information for an uploaded file."""
    return f"File inspection results for '{filename}': Valid structure, verified content."

@tool
def read_file(
    file_id: str,
    section: str | None = None,
    row_start: int | None = None,
    row_end: int | None = None,
    config: RunnableConfig = None,
) -> str:
    """Read contents of an uploaded file in bounded chunks.
    For spreadsheets, returns schema, row count, and a sample by default, or row ranges on request.
    For images, returns dimensions and vision model data.
    """
    try:
        uf = UploadedFile.objects.select_related("thread__user").get(id=file_id)
    except (UploadedFile.DoesNotExist, ValueError):
        return "Error: File not found."

    # Verify the file belongs to the current thread / user
    cfg_configurable = (config or {}).get("configurable", {})
    cfg_thread_id = cfg_configurable.get("thread_id")
    cfg_user_id = cfg_configurable.get("user_id")

    if cfg_thread_id and str(uf.thread_id) != str(cfg_thread_id):
        return "Error: File does not belong to the current thread."
    if cfg_user_id and str(uf.thread.user_id) != str(cfg_user_id):
        return "Error: Access denied. File does not belong to the current thread's user."

    # Read parsed metadata if available
    parsed_data = storage.read_parsed(uf.parsed_path) if uf.parsed_path else {}
    ext = Path(uf.name).suffix.lower()

    # Handle spreadsheets (.xlsx, .xls, .csv)
    if ext in (".xlsx", ".xls", ".csv") or "spreadsheet" in uf.mime:
        if row_start is not None or row_end is not None:
            # User requested specific row ranges
            try:
                if ext == ".csv":
                    df = pd.read_csv(uf.path)
                else:
                    df = pd.read_excel(uf.path)

                start_idx = max(0, (row_start or 1) - 1)
                end_idx = row_end if row_end is not None else (start_idx + 50)
                sliced = df.iloc[start_idx:end_idx]

                lines = [
                    f"Spreadsheet: {uf.name} (Rows {start_idx + 1} to {min(end_idx, len(df))} of {len(df)})",
                    sliced.to_string(index=True),
                ]
                output = "\n".join(lines)
            except Exception as exc:
                output = f"Error reading spreadsheet row range: {str(exc)}"
        else:
            # Default: schema, row count, and sample
            structured = parsed_data.get("structured_data") or {}
            schema = structured.get("schema", [])
            row_count = structured.get("row_count", 0)
            sample = structured.get("sample", [])

            lines = [
                f"Spreadsheet: {uf.name}",
                f"Total Rows: {row_count}",
                f"Schema: {schema}",
                f"Sample rows (first {len(sample)}):",
            ]
            for r in sample:
                lines.append(str(r))
            output = "\n".join(lines)

    # Handle images (return dimensions and vision model data)
    elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg") or uf.mime.startswith("image/"):
        image_info = parsed_data.get("image_info") or parsed_data.get("metadata") or {}
        w = image_info.get("width", "unknown")
        h = image_info.get("height", "unknown")
        fmt = image_info.get("format", ext.lstrip(".").upper())
        mode = image_info.get("mode", "RGB")
        output = (
            f"Image '{uf.name}': Dimensions {w}x{h} px, format {fmt}, mode {mode}.\n"
            f"Vision Model Payload ready for file_id {uf.id} ({uf.path})."
        )

    # Handle text, documents, PDF, PPTX, JSON, ZIP
    else:
        text_content = parsed_data.get("text", "")
        if not text_content and uf.path and os.path.exists(uf.path):
            try:
                with open(uf.path, "r", encoding="utf-8", errors="replace") as f:
                    text_content = f.read()
            except Exception:
                text_content = "Unable to read raw file."

        if section and text_content:
            # Search for section identifier (e.g. Page X, Slide Y, or header)
            lower_content = text_content.lower()
            target = str(section).lower()
            idx = lower_content.find(target)
            if idx != -1:
                start = max(0, idx - 50)
                end = min(len(text_content), idx + 2000)
                output = f"Section '{section}' of {uf.name}:\n" + text_content[start:end]
            else:
                output = f"Section '{section}' not found in {uf.name}. Initial content:\n" + text_content[:2000]
        else:
            output = text_content or f"File {uf.name} has no extractable text."

    # Cap output size and say when truncated
    if len(output) > MAX_READ_CHUNK:
        output = output[:MAX_READ_CHUNK] + "\n... [output truncated: remaining content omitted for safety]"

    return output

@tool
def failing_tool(query: str = "fail") -> str:
    """A tool designed to raise an error to verify error handling and loop termination."""
    raise ValueError(f"Simulated tool error executing query: {query}")

# Registered tools for agent node
ALL_TOOLS = [search_web, inspect_file, read_file, failing_tool]
