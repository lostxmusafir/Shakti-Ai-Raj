from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_MAX_BYTES = 100 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3


@dataclass(frozen=True)
class DatasetSource:
    dataset_id: str
    source_name: str
    official_url: str
    provider: str
    category: str
    file_format: str
    license: str
    attribution: str
    purpose: str
    max_bytes: int = DEFAULT_MAX_BYTES

    def as_manifest_record(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "retrieval_date": None,
            "retrieval_status": "not_run",
            "file_path": None,
            "sha256": None,
            "row_count": None,
            "column_count": None,
            "quality_status": "pending",
            "approval_status": "pending",
        }


@dataclass
class DownloadResult:
    dataset_id: str
    status: str
    file_path: Optional[str]
    sha256: Optional[str]
    bytes_downloaded: int
    error: Optional[str] = None


def default_sources() -> List[DatasetSource]:
    return [
        DatasetSource(
            dataset_id="microsoft-financial-sample",
            source_name="Microsoft Financial Sample",
            official_url="https://download.microsoft.com/download/1/4/E/14EDED28-6C58-4055-A65C-23B4DA81C4DE/Financial%20Sample.xlsx",
            provider="Microsoft Learn / Power BI",
            category="finance",
            file_format="xlsx",
            license="Microsoft sample data; follow the official sample terms",
            attribution="Microsoft Financial Sample",
            purpose="Sales, profit, country, product, and time-series analysis",
            max_bytes=25 * 1024 * 1024,
        ),
        DatasetSource(
            dataset_id="uci-online-retail",
            source_name="UCI Online Retail",
            official_url="https://archive.ics.uci.edu/static/public/352/online+retail.zip",
            provider="UCI Machine Learning Repository",
            category="retail",
            file_format="zip/xlsx",
            license="CC BY 4.0",
            attribution="Chen, D. (2015). Online Retail. UCI Machine Learning Repository. https://doi.org/10.24432/C5BW33",
            purpose="Retail transactions, revenue, returns, customer and product analysis",
            max_bytes=50 * 1024 * 1024,
        ),
        DatasetSource(
            dataset_id="uci-bank-marketing",
            source_name="UCI Bank Marketing",
            official_url="https://archive.ics.uci.edu/static/public/222/bank+marketing.zip",
            provider="UCI Machine Learning Repository",
            category="marketing",
            file_format="zip/csv",
            license="CC BY 4.0",
            attribution="Moro, S., Rita, P., & Cortez, P. (2014). Bank Marketing. UCI Machine Learning Repository. https://doi.org/10.24432/C5K306",
            purpose="Campaign conversion, segmentation, and categorical analysis",
            max_bytes=10 * 1024 * 1024,
        ),
        DatasetSource(
            dataset_id="nyc-taxi-yellow-2025-01",
            source_name="NYC TLC Yellow Taxi Trip Records (2025-01 sample)",
            official_url="https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-01.parquet",
            provider="New York City Taxi and Limousine Commission",
            category="transportation",
            file_format="parquet",
            license="NYC TLC public-use data; see official data terms",
            attribution="NYC Taxi and Limousine Commission",
            purpose="Bounded DuckDB/Parquet time-series and trip aggregation benchmark",
            max_bytes=100 * 1024 * 1024,
        ),
    ]


class DatasetAcquisition:
    def __init__(self, output_dir: str | os.PathLike[str], timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS):
        self.output_dir = Path(output_dir).resolve()
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _validate_url(url: str) -> None:
        if not url.lower().startswith("https://"):
            raise ValueError("Dataset acquisition requires an HTTPS URL.")

    @staticmethod
    def _safe_extract(archive_path: Path, destination: Path, max_bytes: int) -> List[str]:
        destination = destination.resolve()
        extracted: List[str] = []
        total = 0
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                total += member.file_size
                if total > max_bytes:
                    raise ValueError("Archive exceeds the configured decompressed size limit.")
                target = (destination / member.filename).resolve()
                if target != destination and destination not in target.parents:
                    raise ValueError("Archive contains a path traversal entry.")
                if member.is_dir():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                extracted.append(str(target))
        return extracted

    def download(self, source: DatasetSource, force: bool = False) -> DownloadResult:
        self._validate_url(source.official_url)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = source.official_url.rstrip("/").rsplit("/", 1)[-1] or f"{source.dataset_id}.bin"
        filename = filename.replace("%20", " ")
        target = self.output_dir / f"{source.dataset_id}-{filename}"
        if target.exists() and not force:
            return DownloadResult(source.dataset_id, "already_present", str(target), self._sha256(target), target.stat().st_size)

        request = urllib.request.Request(source.official_url, headers={"User-Agent": "UniversalAIAnalyst/1.0"})
        temporary = target.with_suffix(target.suffix + ".part")
        last_error: Optional[str] = None
        for attempt in range(MAX_RETRIES):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > source.max_bytes:
                        raise ValueError("Remote dataset exceeds the configured download limit.")
                    total = 0
                    with temporary.open("wb") as output:
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            total += len(chunk)
                            if total > source.max_bytes:
                                raise ValueError("Dataset exceeded the configured download limit.")
                            output.write(chunk)
                os.replace(temporary, target)
                return DownloadResult(source.dataset_id, "downloaded", str(target), self._sha256(target), total)
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                last_error = str(exc)
                if temporary.exists():
                    temporary.unlink()
                if attempt + 1 < MAX_RETRIES:
                    time.sleep(0.5 * (attempt + 1))
        return DownloadResult(source.dataset_id, "failed", None, None, 0, last_error)

    def write_manifest(self, path: str | os.PathLike[str], results: Iterable[DownloadResult]) -> None:
        manifest_path = Path(path)
        by_id = {source.dataset_id: source.as_manifest_record() for source in default_sources()}
        if manifest_path.exists():
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
                by_id.update({record["dataset_id"]: record for record in existing if record.get("dataset_id")})
            except (OSError, ValueError, TypeError):
                pass
        for result in results:
            record = by_id.setdefault(result.dataset_id, {"dataset_id": result.dataset_id})
            record.update({
                "retrieval_date": date.today().isoformat(),
                "retrieval_status": result.status,
                "file_path": result.file_path,
                "sha256": result.sha256,
                "bytes_downloaded": result.bytes_downloaded,
                "error": result.error,
            })
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(list(by_id.values()), indent=2) + "\n", encoding="utf-8")
