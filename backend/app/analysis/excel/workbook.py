import hashlib
import json
import os
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from openpyxl import load_workbook


MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1_000
MAX_ROWS = 100_000


class ExcelWorkbookError(ValueError):
    pass


class ExcelWorkbookService:
    """Read-only XLSX inspection with bounded ZIP and row handling."""

    @staticmethod
    def _validate_path(path: str) -> Path:
        file_path = Path(path).resolve()
        if not file_path.is_file():
            raise ExcelWorkbookError("Workbook does not exist.")
        if file_path.suffix.lower() != ".xlsx":
            raise ExcelWorkbookError("Only .xlsx workbooks are supported by the Excel runtime skill.")
        if file_path.stat().st_size > MAX_FILE_BYTES:
            raise ExcelWorkbookError("Workbook exceeds the safe 50 MB size limit.")
        try:
            with zipfile.ZipFile(file_path) as archive:
                members = archive.infolist()
                if len(members) > MAX_ARCHIVE_MEMBERS:
                    raise ExcelWorkbookError("Workbook contains too many ZIP members.")
                total_size = sum(member.file_size for member in members)
                if total_size > MAX_UNCOMPRESSED_BYTES:
                    raise ExcelWorkbookError("Workbook exceeds the safe decompressed size limit.")
                for member in members:
                    if member.compress_size and member.file_size / member.compress_size > MAX_COMPRESSION_RATIO:
                        raise ExcelWorkbookError("Workbook contains an unsafe compression ratio.")
        except zipfile.BadZipFile as exc:
            raise ExcelWorkbookError("Workbook is not a valid XLSX ZIP package.") from exc
        return file_path

    @staticmethod
    def _open(path: str):
        file_path = ExcelWorkbookService._validate_path(path)
        return load_workbook(
            filename=file_path,
            read_only=True,
            data_only=False,
            keep_links=False,
            keep_vba=False,
        )

    @staticmethod
    def _text(value: Any) -> str:
        return "" if value is None else str(value).strip()

    @staticmethod
    def _headers(values: Sequence[Any]) -> List[str]:
        headers: List[str] = []
        seen: Dict[str, int] = defaultdict(int)
        for index, value in enumerate(values, start=1):
            base = ExcelWorkbookService._text(value) or f"Column_{index}"
            seen[base] += 1
            headers.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
        return headers

    @staticmethod
    def profile(path: str) -> Dict[str, Any]:
        file_path = ExcelWorkbookService._validate_path(path)
        workbook = load_workbook(
            filename=file_path,
            read_only=True,
            data_only=False,
            keep_links=False,
            keep_vba=False,
        )
        table_workbook = load_workbook(
            filename=file_path,
            read_only=False,
            data_only=False,
            keep_links=False,
            keep_vba=False,
        )
        profiles: List[Dict[str, Any]] = []
        try:
            for sheet in workbook.worksheets:
                header_values = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
                headers = ExcelWorkbookService._headers(header_values)
                formula_count = 0
                formula_samples: List[Dict[str, Any]] = []
                nonempty_rows = 0
                for row_number, row in enumerate(sheet.iter_rows(values_only=False), start=1):
                    values = [cell.value for cell in row]
                    if any(value is not None for value in values):
                        nonempty_rows += 1
                    for cell in row:
                        if isinstance(cell.value, str) and cell.value.startswith("="):
                            formula_count += 1
                            if len(formula_samples) < 20:
                                formula_samples.append({
                                    "cell": cell.coordinate,
                                    "formula": cell.value,
                                })
                profiles.append({
                    "name": sheet.title,
                    "headers": headers,
                    "row_count": max(0, nonempty_rows - 1),
                    "column_count": len(headers),
                    "max_row": sheet.max_row or 0,
                    "max_column": sheet.max_column or 0,
                    "tables": sorted(list(table_workbook[sheet.title].tables.keys())),
                    "formula_count": formula_count,
                    "formula_samples": formula_samples,
                })
        finally:
            workbook.close()
            table_workbook.close()
        return {
            "workbook_type": "xlsx",
            "sheets": [sheet["name"] for sheet in profiles],
            "sheet_profiles": profiles,
            "formula_count": sum(sheet["formula_count"] for sheet in profiles),
        }

    @staticmethod
    def _records(path: str, sheet_name: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        workbook = ExcelWorkbookService._open(path)
        try:
            if sheet_name not in workbook.sheetnames:
                raise ExcelWorkbookError(f"Worksheet '{sheet_name}' does not exist.")
            sheet = workbook[sheet_name]
            header_values = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
            headers = ExcelWorkbookService._headers(header_values)
            records: List[Dict[str, Any]] = []
            for source_row, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                row = list(values[: len(headers)])
                if not any(value is not None and value != "" for value in row):
                    continue
                if len(records) >= MAX_ROWS:
                    raise ExcelWorkbookError("Worksheet exceeds the safe 100,000-row analysis limit.")
                records.append({
                    header: row[index] if index < len(row) else None
                    for index, header in enumerate(headers)
                } | {"_source_row": source_row})
            return headers, records
        finally:
            workbook.close()

    @staticmethod
    def find_duplicates(path: str, sheet_name: str, columns: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        headers, records = ExcelWorkbookService._records(path, sheet_name)
        key_columns = list(columns or headers)
        missing = [column for column in key_columns if column not in headers]
        if missing:
            raise ExcelWorkbookError(f"Duplicate key columns not found: {missing}")
        groups: Dict[Tuple[Any, ...], List[int]] = defaultdict(list)
        for record in records:
            key = tuple(record.get(column) for column in key_columns)
            if all(value is None or value == "" for value in key):
                continue
            groups[key].append(record["_source_row"])
        duplicate_groups = [
            {"key": dict(zip(key_columns, key)), "source_rows": rows}
            for key, rows in groups.items() if len(rows) > 1
        ]
        return {
            "operation": "duplicate_detection",
            "sheet": sheet_name,
            "key_columns": key_columns,
            "duplicate_group_count": len(duplicate_groups),
            "duplicate_row_count": sum(len(group["source_rows"]) for group in duplicate_groups),
            "duplicate_groups": duplicate_groups,
            "evidence_rows": [row for group in duplicate_groups for row in group["source_rows"]][:100],
            "source_row_count": len(records),
        }

    @staticmethod
    def missing_values(path: str, sheet_name: str) -> Dict[str, Any]:
        headers, records = ExcelWorkbookService._records(path, sheet_name)
        counts = {header: 0 for header in headers}
        evidence: Dict[str, List[int]] = {header: [] for header in headers}
        for record in records:
            for header in headers:
                if record.get(header) is None or record.get(header) == "":
                    counts[header] += 1
                    if len(evidence[header]) < 20:
                        evidence[header].append(record["_source_row"])
        return {
            "operation": "missing_value_detection",
            "sheet": sheet_name,
            "missing_counts": counts,
            "evidence_rows": sorted({row for rows in evidence.values() for row in rows}),
            "evidence_by_column": evidence,
            "source_row_count": len(records),
        }

    @staticmethod
    def compare_sheets(path: str, left_sheet: str, right_sheet: str, key_columns: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        left_headers, left_records = ExcelWorkbookService._records(path, left_sheet)
        right_headers, right_records = ExcelWorkbookService._records(path, right_sheet)
        common = [column for column in left_headers if column in right_headers]
        keys = list(key_columns or common[:1])
        if not keys:
            raise ExcelWorkbookError("The sheets do not share a comparison column.")
        left_by_key = {tuple(record.get(key) for key in keys): record for record in left_records}
        right_by_key = {tuple(record.get(key) for key in keys): record for record in right_records}
        left_only = sorted(set(left_by_key) - set(right_by_key), key=str)
        right_only = sorted(set(right_by_key) - set(left_by_key), key=str)
        changed: List[Dict[str, Any]] = []
        compare_columns = [column for column in common if column not in keys]
        for key in sorted(set(left_by_key) & set(right_by_key), key=str):
            differences = {
                column: {"left": left_by_key[key].get(column), "right": right_by_key[key].get(column)}
                for column in compare_columns
                if left_by_key[key].get(column) != right_by_key[key].get(column)
            }
            if differences:
                changed.append({
                    "key": dict(zip(keys, key)),
                    "differences": differences,
                    "left_source_row": left_by_key[key]["_source_row"],
                    "right_source_row": right_by_key[key]["_source_row"],
                })
        return {
            "operation": "multi_sheet_comparison",
            "left_sheet": left_sheet,
            "right_sheet": right_sheet,
            "key_columns": keys,
            "left_only_count": len(left_only),
            "right_only_count": len(right_only),
            "changed_count": len(changed),
            "left_only": [dict(zip(keys, key)) for key in left_only[:100]],
            "right_only": [dict(zip(keys, key)) for key in right_only[:100]],
            "changed": changed[:100],
            "evidence_rows": [item["left_source_row"] for item in changed[:100]],
            "source_row_count": len(left_records) + len(right_records),
        }

    @staticmethod
    def inspect_formulas(path: str, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        profile = ExcelWorkbookService.profile(path)
        selected = [
            sheet for sheet in profile["sheet_profiles"]
            if sheet_name is None or sheet["name"] == sheet_name
        ]
        if sheet_name and not selected:
            raise ExcelWorkbookError(f"Worksheet '{sheet_name}' does not exist.")
        return {
            "operation": "formula_inspection",
            "sheets": selected,
            "formula_count": sum(sheet["formula_count"] for sheet in selected),
            "calculated": False,
            "note": "Formula text was inspected without executing or recalculating workbook formulas.",
            "source_row_count": sum(sheet["row_count"] for sheet in selected),
        }

    @staticmethod
    def _result(operation: Dict[str, Any], file_id: str = "") -> Dict[str, Any]:
        rows = operation.get("rows") or []
        result = {
            "columns": list(rows[0].keys()) if rows else ["operation"],
            "rows": rows,
            "row_count": len(rows),
            "matched_row_count": operation.get("source_row_count", len(rows)),
            "source_row_count": operation.get("source_row_count"),
            "evidence_rows": operation.get("evidence_rows", []),
            "engine": "openpyxl",
            "workbook_operation": operation.get("operation"),
            "source_file_id": file_id,
        }
        result["query_hash"] = hashlib.sha256(json.dumps(operation, sort_keys=True, default=str).encode()).hexdigest()
        result["result_hash"] = hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()
        return result

    @staticmethod
    def run_question(path: str, question: str, profile: Dict[str, Any], file_id: str = "") -> Optional[Dict[str, Any]]:
        text = (question or "").lower()
        sheets = profile.get("sheets", [])
        if not sheets:
            return None
        if any(term in text for term in ("compare", "difference", "differences")) and len(sheets) >= 2:
            mentioned_sheets = [sheet for sheet in sheets if sheet.lower() in text]
            selected_sheets = mentioned_sheets if len(mentioned_sheets) >= 2 else sheets[:2]
            operation = ExcelWorkbookService.compare_sheets(path, selected_sheets[0], selected_sheets[1])
        elif any(term in text for term in ("duplicate", "duplicates")):
            headers = profile.get("sheet_profiles", [{}])[0].get("headers", [])
            key_columns = [header for header in headers if re.search(r"employee|employee id|staff|user id|^id$|name", header, re.I)]
            operation = ExcelWorkbookService.find_duplicates(path, sheets[0], key_columns[:1] or headers)
        elif any(term in text for term in ("missing", "blank", "null", "empty")):
            operation = ExcelWorkbookService.missing_values(path, sheets[0])
        elif "formula" in text or "calculation" in text:
            operation = ExcelWorkbookService.inspect_formulas(path)
        else:
            return None
        if operation["operation"] == "duplicate_detection":
            operation["rows"] = operation["duplicate_groups"]
        elif operation["operation"] == "missing_value_detection":
            operation["rows"] = [{"sheet": operation["sheet"], "missing_counts": operation["missing_counts"]}]
        elif operation["operation"] == "multi_sheet_comparison":
            operation["rows"] = [{
                key: operation[key]
                for key in ("left_sheet", "right_sheet", "left_only_count", "right_only_count", "changed_count")
            }]
        elif operation["operation"] == "formula_inspection":
            operation["rows"] = [
                dict(sheet, note=operation["note"])
                for sheet in operation["sheets"]
            ]
        return ExcelWorkbookService._result(operation, file_id)

    @staticmethod
    def explain(result: Dict[str, Any], question: str) -> str:
        operation = result.get("workbook_operation")
        if operation == "duplicate_detection":
            return f"Found **{sum(len(group.get('source_rows', [])) for group in result.get('rows', []))}** duplicate records in the workbook."
        if operation == "missing_value_detection":
            counts = result.get("rows", [{}])[0].get("missing_counts", {}) if result.get("rows") else {}
            return "Missing-value scan completed: " + ", ".join(f"**{key}** ({value})" for key, value in counts.items() if value) if any(counts.values()) else "No missing values were detected."
        if operation == "multi_sheet_comparison":
            row = result.get("rows", [{}])[0] if result.get("rows") else {}
            return f"Compared **{row.get('left_sheet')}** with **{row.get('right_sheet')}**: **{row.get('changed_count', 0)}** changed, **{row.get('left_only_count', 0)}** left-only, and **{row.get('right_only_count', 0)}** right-only records."
        if operation == "formula_inspection":
            return f"Inspected **{result.get('row_count', 0)}** workbook formula summary rows without recalculating formulas."
        return "Workbook analysis completed deterministically."

    @staticmethod
    def sanitize_export_value(value: Any) -> Any:
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
            return "'" + value
        return value
