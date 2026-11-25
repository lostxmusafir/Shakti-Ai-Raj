from typing import Dict, Any, List
from app.core.exceptions import PlanValidationError
from app.ai.planning.schemas import AnalysisPlan
from app.analysis.execution.sanitizer import SQLSanitizer
from app.models.file import StoredFile

SUPPORTED_OPERATORS = {
    "equals", "not_equals", "greater_than", "less_than",
    "greater_than_or_equal", "less_than_or_equal",
    "in", "not_in", "contains", "not_contains", "is_null", "is_not_null"
}

SUPPORTED_AGGREGATES = {"count", "sum", "avg", "min", "max", "median", "count_distinct", "count_nonzero"}
SUPPORTED_JOIN_TYPES = {"inner", "left", "right", "outer", "anti", "semi"}

class PlanValidator:
    @staticmethod
    def validate_plan(plan: AnalysisPlan, files_map: Dict[str, StoredFile]) -> AnalysisPlan:
        if not plan.datasets:
            raise PlanValidationError("Analysis plan must reference at least one dataset.")

        # Check datasets exist and are accessible
        alias_to_columns: Dict[str, set] = {}
        for ds in plan.datasets:
            if ds.file_id not in files_map:
                raise PlanValidationError(f"Referenced file_id '{ds.file_id}' does not exist or user lacks access.")
            
            stored_file = files_map[ds.file_id]
            schema = stored_file.schema_profile or {}
            cols = {c["name"] for c in schema.get("columns", [])}
            alias_to_columns[ds.alias] = cols

        # If custom SQL is provided, validate statement type and sanitize
        if plan.sql_query:
            sql_clean = plan.sql_query.strip().upper()
            if not (sql_clean.startswith("SELECT") or sql_clean.startswith("WITH")):
                raise PlanValidationError("Custom SQL must begin with SELECT or WITH.")
            allowed_aliases = [ds.alias for ds in plan.datasets] + ["v", "v0", "incidents", "dataset"]
            try:
                SQLSanitizer.validate_sql(plan.sql_query, allowed_aliases)
            except Exception as e:
                raise PlanValidationError(f"Plan custom SQL failed security validation: {e}")
            return plan

        # Helper to find column across aliases
        all_columns = set.union(*alias_to_columns.values()) if alias_to_columns else set()

        # Validate filters
        for cond in plan.filters:
            if cond.operator not in SUPPORTED_OPERATORS:
                raise PlanValidationError(f"Unsupported filter operator: '{cond.operator}'. Supported: {SUPPORTED_OPERATORS}")
            if cond.column not in all_columns:
                match = [c for c in all_columns if c.lower() == cond.column.lower()]
                if match:
                    cond.column = match[0]
                else:
                    raise PlanValidationError(f"Column '{cond.column}' in filter condition not found in datasets. Available: {list(all_columns)}")

        # Validate group_by
        column_roles: Dict[str, str] = {}
        for ds in plan.datasets:
            stored_file = files_map[ds.file_id]
            schema = stored_file.schema_profile or {}
            for c in schema.get("columns", []):
                column_roles[c["name"].lower()] = c.get("role", "dimension")

        for g_col in plan.group_by:
            match = [c for c in all_columns if c.lower() == g_col.lower()]
            if not match:
                raise PlanValidationError(f"Group by column '{g_col}' not found in datasets. Available: {list(all_columns)}")
            
            actual_col = match[0]
            col_role = column_roles.get(actual_col.lower())
            if col_role in ["measure", "sparse_measure"] and (
                plan.intent in ["scalar_count", "comparative_count"]
                or plan.result_shape in ["scalar_metric", "two_metrics", "multi_metric"]
            ):
                raise PlanValidationError(
                    f"Measure column '{actual_col}' (role: {col_role}) cannot be grouped for count query intent '{plan.intent}'."
                )

        # Validate aggregations
        for agg in plan.aggregations:
            if agg.function.lower() not in SUPPORTED_AGGREGATES:
                raise PlanValidationError(f"Unsupported aggregate function '{agg.function}'. Supported: {SUPPORTED_AGGREGATES}")
            if agg.function.lower() in {"count_distinct", "distinct_count"} and (not agg.column or agg.column == "*"):
                raise PlanValidationError("Aggregate 'count_distinct' requires a column.")
            if agg.column and agg.column != "*":
                if agg.column not in all_columns:
                    match = [c for c in all_columns if c.lower() == agg.column.lower()]
                    if match:
                        agg.column = match[0]
                    else:
                        raise PlanValidationError(f"Aggregation column '{agg.column}' not found in datasets.")
            if agg.filter_condition:
                if agg.filter_condition.operator not in SUPPORTED_OPERATORS:
                    raise PlanValidationError(f"Unsupported filter operator in aggregate condition: '{agg.filter_condition.operator}'.")
                if agg.filter_condition.column not in all_columns:
                    match = [c for c in all_columns if c.lower() == agg.filter_condition.column.lower()]
                    if match:
                        agg.filter_condition.column = match[0]
                    else:
                        raise PlanValidationError(f"Column '{agg.filter_condition.column}' in aggregate filter not found in datasets.")

        # Validate having
        if plan.having:
            agg_aliases = {agg.alias for agg in plan.aggregations if agg.alias}
            valid_targets = all_columns | agg_aliases
            for cond in plan.having:
                if cond.operator not in SUPPORTED_OPERATORS:
                    raise PlanValidationError(f"Unsupported having operator: '{cond.operator}'. Supported: {SUPPORTED_OPERATORS}")
                if cond.column not in valid_targets:
                    match = [c for c in valid_targets if c.lower() == cond.column.lower()]
                    if match:
                        cond.column = match[0]
                    else:
                        raise PlanValidationError(f"Having condition column '{cond.column}' not found in datasets or aggregate aliases.")

        # Validate joins
        for join in plan.joins:
            if join.join_type.lower() not in SUPPORTED_JOIN_TYPES:
                raise PlanValidationError(f"Unsupported join type: '{join.join_type}'. Supported: {SUPPORTED_JOIN_TYPES}")
            if join.left_dataset not in alias_to_columns:
                raise PlanValidationError(f"Join left dataset alias '{join.left_dataset}' not defined.")
            if join.right_dataset not in alias_to_columns:
                raise PlanValidationError(f"Join right dataset alias '{join.right_dataset}' not defined.")
            
            left_cols = alias_to_columns[join.left_dataset]
            right_cols = alias_to_columns[join.right_dataset]
            
            if join.left_column not in left_cols:
                raise PlanValidationError(f"Join column '{join.left_column}' not found in '{join.left_dataset}'.")
            if join.right_column not in right_cols:
                raise PlanValidationError(f"Join column '{join.right_column}' not found in '{join.right_dataset}'.")

        # Sanitize limit
        if plan.limit and plan.limit > 10000:
            plan.limit = 10000

        return plan
