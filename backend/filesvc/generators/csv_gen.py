import csv
from filesvc.generators.base import BaseGenerator
from filesvc.generators.specs import validate_spec_for_kind

class CsvGenerator(BaseGenerator):
    """Generator for CSV spreadsheets from structured spec."""
    default_extension = ".csv"

    def validate_spec(self, spec: dict) -> None:
        super().validate_spec(spec)
        validate_spec_for_kind("csv", spec)

    def generate(self, spec: dict, output_path: str) -> None:
        self.validate_spec(spec)
        headers = spec.get("headers", [])
        rows = spec.get("rows", [])

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if headers:
                writer.writerow(headers)
            for r in rows:
                writer.writerow(list(r) if isinstance(r, (list, tuple)) else [r])

    def summarize_spec(self, spec: dict) -> str:
        rows = len(spec.get("rows", []))
        cols = len(spec.get("headers", []))
        return f"CSV with {rows} row(s), {cols} column(s)"
