"""Generate deterministic fictitious enterprise benchmark datasets."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.learning.synthetic import (
    generate_dlp,
    generate_finance,
    generate_hr,
    generate_sales,
    write_csv,
    write_policy_rules,
    write_xlsx,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="data/benchmark/synthetic")
    parser.add_argument("--seed", type=int, default=20261123)
    parser.add_argument("--scale", type=int, default=5000, choices=[100, 1000, 5000, 50000])
    args = parser.parse_args()
    root = Path(args.output_dir)
    root.mkdir(parents=True, exist_ok=True)

    dlp = generate_dlp(args.scale, args.seed)
    write_csv(root / f"dlp_incidents_{args.scale}.csv", dlp)
    write_xlsx(root / f"dlp_incidents_{args.scale}.xlsx", {"Incidents": dlp})

    hr = generate_hr(args.seed)
    for name, rows in hr.items():
        write_csv(root / "hr" / f"{name}.csv", rows)
    write_xlsx(root / "hr" / "hr_relational.xlsx", hr)

    finance = generate_finance(args.seed)
    for name, rows in finance.items():
        write_csv(root / "finance" / f"{name}.csv", rows)

    sales = generate_sales(args.seed)
    for name, rows in sales.items():
        write_csv(root / "sales" / f"{name}.csv", rows)

    write_policy_rules(root / "policies.json")
    print(f"Generated seed={args.seed} scale={args.scale} under {root.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
