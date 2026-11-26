"""Independent Pandas recomputation for the difficult and null-sensitive cases.

The primary ground truth in ``ground_truth.json`` is hand-written SQL executed by
DuckDB. This module recomputes a representative subset of those answers with a
second engine (Pandas) and a second formulation, so a mistake in either the SQL
or the expectation is caught before the blind run.

Checks are keyed by question id and must return the same primary numeric value
as the DuckDB ground truth.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .ground_truth import RESULTS_PATH, load_key, sample_path

TOLERANCE = 0.02


def _frame(dataset_id: str) -> pd.DataFrame:
    return pd.read_csv(sample_path(dataset_id), low_memory=False)


def _check_001_q3(df: pd.DataFrame) -> float:
    return float(((df["CustomerID"].isna()) & (df["Quantity"] > 0)).sum())


def _check_001_q4(df: pd.DataFrame) -> float:
    sales = df[(df["Quantity"] > 0) & (~df["InvoiceNo"].astype(str).str.startswith("C"))].copy()
    sales["revenue"] = sales["Quantity"] * sales["UnitPrice"]
    grouped = sales.groupby("Country")["revenue"].sum()
    return float(100.0 * grouped.max() / grouped.sum())


def _check_002_q4(df: pd.DataFrame) -> float:
    grouped = df.groupby("Product")["Profit"].sum()
    return float(100.0 * grouped.max() / grouped.sum())


def _check_003_q3(df: pd.DataFrame) -> float:
    return float(((df["Region"] == 3) & (df["milk"] > 10000)).sum())


def _check_005_q3(df: pd.DataFrame) -> float:
    return float(((df["housing"] == "yes") & (df["y"] == True)).sum())  # noqa: E712


def _check_006_q3(df: pd.DataFrame) -> float:
    return float(((df["LIMIT_BAL"] > 200000) & (df["default payment next month"] == 1)).sum())


def _check_006_q4(df: pd.DataFrame) -> list[float]:
    rate = {}
    for label, mask in (("30 plus", df["AGE"] >= 30), ("under 30", df["AGE"] < 30)):
        rate[label] = float(100.0 * (df.loc[mask, "default payment next month"] == 1).mean())
    return [rate["30 plus"], rate["under 30"]]


def _check_007_q3(df: pd.DataFrame) -> float:
    return float(((df["housing"] == "rent") & (df["credit_amount"] > 5000)).sum())


def _check_009_q3(df: pd.DataFrame) -> float:
    return float(((df["payment_type"] == 1) & (df["trip_distance"] > 10)).sum())


def _check_010_q3(df: pd.DataFrame) -> float:
    return float(df.loc[df["passenger_count"].isna(), "fare_amount"].mean())


def _check_011_q3(df: pd.DataFrame) -> float:
    return float(df["PUlocationID"].isna().sum())


def _check_011_q4(df: pd.DataFrame) -> float:
    return float(100.0 * df["PUlocationID"].notna().sum() / len(df))


def _check_012_q4(df: pd.DataFrame) -> list[float]:
    counts = df.groupby("Airline").size().sort_index().sort_values(ascending=False, kind="stable")
    top = list(counts.index[:5])
    rates = df.groupby("Airline")["Delay"].mean()
    return [float(100.0 * rates[airline]) for airline in top]


def _check_013_q3(df: pd.DataFrame) -> float:
    return float(((df["full_or_part_time"] == "P") & (df["salary_or_hourly"] == "HOURLY")).sum())


def _check_015_q3(df: pd.DataFrame) -> float:
    return float((df["number_of_positions"] > 1).sum())


def _check_016_q3(df: pd.DataFrame) -> float:
    return float(((df["hours-per-week"] > 50) & (df["class"] == ">50K")).sum())


def _check_017_q3(df: pd.DataFrame) -> float:
    return float((df["award_amount"] < 0).sum())


def _check_017_q4(df: pd.DataFrame) -> float:
    return float(100.0 * (df["award_amount"] > 1_000_000).sum() / len(df))


def _check_018_q3(df: pd.DataFrame) -> float:
    return float((df["total_fee"] == 0).sum())


def _check_019_q3(df: pd.DataFrame) -> float:
    return float(df["status"].isin(["Open", "In Progress"]).sum())


def _check_019_q4(df: pd.DataFrame) -> float:
    return float(100.0 * df["complaint_type"].astype(str).str.startswith("Noise").sum() / len(df))


def _check_020_q3(df: pd.DataFrame) -> float:
    return float((df["arrest"].astype(str).str.lower() == "true").mul(df["domestic"].astype(str).str.lower() == "true").sum())


def _check_021_q3(df: pd.DataFrame) -> float:
    return float(df["value"].isna().sum())


def _check_021_q4(df: pd.DataFrame) -> float:
    india = df[(df["country_name"] == "India") & (df["year"].isin([2000, 2024]))].set_index("year")["value"]
    return float(100.0 * (india.loc[2024] - india.loc[2000]) / india.loc[2000])


def _check_022_q3(df: pd.DataFrame) -> float:
    return float(df["value"].isna().sum())


def _check_023_q3(df: pd.DataFrame) -> float:
    return float((df["value"] == 0).sum())


def _check_024_q3(df: pd.DataFrame) -> float:
    return float(df["value"].isna().sum())


def _check_026_q3(df: pd.DataFrame) -> float:
    return float(df["payment_date"].isna().sum())


def _check_027_q4(df: pd.DataFrame) -> float:
    grouped = df.assign(failed=df["results"].eq("Fail")).groupby("risk")["failed"].mean()
    return float(100.0 * grouped.max())


def _check_028_q4(df: pd.DataFrame) -> float:
    mask = (df["species"] == "Iris-virginica") & (df["petal_length"] > 5)
    return float(100.0 * mask.sum() / len(df))


def _check_030_q4(df: pd.DataFrame) -> float:
    return float(df["heating_load"].corr(df["cooling_load"]))


CHECKS = {
    "internet-001-q3": _check_001_q3,
    "internet-001-q4": _check_001_q4,
    "internet-002-q4": _check_002_q4,
    "internet-003-q3": _check_003_q3,
    "internet-005-q3": _check_005_q3,
    "internet-006-q3": _check_006_q3,
    "internet-006-q4": _check_006_q4,
    "internet-007-q3": _check_007_q3,
    "internet-009-q3": _check_009_q3,
    "internet-010-q3": _check_010_q3,
    "internet-011-q3": _check_011_q3,
    "internet-011-q4": _check_011_q4,
    "internet-012-q4": _check_012_q4,
    "internet-013-q3": _check_013_q3,
    "internet-015-q3": _check_015_q3,
    "internet-016-q3": _check_016_q3,
    "internet-017-q3": _check_017_q3,
    "internet-017-q4": _check_017_q4,
    "internet-018-q3": _check_018_q3,
    "internet-019-q3": _check_019_q3,
    "internet-019-q4": _check_019_q4,
    "internet-020-q3": _check_020_q3,
    "internet-021-q3": _check_021_q3,
    "internet-021-q4": _check_021_q4,
    "internet-022-q3": _check_022_q3,
    "internet-023-q3": _check_023_q3,
    "internet-024-q3": _check_024_q3,
    "internet-026-q3": _check_026_q3,
    "internet-027-q4": _check_027_q4,
    "internet-028-q4": _check_028_q4,
    "internet-030-q4": _check_030_q4,
}


def run_independent_checks() -> dict:
    key = {answer["q_id"]: answer for answer in load_key()["answers"]}
    if not RESULTS_PATH.exists():
        raise SystemExit("run eval.internet.ground_truth first")
    stored = json.loads(RESULTS_PATH.read_text())["results"]
    outcomes = []
    for q_id, check in CHECKS.items():
        dataset_id = key[q_id]["dataset_id"]
        frame = _frame(dataset_id)
        try:
            computed = check(frame)
        except Exception as exc:  # noqa: BLE001
            outcomes.append({"q_id": q_id, "status": "error", "error": str(exc)})
            continue
        expected_values = stored.get(q_id, {}).get("measures") or []
        if not expected_values:
            outcomes.append({"q_id": q_id, "status": "missing_expected"})
            continue
        computed_values = computed if isinstance(computed, list) else [computed]
        if len(computed_values) != len(expected_values):
            outcomes.append({"q_id": q_id, "status": "shape_mismatch", "pandas_value": computed_values, "duckdb_value": expected_values})
            continue
        deltas = [float(a) - float(b) for a, b in zip(computed_values, expected_values)]
        ok = all(abs(delta) <= TOLERANCE for delta in deltas)
        outcomes.append(
            {
                "q_id": q_id,
                "status": "match" if ok else "mismatch",
                "pandas_value": [round(float(v), 6) for v in computed_values],
                "duckdb_value": [round(float(v), 6) for v in expected_values],
                "delta": [round(delta, 6) for delta in deltas],
            }
        )
    matched = sum(1 for item in outcomes if item["status"] == "match")
    return {"checks": outcomes, "total": len(outcomes), "matched": matched}


def main() -> int:
    report = run_independent_checks()
    for item in report["checks"]:
        if item["status"] != "match":
            print("MISMATCH", item)
    print(f"independent recomputation: {report['matched']}/{report['total']} match")
    return 0 if report["matched"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
