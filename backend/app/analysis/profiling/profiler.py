import os
import re
import logging
from typing import Dict, Any, List
import duckdb
import polars as pl
import openpyxl
from app.analysis.excel.workbook import ExcelWorkbookService

logger = logging.getLogger(__name__)

class DataProfiler:
    @staticmethod
    def profile_file(file_path: str, filename: str) -> Dict[str, Any]:
        ext = os.path.splitext(filename)[1].lower()
        if ext in [".csv", ".txt"]:
            return DataProfiler._profile_csv(file_path)
        elif ext in [".xlsx", ".xls"]:
            return DataProfiler._profile_excel(file_path)
        else:
            raise ValueError(f"Unsupported file format for profiling: {ext}")

    @staticmethod
    def _profile_csv(file_path: str) -> Dict[str, Any]:
        # Read using Polars with automatic type inference
        df = pl.read_csv(file_path, infer_schema_length=10000, ignore_errors=True)
        return DataProfiler._extract_profile_from_df(df, sheet_names=["Sheet1"])

    @staticmethod
    def _profile_excel(file_path: str) -> Dict[str, Any]:
        workbook_meta = ExcelWorkbookService.profile(file_path)
        sheet_names = workbook_meta["sheets"]

        # Read first/primary sheet via Polars
        primary_sheet = sheet_names[0] if sheet_names else "Sheet1"
        try:
            df = pl.read_excel(file_path, sheet_name=primary_sheet)
        except Exception:
            # Fallback using DuckDB excel extension or openpyxl
            import pandas as pd
            pdf = pd.read_excel(file_path, sheet_name=primary_sheet)
            df = pl.from_pandas(pdf)

        profile = DataProfiler._extract_profile_from_df(df, sheet_names=sheet_names)
        profile["sheet_profiles"] = workbook_meta["sheet_profiles"]
        profile["formula_count"] = workbook_meta["formula_count"]
        profile["workbook_type"] = workbook_meta["workbook_type"]
        return profile

    @staticmethod
    def _extract_profile_from_df(df: pl.DataFrame, sheet_names: List[str]) -> Dict[str, Any]:
        row_count = df.height
        columns_profile = []

        for col_name in df.columns:
            series = df[col_name]
            null_count = series.null_count()
            unique_count = series.n_unique()
            dtype_str = str(series.dtype).lower()

            # Map polars type to clean simplified type
            if "int" in dtype_str:
                inferred = "integer"
            elif "float" in dtype_str:
                inferred = "float"
            elif "bool" in dtype_str:
                inferred = "boolean"
            elif "date" in dtype_str or "time" in dtype_str:
                inferred = "datetime"
            else:
                inferred = "string"

            # Get up to 5 non-null sample values
            samples = series.drop_nulls().head(5).to_list()
            # Clean samples for json serialization
            clean_samples = [str(s) for s in samples]

            col_meta: Dict[str, Any] = {
                "name": col_name,
                "inferred_type": inferred,
                "null_count": null_count,
                "unique_count": unique_count,
                "sample_values": clean_samples,
            }

            if inferred == "string" and 1 < unique_count <= 100:
                try:
                    top_values = series.value_counts(sort=True).head(20).to_dicts()
                    col_meta["top_values"] = {
                        str(item[col_name]): int(item["count"])
                        for item in top_values
                    }
                except Exception:
                    col_meta["top_values"] = {}

            if inferred == "string":
                domain_counts: Dict[str, int] = {}
                for value in series.drop_nulls().to_list():
                    for domain in re.findall(r"@([A-Za-z0-9.-]+)", str(value).lower()):
                        domain_counts[domain] = domain_counts.get(domain, 0) + 1
                if domain_counts:
                    col_meta["domain_counts"] = dict(
                        sorted(domain_counts.items(), key=lambda item: item[1], reverse=True)[:20]
                    )

            if inferred in ["integer", "float"] and row_count > 0:
                try:
                    col_meta["min"] = float(series.min()) if series.min() is not None else None
                    col_meta["max"] = float(series.max()) if series.max() is not None else None
                    col_meta["mean"] = round(float(series.mean()), 2) if series.mean() is not None else None
                except Exception:
                    pass

            columns_profile.append(col_meta)

        return {
            "sheets": sheet_names,
            "row_count": row_count,
            "column_count": len(df.columns),
            "columns": columns_profile
        }
