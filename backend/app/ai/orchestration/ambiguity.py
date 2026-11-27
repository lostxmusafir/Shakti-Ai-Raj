import re
import uuid
from typing import Any, Dict, List, Optional

from app.models.file import StoredFile


class AmbiguityDetector:
    """
    Pure, deterministic detector for genuine analytical ambiguities that would
    otherwise force the planner to guess. High-confidence queries return None.
    """

    @staticmethod
    def _slug(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")

    @classmethod
    def detect(
        cls,
        question: str,
        files_map: Dict[str, StoredFile],
        resolved_bindings: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        q = (question or "").strip()
        q_lower = q.lower()
        resolved_concepts = {b.get("concept") for b in (resolved_bindings or []) if b.get("concept")}

        # 0. High-impact destructive / write operation confirmation
        if "high_impact_approval" not in resolved_concepts and any(
            kw in q_lower
            for kw in (
                "delete dataset",
                "delete file",
                "remove dataset",
                "modify policy",
                "update policy",
                "delete policy",
                "drop table",
            )
        ):
            return {
                "interrupt_id": f"intr_{uuid.uuid4().hex[:12]}",
                "type": "confirmation",
                "reason": "HIGH_IMPACT_APPROVAL",
                "question": f"Confirm high-impact action: '{q}'?",
                "options": [
                    {"id": "approve", "label": "Approve"},
                    {"id": "cancel", "label": "Cancel"},
                ],
                "context": {"original_question": q, "concept": "high_impact_approval"},
            }

        if not files_map:
            return None

        # Aggregate columns across files (or active bound family)
        first_file = next(iter(files_map.values()))
        profile = first_file.schema_profile or {}
        columns = profile.get("columns", [])
        is_mixed = bool(profile.get("is_mixed", False))
        families = profile.get("record_families", []) or []

        bound_family = next(
            (b.get("binding") for b in (resolved_bindings or []) if b.get("concept") == "record_family"),
            None,
        )

        # Active column subset if mixed & family already bound
        active_col_names: Optional[set] = None
        if is_mixed and bound_family and families:
            for fam in families:
                if fam.get("family") == bound_family or fam.get("family_name") == bound_family:
                    active_col_names = set(fam.get("active_columns", []))
                    break

        scoped_cols = [
            c for c in columns
            if active_col_names is None or c.get("name") in active_col_names
        ]

        # 1. Ambiguous record family in mixed dataset
        if is_mixed and len(families) >= 2 and "record_family" not in resolved_concepts:
            # High-confidence family signals should NOT interrupt
            is_debit_credit_entries = (
                "debit" in q_lower
                and "credit" in q_lower
                and any(t in q_lower for t in ("entry", "entries", "transaction", "transactions", "kitne", "kitni", "alag alag"))
            )
            is_email_security = any(t in q_lower for t in ("email", "emails", "mail", "mails", "gmail", "yahoo", "external"))
            if not is_debit_credit_entries and not is_email_security:
                # Check if question mentions a status/generic term like "blocked records" that matches >1 family
                # or doesn't uniquely match a single family's active columns
                matching_families = []
                for fam in families:
                    fam_cols_lower = {c.lower() for c in fam.get("active_columns", [])}
                    # If question asks about blocked/records/status, check if family has status/action
                    if any(t in q_lower for t in ("blocked", "record", "records")) and (
                        "action" in fam_cols_lower or "status" in fam_cols_lower
                    ):
                        matching_families.append(fam)
                if len(matching_families) >= 2:
                    return {
                        "interrupt_id": f"intr_{uuid.uuid4().hex[:12]}",
                        "type": "choice",
                        "reason": "AMBIGUOUS_RECORD_FAMILY",
                        "question": "Which record type / family do you want to analyze?",
                        "options": [
                            {
                                "id": cls._slug(str(f.get("family_name") or f.get("family"))),
                                "label": str(f.get("family_name") or f.get("family")),
                                "value": str(f.get("family") or f.get("family_name")),
                            }
                            for f in matching_families
                        ],
                        "context": {"original_question": q, "concept": "record_family"},
                    }

        # 2. Ask for a measure when the question names no measure or its metric has no direct column.
        if "metric" not in resolved_concepts:
            numeric_cols = [
                c["name"] for c in scoped_cols
                if c.get("role") in ("measure", "sparse_measure")
                or c.get("inferred_type") in ("integer", "float")
            ]
            amount_cols = [
                c for c in numeric_cols
                if any(kw in c.lower() for kw in ("amount", "amt", "price", "value", "cost", "fare", "fee"))
            ]
            explicit_measure = any(
                col.lower() in q_lower or col.lower().replace("_", " ") in q_lower
                for col in numeric_cols
            )
            has_size_unit = any(
                re.search(rf"\b{unit}\b", q_lower)
                for unit in ("kb", "mb", "gb", "byte", "bytes")
            )
            unit_measure_cols = [
                col for col in numeric_cols
                if any(token in col.lower() for token in ("size", "data", "bytes", "volume", "bandwidth", "transfer"))
                or re.search(r"\b(?:kb|mb|gb|bytes?)\b", col.lower())
            ]
            if has_size_unit and len(unit_measure_cols) == 1:
                explicit_measure = True
            count_request = any(
                term in q_lower
                for term in ("count", "how many", "kitne", "kitni", "records", "rows", "entries", "transactions", "incidents")
            )
            financial_request = any(
                term in q_lower
                for term in ("amount", "revenue", "profit", "sales", "income", "cost", "salary", "kamai", "kharch")
            )
            vague_total = not count_request and not explicit_measure and any(
                term in q_lower for term in ("total", "kitna", "how much", "kya hai")
            )
            unmatched_financial = financial_request and not explicit_measure
            options = amount_cols if "amount" in q_lower and len(amount_cols) > 1 else numeric_cols
            ask_for_metric = bool(options) and (
                (unmatched_financial and not ("amount" in q_lower and len(amount_cols) < 2))
                or (vague_total and len(numeric_cols) > 1)
                or ("amount" in q_lower and len(amount_cols) > 1 and not explicit_measure)
            )
            if ask_for_metric:
                return {
                    "interrupt_id": f"intr_{uuid.uuid4().hex[:12]}",
                    "type": "choice",
                    "reason": "AMBIGUOUS_METRIC",
                    "question": "Which numeric measure should I use?",
                    "options": [
                        {"id": cls._slug(col), "label": col, "value": col}
                        for col in options
                    ],
                    "context": {"original_question": q, "concept": "metric"},
                }

        # 3. Ambiguous date column (e.g. "Last month ka revenue batao" with invoice_date, payment_date, created_date)
        if "date_column" not in resolved_concepts and any(
            kw in q_lower
            for kw in ("last month", "this month", "pichle mahine", "is mahine", "yesterday", "today", "monthly", "date wise", "by month")
        ):
            date_cols = [
                c["name"]
                for c in scoped_cols
                if c.get("role") == "timestamp"
                or c.get("inferred_type") == "datetime"
                or any(d in c["name"].lower() for d in ("date", "time", "created_at", "updated_at"))
            ]
            explicit_date = any(col.lower() in q_lower or col.lower().replace("_", " ") in q_lower for col in date_cols)
            if len(date_cols) >= 2 and not explicit_date:
                return {
                    "interrupt_id": f"intr_{uuid.uuid4().hex[:12]}",
                    "type": "choice",
                    "reason": "AMBIGUOUS_DATE",
                    "question": "Which date column should be used for this time filter?",
                    "options": [
                        {"id": cls._slug(col), "label": col, "value": col}
                        for col in date_cols
                    ],
                    "context": {"original_question": q, "concept": "date_column"},
                }

        # 4. Ambiguous aggregation on a single sparse measure (e.g. "Credit kitna hai?" without entries/count/total/avg)
        if "aggregation" not in resolved_concepts:
            has_explicit_agg = any(
                kw in q_lower
                for kw in (
                    "entry", "entries", "transaction", "transactions", "count", "kitni",
                    "total", "sum", "average", "avg", "mean", "top", "highest", "max", "min",
                    "alag alag", "dono", "both",
                )
            )
            if not has_explicit_agg and any(kw in q_lower for kw in ("kitna", "how much", "kya hai")):
                sparse_cols = [
                    c["name"]
                    for c in scoped_cols
                    if c.get("role") == "sparse_measure"
                    and c["name"].lower() in q_lower
                ]
                if len(sparse_cols) == 1:
                    col_name = sparse_cols[0]
                    return {
                        "interrupt_id": f"intr_{uuid.uuid4().hex[:12]}",
                        "type": "choice",
                        "reason": "AMBIGUOUS_AGGREGATION",
                        "question": f"What do you want to calculate for {col_name}?",
                        "options": [
                            {"id": "count_entries", "label": f"Number of {col_name} entries", "value": "count_entries"},
                            {"id": "sum_amount", "label": f"Total {col_name} amount", "value": "sum"},
                            {"id": "avg_amount", "label": f"Average {col_name} amount", "value": "avg"},
                        ],
                        "context": {"original_question": q, "concept": "aggregation", "column": col_name},
                    }

        # 5. Free-text corporate domain clarification when explicitly unknown
        if "internal_domain" not in resolved_concepts and any(
            kw in q_lower for kw in ("which company domain", "internal domain", "company domain")
        ):
            return {
                "interrupt_id": f"intr_{uuid.uuid4().hex[:12]}",
                "type": "free_text",
                "reason": "AMBIGUOUS_DOMAIN",
                "question": "Which company domain should be considered internal?",
                "options": [],
                "placeholder": "e.g. company.com",
                "context": {"original_question": q, "concept": "internal_domain"},
            }

        return None

    @staticmethod
    def validate_resume_response(payload: Dict[str, Any], user_response: Any) -> Dict[str, Any]:
        """
        Validates the user's resume payload against the active interrupt schema.
        Raises ValueError on invalid options or empty free-text.
        """
        if not payload:
            raise ValueError("No pending interrupt payload.")

        itype = payload.get("type", "choice")
        options = payload.get("options") or []
        concept = (payload.get("context") or {}).get("concept", "clarification")

        if itype in ("choice", "confirmation"):
            selected_raw = user_response.get("selected") if isinstance(user_response, dict) else user_response
            if not isinstance(selected_raw, str) or not selected_raw.strip():
                raise ValueError("Please select one of the provided options.")
            sel_norm = selected_raw.strip().lower()
            matched = next(
                (
                    opt for opt in options
                    if str(opt.get("id", "")).lower() == sel_norm
                    or str(opt.get("label", "")).lower() == sel_norm
                    or str(opt.get("value", "")).lower() == sel_norm
                ),
                None,
            )
            if not matched:
                raise ValueError(f"Invalid option '{selected_raw}'. Allowed: {[o.get('id') for o in options]}")
            return {
                "resolved_by": "user",
                "concept": concept,
                "binding": matched.get("value", matched.get("label", matched.get("id"))),
                "option_id": matched.get("id"),
                "label": matched.get("label"),
                "reason": payload.get("reason"),
                "column": (payload.get("context") or {}).get("column"),
            }

        if itype == "free_text":
            text_raw = user_response.get("text") if isinstance(user_response, dict) else user_response
            if not isinstance(text_raw, str) or not text_raw.strip():
                raise ValueError("Clarification text cannot be empty.")
            cleaned = text_raw.strip()
            if len(cleaned) > 120 or any(ch in cleaned for ch in (";", "--", "/*", "*/")):
                raise ValueError("Invalid characters in clarification response.")
            return {
                "resolved_by": "user",
                "concept": concept,
                "binding": cleaned,
                "label": cleaned,
                "reason": payload.get("reason"),
            }

        raise ValueError(f"Unsupported interrupt type: {itype}")

    @staticmethod
    def apply_bindings_to_question(question: str, bindings: List[Dict[str, Any]]) -> str:
        """Produces an enriched question string incorporating user-resolved bindings."""
        if not bindings:
            return question
        q = question
        for b in bindings:
            concept = b.get("concept")
            val = b.get("binding")
            if not val:
                continue
            if concept == "metric":
                q = f"Total {val} ({q})"
            elif concept == "aggregation":
                col = b.get("column") or ""
                if val == "count_entries":
                    q = f"{col} entries kitni hain?"
                elif val == "sum":
                    q = f"Total {col} amount kitna hai?"
                elif val == "avg":
                    q = f"Average {col} amount kitna hai?"
            elif concept == "date_column":
                q = f"{q} [date column: {val}]"
            elif concept == "record_family":
                q = f"{q} [record family: {val}]"
            elif concept == "internal_domain":
                q = f"{q} [internal domain: {val}]"
        return q
