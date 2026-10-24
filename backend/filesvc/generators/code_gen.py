from filesvc.generators.base import BaseGenerator

class CodeGenerator(BaseGenerator):
    """Generator for source code files from structured spec."""
    default_extension = ".py"

    def validate_spec(self, spec: dict) -> None:
        super().validate_spec(spec)
        if "code" not in spec:
            raise ValueError("Code spec must contain 'code' string field.")

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
