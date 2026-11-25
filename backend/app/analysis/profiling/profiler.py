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
        if ext == ".csv":
            return DataProfiler._profile_csv(file_path)
        elif ext in [".xlsx", ".xls"]:
            return DataProfiler._profile_excel(file_path)
        elif ext == ".parquet":
            return DataProfiler._profile_parquet(file_path)
        else:
            raise ValueError(f"Unsupported file format for profiling: {ext}")

    @staticmethod
    def _profile_parquet(file_path: str) -> Dict[str, Any]:
        df = pl.read_parquet(file_path)
        return DataProfiler._extract_profile_from_df(df, sheet_names=["Sheet1"])

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
    def _classify_column_role(
        col_name: str,
        inferred_type: str,
        row_count: int,
        unique_count: int,
        null_count: int,
        zero_count: int,
        non_zero_count: int,
        sample_values: List[str]
    ) -> str:
        name_lower = col_name.strip().lower()

        # 1. Timestamp
        if inferred_type == "datetime":
            return "timestamp"
        if any(term in name_lower for term in ["time", "date", "timestamp", "datetime", "created_at", "updated_at"]):
            return "timestamp"

        # 2. Flag
        if inferred_type == "boolean":
            return "flag"
        if unique_count <= 2 and (name_lower.startswith("is_") or name_lower.startswith("has_")):
            return "flag"

        # 3. Identifier
        id_suffixes = ("_id", " id", "id", "_key", " key", "_code", " code", "_no", " no", "number")
        if (any(name_lower.endswith(sfx) or name_lower == sfx for sfx in id_suffixes)
                and inferred_type != "float" and row_count > 0 and (unique_count / row_count > 0.4 or unique_count >= 100)):
            return "identifier"

        # 4. Status
        if inferred_type == "string" and (
            name_lower in {"status", "action", "severity", "state", "stage", "action_status", "channel"}
            or (1 < unique_count <= 20 and any(kw in name_lower for kw in ["status", "action", "severity", "stage", "channel", "priority"]))
        ):
            return "status"

        # 5. Text
        if inferred_type == "string" and (
            any(len(str(s)) > 80 for s in sample_values)
            or name_lower in {"description", "policies", "policy", "notes", "comment", "file name", "file_name", "message", "query"}
        ):
            return "text"

        # 6. Numeric Measures vs Sparse Measures
        if inferred_type in ["integer", "float"]:
            # If zero or null indicates absent event (e.g. debit/credit entries, refund, discounts)
            if row_count > 0 and (null_count > 0 or zero_count > 0) and non_zero_count > 0:
                return "sparse_measure"
            return "measure"

        # 7. Dimension (categorical grouping field)
        if inferred_type == "string":
            return "dimension"

        return "dimension"

    @staticmethod
    def _extract_profile_from_df(df: pl.DataFrame, sheet_names: List[str]) -> Dict[str, Any]:
        row_count = df.height
        columns_profile = []

        for col_name in df.columns:
            series = df[col_name]
            null_count = int(series.null_count())
            unique_count = int(series.n_unique())
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

            zero_count = 0
            non_zero_count = 0
            if inferred in ["integer", "float"] and row_count > 0:
                try:
                    zero_count = int((series == 0).sum())
                    non_zero_count = int(((series != 0) & series.is_not_null()).sum())
                except Exception:
                    zero_count = 0
                    non_zero_count = max(0, row_count - null_count)

            role = DataProfiler._classify_column_role(
                col_name=col_name,
                inferred_type=inferred,
                row_count=row_count,
                unique_count=unique_count,
                null_count=null_count,
                zero_count=zero_count,
                non_zero_count=non_zero_count,
                sample_values=clean_samples,
            )

            col_meta: Dict[str, Any] = {
                "name": col_name,
                "inferred_type": inferred,
                "role": role,
                "null_count": null_count,
                "unique_count": unique_count,
                "distinct_count": unique_count,
                "zero_count": zero_count,
                "non_zero_count": non_zero_count,
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
