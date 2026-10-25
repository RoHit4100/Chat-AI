from filesvc.generators.base import BaseGenerator
from filesvc.generators.specs import validate_spec_for_kind

class MarkdownGenerator(BaseGenerator):
    """Generator for Markdown (.md) documents from structured spec."""
    default_extension = ".md"

    def validate_spec(self, spec: dict) -> None:
        super().validate_spec(spec)
        validate_spec_for_kind("md", spec)

    def generate(self, spec: dict, output_path: str) -> None:
        self.validate_spec(spec)
        lines = []

        title = spec.get("title")
        if title:
            lines.append(f"# {title}\n")

        description = spec.get("description")
        if description:
            lines.append(f"{description}\n")

        content = spec.get("content")
        if content:
            lines.append(str(content))

        for sec in spec.get("sections", []):
            if isinstance(sec, dict):
                heading = sec.get("heading")
                level = sec.get("level", 2)
                if heading:
                    lines.append(f"\n{'#' * level} {heading}\n")
                s_content = sec.get("content")
                if s_content:
                    lines.append(f"{s_content}\n")
                for b in sec.get("bullets", []):
                    lines.append(f"- {b}")
            elif isinstance(sec, str):
                lines.append(f"\n{sec}")

        full_md = "\n".join(lines).strip() + "\n"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_md)

    def summarize_spec(self, spec: dict) -> str:
        title = spec.get("title") or "Markdown Document"
        sections = len(spec.get("sections", []))
        chars = len(spec.get("content", ""))
        return f"Markdown '{title}' ({sections} section(s), {chars} char(s))"
