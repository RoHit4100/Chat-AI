from filesvc.generators.base import BaseGenerator
from filesvc.generators.specs import validate_spec_for_kind

class CodeGenerator(BaseGenerator):
    """Generator for source code files from structured spec."""
    default_extension = ".py"

    def validate_spec(self, spec: dict) -> None:
        super().validate_spec(spec)
        validate_spec_for_kind("code", spec)

    def generate(self, spec: dict, output_path: str) -> None:
        self.validate_spec(spec)
        code = str(spec.get("code", ""))
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(code)

    def summarize_spec(self, spec: dict) -> str:
        lang = spec.get("language", "code")
        code = str(spec.get("code", ""))
        lines = len(code.splitlines())
        return f"Code ({lang}): {lines} line(s)"
