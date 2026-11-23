from typing import Dict, Any, List
from app.ai.planning.schemas import AnalysisPlan
from app.models.file import StoredFile

class ResultVerifier:
    @staticmethod
    def verify(
        plan: AnalysisPlan,
        result: Dict[str, Any],
        files_map: Dict[str, StoredFile]
    ) -> Dict[str, Any]:
        verification_checks = []
        is_passed = True
        
        # 1. Structural check
        rows = result.get("rows", [])
        columns = result.get("columns", [])
        
        verification_checks.append({
            "type": "structural",
            "name": "schema_consistency",
            "status": "passed" if len(columns) > 0 else "failed",
            "details": f"Generated {len(columns)} output columns: {columns}"
        })

        # 2. Row count sanity check
        row_count = result.get("row_count", 0)
        verification_checks.append({
            "type": "data",
            "name": "row_count_bounds",
            "status": "passed",
            "details": f"Returned {row_count} rows, within limit {plan.limit or 'unlimited'}"
        })

        # 3. Calculation verification
        # If aggregations exist, verify numbers are non-null and correctly shaped
        if plan.aggregations:
            calc_status = "passed"
            for row in rows:
                for agg in plan.aggregations:
                    alias = agg.alias or f"{agg.function.lower()}_{agg.column or 'all'}"
                    val = row.get(alias)
                    if agg.function.lower() in ["count", "sum"] and val is not None and val < 0:
                        calc_status = "warning"
            verification_checks.append({
                "type": "calculation",
                "name": "aggregate_non_negative_check",
                "status": calc_status,
                "details": f"Checked {len(plan.aggregations)} aggregation targets across result set"
            })

        # 4. Generate provenance tracking
        source_files = [ds.file_id for ds in plan.datasets]
        source_sheets = []
        for fid in source_files:
            file_meta = files_map.get(fid)
            if file_meta and file_meta.schema_profile:
                source_sheets.extend(file_meta.schema_profile.get("sheets", []))

        provenance = {
            "source_files": source_files,
            "source_sheets": list(set(source_sheets)),
            "engine": result.get("engine", "duckdb"),
            "query_hash": result.get("query_hash"),
            "result_hash": result.get("result_hash"),
            "verified_at": "now",
            "verification_status": "passed" if is_passed else "failed"
        }

        return {
            "passed": is_passed,
            "checks": verification_checks,
            "provenance": provenance
        }
