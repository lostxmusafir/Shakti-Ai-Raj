"""Reproducible acquisition of the 30 blind public-internet datasets.

For every catalog entry this module:

1. downloads the publisher's file / API response over HTTPS,
2. records the SHA-256 of the exact bytes retrieved,
3. creates a deterministic bounded sample (reservoir sample, seed 42) when the
   source is larger than the configured limit,
4. writes the sample as CSV and records full provenance in the manifest.

Large raw downloads are removed after sampling unless ``--keep-raw`` is given,
so bulk source data never enters Git.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import duckdb
import pandas as pd

from .catalog import CATALOG, BY_ID, InternetDataset

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data" / "benchmark" / "internet"
SAMPLE_DIR = DATA_DIR / "samples"
RAW_DIR = DATA_DIR / "raw"
MANIFEST_PATH = DATA_DIR / "manifest.json"
RANDOM_SEED = 42
MAX_BYTES = 200 * 1024 * 1024
USER_AGENT = "universal-ai-analyst-blind-eval/1.0"


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------
def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch(url: str, timeout: int = 120) -> bytes:
    if not url.lower().startswith("https://"):
        raise ValueError(f"refusing non-HTTPS retrieval: {url}")
    last: Optional[Exception] = None
    for attempt in range(3):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                buffer = io.BytesIO()
                total = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError(f"source exceeds {MAX_BYTES} byte cap: {url}")
                    buffer.write(chunk)
                return buffer.getvalue()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"download failed for {url}: {last}")


# ---------------------------------------------------------------------------
# loaders: every loader returns a staging parquet path plus the original row count
# ---------------------------------------------------------------------------
def _normalise_column_names(con: duckdb.DuckDBPyConnection, table: str = "raw") -> None:
    """Drop literal quote characters that some publishers leave in headers."""
    columns = [row[0] for row in con.execute(f'DESCRIBE SELECT * FROM "{table}"').fetchall()]
    for name in columns:
        stripped = name.strip('"')
        if stripped != name:
            con.execute(
                'ALTER TABLE "{}" RENAME COLUMN "{}" TO "{}"'.format(
                    table, name.replace('"', '""'), stripped.replace('"', '""')
                )
            )


def _duckdb_from_file(path: Path, read_csv_options: Optional[dict] = None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("SET threads = 1")
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        con.execute("CREATE TABLE raw AS SELECT * FROM read_parquet(?)", [str(path)])
    else:
        # CSV-family inputs (.csv, .data, .txt) are all handed to DuckDB's
        # sniffer; only parquet needs a dedicated reader.
        options = dict(read_csv_options or {})
        clause = ", ".join(f"{key}={value!r}" for key, value in options.items())
        sql = "CREATE TABLE raw AS SELECT * FROM read_csv_auto(?)" if not clause else f"CREATE TABLE raw AS SELECT * FROM read_csv_auto(?, {clause})"
        con.execute(sql, [str(path)])
    _normalise_column_names(con)
    return con


def _apply_renames(staged: Path, workdir: Path, mapping: dict[str, str]) -> Path:
    if not mapping:
        return staged
    con = duckdb.connect(":memory:")
    con.execute("SET threads = 1")
    try:
        con.execute("CREATE TABLE r AS SELECT * FROM read_parquet(?)", [str(staged)])
        _normalise_column_names(con, "r")
        actual = {row[0]: row[0] for row in con.execute("DESCRIBE SELECT * FROM r").fetchall()}
        for old, new in mapping.items():
            match = actual.get(old) or next((name for name in actual if name.strip('"') == old), None)
            if match is None:
                raise KeyError(f"cannot rename missing column {old}")
            con.execute(
                'ALTER TABLE r RENAME COLUMN "{}" TO "{}"'.format(
                    match.replace('"', '""'), new.replace('"', '""')
                )
            )
        renamed = workdir / "renamed.parquet"
        con.execute("COPY (SELECT * FROM r) TO ? (FORMAT PARQUET)", [str(renamed)])
        return renamed
    finally:
        con.close()


def _stage_dataframe(df: pd.DataFrame, workdir: Path) -> Path:
    target = workdir / "staged.parquet"
    con = duckdb.connect(":memory:")
    con.execute("SET threads = 1")
    try:
        con.register("frame", df)
        con.execute("COPY (SELECT * FROM frame) TO ? (FORMAT PARQUET)", [str(target)])
    finally:
        con.close()
    return target


def _parse_arff(path: Path) -> pd.DataFrame:
    attributes: list[tuple[str, str]] = []
    rows: list[list[str]] = []
    in_data = False
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("%"):
                continue
            lowered = stripped.lower()
            if lowered.startswith("@attribute"):
                match = re.match(r"@attribute\s+(?P<name>'[^']*'|\"[^\"]*\"|\S+)\s+(?P<type>.+)", stripped, re.IGNORECASE)
                if match:
                    name = match.group("name").strip("'\"")
                    attributes.append((name, match.group("type")))
            elif lowered.startswith("@data"):
                in_data = True
            elif in_data:
                rows.append([part.strip().strip("'\"") for part in stripped.split(",")])
    frame = pd.DataFrame(rows, columns=[name for name, _ in attributes])
    for name, dtype in attributes:
        if dtype.lower() in {"numeric", "real", "integer"} and name in frame.columns:
            frame[name] = pd.to_numeric(frame[name], errors="coerce")
    return frame


def _load(dataset: InternetDataset, downloaded: bytes, workdir: Path) -> tuple[Path, int]:
    options = dict(dataset.loader_options)
    if dataset.loader == "parquet":
        path = workdir / "source.parquet"
        path.write_bytes(downloaded)
        con = _duckdb_from_file(path)
        try:
            count = con.execute("SELECT COUNT(*) FROM raw").fetchone()[0]
            staged = workdir / "staged.parquet"
            con.execute("COPY (SELECT * FROM raw) TO ? (FORMAT PARQUET)", [str(staged)])
        finally:
            con.close()
        return staged, int(count)

    if dataset.loader == "openml_csv":
        path = workdir / "source.csv"
        path.write_bytes(downloaded)
        con = _duckdb_from_file(path)
        try:
            count = con.execute("SELECT COUNT(*) FROM raw").fetchone()[0]
            staged = workdir / "staged.parquet"
            con.execute("COPY (SELECT * FROM raw) TO ? (FORMAT PARQUET)", [str(staged)])
        finally:
            con.close()
        return _apply_renames(staged, workdir, options.get("rename_columns", {})), int(count)

    if dataset.loader == "socrata":
        path = workdir / "source.csv"
        path.write_bytes(downloaded)
        con = _duckdb_from_file(path)
        try:
            count = con.execute("SELECT COUNT(*) FROM raw").fetchone()[0]
            staged = workdir / "staged.parquet"
            con.execute("COPY (SELECT * FROM raw) TO ? (FORMAT PARQUET)", [str(staged)])
        finally:
            con.close()
        return staged, int(count)

    if dataset.loader == "worldbank":
        payload = json.loads(downloaded.decode("utf-8"))
        if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
            raise ValueError("unexpected World Bank API payload")
        rows = []
        for observation in payload[1]:
            if not observation:
                continue
            rows.append(
                {
                    "country_name": (observation.get("country") or {}).get("value"),
                    "country_code": observation.get("countryiso3code"),
                    "country_id": (observation.get("country") or {}).get("id"),
                    "indicator_name": (observation.get("indicator") or {}).get("value"),
                    "indicator_code": (observation.get("indicator") or {}).get("id"),
                    "year": int(observation["date"]) if observation.get("date") else None,
                    "value": observation.get("value"),
                }
            )
        frame = pd.DataFrame(rows)
        return _stage_dataframe(frame, workdir), len(frame)

    if dataset.loader == "xlsx":
        path = workdir / "source.xlsx"
        path.write_bytes(downloaded)
        frame = pd.read_excel(
            path,
            sheet_name=options.get("sheet", 0),
            header=options.get("header_row", 0),
            engine="openpyxl",
        )
        staged = _stage_dataframe(frame, workdir)
        return _apply_renames(staged, workdir, options.get("rename_columns", {})), len(frame)

    if dataset.loader == "uci_zip":
        archive_path = workdir / "source.zip"
        archive_path.write_bytes(downloaded)
        extract_dir = workdir / "unzipped"
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                target = (extract_dir / member.filename).resolve()
                if extract_dir.resolve() not in target.parents and target != extract_dir.resolve():
                    raise ValueError("zip path traversal")
                if member.is_dir():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)
        pattern = options.get("inner_glob", "*.csv")
        candidates = sorted(extract_dir.rglob(pattern))
        # Some publishers ship a zip inside a zip (UCI bank marketing). Expand
        # nested archives once, then re-check the pattern.
        nested_archives = sorted(extract_dir.rglob("*.zip"))
        if not candidates and nested_archives:
            for nested in nested_archives:
                nested_dir = nested.with_suffix(".unzipped")
                with zipfile.ZipFile(nested) as archive:
                    for member in archive.infolist():
                        target = (nested_dir / member.filename).resolve()
                        if nested_dir.resolve() not in target.parents and target != nested_dir.resolve():
                            raise ValueError("zip path traversal")
                        if member.is_dir():
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as src, target.open("wb") as out:
                            shutil.copyfileobj(src, out)
            candidates = sorted(extract_dir.rglob(pattern))
        if not candidates:
            raise FileNotFoundError(f"no {pattern} inside archive for {dataset.dataset_id}")
        inner = candidates[0]
        suffix = inner.suffix.lower()
        if suffix in {".xlsx", ".xls"}:
            frame = pd.read_excel(
                inner,
                sheet_name=options.get("sheet", 0),
                header=options.get("header_row", 0),
                engine="openpyxl" if suffix == ".xlsx" else "xlrd",
            )
            if options.get("column_names"):
                frame.columns = options["column_names"]
            staged = _stage_dataframe(frame, workdir)
            return _apply_renames(staged, workdir, options.get("rename_columns", {})), len(frame)
        if suffix == ".arff":
            frame = _parse_arff(inner)
            return _stage_dataframe(frame, workdir), len(frame)
        con = _duckdb_from_file(
            inner,
            {
                "header": options.get("header", True),
                "sep": options.get("sep", ","),
            },
        )
        try:
            count = con.execute("SELECT COUNT(*) FROM raw").fetchone()[0]
            if options.get("column_names"):
                names = options["column_names"]
                projection = ", ".join(f"column{i} AS \"{name}\"" for i, name in enumerate(names))
                con.execute(f"CREATE TABLE renamed AS SELECT {projection} FROM raw")
            else:
                con.execute("CREATE TABLE renamed AS SELECT * FROM raw")
            staged = workdir / "staged.parquet"
            con.execute("COPY (SELECT * FROM renamed) TO ? (FORMAT PARQUET)", [str(staged)])
        finally:
            con.close()
        return staged, int(count)

    raise ValueError(f"unknown loader {dataset.loader}")


# ---------------------------------------------------------------------------
# deterministic sampling
# ---------------------------------------------------------------------------
def _sample(staged: Path, target: Path, max_rows: int) -> tuple[int, int, str]:
    con = duckdb.connect(":memory:")
    con.execute("SET threads = 1")
    try:
        con.execute("CREATE TABLE src AS SELECT * FROM read_parquet(?)", [str(staged)])
        total = int(con.execute("SELECT COUNT(*) FROM src").fetchone()[0])
        if total <= max_rows:
            con.execute("COPY (SELECT * FROM src) TO ? (HEADER, DELIMITER ',')", [str(target)])
            return total, total, "full source (source row count within bounded-sample limit); no rows dropped"
        con.execute(
            f"CREATE TABLE picked AS SELECT * FROM "
            f"(SELECT *, row_number() OVER () AS __source_ordinal FROM src) "
            f"USING SAMPLE {int(max_rows)} ROWS (reservoir, {RANDOM_SEED})"
        )
        con.execute(
            "COPY (SELECT * EXCLUDE __source_ordinal FROM picked ORDER BY __source_ordinal) "
            "TO ? (HEADER, DELIMITER ',')",
            [str(target)],
        )
        sampled = int(con.execute("SELECT COUNT(*) FROM picked").fetchone()[0])
        return total, sampled, (
            f"duckdb reservoir sample of {sampled} rows from {total} "
            f"(USING SAMPLE {max_rows} ROWS (reservoir, {RANDOM_SEED})); "
            "sample rows kept in original source order"
        )
    finally:
        con.close()


def acquire(dataset: InternetDataset, force: bool = False, keep_raw: bool = False) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    sample_path = SAMPLE_DIR / f"{dataset.dataset_id}.csv"
    record_path = DATA_DIR / "records" / f"{dataset.dataset_id}.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)

    if record_path.exists() and sample_path.exists() and not force:
        return json.loads(record_path.read_text(encoding="utf-8"))

    raw_sha = None
    if keep_raw:
        raw_path = RAW_DIR / f"{dataset.dataset_id}.bin"
        if not raw_path.exists():
            raw_path.write_bytes(_fetch(dataset.source_url))
        downloaded = raw_path.read_bytes()
        raw_sha = _sha256_file(raw_path)
    else:
        downloaded = _fetch(dataset.source_url)
        raw_sha = _sha256_bytes(downloaded)

    workdir = Path(tempfile.mkdtemp(prefix=f"acquire-{dataset.dataset_id}-"))
    try:
        staged, original_rows = _load(dataset, downloaded, workdir)
        original_rows, sample_rows, sample_method = _sample(staged, sample_path, dataset.max_sample_rows)
        con = duckdb.connect(":memory:")
        try:
            columns = [row[0] for row in con.execute("DESCRIBE SELECT * FROM read_csv_auto(?)", [str(sample_path)]).fetchall()]
            dtypes = {row[0]: row[1] for row in con.execute("DESCRIBE SELECT * FROM read_csv_auto(?)", [str(sample_path)]).fetchall()}
        finally:
            con.close()
        record = {
            "test_id": dataset.test_id,
            "dataset_id": dataset.dataset_id,
            "source": dataset.source,
            "dataset_name": dataset.dataset_name,
            "source_url": dataset.source_url,
            "landing_url": dataset.landing_url,
            "license_or_terms": dataset.license_or_terms,
            "category": dataset.category,
            "download_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sha256": raw_sha,
            "sha256_scope": "raw bytes as retrieved from source_url",
            "sample_sha256": _sha256_file(sample_path),
            "original_rows": int(original_rows),
            "test_sample_rows": int(sample_rows),
            "columns": columns,
            "column_types": dtypes,
            "sample_method": sample_method,
            "random_seed": RANDOM_SEED,
            "sample_path": str(sample_path.relative_to(ROOT)),
        }
        record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return record
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def write_manifest(records: list[dict[str, Any]]) -> Path:
    records = sorted(records, key=lambda item: item["test_id"])
    payload = {
        "manifest_version": "blind-internet-1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_count": len(records),
        "random_seed": RANDOM_SEED,
        "datasets": records,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return MANIFEST_PATH


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", action="append", dest="datasets", help="dataset id; repeat to select")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-raw", action="store_true")
    args = parser.parse_args(argv)

    selected = CATALOG
    if args.datasets:
        unknown = set(args.datasets) - set(BY_ID)
        if unknown:
            parser.error(f"unknown dataset id(s): {sorted(unknown)}")
        selected = [BY_ID[dataset_id] for dataset_id in args.datasets]

    records = []
    failures = 0
    for dataset in selected:
        try:
            record = acquire(dataset, force=args.force, keep_raw=args.keep_raw)
            records.append(record)
            print(
                f"{record['test_id']} {record['dataset_id']}: "
                f"{record['original_rows']} -> {record['test_sample_rows']} rows, "
                f"{len(record['columns'])} cols"
            )
        except Exception as exc:  # noqa: BLE001 - acquisition failures must be reported, not hidden
            failures += 1
            print(f"{dataset.test_id} {dataset.dataset_id}: FAILED {exc}", file=sys.stderr)

    if records:
        # Rebuild from every on-disk record so a removed or renamed dataset can
        # never linger in the manifest.
        on_disk = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((DATA_DIR / "records").glob("*.json"))
        ]
        write_manifest(on_disk)

    print(f"\n{len(records)} dataset(s) acquired, {failures} failure(s).")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
