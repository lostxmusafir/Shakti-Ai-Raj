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
            "revenue", "profit", "sales", "gross sales", "amount", "cost", "salary", "payroll", "gross pay",
            "kharch", "kamai", "daam"
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

    MEASURE_TOKENS = {
        "profit", "revenue", "sales", "income", "amount", "amt", "cost", "salary",
        "pay", "price", "value", "fee", "budget", "margin", "discount", "tax",
        "balance", "debit", "credit", "expense", "spend", "earning", "earnings",
        "commission", "bonus", "refund", "units", "quantity", "qty", "count",
        "hours", "duration", "score", "rate", "ratio", "pct", "percent",
        "percentage", "weight", "size", "bytes", "kb", "mb", "gb", "tb",
        "bandwidth", "traffic", "volume", "transferred", "transfer",
    }

    DIMENSION_NOUN_TOKENS = {
        "region", "group", "category", "type", "department", "dept", "channel",
        "team", "division", "segment", "tier", "status", "country", "city",
        "state", "product", "zone", "area", "branch", "office", "unit",
        "name", "location", "market", "territory", "sector", "line", "class",
        "brand", "vendor", "supplier", "customer", "client", "employee",
        "manager", "owner", "account", "method", "mode", "source", "destination",
        "center", "centre", "hub", "site", "store", "warehouse", "role",
        "stage", "phase", "campaign", "program", "project", "port", "desk",
        "facility",
    }

    @staticmethod
    def _slug(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "metric"

    @staticmethod
    def _col_tokens(col: str) -> List[str]:
        return re.findall(r"[a-z]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", col).lower())

    @staticmethod
    def _word_token_pattern(token: str) -> str:
        if len(token) >= 4 and token.endswith("y") and token[-2] not in "aeiou":
            return rf"{re.escape(token[:-1])}(?:y|ies)"
        if len(token) >= 2 and (token.endswith(("ch", "sh")) or token[-1] in "sxz"):
            return rf"{re.escape(token)}(?:es)?"
        return rf"{re.escape(token)}s?"

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
            r"\bsaal\b": "year",
            r"\bmahina\b": "month",
            r"\bmahine\b": "month",
            r"\bmahino\b": "month",
            r"\bmonthly\b": "month",
            r"\bannual\b": "year",
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

        # Build column roles and inferred types without defaulting missing roles to "dimension"
        col_roles: Dict[str, str] = {}
        col_types: Dict[str, str] = {}
        for c in prof.get("columns", []):
            c_name = str(c.get("name", ""))
            if not c_name:
                continue
            if c.get("role"):
                col_roles[c_name] = str(c["role"])
            if c.get("inferred_type"):
                col_types[c_name] = str(c["inferred_type"])

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

        # Schema-driven scalar transfer maximum. This covers natural forms
        # such as "sabse bada transaction" without tying the rule to a file
        # name or a particular DLP dataset.
        if (
            "transaction" in q_norm
            and re.search(r"\b(?:highest|maximum|max|largest|biggest|sabse|bada)\b", q_norm)
            and not re.search(r"\baction\b", q_norm)
        ):
            transfer_measures = [
                c for c in active_cols
                if col_roles.get(c) in ("measure", "sparse_measure")
                and "transaction" in cls._col_tokens(c)
                and any(token in cls._col_tokens(c) for token in ("size", "amount", "value"))
            ]
            if len(transfer_measures) == 1:
                transfer_col = transfer_measures[0]
                transfer_alias = f"max_{cls._slug(transfer_col)}"
                return SemanticResolution(
                    intent="scalar_metric",
                    target_concept=transfer_alias,
                    result_shape="scalar_metric",
                    requested_concepts=[transfer_col],
                    record_family=selected_family_name,
                    mapped_columns={"measure": transfer_col},
                    suggested_aggregates=[{"function": "max", "column": transfer_col, "alias": transfer_alias}],
                    suggested_filters=filters,
                    notes=[f"Scalar maximum of '{transfer_col}'"],
                )

        # -------------------------------------------------------------
        # 4. Generic Dimension & Measure Helpers (Schema-driven)
        # -------------------------------------------------------------
        def _is_temporal_col(col: str) -> bool:
            if col_roles.get(col) == "timestamp" or col_types.get(col) == "datetime":
                return True
            if col not in col_roles:
                cl = col.lower()
                tokens = set(cls._col_tokens(col))
                if (
                    (tokens & {"date", "time", "timestamp", "datetime"})
                    or cl.endswith(("_at", "_date", "_time"))
                    or cl in {"created_at", "updated_at"}
                ):
                    return True
            return False

        def _is_likely_measure(col: str) -> bool:
            tokens = cls._col_tokens(col)
            is_id_like = bool(tokens and tokens[-1] in {"id", "no", "code", "key"})
            if col in col_roles:
                return col_roles[col] in ("measure", "sparse_measure")
            if _is_temporal_col(col) or is_id_like:
                return False
            if col in col_types:
                return col_types[col] in ("integer", "float")
            if len(tokens) > 1 and tokens[-1] in cls.DIMENSION_NOUN_TOKENS:
                return False
            return bool(set(tokens) & cls.MEASURE_TOKENS)

        def _full_col_plural_patterns(col: str) -> List[str]:
            cl = col.lower()
            pats: List[str] = []
            if re.fullmatch(r"[a-z]+", cl):
                pats.append(cls._word_token_pattern(cl))
            tokens = cls._col_tokens(col)
            if len(tokens) >= 2 and re.fullmatch(r"[a-z_ ]+", cl):
                pats.append(r"\s+".join([re.escape(t) for t in tokens[:-1]] + [cls._word_token_pattern(tokens[-1])]))
            return list(dict.fromkeys(pats))

        def _match_dimension(excluded_phrase_col: Optional[str] = None) -> Optional[str]:
            q_dim = q_norm
            if excluded_phrase_col:
                m_low = excluded_phrase_col.lower()
                for phrase in dict.fromkeys((m_low, m_low.replace("_", " "))):
                    q_dim = re.sub(rf"\b{re.escape(phrase)}\b", " ", q_dim)
                q_dim = " ".join(q_dim.split())

            dim_candidates = [
                c for c in active_cols
                if not _is_temporal_col(c)
                and not _is_likely_measure(c)
                and col_roles.get(c, "dimension") not in ("measure", "sparse_measure", "timestamp", "identifier")
            ]

            sorted_dims = sorted(dim_candidates, key=lambda col: len(col), reverse=True)
            # 1a. Exact or underscore-spaced column name matches take precedence (longest phrase first)
            for c in sorted_dims:
                cl = c.lower()
                if (
                    re.search(rf"\b{re.escape(cl)}\b", q_dim)
                    or re.search(rf"\b{re.escape(cl.replace('_', ' '))}\b", q_dim)
                ):
                    return c

            # 1b. Pluralized full column name matches (longest phrase first)
            for c in sorted_dims:
                for pat in _full_col_plural_patterns(c):
                    if re.search(rf"\b{pat}\b", q_dim):
                        return c

            # 2. Natural token match (e.g., DestinationDomain -> domain/domains, Country -> country/countries)
            for c in dim_candidates:
                parts = [p for p in cls._col_tokens(c) if len(p) >= 4]
                for p in parts:
                    if p in ("name", "level", "type", "time", "date", "size"):
                        continue
                    if re.search(rf"\b{cls._word_token_pattern(p)}\b", q_dim):
                        return c
            return None

        def _match_measure() -> Optional[str]:
            num_candidates = [c for c in active_cols if _is_likely_measure(c)]
            if not num_candidates:
                return None
            sorted_nums = sorted(num_candidates, key=lambda col: len(col), reverse=True)
            if re.search(r"\bdata\b", q_norm) and (
                re.search(r"\b(?:bheja|sent|transfer|transferred)\b", q_norm)
                or ("source" in q_norm and re.search(r"\b(?:highest|maximum|max|top|sabse)\b", q_norm))
            ) or (
                "transaction" in q_norm
                and re.search(r"\b(?:highest|maximum|max|largest|biggest|sabse|bada)\b", q_norm)
            ):
                volume_cols = [
                    c for c in num_candidates
                    if any(token in set(cls._col_tokens(c)) for token in ("size", "volume", "bytes", "transfer", "bandwidth"))
                ]
                if len(volume_cols) == 1:
                    return volume_cols[0]
            # Preserve an explicit multi-word measure match (for example,
            # "gross profit") before falling back to token scoring.
            for c in sorted_nums:
                normalized_col = " ".join(c.lower().split())
                if normalized_col and re.search(rf"\b{re.escape(normalized_col)}\b", q_norm):
                    return c
            # Prefer a single-token exact match over a broader name such as
            # "Gross Sales" when the user asked specifically for "Sales".
            query_tokens = set(re.findall(r"[a-z]+", q_norm))
            generic_measure_tokens = {"total", "avg", "sum", "net", "gross", "num", "val", "value", "sold", "paid", "made", "earned", "spent", "sent"}
            token_matches = []
            for index, c in enumerate(num_candidates):
                tokens = [t for t in cls._col_tokens(c) if len(t) >= 3 and t not in generic_measure_tokens]
                hits = sum(1 for token in tokens if token in query_tokens)
                if hits:
                    token_matches.append((hits / max(len(tokens), 1), hits, -len(c.strip()), -index, c))
            if token_matches:
                best = max(token_matches)
                if best[0] >= 0.5:
                    return best[-1]
            # 1a. Exact or underscore-spaced name match with word boundaries (longest phrase first)
            for c in sorted_nums:
                cl = c.lower()
                if (
                    re.search(rf"\b{re.escape(cl)}\b", q_norm)
                    or re.search(rf"\b{re.escape(cl.replace('_', ' '))}\b", q_norm)
                ):
                    return c
            # 1b. Pluralized full column name match (longest phrase first)
            for c in sorted_nums:
                for pat in _full_col_plural_patterns(c):
                    if re.search(rf"\b{pat}\b", q_norm):
                        return c
            # 2. Significant token match
            generic_measure_tokens = {
                "total", "avg", "sum", "net", "gross", "num", "val", "value",
                "sold", "paid", "made", "earned", "spent", "sent",
            }
            # Prefer the column with the most query tokens when a qualifier
            # such as "maximum" sits before a multi-word measure name.
            query_tokens = set(re.findall(r"[a-z]+", q_norm))
            scored_candidates = []
            for c in num_candidates:
                tokens = [t for t in cls._col_tokens(c) if len(t) >= 3 and t not in generic_measure_tokens]
                hits = sum(
                    1 for token in tokens
                    if token in query_tokens or any(re.fullmatch(cls._word_token_pattern(token), query_token) for query_token in query_tokens)
                )
                if hits:
                    scored_candidates.append((hits / max(len(tokens), 1), hits, c))
            if scored_candidates:
                _, _, best_column = max(scored_candidates)
                return best_column
            # 3. Domain-agnostic volume / bandwidth / transfer synonym match
            if any(k in q_norm for k in ("bandwidth", "data transfer", "transferred", "traffic", "volume", "mb", "gb", "kb", "bytes", "data size")):
                for c in num_candidates:
                    cl = c.lower()
                    if any(u in cl for u in ("mb", "gb", "kb", "bytes", "transfer", "bandwidth", "size")):
                        return c
            # 4. Unambiguous monetary synonym fallback
            monetary_terms = set(cls.KEYWORD_CONCEPTS["MONETARY_AMOUNT"])
            monetary_query = re.sub(r"\bcost\s+center\b", "", q_norm)
            if any(re.search(rf"\b{re.escape(m)}\b", monetary_query) for m in monetary_terms):
                monetary_cols = [c for c in num_candidates if set(cls._col_tokens(c)) & monetary_terms]
                if len(monetary_cols) == 1:
                    return monetary_cols[0]
            # Payroll is a business concept, not necessarily a column name.
            if re.search(r"\bpayroll\b|\bgross\s+pay\b", q_norm):
                payroll_cols = [
                    c for c in num_candidates
                    if set(cls._col_tokens(c)) & {"pay", "payroll", "salary", "wage", "gross"}
                ]
                if len(payroll_cols) == 1:
                    return payroll_cols[0]
            # In DLP data, "data bheja" means transfer volume even when the
            # user does not say "size" or "volume" explicitly.
            if re.search(r"\bdata\b", q_norm) and (
                re.search(r"\b(?:bheja|sent|transfer|transferred)\b", q_norm)
                or ("source" in q_norm and re.search(r"\b(?:highest|maximum|max|top|sabse)\b", q_norm))
            ):
                volume_cols = [
                    c for c in num_candidates
                    if any(token in set(cls._col_tokens(c)) for token in ("size", "volume", "bytes", "transfer", "bandwidth"))
                ]
                if len(volume_cols) == 1:
                    return volume_cols[0]
            return None

        matched_meas = _match_measure()
        transaction_measures = [
            c for c in active_cols
            if _is_likely_measure(c)
            and "transaction" in cls._col_tokens(c)
            and any(token in cls._col_tokens(c) for token in ("size", "amount", "value"))
        ]
        if transaction_measures and (
            ("transaction" in q_norm and re.search(r"\b(?:highest|maximum|max|largest|biggest|sabse|bada)\b", q_norm))
            or ("average" in q_norm and "size" in q_norm)
        ):
            matched_meas = transaction_measures[0] if len(transaction_measures) == 1 else matched_meas
        matched_dim = _match_dimension(matched_meas)

        def _has_dim_grouping_cue(dim_col: Optional[str]) -> bool:
            if any(k in q_norm for k in ("breakdown", "distribution", "wise", " vs ", " versus ")):
                return True
            if not dim_col:
                return False
            dl = dim_col.lower()
            dim_patterns = [re.escape(dl), re.escape(dl.replace("_", " ")), *_full_col_plural_patterns(dim_col)]
            for p in cls._col_tokens(dim_col):
                if len(p) >= 4 and p not in ("name", "level", "type", "time", "date", "size"):
                    dim_patterns.append(cls._word_token_pattern(p))
            dim_alt = "|".join(dict.fromkeys(dim_patterns))
            return bool(
                re.search(rf"\b(?:by|per|each|every)\s+(?:the\s+)?(?:{dim_alt})\b", q_norm)
                or re.search(rf"\bhar\s+(?:ek\s+)?(?:{dim_alt})\b", q_norm)
                or re.search(r"\b(?:ke\s+)?hisaab\s+se\b", q_norm)
                or re.search(r"\b(?:ke\s+)?hisab\s+se\b", q_norm)
            )

        is_breakdown = (
            _has_dim_grouping_cue(matched_dim)
            and not ("debit" in q_norm and "credit" in q_norm)
        )

        is_avg_query = any(re.search(rf"\b{w}\b", q_norm) for w in ("average", "avg", "mean", "ausat"))
        explicit_count_nouns = any(
            re.search(rf"\b{w}\b", q_norm)
            for w in ("count", "rows", "records", "entries", "events", "incidents", "transactions", "unique", "distinct")
        )
        # Hindi uses "kitna/kitni" for both counts and metric totals. Once a
        # concrete measure is resolved, treat it as a value question unless a
        # count noun (records, entries, incidents, etc.) is also present.
        is_explicit_count = explicit_count_nouns or (
            any(p in q_norm for p in ("how many", "kitne", "kitni")) and matched_meas is None
        )

        active_filter = None
        if re.search(r"\bactive\b", q_norm):
            for col_profile in prof.get("columns", []):
                col_name = str(col_profile.get("name", ""))
                if "status" not in col_name.lower():
                    continue
                for value in (col_profile.get("top_values") or {}):
                    if str(value).lower() == "active":
                        active_filter = {"column": col_name, "operator": "equals", "value": value}
                        break
                if active_filter:
                    break
        if active_filter:
            filters.append(active_filter)

        def _build_agg(measure_col: Optional[str]) -> tuple[str, List[Dict[str, Any]], str, List[str]]:
            if measure_col and not is_explicit_count:
                agg_func = "avg" if is_avg_query else "sum"
                agg_prefix = "avg" if agg_func == "avg" else "total"
                agg_alias = f"{agg_prefix}_{cls._slug(measure_col)}"
                mapped_cols["measure"] = measure_col
                mapped_cols[measure_col.lower()] = measure_col
                return (
                    agg_alias,
                    [{"function": agg_func, "column": measure_col, "alias": agg_alias}],
                    agg_alias,
                    [matched_dim, measure_col] if matched_dim else [measure_col],
                )
            return (
                "count",
                [{"function": "count", "column": "*", "alias": "count"}],
                matched_dim or "count",
                [matched_dim] if matched_dim else ["count"],
            )

        # Generic Top-N / Bottom-N Ranking takes precedence when both ranking and breakdown cues appear
        has_top_ranking = any(
            re.search(rf"\b{re.escape(k)}\b", q_norm) for k in cls.KEYWORD_CONCEPTS["RANKING_TOP"]
        )
        has_bottom_ranking = any(
            re.search(rf"\b{re.escape(k)}\b", q_norm) for k in cls.KEYWORD_CONCEPTS["RANKING_BOTTOM"]
        )
        has_ranking = has_top_ranking or has_bottom_ranking
        sort_ascending = bool(has_bottom_ranking and not has_top_ranking)
        if has_ranking and matched_dim and not ("debit" in q_norm and "credit" in q_norm):
            mapped_cols["dimension"] = matched_dim
            limit_match = re.search(r"\b(?:top|bottom)\s+(\d+)\b", q_norm)
            singular_terms = (
                "top", "sabse zyada", "most", "highest", "maximum", "max", "sabse bada",
                "sabse kam", "least", "lowest", "minimum", "min", "chhota",
            )
            if limit_match:
                top_limit = int(limit_match.group(1))
            elif any(re.search(rf"\b{re.escape(t)}\b", q_norm) for t in singular_terms):
                top_limit = 1
            else:
                top_limit = 5
            agg_alias, aggs, target_concept, req_concepts = _build_agg(matched_meas)
            return SemanticResolution(
                intent="top_n",
                target_concept=target_concept,
                result_shape="ranked_rows",
                requested_concepts=req_concepts,
                record_family=selected_family_name,
                limit=top_limit,
                mapped_columns=mapped_cols,
                suggested_aggregates=aggs,
                suggested_filters=filters,
                suggested_sort={"column": agg_alias, "ascending": sort_ascending, "limit": top_limit},
                suggested_group_by=[matched_dim],
                notes=[f"Ranked '{matched_dim}' by '{agg_alias}'"],
            )

        if is_breakdown and matched_dim:
            mapped_cols["dimension"] = matched_dim
            agg_alias, aggs, target_concept, req_concepts = _build_agg(matched_meas)
            sort = {"column": agg_alias, "ascending": False, "limit": 50}
            return SemanticResolution(
                intent="grouped_distribution",
                target_concept=target_concept,
                result_shape="grouped_rows",
                requested_concepts=req_concepts,
                record_family=selected_family_name,
                limit=50,
                mapped_columns=mapped_cols,
                suggested_aggregates=aggs,
                suggested_filters=filters,
                suggested_sort=sort,
                suggested_group_by=[matched_dim],
                notes=[f"Grouped distribution by '{matched_dim}'"],
            )

        # A scalar maximum is different from a ranked group. Keep this branch
        # before the generic sum fallback so "maximum transaction size" does
        # not become SUM or a one-row grouped query.
        is_max_query = any(
            re.search(rf"\b{re.escape(word)}\b", q_norm)
            for word in ("max", "maximum", "largest", "biggest", "highest")
        )
        if matched_meas and not matched_dim and not is_explicit_count and is_max_query:
            alias = f"max_{cls._slug(matched_meas)}"
            return SemanticResolution(
                intent="scalar_metric",
                target_concept=alias,
                result_shape="scalar_metric",
                requested_concepts=[matched_meas],
                record_family=selected_family_name,
                mapped_columns={"measure": matched_meas, matched_meas.lower(): matched_meas},
                suggested_aggregates=[{"function": "max", "column": matched_meas, "alias": alias}],
                suggested_filters=filters,
                notes=[f"Scalar maximum of '{matched_meas}'"],
            )

        # Generic scalar SUM/AVG when measure is matched with total/overall/sum/avg (no group_by)
        if (
            matched_meas
            and not matched_dim
            and not is_explicit_count
            and not ("debit" in q_norm and "credit" in q_norm)
            and (is_avg_query or any(re.search(rf"\b{w}\b", q_norm) for w in ("total", "overall", "sum", "pura", "puri", "poora", "poori", "kul")))
        ):
            agg_alias, aggs, target_concept, req_concepts = _build_agg(matched_meas)
            return SemanticResolution(
                intent="scalar_count",
                target_concept=target_concept,
                result_shape="scalar_metric",
                requested_concepts=req_concepts,
                record_family=selected_family_name,
                mapped_columns=mapped_cols,
                suggested_aggregates=aggs,
                suggested_filters=filters,
                notes=[f"Scalar aggregate of '{matched_meas}'"],
            )

        # -------------------------------------------------------------
        # 5. Resolve Sender / Entity
        # -------------------------------------------------------------
        has_sender = any(k in q_lower for k in cls.KEYWORD_CONCEPTS["SENDER_ENTITY"]) and not (
            is_explicit_count or active_filter
        )
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
            for candidate in ["size_kb", "transaction size (kb)", "data_size_bytes", "bytes", "size", "datatransferredmb"]:
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
                    agg_fn_8 = "avg" if is_avg_query else "sum"
                    agg_pfx_8 = "avg" if agg_fn_8 == "avg" else "total"
                    aggs.append({"function": agg_fn_8, "column": cols_lower[term], "alias": f"{agg_pfx_8}_{term.replace(' ', '_')}"})
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
        has_top_11 = any(re.search(rf"\b{re.escape(k)}\b", q_norm) for k in cls.KEYWORD_CONCEPTS["RANKING_TOP"])
        has_bottom_11 = any(re.search(rf"\b{re.escape(k)}\b", q_norm) for k in cls.KEYWORD_CONCEPTS["RANKING_BOTTOM"])
        if not sort and (has_top_11 or has_bottom_11):
            sort_target = aggs[-1]["alias"] if aggs else (mapped_cols.get("data_size") or mapped_cols.get("profit") or mapped_cols.get("revenue"))
            if sort_target:
                asc_11 = bool(has_bottom_11 and not has_top_11)
                limit_match_11 = re.search(r"\b(?:top|bottom)\s+(\d+)\b", q_norm)
                limit_11 = int(limit_match_11.group(1)) if limit_match_11 else (5 if "top 5" in q_lower else (10 if "top 10" in q_lower else 1))
                sort = {"column": sort_target, "ascending": asc_11, "limit": limit_11}
                notes.append(f"Sort {'ascending' if asc_11 else 'descending'} by {sort_target}")

        # Intent detection
        if "policy" in q_lower or any(k in q_lower for k in cls.KEYWORD_CONCEPTS["POLICY_COMPLIANCE"]):
            intent = "POLICY_EVALUATION"
        elif "compare" in q_lower or "split" in q_lower:
            if intent != "comparative_count":
                intent = "COMPARISON_ANALYSIS"

        dedup_group_by = list(dict.fromkeys(group_by))

        # Default count if needed
        if not aggs and not sort:
            alias_name = "external_email_incidents" if "external" in mapped_cols else (
                "blocked_incidents" if "action" in mapped_cols else "total_records"
            )
            aggs.append({"function": "count", "column": "*", "alias": alias_name})
            if dedup_group_by:
                if intent in ("DATA_ANALYSIS", "scalar_count"):
                    intent = "grouped_distribution"
                result_shape = "grouped_rows"
            else:
                intent = "scalar_count"
                result_shape = "scalar_metric"
        elif dedup_group_by:
            if intent in ("DATA_ANALYSIS", "scalar_count"):
                intent = "top_n" if sort else "grouped_distribution"
            if result_shape in (None, "scalar_metric"):
                result_shape = "ranked_rows" if intent == "top_n" else "grouped_rows"

        target_concept = aggs[0]["alias"] if aggs else (dedup_group_by[0] if dedup_group_by else "record_count")
        return SemanticResolution(
            intent=intent,
            target_concept=target_concept,
            result_shape=result_shape or ("two_metrics" if intent == "comparative_count" else ("grouped_rows" if dedup_group_by else "scalar_metric")),
            requested_concepts=requested_concepts or [target_concept],
            record_family=selected_family_name,
            mapped_columns=mapped_cols,
            suggested_aggregates=aggs,
            suggested_filters=filters,
            suggested_sort=sort,
            suggested_group_by=dedup_group_by,
            notes=notes
        )
