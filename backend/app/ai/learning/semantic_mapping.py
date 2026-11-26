import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class SemanticResolution(BaseModel):
    intent: str
    target_concept: str
    result_shape: Optional[str] = None  # scalar_metric, two_metrics, multi_metric, grouped_rows, ranked_rows
    requested_concepts: List[str] = []
    record_family: Optional[str] = None
    limit: Optional[int] = None
    mapped_columns: Dict[str, str] = {}
    suggested_aggregates: List[Dict[str, Any]] = []
    suggested_filters: List[Dict[str, Any]] = []
    suggested_sort: Optional[Dict[str, Any]] = None
    suggested_group_by: List[str] = []
    confidence: float = 1.0
    notes: List[str] = []
    needs_clarification: bool = False
    clarification_message: Optional[str] = None


class SemanticMapper:
    """
    Maps natural language questions in English, Hindi, and Hinglish
    to dataset-specific column semantics based on inspected schema profiles.
    Separates Dimensions, Measures, and Sparse Measures according to architecture rules.
    Understands logical record families in mixed datasets automatically.
    """

    KEYWORD_CONCEPTS = {
        "SENDER_ENTITY": [
            "kisne", "who", "sender", "employee", "user", "person", "kiska", "kaun", "bheja kisne"
        ],
        "EXTERNAL_TRANSFER": [
            "bahar", "external", "outside", "non-company", "personal", "third-party", "vendor", "out mail"
        ],
        "DATA_VOLUME": [
            "kitna data", "data size", "mb", "gb", "kb", "volume", "bytes", "size", "bheja"
        ],
        "BLOCKED_ACTION": [
            "blocked", "block", "roka", "quarantine", "rejected"
        ],
        "MONETARY_AMOUNT": [
            "revenue", "profit", "sales", "gross sales", "amount", "cost", "salary", "kharch", "kamai", "daam"
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

    @classmethod
    def normalize_question(cls, question: str) -> str:
        q = question.strip().lower()
        typos = {
            r"\bwich\b": "which",
            r"\bhigest\b": "highest",
            r"\bout mail\b": "external email",
            r"\bbhai\b": "",
            r"\bwali\b": "",
            r"\bcount batao\b": "count",
            r"\bdikhao\b": "show",
            r"\bbatao\b": "tell",
        }
        for pat, repl in typos.items():
            q = re.sub(pat, repl, q)
        return " ".join(q.split())

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
        q_norm = cls.normalize_question(question)
        q_lower = question.lower().strip()
        cols_lower = {c.lower(): c for c in columns}
        prof = schema_profile or {}
        is_mixed = prof.get("is_mixed", False)
        families = prof.get("record_families", [])
        primary_domain = prof.get("primary_domain")
        disc_col = prof.get("discriminator_column")

        mapped_cols: Dict[str, str] = {}
        aggs: List[Dict[str, Any]] = []
        filters: List[Dict[str, Any]] = []
        group_by: List[str] = []
        sort = None
        notes: List[str] = []
        requested_concepts: List[str] = []
        selected_family_name = None
        intent = "DATA_ANALYSIS"
        result_shape = None

        # Build column roles dictionary
        col_roles: Dict[str, str] = {}
        for c in prof.get("columns", []):
            c_name = str(c.get("name", ""))
            col_roles[c_name] = c.get("role", "dimension")

        # -------------------------------------------------------------
        # 1. Cross-family Queries (e.g. record types overview / comparison)
        # -------------------------------------------------------------
        cross_family_terms = [
            "record type", "record types", "record_type", "har record type",
            "kaun kaun se record types", "har type me", "record type wise",
            "record types hain", "record type me kitne", "dataset me kaun kaun"
        ]
        is_cross_family = any(term in q_norm for term in cross_family_terms) or (
            any(f["family"].lower() in q_norm for f in families) and
            any(term in q_norm for term in ("compare", "aur", "and", "vs", "kitne kitne")) and
            len(families) >= 2 and
            sum(1 for f in families if any(word in q_norm for word in f["family"].lower().split())) >= 2
        )

        if is_cross_family and disc_col and disc_col in columns:
            mapped_cols[disc_col.lower()] = disc_col
            return SemanticResolution(
                intent="grouped_distribution",
                target_concept="record_type_count",
                result_shape="grouped_rows",
                requested_concepts=[disc_col],
                record_family="all",
                mapped_columns=mapped_cols,
                suggested_aggregates=[{"function": "count", "column": "*", "alias": "count"}],
                suggested_filters=[],
                suggested_sort={"column": "count", "ascending": False, "limit": 50},
                suggested_group_by=[disc_col],
                notes=["Grouped by discriminator column across record families"]
            )

        # -------------------------------------------------------------
        # 2. Entire Dataset Scoped Queries
        # -------------------------------------------------------------
        is_entire_dataset = any(term in q_norm for term in [
            "entire dataset", "poore dataset", "whole dataset", "entire table", "whole table", "overall dataset"
        ])

        if is_entire_dataset:
            if any(term in q_norm for term in ["null", "missing", "khali"]):
                for col in columns:
                    if col.lower() in q_norm:
                        mapped_cols[col.lower()] = col
                        filters.append({"column": col, "operator": "is_null", "value": None})
                        return SemanticResolution(
                            intent="scalar_count",
                            target_concept=f"entire_dataset_{col.lower()}_null",
                            result_shape="scalar_metric",
                            requested_concepts=[col],
                            record_family="entire_dataset",
                            mapped_columns=mapped_cols,
                            suggested_aggregates=[{"function": "count", "column": "*", "alias": f"{col.lower()}_null_count"}],
                            suggested_filters=filters,
                            notes=[f"Counted nulls for '{col}' across entire dataset"]
                        )
            if any(term in q_norm for term in ["record", "records", "rows", "row", "count", "kitne", "kitni"]):
                return SemanticResolution(
                    intent="scalar_count",
                    target_concept="total_records",
                    result_shape="scalar_metric",
                    requested_concepts=["total_records"],
                    record_family="entire_dataset",
                    mapped_columns=mapped_cols,
                    suggested_aggregates=[{"function": "count", "column": "*", "alias": "total_records"}],
                    notes=["Counted total records across entire dataset"]
                )

        if any(term in q_norm for term in ["total records kitne", "total kitne records", "kitne total records", "total record kitne", "total rows kitni"]) and not any(f["family"].lower() in q_norm for f in families):
            return SemanticResolution(
                intent="scalar_count",
                target_concept="total_records",
                result_shape="scalar_metric",
                requested_concepts=["total_records"],
                record_family="entire_dataset",
                mapped_columns=mapped_cols,
                suggested_aggregates=[{"function": "count", "column": "*", "alias": "total_records"}],
                notes=["Counted total records across entire dataset"]
            )

        # -------------------------------------------------------------
        # 3. Family Selection for Mixed Datasets
        # -------------------------------------------------------------
        selected_family = None
        if is_mixed and families:
            family_scores: Dict[str, float] = {}
            for f in families:
                score = 0.0
                fname = f["family"].lower()
                for word in fname.split():
                    if len(word) > 2 and word in q_norm:
                        score += 8.0

                if "transaction" in fname and any(w in q_norm for w in ["transaction", "transactions", "txn", "banking", "payment", "debit", "credit"]):
                    score += 6.0
                if ("incident" in fname or "dlp" in fname or "security" in fname) and any(w in q_norm for w in ["incident", "incidents", "security", "dlp", "breach", "violation", "email"]):
                    score += 6.0

                for c in columns:
                    c_low = c.lower()
                    if c_low in q_norm:
                        if c in f.get("active_columns", []):
                            role = f.get("column_roles", {}).get(c, "dimension")
                            if role in ("measure", "sparse_measure"):
                                score += 12.0
                            elif role in ("status", "identifier"):
                                score += 6.0
                            else:
                                score += 4.0
                        if c in f.get("mostly_not_applicable_columns", []):
                            score -= 10.0

                family_scores[f["family"]] = score

            ranked_families = sorted(families, key=lambda f: family_scores[f["family"]], reverse=True)
            top_family = ranked_families[0]
            top_score = family_scores[top_family["family"]]

            if top_score > 0:
                selected_family = top_family
                selected_family_name = top_family["family"]
                disc = top_family.get("discriminator")
                if disc and disc.get("column"):
                    col_name = disc["column"]
                    op = disc.get("operator", "equals")
                    val = disc.get("value")
                    filters.append({"column": col_name, "operator": op, "value": val})
                    notes.append(f"Restricted analysis to record family '{selected_family_name}' via {col_name} {op} {val}")

        active_cols = selected_family.get("active_columns", columns) if selected_family else columns

        # -------------------------------------------------------------
        # 4. Resolve Sender / Entity
        # -------------------------------------------------------------
        has_sender = any(k in q_lower for k in cls.KEYWORD_CONCEPTS["SENDER_ENTITY"])
        if has_sender:
            for candidate in ["src", "source", "sender", "employee_id", "full_name", "employee", "customerid", "customer_id"]:
                if candidate in cols_lower:
                    mapped_cols["entity"] = cols_lower[candidate]
                    group_by.append(cols_lower[candidate])
                    notes.append(f"Mapped entity to column '{cols_lower[candidate]}'")
                    break

        # -------------------------------------------------------------
        # 5. Resolve External Transfer
        # -------------------------------------------------------------
        has_external = any(k in q_lower for k in cls.KEYWORD_CONCEPTS["EXTERNAL_TRANSFER"])
        if has_external:
            for candidate in ["is_ext", "destination", "dest", "recipient_domain", "country"]:
                if candidate in cols_lower:
                    mapped_cols["external"] = cols_lower[candidate]
                    if candidate == "is_ext":
                        filters.append({"column": cols_lower[candidate], "operator": "equals", "value": 1})
                    elif candidate in ["destination", "dest"]:
                        dom_val = primary_domain or "raj.com"
                        filters.append({"column": cols_lower[candidate], "operator": "has_external_recipient", "value": dom_val})
                        if "split" in q_lower or "vs" in q_lower:
                            group_by.append(cols_lower[candidate])
                    notes.append(f"Mapped external transfer to '{cols_lower[candidate]}'")
                    break

        # -------------------------------------------------------------
        # 6. Resolve Data Volume / Size
        # -------------------------------------------------------------
        has_volume = any(k in q_lower for k in cls.KEYWORD_CONCEPTS["DATA_VOLUME"])
        if has_volume:
            for candidate in ["size_kb", "transaction size (kb)", "data_size_bytes", "bytes", "size"]:
                if candidate in cols_lower:
                    mapped_cols["data_size"] = cols_lower[candidate]
                    aggs.append({"function": "sum", "column": cols_lower[candidate], "alias": "total_size"})
                    notes.append(f"Mapped volume to '{cols_lower[candidate]}'")
                    break

        # -------------------------------------------------------------
        # 7. Debit & Credit Semantics
        # -------------------------------------------------------------
        debit_col = cols_lower.get("debit")
        credit_col = cols_lower.get("credit")
        if debit_col and credit_col and ("debit" in q_norm and "credit" in q_norm) and not any(term in q_norm for term in ("top", "highest")):
            mapped_cols["debit"] = debit_col
            mapped_cols["credit"] = credit_col
            aggs = [
                {"function": "count_nonzero", "column": debit_col, "alias": "debit_entries"},
                {"function": "count_nonzero", "column": credit_col, "alias": "credit_entries"}
            ]
            intent = "comparative_count"
            result_shape = "two_metrics"
            requested_concepts = [debit_col, credit_col]
        elif debit_col and "debit" in q_norm and not credit_col:
            mapped_cols["debit"] = debit_col
            if any(term in q_norm for term in ("top", "highest")):
                filters.append({"column": debit_col, "operator": "greater_than", "value": 0})
                group_by = [debit_col]
                sort = {"column": debit_col, "ascending": False, "limit": 5}
                intent = "top_n"
                result_shape = "ranked_rows"
            elif any(term in q_norm for term in ("total", "sum", "amount")) and not any(term in q_norm for term in ("count", "entries", "kitne", "kitni")):
                aggs = [{"function": "sum", "column": debit_col, "alias": "total_debit"}]
                intent = "scalar_count"
                result_shape = "scalar_metric"
            elif any(term in q_norm for term in ("missing", "null", "khali")):
                filters.append({"column": debit_col, "operator": "is_null", "value": None})
                aggs = [{"function": "count", "column": "*", "alias": "missing_debit_entries"}]
                intent = "scalar_count"
                result_shape = "scalar_metric"
            else:
                aggs = [{"function": "count_nonzero", "column": debit_col, "alias": "debit_entries"}]
                intent = "scalar_count"
                result_shape = "scalar_metric"
        elif credit_col and "credit" in q_norm and not debit_col:
            mapped_cols["credit"] = credit_col
            if any(term in q_norm for term in ("average", "avg", "ausat", "mean")):
                aggs = [{"function": "avg", "column": credit_col, "alias": "avg_credit"}]
                intent = "scalar_count"
                result_shape = "scalar_metric"
            elif any(term in q_norm for term in ("total", "sum", "amount")) and not any(term in q_norm for term in ("count", "entries", "kitne", "kitni")):
                aggs = [{"function": "sum", "column": credit_col, "alias": "total_credit"}]
                intent = "scalar_count"
                result_shape = "scalar_metric"
            else:
                aggs = [{"function": "count_nonzero", "column": credit_col, "alias": "credit_entries"}]
                intent = "scalar_count"
                result_shape = "scalar_metric"
        elif debit_col and "debit" in q_norm:
            mapped_cols["debit"] = debit_col
            if any(term in q_norm for term in ("top", "highest")):
                filters.append({"column": debit_col, "operator": "greater_than", "value": 0})
                group_by = [debit_col]
                sort = {"column": debit_col, "ascending": False, "limit": 5}
                intent = "top_n"
                result_shape = "ranked_rows"
            elif any(term in q_norm for term in ("total", "sum", "amount")) and not any(term in q_norm for term in ("count", "entries", "kitne", "kitni")):
                aggs = [{"function": "sum", "column": debit_col, "alias": "total_debit"}]
                intent = "scalar_count"
                result_shape = "scalar_metric"
            elif any(term in q_norm for term in ("missing", "null", "khali")):
                filters.append({"column": debit_col, "operator": "is_null", "value": None})
                aggs = [{"function": "count", "column": "*", "alias": "missing_debit_entries"}]
                intent = "scalar_count"
                result_shape = "scalar_metric"
            else:
                aggs = [{"function": "count_nonzero", "column": debit_col, "alias": "debit_entries"}]
                intent = "scalar_count"
                result_shape = "scalar_metric"
        elif credit_col and "credit" in q_norm:
            mapped_cols["credit"] = credit_col
            if any(term in q_norm for term in ("average", "avg", "ausat", "mean")):
                aggs = [{"function": "avg", "column": credit_col, "alias": "avg_credit"}]
                intent = "scalar_count"
                result_shape = "scalar_metric"
            elif any(term in q_norm for term in ("total", "sum", "amount")) and not any(term in q_norm for term in ("count", "entries", "kitne", "kitni")):
                aggs = [{"function": "sum", "column": credit_col, "alias": "total_credit"}]
                intent = "scalar_count"
                result_shape = "scalar_metric"
            else:
                aggs = [{"function": "count_nonzero", "column": credit_col, "alias": "credit_entries"}]
                intent = "scalar_count"
                result_shape = "scalar_metric"

        # -------------------------------------------------------------
        # 8. Monetary / Finance / Sales
        # -------------------------------------------------------------
        if not aggs and any(k in q_lower for k in cls.KEYWORD_CONCEPTS["MONETARY_AMOUNT"]):
            for term in ["profit", "revenue", "sales", "gross sales", "amount", "salary", "base_salary", "net_paid"]:
                if term in cols_lower:
                    mapped_cols[term] = cols_lower[term]
                    aggs.append({"function": "sum", "column": cols_lower[term], "alias": f"total_{term.replace(' ', '_')}"})
                    notes.append(f"Mapped monetary metric to '{cols_lower[term]}'")
                    break

        # Retail revenue
        if "revenue" in q_lower and "description" in cols_lower and "quantity" in cols_lower and "unitprice" in cols_lower:
            mapped_cols["product"] = cols_lower["description"]
            mapped_cols["revenue"] = f"{cols_lower['quantity']} * {cols_lower['unitprice']}"
            group_by.append(cols_lower["description"])
            aggs = [{"function": "sum_product", "column": mapped_cols["revenue"], "alias": "total_revenue"}]
            notes.append(f"Mapped revenue to derived expression '{mapped_cols['revenue']}'")

        # -------------------------------------------------------------
        # 9. Blocked / Action Status
        # -------------------------------------------------------------
        if any(k in q_lower for k in cls.KEYWORD_CONCEPTS["BLOCKED_ACTION"]):
            for candidate in ["action", "status", "action_status", "approval_status"]:
                if candidate in cols_lower:
                    mapped_cols["action"] = cols_lower[candidate]
                    actual_value = cls._profiled_value(cols_lower[candidate], schema_profile, "Blocked")
                    filters.append({"column": cols_lower[candidate], "operator": "equals", "value": actual_value})
                    notes.append(f"Filtered '{cols_lower[candidate]}' = '{actual_value}'")
                    break

        # -------------------------------------------------------------
        # 10. Severity (High, Critical, etc.)
        # -------------------------------------------------------------
        if "severity" in cols_lower:
            if "high severity" in q_norm or ("high" in q_norm and not any(term in q_norm for term in ["highest", "sabse zyada"])):
                filters.append({"column": cols_lower["severity"], "operator": "equals", "value": "High"})
            elif "critical" in q_norm:
                filters.append({"column": cols_lower["severity"], "operator": "equals", "value": "Critical"})

        # -------------------------------------------------------------
        # 11. Ranking / Sorting
        # -------------------------------------------------------------
        if not sort and any(k in q_lower for k in cls.KEYWORD_CONCEPTS["RANKING_TOP"]):
            sort_target = aggs[-1]["alias"] if aggs else (mapped_cols.get("data_size") or mapped_cols.get("profit") or mapped_cols.get("revenue"))
            if sort_target:
                sort = {"column": sort_target, "ascending": False, "limit": 5 if "top 5" in q_lower else (10 if "top 10" in q_lower else 1)}
                notes.append(f"Sort descending by {sort_target}")

        # Intent detection
        if "policy" in q_lower or any(k in q_lower for k in cls.KEYWORD_CONCEPTS["POLICY_COMPLIANCE"]):
            intent = "POLICY_EVALUATION"
        elif "compare" in q_lower or "split" in q_lower:
            if intent != "comparative_count":
                intent = "COMPARISON_ANALYSIS"

        # If country in query for finance
        if "country" in q_lower and "country" in cols_lower and "country" not in [g.lower() for g in group_by]:
            group_by.append(cols_lower["country"])

        # Default count if needed
        if not aggs and not sort:
            alias_name = "external_email_incidents" if "external" in mapped_cols else (
                "blocked_incidents" if "action" in mapped_cols else "total_records"
            )
            aggs.append({"function": "count", "column": "*", "alias": alias_name})
            intent = "scalar_count"
            result_shape = "scalar_metric"

        target_concept = aggs[0]["alias"] if aggs else (group_by[0] if group_by else "record_count")
        return SemanticResolution(
            intent=intent,
            target_concept=target_concept,
            result_shape=result_shape or ("two_metrics" if intent == "comparative_count" else ("grouped_rows" if group_by else "scalar_metric")),
            requested_concepts=requested_concepts or [target_concept],
            record_family=selected_family_name,
            mapped_columns=mapped_cols,
            suggested_aggregates=aggs,
            suggested_filters=filters,
            suggested_sort=sort,
            suggested_group_by=list(dict.fromkeys(group_by)),
            notes=notes
        )
