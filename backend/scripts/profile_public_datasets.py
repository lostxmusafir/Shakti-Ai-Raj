"""Profile acquired public sources and update their provenance manifest."""

import argparse
import json
import sys
import zipfile
from pathlib import Path

import duckdb
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.profiling.profiler import DataProfiler
from app.learning.acquisition import DatasetAcquisition


def _profile_path(path: Path) -> tuple[int, int]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        connection = duckdb.connect(":memory:")
        try:
            row_count = connection.execute("SELECT COUNT(*) FROM read_csv_auto(?)", [str(path)]).fetchone()[0]
            column_count = len(connection.execute("DESCRIBE SELECT * FROM read_csv_auto(?)", [str(path)]).fetchall())
            return int(row_count), int(column_count)
        finally:
            connection.close()
    if suffix in {".xlsx", ".xls"}:
        try:
            profile = DataProfiler.profile_file(str(path), path.name)
            return int(profile.get("row_count", 0)), int(profile.get("column_count", 0))
        except Exception:
            if suffix != ".xlsx":
                raise
            workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False, keep_vba=False)
            try:
                sheet = workbook[workbook.sheetnames[0]]
                return max(0, (sheet.max_row or 0) - 1), int(sheet.max_column or 0)
            finally:
                workbook.close()
    if suffix == ".parquet":
        connection = duckdb.connect(":memory:")
        try:
            row_count = connection.execute("SELECT COUNT(*) FROM read_parquet(?)", [str(path)]).fetchone()[0]
            column_count = len(connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall())
            return int(row_count), int(column_count)
        finally:
            connection.close()
    raise ValueError(f"Unsupported profile format: {path.suffix}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/benchmark/manifests/public_sources.json")
    parser.add_argument("--output-dir", default="data/benchmark/public")
    parser.add_argument("--dataset", action="append", dest="datasets")
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    records = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    for record in records:
        if args.datasets and record.get("dataset_id") not in set(args.datasets):
            continue
        if record.get("retrieval_status") not in {"downloaded", "already_present"}:
            continue
        path = Path(record["file_path"])
        try:
            profile_path = path
            if path.suffix.lower() == ".zip":
                extract_dir = output_dir / "extracted" / record["dataset_id"]
                extracted = DatasetAcquisition._safe_extract(path, extract_dir, 250 * 1024 * 1024)
                archives = [Path(item) for item in extracted if Path(item).suffix.lower() == ".zip"]
                while archives:
                    nested = archives.pop(0)
                    nested_dir = nested.with_suffix(nested.suffix + "_extracted")
                    nested_extracted = DatasetAcquisition._safe_extract(nested, nested_dir, 250 * 1024 * 1024)
                    extracted.extend(nested_extracted)
                    archives.extend(Path(item) for item in nested_extracted if Path(item).suffix.lower() == ".zip")
                candidates = [Path(item) for item in extracted if Path(item).suffix.lower() in {".xlsx", ".csv", ".parquet"}]
                if not candidates:
                    raise ValueError("Archive contains no supported tabular file.")
                profile_path = sorted(candidates, key=lambda item: item.name.lower())[0]
            rows, columns = _profile_path(profile_path)
            record.update({
                "profile_path": str(profile_path.resolve()),
                "row_count": rows,
                "column_count": columns,
                "quality_status": "profiled",
            })
            record.pop("quality_error", None)
        except Exception as exc:
            record.update({"quality_status": "profile_failed", "quality_error": str(exc)})
    manifest_path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    for record in records:
        if record.get("retrieval_status") in {"downloaded", "already_present"}:
            print(record["dataset_id"], record.get("quality_status"), record.get("row_count"), record.get("column_count"))
    return 0 if all(record.get("quality_status") != "profile_failed" for record in records if record.get("retrieval_status") in {"downloaded", "already_present"}) else 1


if __name__ == "__main__":
    raise SystemExit(main())
