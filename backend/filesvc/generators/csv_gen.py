import csv
from filesvc.generators.base import BaseGenerator

class CsvGenerator(BaseGenerator):
    """Generator for CSV spreadsheets from structured spec."""
    default_extension = ".csv"

    def validate_spec(self, spec: dict) -> None:
        super().validate_spec(spec)
        if not spec.get("headers") and not spec.get("rows"):
            raise ValueError("CSV spec must contain 'headers' or 'rows'.")

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
