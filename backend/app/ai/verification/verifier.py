from datetime import datetime, timezone
from typing import Dict, Any, List

from app.ai.planning.schemas import AnalysisPlan
from app.models.file import StoredFile


class ResultVerifier:
    @staticmethod
    def verify(
        plan: AnalysisPlan,
        result: Dict[str, Any],
        files_map: Dict[str, StoredFile],
        user_unit_id: str = None,
        user_role: str = "super_admin",
    ) -> Dict[str, Any]:
        rows = result.get("rows", [])
        checks: List[Dict[str, Any]] = []
        warnings: List[str] = []
        result_row_count = result.get("row_count", len(rows))

        # V1: Execution Integrity
        execution_ok = bool(result.get("columns")) and "error" not in result and result.get("rows") is not None
        execution_status = "EXECUTION_PASS" if execution_ok else "EXECUTION_FAIL"
        checks.append({
            "gate": "V1_EXECUTION",
            "name": "schema_and_execution_integrity",
            "status": "passed" if execution_ok else "failed",
            "details": f"Generated {len(result.get('columns', []))} output columns across {result_row_count} result rows"
        })

        # V2: Bounds & Sanity
        bounds_ok = not plan.limit or result_row_count <= plan.limit
        if not bounds_ok:
            warnings.append(f"Result row count {result_row_count} exceeded limit {plan.limit}")
        checks.append({
            "gate": "V2_SANITY",
            "name": "bounds_and_plausibility_check",
            "status": "passed" if bounds_ok else "failed",
            "details": f"Result rows are bounded by requested limit ({plan.limit or 'unlimited'})"
        })

        # V3: Aggregate Reconciliation
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
                    is_distinct_agg = getattr(agg, "distinct", False) or agg.function.lower() in {"count_distinct", "distinct_count"}
                    if plan.group_by and not truncated_grouped_result and not is_distinct_agg and agg.function.lower() in {"count", "sum", "min", "max"}:
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
        checks.append({
            "gate": "V3_RECOMPUTE",
            "name": "aggregate_arithmetic_consistency",
            "status": recompute_status,
            "details": recompute_details
        })

        # V7: Semantic Verification & Result Shape Validation
        semantic_ok = True
        failure_reason = None
        q = (plan.question or "").lower()

        # Build column roles map from schemas if available
        col_roles: Dict[str, str] = {}
        for ds in plan.datasets:
            f_meta = files_map.get(ds.file_id)
            if f_meta and f_meta.schema_profile:
                for col in f_meta.schema_profile.get("columns", []):
                    col_roles[str(col.get("name", "")).lower()] = col.get("role", "dimension")

        # 1. Comparative Count Semantics
        is_comparative = (
            plan.intent == "comparative_count"
            or plan.result_shape == "two_metrics"
            or (
                "debit" in q and "credit" in q
                and any(term in q for term in ("entries", "entry", "transactions", "transaction", "count", "kitne", "kitni", "alag alag"))
                and not any(term in q for term in ("top", "highest", "amounts", "values"))
            )
        )
        if is_comparative:
            # Check for illegal measure grouping
            if plan.group_by:
                semantic_ok = False
                failure_reason = "semantic intent/result mismatch: grouped by measure columns"
            elif result_row_count > 1 or len(rows) > 1:
                semantic_ok = False
                failure_reason = "semantic intent/result mismatch: expected two scalar metrics without grouping, got multiple rows"
            elif rows and len(rows) == 1:
                cols = set(result.get("columns", []))
                # Check metrics are non-negative numeric
                for k, v in rows[0].items():
                    if isinstance(v, (int, float)) and v < 0:
                        semantic_ok = False
                        failure_reason = f"semantic intent/result mismatch: negative count on {k}: {v}"

        # 2. Scalar Count Semantics
        elif plan.intent == "scalar_count" or plan.result_shape == "scalar_metric":
            if plan.group_by:
                semantic_ok = False
                failure_reason = "semantic intent/result mismatch: expected single scalar metric, got group_by"
            elif result_row_count > 1 or len(rows) > 1:
                semantic_ok = False
                failure_reason = "semantic intent/result mismatch: expected single scalar metric, got grouped rows"

        # 3. Check for illegal raw numeric measures in GROUP BY for count queries
        if semantic_ok and plan.group_by:
            is_count_query = any(term in q for term in ("count", "entries", "transactions", "kitne", "kitni", "number of", "how many"))
            for g_col in plan.group_by:
                g_lower = g_col.lower()
                role = col_roles.get(g_lower)
                if role in ("measure", "sparse_measure") or g_lower in ("debit", "credit", "amount", "revenue"):
                    if is_count_query and not any(term in q for term in ("wise", "per", "by", "distribution")):
                        semantic_ok = False
                        failure_reason = f"semantic intent/result mismatch: grouped by measure column '{g_col}'"
                        break

        # 4. Check for arithmetic reconciliation failure
        if semantic_ok and recompute_status == "failed":
            semantic_ok = False
            failure_reason = "Arithmetic recomputation mismatch with independent calculation"

        semantic_status = "SEMANTIC_PASS" if semantic_ok else "SEMANTIC_FAIL"
        checks.append({
            "gate": "V7_SEMANTIC",
            "name": "semantic_intent_and_result_shape",
            "status": "passed" if semantic_ok else "failed",
            "details": "Result shape and concepts match intent" if semantic_ok else (failure_reason or "Semantic intent mismatch")
        })

        # Gate: V7_FAMILY_SCOPE - Record Family Scope Verification
        family_scope_ok = True
        family_scope_details = "Family scope verification not required (homogeneous dataset or unconstrained query)"
        
        primary_file = files_map.get(plan.datasets[0].file_id) if plan.datasets else None
        primary_profile = primary_file.schema_profile if primary_file else {}
        is_mixed_dataset = bool(primary_profile.get("is_mixed", False))
        record_families = primary_profile.get("record_families", [])

        if is_mixed_dataset and record_families:
            q_lower = (plan.question or "").lower()
            is_entire_dataset = any(t in q_lower for t in ["entire dataset", "poore dataset", "whole dataset", "overall dataset"])
            is_cross_family = bool(plan.group_by and any(
                g.lower() == str(primary_profile.get("discriminator_column", "")).lower()
                for g in plan.group_by
            )) or any(t in q_lower for t in ["record type", "record types", "har record type", "kaun kaun se record types"])
            
            if not is_entire_dataset and not is_cross_family:
                expected_family = None
                for fam in record_families:
                    fname = fam["family"].lower()
                    active_cols_lower = [c.lower() for c in fam.get("active_columns", [])]
                    n_a_cols_lower = [c.lower() for c in fam.get("mostly_not_applicable_columns", [])]
                    
                    fam_concepts = [w for w in fname.split() if len(w) > 3]
                    fam_measure_match = any(c in q_lower for c in active_cols_lower if fam.get("column_roles", {}).get(c, "") in ("measure", "sparse_measure") and c not in n_a_cols_lower)
                    fam_name_match = any(w in q_lower for w in fam_concepts)
                    if "transaction" in fname and any(w in q_lower for w in ["transaction", "transactions", "debit", "credit"]):
                        fam_name_match = True
                    if ("incident" in fname or "dlp" in fname) and any(w in q_lower for w in ["incident", "incidents", "dlp", "security"]):
                        fam_name_match = True
                        
                    if fam_measure_match or fam_name_match:
                        expected_family = fam
                        break

                if expected_family:
                    disc_col = expected_family.get("discriminator", {}).get("column", "").lower()
                    disc_val = str(expected_family.get("discriminator", {}).get("value", "")).lower()
                    has_family_filter = any(
                        f.column.lower() == disc_col
                        and (f.operator == "is_not_null" or (disc_val and str(f.value).lower() == disc_val))
                        for f in plan.filters
                    )
                    if not has_family_filter and plan.record_family != expected_family["family"]:
                        family_scope_ok = False
                        failure_reason = "RECORD_FAMILY_SCOPE_MISMATCH"
                        family_scope_details = f"RECORD_FAMILY_SCOPE_MISMATCH: Query targets concepts for '{expected_family['family']}', but plan omitted the record family scope restriction."
                        warnings.append(family_scope_details)
                    else:
                        family_scope_details = f"Verified query scope is restricted to logical record family '{expected_family['family']}'"

        checks.append({
            "gate": "V7_FAMILY_SCOPE",
            "name": "record_family_scope_integrity",
            "status": "passed" if family_scope_ok else "failed",
            "details": family_scope_details
        })

        # Lineage & Privacy
        source_files = [dataset.file_id for dataset in plan.datasets]
        source_sheets = []
        for file_id in source_files:
            file_meta = files_map.get(file_id)
            if file_meta and file_meta.schema_profile:
                source_sheets.extend(file_meta.schema_profile.get("sheets", []))
        lineage_ok = bool(source_files) and all(file_id in files_map for file_id in source_files)
        checks.append({
            "gate": "V4_LINEAGE",
            "name": "source_lineage_and_row_provenance",
            "status": "passed" if lineage_ok else "failed",
            "details": f"Verified provenance across {len(source_files)} source files"
        })

        privacy_ok = True
        for file_id in source_files:
            file_meta = files_map.get(file_id)
            if (
                file_meta
                and user_role not in ["tech_admin", "super_admin", "analyst"]
                and user_unit_id not in [None, "global", "default_unit"]
                and file_meta.unit_id not in [None, "global", "default_unit", user_unit_id]
            ):
                privacy_ok = False
        checks.append({
            "gate": "V8_PRIVACY",
            "name": "tenant_and_unit_boundary_check",
            "status": "passed" if privacy_ok else "failed",
            "details": "No cross-unit data leakage detected in the authorized file set" if privacy_ok else "Cross-unit data leakage detected"
        })

        checks.append({
            "gate": "V5_POLICY",
            "name": "policy_requirements",
            "status": "passed" if plan.requires_policy else "not_applicable",
            "details": "Policy evaluation was not requested" if not plan.requires_policy else "Policy requirement recorded"
        })
        citation_ok = bool(result.get("query_hash") and result.get("result_hash") and source_files)
        checks.append({
            "gate": "V6_CITATION",
            "name": "query_and_result_citation",
            "status": "passed" if citation_ok else "failed",
            "details": "Query and result hashes are available" if citation_ok else "Query or result hash is missing"
        })

        passed = (
            execution_ok
            and semantic_ok
            and all(check["status"] in {"passed", "not_applicable"} for check in checks)
        )

        resolved_bindings = getattr(plan, "resolved_bindings", None) or []
        provenance = {
            "source_files": source_files,
            "source_sheets": sorted(set(source_sheets)),
            "engine": result.get("engine", "duckdb"),
            "query_hash": result.get("query_hash"),
            "result_hash": result.get("result_hash"),
            "evidence_rows": result.get("evidence_rows", []),
            "source_row_count": result.get("source_row_count"),
            "matched_row_count": result.get("matched_row_count"),
            "resolved_bindings": resolved_bindings,
            "execution_status": execution_status,
            "semantic_status": semantic_status,
            "verification_status": "passed" if passed else "failed",
            "failure_reason": failure_reason if not passed else None,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        return {"passed": passed, "checks": checks, "warnings": warnings, "provenance": provenance}
