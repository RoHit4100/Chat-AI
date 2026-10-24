from pathlib import Path
import pandas as pd
from filesvc.parsers.base import BaseParser, ParsedResult

class SpreadsheetParser(BaseParser):
    """Parser for spreadsheets (.xlsx, .xls, .csv) using pandas and openpyxl."""

    def parse(self, file_path: str, original_filename: str) -> ParsedResult:
        ext = Path(original_filename).suffix.lower()
        if ext == ".csv":
            try:
                df = pd.read_csv(file_path, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(file_path, encoding="latin-1")
        else:
            df = pd.read_excel(file_path)

        columns = [str(c) for c in df.columns]
        row_count = len(df)
        col_count = len(columns)
        schema = [{"column": col, "type": str(df[col].dtype)} for col in columns]

        # Convert sample head rows to JSON-safe primitives
        sample_df = df.head(10).fillna("")
        sample_records = sample_df.to_dict(orient="records")

        # Human-readable formatted preview text
        preview_lines = [
            f"Spreadsheet: {original_filename}",
            f"Rows: {row_count}, Columns: {col_count}",
            f"Schema: {', '.join(f'{c} ({df[c].dtype})' for c in columns)}",
            "--- Sample Data (first 10 rows) ---",
        ]
        for i, row in enumerate(sample_records):
            preview_lines.append(f"Row {i + 1}: {row}")

        full_text = "\n".join(preview_lines)
        cols_summary = ", ".join(columns[:6]) + ("..." if len(columns) > 6 else "")
        summary = f"Spreadsheet '{original_filename}': {row_count} rows, {col_count} columns [{cols_summary}]."

        return ParsedResult(
            text=full_text,
            summary=summary,
            metadata={
                "row_count": row_count,
                "column_count": col_count,
                "columns": columns,
                "schema": schema,
            },
            structured_data={
                "columns": columns,
                "row_count": row_count,
                "schema": schema,
                "sample": sample_records,
            },
        )
