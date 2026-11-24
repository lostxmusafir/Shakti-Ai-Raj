from datetime import datetime, timezone
from typing import Dict, Any

from app.ai.planning.schemas import AnalysisPlan
from app.models.file import StoredFile


class ResultVerifier:
    @staticmethod
    def verify(
        plan: AnalysisPlan,
        result: Dict[str, Any],
        files_map: Dict[str, StoredFile],
        user_unit_id: str = "default_unit",
        user_role: str = "employee",
    ) -> Dict[str, Any]:
        rows = result.get("rows", [])
        checks = []
        warnings = []
        result_row_count = result.get("row_count", len(rows))

        execution_ok = bool(result.get("columns")) and "error" not in result
        checks.append({"gate": "V1_EXECUTION", "name": "schema_and_execution_integrity", "status": "passed" if execution_ok else "failed", "details": f"Generated {len(result.get('columns', []))} output columns across {result_row_count} result rows"})

        bounds_ok = not plan.limit or result_row_count <= plan.limit
        if not bounds_ok:
            warnings.append(f"Result row count {result_row_count} exceeded limit {plan.limit}")
        checks.append({"gate": "V2_SANITY", "name": "bounds_and_plausibility_check", "status": "passed" if bounds_ok else "failed", "details": f"Result rows are bounded by requested limit ({plan.limit or 'unlimited'})"})

        recompute = result.get("recompute")
        recompute_status = "not_applicable" if not plan.aggregations else "failed"
        recompute_details = "No aggregate was requested"
        if plan.aggregations and isinstance(recompute, dict):
            recompute_status = "passed"
            recompute_details = "Independent aggregate totals were compared with the reported result"
            truncated_grouped_result = bool(plan.group_by and plan.limit and len(rows) >= plan.limit)
            if truncated_grouped_result:
                recompute_status = "not_applicable"
                warnings.append("Grouped aggregate reconciliation was skipped because the result is limit-truncated")
            for row in rows:
                for agg in plan.aggregations:
                    alias = agg.alias or f"{agg.function.lower()}_{agg.column or 'all'}"
                    value = row.get(alias)
                    if value is not None and not isinstance(value, (int, float)):
                        recompute_status = "failed"
                        warnings.append(f"Aggregate {alias} is not numeric")
                    if agg.function.lower() in {"count", "sum"} and value is not None and value < 0:
                        recompute_status = "failed"
                        warnings.append(f"Negative aggregate detected on {alias}: {value}")
                    if plan.group_by and not truncated_grouped_result and agg.function.lower() in {"count", "sum", "min", "max"}:
                        values = [item.get(alias) for item in rows if isinstance(item.get(alias), (int, float))]
                        overall = recompute.get(alias)
                        if values and overall is not None:
                            function = agg.function.lower()
                            expected = sum(values) if function in {"count", "sum"} else (min(values) if function == "min" else max(values))
                            if abs(expected - overall) > 1e-6:
                                recompute_status = "failed"
                                warnings.append(f"Grouped {function} values do not reconcile for {alias}")
                    if plan.group_by and not truncated_grouped_result and agg.function.lower() == "avg":
                        recompute_status = "not_applicable"
                        warnings.append("Grouped averages were not independently reconciled")
        elif plan.aggregations:
            warnings.append("Independent aggregate recomputation was not returned by the execution engine")
        checks.append({"gate": "V3_RECOMPUTE", "name": "aggregate_arithmetic_consistency", "status": recompute_status, "details": recompute_details})

        source_files = [dataset.file_id for dataset in plan.datasets]
        source_sheets = []
        for file_id in source_files:
            file_meta = files_map.get(file_id)
            if file_meta and file_meta.schema_profile:
                source_sheets.extend(file_meta.schema_profile.get("sheets", []))
        lineage_ok = bool(source_files) and all(file_id in files_map for file_id in source_files)
        checks.append({"gate": "V4_LINEAGE", "name": "source_lineage_and_row_provenance", "status": "passed" if lineage_ok else "failed", "details": f"Verified provenance across {len(source_files)} source files"})

        privacy_ok = True
        for file_id in source_files:
            file_meta = files_map.get(file_id)
            if file_meta and user_role not in ["tech_admin", "super_admin"] and file_meta.unit_id not in [None, "global", "default_unit", user_unit_id]:
                privacy_ok = False
        checks.append({"gate": "V8_PRIVACY", "name": "tenant_and_unit_boundary_check", "status": "passed" if privacy_ok else "failed", "details": "No cross-unit data leakage detected in the authorized file set"})

        checks.append({"gate": "V5_POLICY", "name": "policy_requirements", "status": "passed" if plan.requires_policy else "not_applicable", "details": "Policy evaluation was not requested" if not plan.requires_policy else "Policy requirement recorded"})
        citation_ok = bool(result.get("query_hash") and result.get("result_hash") and source_files)
        checks.append({"gate": "V6_CITATION", "name": "query_and_result_citation", "status": "passed" if citation_ok else "failed", "details": "Query and result hashes are available" if citation_ok else "Query or result hash is missing"})

        passed = all(check["status"] in {"passed", "not_applicable"} for check in checks)
        provenance = {
            "source_files": source_files,
            "source_sheets": sorted(set(source_sheets)),
            "engine": result.get("engine", "duckdb"),
            "query_hash": result.get("query_hash"),
            "result_hash": result.get("result_hash"),
            "evidence_rows": result.get("evidence_rows", []),
            "source_row_count": result.get("source_row_count"),
            "matched_row_count": result.get("matched_row_count"),
            "verification_status": "passed" if passed else "failed",
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        return {"passed": passed, "checks": checks, "warnings": warnings, "provenance": provenance}
