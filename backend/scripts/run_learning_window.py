"""Run bounded offline learning/evaluation checkpoints for a requested window."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_step(command: list[str]) -> dict:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-2000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-minutes", type=float, default=120)
    parser.add_argument("--interval-minutes", type=float, default=5)
    parser.add_argument("--output", default="data/benchmark/reports/learning_window_checkpoints.json")
    args = parser.parse_args()

    if args.duration_minutes <= 0 or args.interval_minutes <= 0:
        raise SystemExit("duration and interval must be positive")

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    checkpoints = []
    cycle = 0

    while True:
        cycle += 1
        started_at = datetime.now(timezone.utc).isoformat()
        steps = [
            run_step([sys.executable, "backend/scripts/test_nexus_files.py", "--output", "data/benchmark/reports/nexus_user_file_test.json"]),
            run_step([sys.executable, "backend/scripts/audit_benchmark.py"]),
            run_step([sys.executable, "backend/scripts/evaluate_orchestrator.py"]),
        ]
        checkpoint = {
            "cycle": cycle,
            "started_at": started_at,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "status": "passed" if all(step["returncode"] == 0 for step in steps) else "failed",
            "steps": steps,
        }
        checkpoints.append(checkpoint)
        output.write_text(json.dumps({
            "mode": "offline_example_based_learning",
            "weights_updated": False,
            "duration_minutes": args.duration_minutes,
            "interval_minutes": args.interval_minutes,
            "started_at": checkpoints[0]["started_at"],
            "latest_status": checkpoint["status"],
            "checkpoints": checkpoints,
        }, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"cycle": cycle, "status": checkpoint["status"], "elapsed_seconds": checkpoint["elapsed_seconds"]}), flush=True)

        if checkpoint["status"] != "passed":
            return 1
        remaining = args.duration_minutes * 60 - (time.monotonic() - started)
        if remaining <= 0:
            return 0
        time.sleep(min(args.interval_minutes * 60, remaining))


if __name__ == "__main__":
    raise SystemExit(main())
