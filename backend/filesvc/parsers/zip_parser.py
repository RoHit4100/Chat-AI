import zipfile
from filesvc.parsers.base import BaseParser, ParsedResult
from filesvc.validators import validate_zip_safety

class ZipParser(BaseParser):
    """Parser for ZIP archives enforcing strict safety constraints."""

    def parse(self, file_path: str, original_filename: str) -> ParsedResult:
        with zipfile.ZipFile(file_path, "r") as zf:
            # Enforce member count, zip bomb, traversal, and nested archive checks
            validate_zip_safety(zf)

            members_info = []
            preview_texts = []
            total_uncompressed = 0

            for info in zf.infolist():
                if info.is_dir():
                    continue
                total_uncompressed += info.file_size
                members_info.append({
                    "filename": info.filename,
                    "file_size": info.file_size,
                    "compress_size": info.compress_size,
                })
                # Read sample text snippet for small text files inside archive
                if info.file_size < 32768 and any(info.filename.lower().endswith(ext) for ext in (".txt", ".md", ".json", ".csv", ".py")):
                    try:
                        sample_bytes = zf.read(info.filename)
                        sample_str = sample_bytes.decode("utf-8", errors="replace")[:200]
                        preview_texts.append(f"[{info.filename}]: {sample_str}")
                    except Exception:
                        pass

            lines = [
                f"ZIP Archive: {original_filename}",
                f"Safe Members: {len(members_info)} file(s)",
                f"Total Uncompressed Size: {total_uncompressed} bytes",
                "--- File Manifest in Archive ---",
            ]
            for m in members_info:
                lines.append(f"- {m['filename']} ({m['file_size']} bytes)")

            if preview_texts:
                lines.append("--- Extracted Previews ---")
                lines.extend(preview_texts)

            full_text = "\n".join(lines)
            summary = f"ZIP archive '{original_filename}': {len(members_info)} member(s), {total_uncompressed} bytes uncompressed."

            return ParsedResult(
                text=full_text,
                summary=summary,
                metadata={
                    "member_count": len(members_info),
                    "total_uncompressed": total_uncompressed,
                    "members": members_info,
                },
                structured_data={
                    "members": members_info,
                    "member_count": len(members_info),
                    "total_uncompressed": total_uncompressed,
                },
            )
