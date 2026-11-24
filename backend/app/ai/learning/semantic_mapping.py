import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class SemanticResolution(BaseModel):
    intent: str
    target_concept: str
    mapped_columns: Dict[str, str] = {}
    suggested_aggregates: List[Dict[str, str]] = []
    suggested_filters: List[Dict[str, Any]] = []
    suggested_sort: Optional[Dict[str, Any]] = None
    suggested_group_by: List[str] = []
    confidence: float = 1.0
    notes: List[str] = []

class SemanticMapper:
    """
    Maps natural language questions in English, Hindi, and Hinglish
    to dataset-specific column semantics based on inspected schema profiles.
    """

    KEYWORD_CONCEPTS = {
        "SENDER_ENTITY": [
            "kisne", "who", "sender", "employee", "user", "person", "kiska", "kaun", "bheja kisne"
        ],
        "EXTERNAL_TRANSFER": [
            "bahar", "external", "outside", "non-company", "personal", "third-party", "vendor"
        ],
        "DATA_VOLUME": [
            "kitna data", "data size", "mb", "gb", "kb", "volume", "bytes", "size", "bheja"
        ],
        "BLOCKED_ACTION": [
            "blocked", "block", "roka", "quarantine", "rejected"
        ],
        "MONETARY_AMOUNT": [
            "revenue", "profit", "sales", "expense", "amount", "cost", "salary", "kharch", "kamai", "daam"
        ],
        "RANKING_TOP": [
            "sabse zyada", "most", "highest", "top", "bada", "maximum", "max", "sabse bada"
        ],
        "RANKING_BOTTOM": [
            "sabse kam", "least", "lowest", "bottom", "minimum", "min", "chhota"
        ],
        "TEMPORAL": [
            "peak hour", "ghanta", "hour", "time", "month", "year", "date", "din", "weekend", "today"
        ],
        "POLICY_COMPLIANCE": [
            "policy", "violate", "violation", "rule", "compliance", "against", "breach"
        ],
        "COMPARISON": [
            "compare", "difference", "split", "vs", "versus", "antar", "reconcile"
        ]
    }

    @staticmethod
    def _profiled_value(column: str, schema_profile: Optional[Dict[str, Any]], fallback: str) -> str:
        for column_profile in (schema_profile or {}).get("columns", []):
            if str(column_profile.get("name", "")).lower() != column.lower():
                continue
            for value in (column_profile.get("top_values") or {}).keys():
                if str(value).lower() in {fallback.lower(), "blocked", "block", "rejected"}:
                    return str(value)
        return fallback

    @classmethod
    def resolve_semantics(
        cls,
        question: str,
        columns: List[str],
        schema_profile: Optional[Dict[str, Any]] = None
    ) -> SemanticResolution:
        q_lower = question.lower().strip()
        cols_lower = {c.lower(): c for c in columns}
        mapped_cols: Dict[str, str] = {}
        aggs = []
        filters = []
        sort = None
        group_by = []
        notes = []

        # 1. Resolve Entity / Sender
        if any(k in q_lower for k in cls.KEYWORD_CONCEPTS["SENDER_ENTITY"]):
            for candidate in ["src", "source", "sender", "employee_id", "full_name", "employee", "customerid", "customer_id"]:
                if candidate in cols_lower:
                    mapped_cols["entity"] = cols_lower[candidate]
                    group_by.append(cols_lower[candidate])
                    notes.append(f"Mapped entity to column '{cols_lower[candidate]}'")
                    break

        # 2. Resolve External
        if any(k in q_lower for k in cls.KEYWORD_CONCEPTS["EXTERNAL_TRANSFER"]):
            for candidate in ["is_ext", "destination", "dest", "recipient_domain", "country"]:
                if candidate in cols_lower:
                    mapped_cols["external"] = cols_lower[candidate]
                    if candidate == "is_ext":
                        filters.append({"column": cols_lower[candidate], "operator": "equals", "value": 1})
                    elif candidate in ["destination", "dest"]:
                        # If asking for split or compare
                        if "split" in q_lower or "vs" in q_lower:
                            group_by.append(cols_lower[candidate])
                    notes.append(f"Mapped external transfer to '{cols_lower[candidate]}'")
                    break

        # 3. Resolve Data Volume / Size
        if any(k in q_lower for k in cls.KEYWORD_CONCEPTS["DATA_VOLUME"]):
            for candidate in ["size_kb", "transaction size (kb)", "data_size_bytes", "bytes", "size"]:
                if candidate in cols_lower:
                    mapped_cols["data_size"] = cols_lower[candidate]
                    aggs.append({"function": "sum", "column": cols_lower[candidate], "alias": "total_size"})
                    notes.append(f"Mapped volume to '{cols_lower[candidate]}'")
                    break

        # 4. Resolve Money / Finance / Sales
        if any(k in q_lower for k in cls.KEYWORD_CONCEPTS["MONETARY_AMOUNT"]):
            for term in ["profit", "revenue", "sales", "gross sales", "amount", "salary", "base_salary", "net_paid"]:
                if term in cols_lower:
                    mapped_cols[term] = cols_lower[term]
                    aggs.append({"function": "sum", "column": cols_lower[term], "alias": f"total_{term.replace(' ', '_')}"})
                    notes.append(f"Mapped monetary metric to '{cols_lower[term]}'")
                    break

        # Retail revenue is a derived metric from actual quantity and unit-price columns.
        if "revenue" in q_lower and "description" in cols_lower and "quantity" in cols_lower and "unitprice" in cols_lower:
            mapped_cols["product"] = cols_lower["description"]
            mapped_cols["revenue"] = f"{cols_lower['quantity']} * {cols_lower['unitprice']}"
            group_by.append(cols_lower["description"])
            aggs.append({"function": "sum_product", "column": mapped_cols["revenue"], "alias": "total_revenue"})
            notes.append(f"Mapped revenue to derived expression '{mapped_cols['revenue']}'")

        # 5. Resolve Blocked / Action Status
        if any(k in q_lower for k in cls.KEYWORD_CONCEPTS["BLOCKED_ACTION"]):
            for candidate in ["action", "status", "action_status", "approval_status"]:
                if candidate in cols_lower:
                    mapped_cols["action"] = cols_lower[candidate]
                    actual_value = cls._profiled_value(cols_lower[candidate], schema_profile, "Blocked")
                    filters.append({"column": cols_lower[candidate], "operator": "equals", "value": actual_value})
                    notes.append(f"Filtered '{cols_lower[candidate]}' = '{actual_value}'")
                    break

        # 6. Resolve Ranking / Sorting
        if any(k in q_lower for k in cls.KEYWORD_CONCEPTS["RANKING_TOP"]):
            sort_target = aggs[-1]["alias"] if aggs else (mapped_cols.get("data_size") or mapped_cols.get("profit") or mapped_cols.get("revenue"))
            if sort_target:
                sort = {"column": sort_target, "ascending": False, "limit": 5 if "top 5" in q_lower else (10 if "top 10" in q_lower else 1)}
                notes.append(f"Sort descending by {sort_target}")

        # Intent detection
        intent = "DATA_ANALYSIS"
        if "policy" in q_lower or any(k in q_lower for k in cls.KEYWORD_CONCEPTS["POLICY_COMPLIANCE"]):
            intent = "POLICY_EVALUATION"
        elif "compare" in q_lower or "split" in q_lower:
            intent = "COMPARISON_ANALYSIS"

        return SemanticResolution(
            intent=intent,
            target_concept=aggs[0]["alias"] if aggs else "record_count",
            mapped_columns=mapped_cols,
            suggested_aggregates=aggs,
            suggested_filters=filters,
            suggested_sort=sort,
            suggested_group_by=list(dict.fromkeys(group_by)),
            notes=notes
        )
