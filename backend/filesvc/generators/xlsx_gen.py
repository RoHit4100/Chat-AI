import os
import shutil
import tempfile
import subprocess
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from filesvc.generators.base import BaseGenerator
from filesvc.generators.specs import validate_spec_for_kind

def recalculate_with_libreoffice(file_path: str) -> bool:
    """Recalculate formulas in Excel workbook using headless LibreOffice Calc to write cached values."""
    abs_path = os.path.abspath(file_path)
    if not os.path.exists(abs_path):
        return False

    out_dir = tempfile.mkdtemp(prefix="soffice_out_")
    profile_dir = tempfile.mkdtemp(prefix="soffice_profile_")
    try:
        env = os.environ.copy()
        env["SAL_USE_VCLPLUGIN"] = "svp"
        cmd = [
            "soffice",
            f"-env:UserInstallation=file://{profile_dir}",
            "--headless",
            "--convert-to", "xlsx",
            "--outdir", out_dir,
            abs_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
        base_name = os.path.basename(abs_path)
        conv_path = os.path.join(out_dir, base_name)
        if os.path.exists(conv_path) and os.path.getsize(conv_path) > 0:
            shutil.copy2(conv_path, abs_path)
            return True
        return False
    except Exception:
        return False
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        shutil.rmtree(profile_dir, ignore_errors=True)

class XlsxGenerator(BaseGenerator):
    """Generator for Excel (.xlsx) workbooks from structured spec with cached values, formatting, and headless recalculation."""
    default_extension = ".xlsx"

    def validate_spec(self, spec: dict) -> None:
        super().validate_spec(spec)
        validate_spec_for_kind("xlsx", spec)

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

        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        total_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
        total_font = Font(name="Calibri", size=11, bold=True)
        total_border = Border(
            top=Side(style="thin", color="808080"),
            bottom=Side(style="double", color="000000"),
        )
        data_font = Font(name="Calibri", size=11)

        has_formulas = False

        for s_spec in sheets_spec:
            ws = wb.create_sheet(title=str(s_spec.get("name", "Sheet"))[:31])
            headers = s_spec.get("headers", [])
            rows = s_spec.get("rows", [])

            current_row = 1
            if headers:
                for col_idx, h in enumerate(headers, start=1):
                    cell = ws.cell(row=current_row, column=col_idx, value=str(h) if h is not None else "")
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                current_row += 1

            for row in rows:
                if not isinstance(row, (list, tuple)):
                    row = [row]

                is_total_row = False
                if len(row) > 0:
                    first_val = row[0]
                    if isinstance(first_val, dict):
                        first_val = first_val.get("value")
                    if first_val and str(first_val).strip().lower() == "total":
                        is_total_row = True

                for col_idx, item in enumerate(row, start=1):
                    cell = ws.cell(row=current_row, column=col_idx)

                    val = None
                    formula = None
                    num_fmt = None
                    bold = is_total_row

                    if isinstance(item, dict):
                        val = item.get("value")
                        formula = item.get("formula")
                        num_fmt = item.get("number_format")
                        if item.get("bold") is not None:
                            bold = bool(item.get("bold"))
                    else:
                        if isinstance(item, str) and item.startswith("="):
                            formula = item
                        else:
                            val = item

                    # If formula given, write formula and trigger headless recalc
                    if formula:
                        cell.value = str(formula)
                        has_formulas = True
                    elif val is not None and val != "":
                        cell.value = val
                    else:
                        cell.value = None

                    # Infer / apply number formatting
                    header_text = str(headers[col_idx - 1] if col_idx <= len(headers) else "").lower()
                    if num_fmt:
                        cell.number_format = str(num_fmt)
                    elif isinstance(val, float) and ("growth" in header_text or "%" in header_text):
                        cell.number_format = "0.0%"
                    elif isinstance(val, (int, float)) and any(k in header_text for k in ["revenue", "amount", "total", "sales", "units", "inr"]):
                        cell.number_format = "#,##0"

                    if is_total_row:
                        cell.font = total_font
                        cell.fill = total_fill
                        cell.border = total_border
                    elif bold:
                        cell.font = Font(name="Calibri", size=11, bold=True)
                    else:
                        cell.font = data_font

                current_row += 1

            # Auto-fit column widths
            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    v_str = str(cell.value or "")
                    if cell.number_format and "0" in cell.number_format and len(v_str) < 10:
                        v_str = v_str + "    "
                    max_len = max(max_len, len(v_str))
                ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

        wb.save(output_path)

        if has_formulas:
            recalculate_with_libreoffice(output_path)

    def summarize_spec(self, spec: dict) -> str:
        sheets = spec.get("sheets")
        if sheets:
            count = len(sheets)
            total_rows = sum(len(s.get("rows", [])) for s in sheets)
            return f"XLSX with {count} sheet(s), {total_rows} row(s)"
        rows = len(spec.get("rows", []))
        cols = len(spec.get("headers", []))
        return f"XLSX with {rows} row(s), {cols} column(s)"
