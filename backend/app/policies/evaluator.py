from typing import Dict, Any, List
import polars as pl
from app.models.policy import Policy, PolicyRule

class PolicyEvaluator:
    @staticmethod
    def evaluate_file_against_policy(
        file_path: str,
        policy: Policy
    ) -> Dict[str, Any]:
        """
        Deterministically evaluates dataset against machine-readable policy rules.
        Returns policy citations, violating rows, count of violations, and evidence.
        """
        try:
            if file_path.endswith(".csv"):
                df = pl.read_csv(file_path, ignore_errors=True)
            else:
                df = pl.read_excel(file_path)
        except Exception as e:
            return {
                "error": f"Failed to read file for policy evaluation: {e}",
                "violations_count": 0,
                "violations": []
            }

        # Add row index for provenance
        df = df.with_row_index("source_row_index", offset=1)
        
        violations = []
        rule_results = []

        for rule in policy.rules:
            cond = rule.condition
            field = cond.get("field")
            operator = cond.get("operator")
            val = cond.get("value")
            val_source = cond.get("value_source")

            if field not in df.columns:
                rule_results.append({
                    "rule_id": rule.rule_id,
                    "status": "skipped",
                    "reason": f"Column '{field}' not found in dataset."
                })
                continue

            rule_violations = []

            # Check rules
            if operator == "equals":
                violating_df = df.filter(pl.col(field) == val)
            elif operator == "not_equals":
                violating_df = df.filter(pl.col(field) != val)
            elif operator == "greater_than":
                violating_df = df.filter(pl.col(field) > val)
            elif operator == "less_than":
                violating_df = df.filter(pl.col(field) < val)
            elif operator == "not_in" and isinstance(val, list):
                violating_df = df.filter(~pl.col(field).is_in(val))
            elif operator == "contains":
                violating_df = df.filter(pl.col(field).cast(pl.Utf8).str.contains(val))
            else:
                violating_df = pl.DataFrame()

            violating_rows = violating_df.to_dicts()
            for v_row in violating_rows:
                rule_violations.append({
                    "source_row": v_row.get("source_row_index"),
                    "rule_id": rule.rule_id,
                    "description": rule.description,
                    "severity": rule.severity,
                    "offending_field": field,
                    "offending_value": v_row.get(field),
                    "full_row": v_row
                })

            violations.extend(rule_violations)
            rule_results.append({
                "rule_id": rule.rule_id,
                "description": rule.description,
                "violation_count": len(rule_violations)
            })

        return {
            "policy_code": policy.policy_code,
            "policy_title": policy.title,
            "policy_version": policy.version,
            "total_violations": len(violations),
            "rule_summaries": rule_results,
            "violations": violations[:100],  # Return up to 100 sample evidence rows
            "evidence_rows": [v["source_row"] for v in violations]
        }
