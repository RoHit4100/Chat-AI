import openpyxl
from openpyxl.styles import Font, PatternFill
from filesvc.generators.base import BaseGenerator

class XlsxGenerator(BaseGenerator):
    """Generator for Excel (.xlsx) workbooks from structured spec using openpyxl."""
    default_extension = ".xlsx"

    def validate_spec(self, spec: dict) -> None:
        super().validate_spec(spec)
        has_simple = bool(spec.get("headers") or spec.get("rows"))
        has_sheets = bool(spec.get("sheets"))
        if not has_simple and not has_sheets:
            raise ValueError("XLSX spec must contain 'headers'/'rows' or 'sheets'.")

    def generate(self, spec: dict, output_path: str) -> None:
        self.validate_spec(spec)
        wb = openpyxl.Workbook()
        wb.remove(wb.active)  # Remove default active sheet

        sheets_spec = spec.get("sheets")
        if not sheets_spec:
            sheets_spec = [{
                "name": spec.get("sheet_name", "Data"),
                "headers": spec.get("headers", []),
                "rows": spec.get("rows", []),
            }]

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")

        for s_spec in sheets_spec:
            ws = wb.create_sheet(title=s_spec.get("name", "Sheet")[:31])
            headers = s_spec.get("headers", [])
            rows = s_spec.get("rows", [])

            if headers:
                ws.append(headers)
                for cell in ws[1]:
                    cell.font = header_font
                    cell.fill = header_fill

            for r in rows:
                ws.append(list(r) if isinstance(r, (list, tuple)) else [r])

        wb.save(output_path)

    def summarize_spec(self, spec: dict) -> str:
        sheets = spec.get("sheets")
        if sheets:
            count = len(sheets)
            total_rows = sum(len(s.get("rows", [])) for s in sheets)
            return f"XLSX with {count} sheet(s), {total_rows} row(s)"
        rows = len(spec.get("rows", []))
        cols = len(spec.get("headers", []))
        return f"XLSX with {rows} row(s), {cols} column(s)"
