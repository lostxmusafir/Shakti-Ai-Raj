import csv
import json
import zipfile

import pytest

from app.learning.acquisition import DatasetAcquisition, DatasetSource, default_sources
from app.learning.synthetic import generate_dlp, generate_hr, write_csv, write_xlsx


def test_public_source_manifest_is_explicit_and_https_only():
    sources = default_sources()
    assert {source.dataset_id for source in sources} == {
        "microsoft-financial-sample",
        "uci-online-retail",
        "uci-bank-marketing",
        "nyc-taxi-yellow-2025-01",
    }
    assert all(source.official_url.startswith("https://") for source in sources)
    assert all(source.license and source.attribution for source in sources)


def test_synthetic_dlp_is_reproducible_and_semantically_correlated():
    first = generate_dlp(100, seed=7)
    second = generate_dlp(100, seed=7)
    assert first == second
    assert len(first) == 100
    assert {row["action"] for row in first} <= {"BLOCKED", "APPROVED", "ALLOWED"}
    assert all(row["data_size_bytes"] == 0 for row in first if row["action"] == "BLOCKED")
    assert any(row["is_external"] for row in first)
    assert any(row["is_approved_destination"] for row in first)


def test_synthetic_relationships_write_csv_and_xlsx(tmp_path):
    hr = generate_hr(seed=10, employees=10)
    write_csv(tmp_path / "employees.csv", hr["employees"])
    write_xlsx(tmp_path / "hr.xlsx", hr)
    with (tmp_path / "employees.csv").open(encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 10
    assert (tmp_path / "hr.xlsx").is_file()
    assert {row["employee_id"] for row in hr["payroll_summary"]} <= {row["employee_id"] for row in hr["employees"]}


def test_acquisition_rejects_non_https_and_archive_traversal(tmp_path):
    acquisition = DatasetAcquisition(tmp_path / "downloads")
    source = DatasetSource("unsafe", "Unsafe", "http://example.test/file.csv", "unknown", "test", "csv", "unknown", "unknown", "test")
    with pytest.raises(ValueError, match="HTTPS"):
        acquisition.download(source)

    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.txt", "bad")
    with pytest.raises(ValueError, match="traversal"):
        acquisition._safe_extract(archive, tmp_path / "extract", 1024)
