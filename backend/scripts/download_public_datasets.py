"""Download approved public benchmark sources with bounded, auditable IO."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.learning.acquisition import DatasetAcquisition, default_sources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", action="append", dest="datasets", help="Dataset id; repeat to select multiple")
    parser.add_argument("--output-dir", default="data/benchmark/public")
    parser.add_argument("--manifest", default="data/benchmark/manifests/public_sources.json")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    sources = default_sources()
    if args.datasets:
        selected = set(args.datasets)
        sources = [source for source in sources if source.dataset_id in selected]
        unknown = selected - {source.dataset_id for source in sources}
        if unknown:
            parser.error(f"Unknown dataset id(s): {sorted(unknown)}")

    acquisition = DatasetAcquisition(args.output_dir)
    results = []
    for source in sources:
        result = acquisition.download(source, force=args.force)
        results.append(result)
        print(f"{result.dataset_id}: {result.status} {result.file_path or result.error or ''}")
    acquisition.write_manifest(args.manifest, results)
    return 0 if all(result.status in {"downloaded", "already_present"} for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
