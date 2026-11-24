"""Generic, schema-driven question understanding and plan construction.

Nothing here knows about a specific business domain. Every column reference is
resolved against the *schema profile* (names, types, cardinality, observed
values); the only hard-coded knowledge is how people phrase analytics questions
in English, Hinglish and Roman Hindi.

Pipeline position:

    profile -> QuestionEngine.analyze -> Interpretation -> GenericPlanner.build_plan
            -> AnalysisPlan -> PlanValidator -> QueryCompiler -> DuckDB

When the question cannot be grounded unambiguously the interpretation carries a
``clarification`` instead of inventing an answer.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.ai.planning.schemas import (
    AggregateOperation,
    AnalysisPlan,
    Condition,
    DatasetRef,
    SortRule,
)

# Aggregates the plan executor can actually run: PlanValidator.SUPPORTED_AGGREGATES
# plus the QueryCompiler implementations. Anything outside this set must be refused
# loudly rather than emitted as an unrunnable AnalysisPlan.
EXECUTABLE_AGGREGATES = {
    "count", "sum", "avg", "min", "max", "median", "count_distinct",
}


class UnsupportedPlanError(ValueError):
    """An interpretation needs a plan feature the executor cannot run yet."""

# ---------------------------------------------------------------------------
# Language lexicon
# ---------------------------------------------------------------------------

PERCENT_WORDS = {"percent", "percentage", "pratishat", "pct", "percenta", "sabse zyada", "kitni", "kitna", "%"}
AVG_WORDS = {"average", "avg", "mean", "ausat", "ausat", "arithmetic_mean"}
DISTINCT_WORDS = {"distinct", "unique", "alag", "different", "alag alag", "alag badal"}
SUM_WORDS = {"total", "sum", "kul", "combined", "jod", "poora", "sab milakar", "jodna"}
COUNT_WORDS = {"count", "kitne", "kitni", "kitna", "record", "records", "rows", "row", "kitne record", "kitne log", "ginti"}
RANK_DESC = {"top", "highest", "most", "max", "maximum", "best", "largest", "biggest",
             "sabse", "zyada", "jyada", "jada", "upar", "peak", "leading", "tops", "sabse zyada", "se zyada", "se upar", "se bada", "sheeshay"}
RANK_ASC = {"bottom", "lowest", "least", "min", "minimum", "smallest", "worst",
            "kam", "chhota", "chhote", "neeche", "low", "kam zyada", "kam se", "kam upar", "se neeche", "kam bada"}
SHARE_WORDS = {"share", "hissa", "hisaa", "contribute", "contribution", "hissa dena", "hissa part", "hisab kitab", "poora hissa", "poora hissa hisab"}
TREND_WORDS = {"trend", "monthly", "month", "mahina", "mahine", "yearly", "quarterly",
               "weekly", "daily", "growth"}
AMBIGUOUS_TERMS = {"best", "worst", "reliability", "reliable", "performance", "performing", "good", "bad", "strong", "weak", "healthy", "important", "valuable", "efficient", "efficiency", "quality", "successful", "risky", "risk"}
NEGATION_WORDS = {"not", "except", "excluding", "without", "nahi", "nhi", "sivay", "chhod", "na", "na karo", "mat karo", "nahi chalega", "door", "khaas nahi", "inkaar"}

STOPWORDS = {
    "the", "a", "an", "of", "for", "in", "on", "at", "to", "from", "with", "by",
    "and", "or", "is", "are", "was", "were", "be", "been", "being", "this", "that",
    "these", "those", "it", "its", "as", "each", "every", "me", "mein", "ka", "ki",
    "ke", "ko", "se", "hai", "hain", "he", "ho", "kya", "kaun", "kaunsi", "kaunsa",
    "kis", "kisko", "batao", "bata", "dikhao", "dikha", "do", "de", "please", "show",
    "give", "list", "tell", "which", "what", "who", "where", "when", "there", "their",
    "has", "have", "had", "highest", "lowest", "most", "least", "all", "total", "top",
    "bottom", "record", "records", "row", "rows", "value", "values", "dataset", "sheet",
    "data", "column", "table", "file", "number", "count", "percentage", "percent",
    "average", "avg", "mean", "sum", "distinct", "unique", "equal", "equals", "greater",
    "less", "than", "more", "fewer", "above", "below", "overall", "per", "wise", "hisab",
    "according", "sabse", "zyada", "jyada", "kam", "sab", "only", "sirf", "ab", "then",
    "now", "also", "vs", "versus", "compare", "comparison", "difference", "between",
    "across", "kitne", "kitna", "kitni", "kul", "ausat", "pratishat", "share", "hissa",
    "contribute", "trend", "monthly", "month", "year", "quarter", "week", "day", "using",
    "among", "where", "when", "seems", "looks", "like", "kaun", "kaunsi", "kaunsa",
}

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "ek": 1, "do": 2, "teen": 3, "char": 4,
    "paanch": 5, "panch": 5, "chhah": 6, "che": 6, "saat": 7, "aath": 8, "nau": 9,
    "das": 10,
}

IDENTIFIER_HINTS = {"id", "code", "no", "num", "number", "pnr", "txn", "ref", "uuid",
                    "key", "phone", "zip", "sku"}


def normalize_text(text: str) -> str:
    text = str(text).lower().replace("%", " percent ")
    text = re.sub(r"[^a-z0-9@.\- ><=!]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> List[str]:
    return [token for token in normalize_text(text).split(" ") if token]


def split_identifier(name: str) -> List[str]:
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(name))
    spaced = re.sub(r"[_\-./]+", " ", spaced)
    return [token for token in normalize_text(spaced).split(" ") if token]


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _looks_like_date(values: Sequence[str]) -> bool:
    return bool(values) and all(re.match(r"^\d{4}-\d{2}-\d{2}", str(v)) for v in values[:3])


# ---------------------------------------------------------------------------
# Schema view
# ---------------------------------------------------------------------------

@dataclass
class Column:
    name: str
    dtype: str
    unique: int
    nulls: int
    top_values: Dict[str, int] = field(default_factory=dict)
    samples: List[str] = field(default_factory=list)
    role: str = "dimension"

    @property
    def tokens(self) -> List[str]:
        return split_identifier(self.name)

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").strip()


class SchemaView:
    def __init__(self, profile: Dict[str, Any]):
        self.row_count = int(profile.get("row_count") or 0)
        self.columns: List[Column] = []
        for raw in profile.get("columns", []):
            name = str(raw.get("name") or "")
            if not name:
                continue
            column = Column(
                name=name,
                dtype=str(raw.get("inferred_type") or "string"),
                unique=int(raw.get("unique_count") or 0),
                nulls=int(raw.get("null_count") or 0),
                top_values={str(k): int(v) for k, v in (raw.get("top_values") or {}).items()},
                samples=[str(v) for v in (raw.get("sample_values") or [])],
            )
            column.role = self._role(column)
            self.columns.append(column)

    def _role(self, column: Column) -> str:
        tokens = set(column.tokens)
        name = normalize_text(column.name)
        if tokens & IDENTIFIER_HINTS or name.endswith(" id") or name.startswith("id "):
            return "identifier"
        if column.dtype in {"datetime", "date"} or _looks_like_date(column.samples):
            return "time"
        if column.dtype == "boolean":
            return "flag"
        if column.dtype in {"integer", "float"}:
            if column.unique <= 2:
                return "flag"
            return "measure"
        if 1 < column.unique <= 60:
            return "dimension"
        if column.unique <= 1:
            return "constant"
        return "text"

    # -- accessors ------------------------------------------------------
    @property
    def dimensions(self) -> List[Column]:
        return [c for c in self.columns if c.role in {"dimension", "flag"}]

    @property
    def measures(self) -> List[Column]:
        return [c for c in self.columns if c.role == "measure"]

    @property
    def times(self) -> List[Column]:
        return [c for c in self.columns if c.role == "time"]

    @property
    def identifiers(self) -> List[Column]:
        return [c for c in self.columns if c.role == "identifier"]

    def all_names(self) -> List[str]:
        return [c.name for c in self.columns]

    def find_column(self, phrase: str, roles: Optional[Iterable[str]] = None,
                    threshold: float = 0.58) -> Tuple[Optional[Column], float]:
        """Resolve a free-text phrase to the best matching column."""
        wanted = set(roles) if roles else None
        tokens = [t for t in tokenize(phrase) if t not in STOPWORDS and len(t) >= 2]
        if not tokens:
            return None, 0.0
        best: Tuple[Optional[Column], float] = (None, 0.0)
        for column in self.columns:
            if wanted is not None and column.role not in wanted:
                continue
            col_tokens = [t for t in column.tokens if len(t) >= 2]
            if not col_tokens:
                continue
            exact = len(set(col_tokens) & set(tokens)) / len(col_tokens)
            fuzzy = max(
                (similarity(token, ref) for token in tokens for ref in col_tokens),
                default=0.0,
            )
            if normalize_text(column.name) in normalize_text(phrase):
                score = 1.0
            else:
                score = max(exact, fuzzy * 0.92)
            if score > best[1]:
                best = (column, score)
        return best if best[1] >= threshold else (None, best[1])

    def find_value(self, phrase: str, column: Optional[Column] = None
                   ) -> Tuple[Optional[Column], Optional[str], float]:
        """Find an observed category value inside a phrase."""
        tokens = set(tokenize(phrase))
        candidates = [column] if column is not None else self.dimensions
        best: Tuple[Optional[Column], Optional[str], float] = (None, None, 0.0)
        for col in candidates:
            if col is None:
                continue
            col_hit = bool({t for t in col.tokens if len(t) >= 3} & tokens)
            for value in col.top_values:
                value_tokens = [t for t in tokenize(value) if len(t) >= 2]
                if not value_tokens:
                    continue
                hits = sum(1 for t in value_tokens if t in tokens)
                if hits == len(value_tokens):
                    score = 1.0 + 0.1 * len(value_tokens)
                else:
                    reserved = STOPWORDS | RANK_ASC | RANK_DESC | COUNT_WORDS | SUM_WORDS | AVG_WORDS | DISTINCT_WORDS | TREND_WORDS
                    eligible = [other for other in tokens if len(other) >= 3 and other not in reserved]
                    fuzzy = max(
                        (max((similarity(t, other) for other in eligible), default=0.0)
                         for t in value_tokens),
                        default=0.0,
                    )
                    score = fuzzy if (fuzzy >= 0.85 if col_hit else fuzzy >= 0.92) else 0.0
                # Values that are ordinary words ("no", "yes") need the column
                # itself to be present, otherwise every question would filter.
                if len(value_tokens) == 1 and value_tokens[0] in STOPWORDS and not col_hit:
                    continue
                if len(value_tokens) == 1 and len(value_tokens[0]) <= 3 and not col_hit:
                    continue
                if score > best[2]:
                    best = (col, value, score)
        return best


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------

@dataclass
class Interpretation:
    intent: str = "scalar_metric"
    group_by: List[str] = field(default_factory=list)
    filters: List[Condition] = field(default_factory=list)
    aggregations: List[Tuple[str, Optional[str], Optional[Condition], str]] = field(default_factory=list)
    derived: List[Tuple[str, str, Optional[str], float, str]] = field(default_factory=list)
    having: List[Tuple[str, str, Optional[float], Optional[str]]] = field(default_factory=list)
    rank_partition: List[str] = field(default_factory=list)
    rank_order: Optional[str] = None
    date_column: Optional[str] = None
    granularity: str = "month"
    sort: List[Tuple[str, bool]] = field(default_factory=list)
    limit: Optional[int] = None
    confidence: float = 1.0
    assumptions: List[str] = field(default_factory=list)
    clarification: Optional[str] = None
    notes: List[str] = field(default_factory=list)


class QuestionEngine:
    """Turns a question + schema profile into an Interpretation."""

    def __init__(self, profile: Dict[str, Any], file_ids: Optional[List[str]] = None):
        self.profile = profile
        self.schema = SchemaView(profile)
        self.file_ids = file_ids or []
        self.text = ""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def analyze(self, question: str) -> Interpretation:
        self.text = normalize_text(question)
        tokens = tokenize(question)
        repaired, corrections = self._repair_tokens(tokens)
        self.tokens = repaired
        token_set = set(repaired)

        interp = Interpretation()
        if corrections:
            interp.assumptions.append(f"corrected {corrections} noisy token(s)")
            interp.confidence -= 0.04 * min(corrections, 3)

        for rule in (
            self._rule_rank_within_group,
            self._rule_per_entity_ratio,
            self._rule_time_series,
            self._rule_share,
            self._rule_rate_by_group,
            self._rule_overall_percentage,
            self._rule_conditional_average,
            self._rule_conditional_count,
            self._rule_top_by_measure,
            self._rule_group_sum,
            self._rule_group_count,
            self._rule_top_bottom_count,
            self._rule_distinct,
            self._rule_scalar_average,
            self._rule_scalar_sum,
            self._rule_scalar_count,
        ):
            result = rule(interp, self.text, token_set)
            if result is not None:
                if result.clarification:
                    result.confidence = min(result.confidence, 0.4)
                elif not result.filters and self._has_unresolved_filter_hint(self.text):
                    result.confidence = min(result.confidence, 0.5)
                result.confidence = round(max(0.0, min(1.0, result.confidence)), 2)
                return result

        # Ambiguity check: terms like 'best', 'worst', 'good', 'quality' without an explicit measure
        if token_set & AMBIGUOUS_TERMS:
            measure, mscore = self.schema.find_column(self.text, roles=("measure",))
            if measure is None or mscore < 0.6:
                interp.clarification = (
                    "That question can be read more than one way. Which measure should decide it "
                    "- record count, a monetary amount, or an explicit rate?"
                )
                interp.confidence = 0.3
                return interp

        # Nothing matched the phrasing templates: try a looser structural read
        # (measure + dimension + aggregation keyword) before giving up.
        loose = self._rule_loose(interp, self.text, token_set)
        if loose is not None:
            loose.confidence = round(max(0.0, min(1.0, loose.confidence)), 2)
            return loose

        interp.notes.append("unmapped")
        interp.confidence = 0.3
        return interp

    # ------------------------------------------------------------------
    # Token repair
    # ------------------------------------------------------------------
    def _repair_tokens(self, tokens: List[str]) -> Tuple[List[str], int]:
        vocab: set[str] = set()
        for column in self.schema.columns:
            vocab.update(t for t in column.tokens if len(t) >= 3)
            for value in column.top_values:
                vocab.update(t for t in tokenize(value) if len(t) >= 3)
        vocab_list = sorted(vocab)
        repaired: List[str] = []
        corrections = 0
        reserved = (
            STOPWORDS | RANK_ASC | RANK_DESC | PERCENT_WORDS | COUNT_WORDS |
            SUM_WORDS | AVG_WORDS | DISTINCT_WORDS | TREND_WORDS | AMBIGUOUS_TERMS | NEGATION_WORDS
        )
        for token in tokens:
            if len(token) < 4 or token in vocab or token in reserved:
                repaired.append(token)
                continue
            best, score = None, 0.0
            for candidate in vocab_list:
                ratio = similarity(token, candidate)
                if ratio > score:
                    best, score = candidate, ratio
            limit = 0.86 if len(token) <= 5 else 0.8
            if best and score >= limit:
                repaired.append(best)
                corrections += 1
            else:
                repaired.append(token)
        return repaired, corrections

    # ------------------------------------------------------------------
    # Shared parsing helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean(fragment: str) -> str:
        fragment = re.sub(r"\b(equal to|equals|is|are|equals to)\b.*$", "", fragment)
        return fragment.strip(" ?.,")

    def _resolve_dimension(self, phrase: str, interp: Optional[Interpretation] = None) -> Optional[Column]:
        column, score = self.schema.find_column(phrase, roles=("dimension", "flag", "time"))
        if column is not None and score >= 0.58:
            if interp is not None and score < 0.85:
                interp.confidence -= round(0.2 * (1.0 - score), 2)
            return column
        return None

    def _resolve_measure(self, phrase: str, interp: Optional[Interpretation] = None) -> Optional[Column]:
        column, score = self.schema.find_column(phrase, roles=("measure",))
        if column is not None and score >= 0.5:
            if interp is not None and score < 0.85:
                interp.confidence -= round(0.2 * (1.0 - score), 2)
            return column
        if len(self.schema.measures) == 1:
            if interp is not None:
                interp.assumptions.append(f"defaulted to only available measure '{self.schema.measures[0].name}'")
                interp.confidence -= 0.12
            return self.schema.measures[0]
        return None

    def _filter_from(self, phrase: str) -> Tuple[Optional[Condition], Optional[Column]]:
        """Extract a Condition (<column> <operator> <value>) from free text.

        Supports:
        - Numeric comparisons: >, >=, <, <=, =, != and English/Hinglish comparison phrases
        - Explicit categorical comparisons: col = 'value', col != 'value'
        - Observed categorical values: finds known category in top_values
        """
        # 1. Numeric / symbol comparisons: e.g. "emi > 5000", "emi >= 5000", "emi <= 500"
        op_map = {
            ">=": "greater_than_or_equal",
            "<=": "less_than_or_equal",
            "!=": "not_equals",
            "<>": "not_equals",
            "==": "equals",
            "=": "equals",
            ">": "greater_than",
            "<": "less_than",
        }

        sym_match = re.search(
            r"(?P<col>[a-zA-Z_][a-zA-Z0-9_ ]*?)\s*(?P<op>>=|<=|!=|<>|==|=|>|<)\s*(?P<val>-?[0-9]+(?:\.[0-9]+)?)",
            phrase,
        )
        if sym_match:
            col_str = sym_match.group("col").strip()
            op_str = sym_match.group("op")
            val_str = sym_match.group("val")
            col, score = self.schema.find_column(col_str, roles=("measure", "dimension", "time", "flag", "identifier"))
            if col is not None and score >= 0.5:
                val = float(val_str) if "." in val_str else int(val_str)
                return Condition(column=col.name, operator=op_map[op_str], value=val), col

        # 2. English word comparisons:
        word_patterns = [
            (r"(?P<col>[a-zA-Z_][a-zA-Z0-9_ ]*?)\s+(?:is\s+)?(?:greater than or equal to|at least|no less than)\s+(?P<val>-?[0-9]+(?:\.[0-9]+)?)", "greater_than_or_equal"),
            (r"(?P<col>[a-zA-Z_][a-zA-Z0-9_ ]*?)\s+(?:is\s+)?(?:less than or equal to|at most|no more than)\s+(?P<val>-?[0-9]+(?:\.[0-9]+)?)", "less_than_or_equal"),
            (r"(?P<col>[a-zA-Z_][a-zA-Z0-9_ ]*?)\s+(?:is\s+)?(?:greater than|more than|above|exceeding|higher than|over)\s+(?P<val>-?[0-9]+(?:\.[0-9]+)?)", "greater_than"),
            (r"(?P<col>[a-zA-Z_][a-zA-Z0-9_ ]*?)\s+(?:is\s+)?(?:less than|fewer than|below|under|lower than)\s+(?P<val>-?[0-9]+(?:\.[0-9]+)?)", "less_than"),
            (r"(?P<col>[a-zA-Z_][a-zA-Z0-9_ ]*?)\s+(?:is\s+)?(?:equal to|equals to|equals)\s+(?P<val>-?[0-9]+(?:\.[0-9]+)?)", "equals"),
            (r"(?P<col>[a-zA-Z_][a-zA-Z0-9_ ]*?)\s+(?:is\s+)?(?:not equal to|not equals)\s+(?P<val>-?[0-9]+(?:\.[0-9]+)?)", "not_equals"),
        ]
        for pat, op_name in word_patterns:
            m = re.search(pat, phrase, re.IGNORECASE)
            if m:
                col_str = m.group("col").strip()
                col, score = self.schema.find_column(col_str, roles=("measure", "dimension", "time", "flag", "identifier"))
                if col is not None and score >= 0.5:
                    val_str = m.group("val")
                    val = float(val_str) if "." in val_str else int(val_str)
                    return Condition(column=col.name, operator=op_name, value=val), col

        # 3. Hinglish / Hindi comparisons:
        hinglish_patterns = [
            (r"(?P<col>[a-zA-Z_][a-zA-Z0-9_ ]*?)\s+(?P<val>-?[0-9]+(?:\.[0-9]+)?)\s*(?:se\s+)?(?:zyada|jyada|upar|bada)", "greater_than"),
            (r"(?P<col>[a-zA-Z_][a-zA-Z0-9_ ]*?)\s+(?P<val>-?[0-9]+(?:\.[0-9]+)?)\s*(?:se\s+)?(?:kam|neeche|chhota)", "less_than"),
            (r"(?P<val>-?[0-9]+(?:\.[0-9]+)?)\s*(?:se\s+)?(?:zyada|jyada|upar|bada)\s+(?P<col>[a-zA-Z_][a-zA-Z0-9_ ]*)", "greater_than"),
            (r"(?P<val>-?[0-9]+(?:\.[0-9]+)?)\s*(?:se\s+)?(?:kam|neeche|chhota)\s+(?P<col>[a-zA-Z_][a-zA-Z0-9_ ]*)", "less_than"),
            (r"(?P<col>[a-zA-Z_][a-zA-Z0-9_ ]*?)\s+(?P<val>-?[0-9]+(?:\.[0-9]+)?)\s*(?:ke\s+)?barabar", "equals"),
        ]
        for pat, op_name in hinglish_patterns:
            m = re.search(pat, phrase, re.IGNORECASE)
            if m:
                col_str = m.group("col").strip()
                col, score = self.schema.find_column(col_str, roles=("measure", "dimension", "time", "flag", "identifier"))
                if col is not None and score >= 0.5:
                    val_str = m.group("val")
                    val = float(val_str) if "." in val_str else int(val_str)
                    return Condition(column=col.name, operator=op_name, value=val), col

        # 4. Explicit categorical comparison: e.g. "cancellation = yes" or "cancellation == yes"
        cat_eq = re.search(r"(?P<col>[a-zA-Z_][a-zA-Z0-9_ ]*?)\s*(?:==|=|!=|<>|\b(?:is|equals|equal to|not equal to)\b)\s*['\"]?(?P<val>[a-zA-Z0-9_]+)['\"]?", phrase)
        if cat_eq:
            col_str = cat_eq.group("col").strip()
            val_str = cat_eq.group("val").strip()
            if len(val_str) >= 2 and val_str.lower() not in STOPWORDS:
                col, score = self.schema.find_column(col_str, roles=("dimension", "flag", "text", "identifier"))
                if col is not None and score >= 0.5:
                    matched_val = val_str
                    for tv in col.top_values:
                        if tv.lower() == val_str.lower():
                            matched_val = tv
                            break
                    return Condition(column=col.name, operator="equals", value=matched_val), col

        # 5. Observed categorical value fallback:
        negated = bool(set(tokenize(phrase)) & NEGATION_WORDS)
        column, value, score = self.schema.find_value(phrase)
        if column is not None and value is not None and score >= 0.8:
            return Condition(
                column=column.name,
                operator="not_equals" if negated else "equals",
                value=value,
            ), column

        return None, None

    def _has_unresolved_filter_hint(self, text: str) -> bool:
        return any(re.search(pat, text, re.IGNORECASE) for pat in [
            r"\b(where|jahan|whose)\b",
            r"\b(have|has|having|with)\b\s+(?:an?\s+)?\w+\s*(?:>|<|=|se|at least|greater|less)",
            r"[><=]",
            r"\bse\s+(?:zyada|kam|upar|neeche|bada|chhota)\b",
        ])

    def _as_condition(self, column: Column, value: str) -> Condition:
        return Condition(column=column.name, operator="equals", value=value)

    @staticmethod
    def _strip_question(fragment: str) -> str:
        return re.sub(r"^(?:the|a|an)\s+", "", fragment.strip(" ?.,")).strip()

    # ------------------------------------------------------------------
    # Rules (ordered, first match wins)
    # ------------------------------------------------------------------
    def _rule_rank_within_group(self, interp, text, tokens) -> Optional[Interpretation]:
        # Patterns carry their own group maps; two of the three define no direction group.
        patterns = [
            (r"for each (.+?),? which (.+?) has the (highest|lowest|most|least) number of records",
             {"partition": 1, "target": 2, "order": 3}),
            (r"har (.+?) ke liye kaun(?:sa|si) (.+?) sabse zyada records wala hai",
             {"partition": 1, "target": 2, "order": None}),
            (r"for every (.+?),? which (.+?) (?:has|records) the (?:highest|most)",
             {"partition": 1, "target": 2, "order": None}),
        ]
        for pattern, groups in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            partition = self._resolve_dimension(match.group(groups["partition"]))
            target = self._resolve_dimension(match.group(groups["target"]))
            if partition is None or target is None:
                continue
            order = match.group(groups["order"]) if groups["order"] else ""
            ascending = order in {"lowest", "least"}
            interp.intent = "ranked_group_metric"
            interp.group_by = [partition.name, target.name]
            interp.aggregations = [("count", None, None, "record_count")]
            interp.rank_partition = [partition.name]
            interp.rank_order = "record_count"
            interp.sort = [(partition.name, True)]
            interp.limit = 100
            if ascending:
                interp.notes.append("rank_ascending")
            return interp
        return None

    def _rule_per_entity_ratio(self, interp, text, tokens) -> Optional[Interpretation]:
        # English: "which city has the worst average EMI burden per loan?"
        # Hinglish: "Loan wale customers me kaunsi city ka average EMI burden sabse kharab hai?"
        # Hindi: "Loan status ke hisaab se kis city ka average EMI sabse zyada?"
        # Every pattern carries its own group map; the previous version read
        # group(4) and group(5) from three-group patterns.
        patterns = [
            (r"which (.+?) has the (highest|lowest|most|least) (.+?) per (.+?)$",
             {"group": 1, "order": 2, "measure": 3, "entity": 4}),
            (r"kis (.+?) ka (.+?) per (.+?) sabse (zyada|kam)",
             {"group": 1, "measure": 2, "entity": 3, "order": 4}),
            (r"(.+?) ka (.+?) per (.+?) sabse (zyada|kam)",
             {"group": 1, "measure": 2, "entity": 3, "order": 4}),
        ]
        for pattern, groups in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            group = self._resolve_dimension(match.group(groups["group"]) or "")
            measure = self._resolve_measure(match.group(groups["measure"]) or "")
            entity = self._resolve_dimension(match.group(groups["entity"]) or "")
            if group is None or measure is None or entity is None:
                continue
            ascending = (match.group(groups["order"]) or "") in {"lowest", "least", "kam"}
            interp.intent = "ratio"
            interp.group_by = [group.name]
            interp.aggregations = [
                ("sum", measure.name, None, "numerator"),
                ("count_distinct", entity.name, None, "denominator"),
            ]
            interp.derived = [("per_entity_metric", "numerator", "denominator", 1.0, "group")]
            # Sort direction: "sabse zyada" = desc, "sabse kam" = asc
            interp.sort = [("per_entity_metric", ascending)]
            interp.limit = 1
            interp.assumptions.append(
                f"per {entity.name} = sum({measure.name}) / distinct {entity.name}"
            )
            return interp
        return None

    def _rule_time_series(self, interp, text, tokens) -> Optional[Interpretation]:
        if not (tokens & TREND_WORDS):
            return None
        date_col = None
        match = (re.search(r"using (.+?)$", text)
                 or re.search(r"by (.+?)$", text)
                 or re.search(r"(.+?) ke hisab se", text))
        if match:
            date_col, score = self.schema.find_column(match.group(1), roles=("time", "dimension"))
            if score < 0.55:
                date_col = None

        if date_col is None:
            candidates = self.schema.times
            if candidates:
                date_col = candidates[0]
            else:
                for c in self.schema.columns:
                    if c.role == "time" or any(k in c.name.lower() for k in ("date", "time", "day", "month", "year", "created", "disbursed")):
                        date_col = c
                        break

        granularity = "month"
        if "yearly" in tokens or "year" in tokens or "saal" in tokens:
            granularity = "year"
        elif "weekly" in tokens or "week" in tokens or "hafte" in tokens or "hafta" in tokens:
            granularity = "week"
        elif "daily" in tokens or "day" in tokens or "din" in tokens or "roz" in tokens:
            granularity = "day"
        elif "quarterly" in tokens or "quarter" in tokens:
            granularity = "quarter"

        if date_col is None:
            interp.intent = "time_series"
            interp.granularity = granularity
            interp.clarification = "No date or timestamp column found in dataset for trend analysis."
            interp.confidence = 0.3
            return interp

        measure = None
        measure_match = (
            re.search(r"(?:monthly|yearly|weekly|daily|quarterly)?\s*(?:total|sum|avg|average)?\s*(.+?)\s+trend", text)
            or re.search(r"trend of (?:monthly|yearly|weekly|daily|quarterly)?\s*(?:total|sum|avg|average)?\s*(.+?)$", text)
            or re.search(r"trend\s+(?:in|of|for)\s+(.+?)$", text)
        )
        if measure_match:
            measure = self._resolve_measure(measure_match.group(1), interp=interp)
        if measure is None:
            measure, mscore = self.schema.find_column(text, roles=("measure",))
            if mscore < 0.5:
                measure = None

        fn = "avg" if (tokens & AVG_WORDS) else "sum"
        interp.intent = "time_series"
        interp.group_by = [date_col.name]
        interp.date_column = date_col.name
        interp.granularity = granularity
        interp.aggregations = [(fn, measure.name, None, f"{fn}_metric")] if measure \
            else [("count", None, None, "metric")]
        interp.sort = [(date_col.name, True)]
        interp.limit = 60
        return interp

    def _rule_share(self, interp, text, tokens) -> Optional[Interpretation]:
        if not (tokens & SHARE_WORDS):
            return None
        match = (re.search(r"share of total (.+?) does each (.+?) contribute", text)
                 or re.search(r"har (.+?) ka total (.+?) me kitna share hai", text))
        if not match:
            return None
        if text.find("share of total") >= 0:
            measure = self._resolve_measure(match.group(1))
            group = self._resolve_dimension(match.group(2))
        else:
            group = self._resolve_dimension(match.group(1))
            measure = self._resolve_measure(match.group(2))
        if group is None:
            return None
        if measure is None and len(self.schema.measures) == 1:
            measure = self.schema.measures[0]
        interp.intent = "share_by_group"
        interp.group_by = [group.name]
        if measure is None:
            interp.aggregations = [("count", None, None, "part")]
            interp.derived = [("share", "part", "part", 100.0, "overall")]
        else:
            interp.aggregations = [("sum", measure.name, None, "part")]
            interp.derived = [("share", "part", "part", 100.0, "overall")]
        interp.sort = [("share", False)]
        interp.limit = 10
        interp.assumptions.append("share = group total / overall total * 100")
        return interp

    def _rule_rate_by_group(self, interp, text, tokens) -> Optional[Interpretation]:
        match = (re.search(r"which (.+?) has the (highest|lowest|most|least) percentage of (.+?)$", text)
                 or re.search(r"kis (.+?) ka (.+?) percentage sabse zyada hai", text))
        if not match:
            return None
        if "percentage of" in text:
            group = self._resolve_dimension(match.group(1))
            phrase = match.group(3)
        else:
            group = self._resolve_dimension(match.group(1))
            phrase = match.group(2)
        if group is None:
            return None
        condition, _ = self._filter_from(phrase)
        if condition is None:
            return None
        interp.intent = "percentage_by_group"
        interp.group_by = [group.name]
        interp.aggregations = [
            ("count", None, None, "total"),
            ("count", None, condition, "numerator"),
        ]
        interp.derived = [("percentage", "numerator", "total", 100.0, "group")]
        interp.sort = [("percentage", "lowest" in text or "least" in text)]
        interp.limit = 1
        interp.assumptions.append(
            f"rate = rows where {condition.column} = {condition.value} / rows in group"
        )
        return interp

    def _rule_overall_percentage(self, interp, text, tokens) -> Optional[Interpretation]:
        if not (tokens & PERCENT_WORDS):
            return None
        patterns = [
            r"percentage of records (?:have|where|with) (.+?)$",
            r"percent records me (.+?) h(?:e|ai|ain)$",
            r"pratishat records? me (.+?) h(?:e|ai|ain)$",
            r"percentage of records where (.+?)$",
            r"percentage of (.+?)$",
            r"(.+?) ka (.+?) percent",
            r"(.+?) ki (.+?) pratishat",
        ]
        condition = None
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                phrase = f"{m.group(1)} {m.group(2)}" if m.lastindex and m.lastindex >= 2 else m.group(1)
                condition, _ = self._filter_from(phrase)
                if condition is not None:
                    break
        if condition is None:
            condition, _ = self._filter_from(text)
        if condition is None:
            return None
        interp.intent = "percentage"
        interp.filters = [condition]
        interp.aggregations = [
            ("count", None, None, "total"),
            ("count", None, condition, "numerator"),
        ]
        interp.derived = [("percentage", "numerator", "total", 100.0, "group")]
        interp.limit = 1
        interp.assumptions.append(
            f"percentage = rows where {condition.column} = {condition.value} / all rows"
        )
        return interp

    def _rule_conditional_average(self, interp, text, tokens) -> Optional[Interpretation]:
        match = re.search(r"among records where (.+?),? what is the (average|total|sum) (.+?) by (.+?)$", text)
        if not match:
            return None
        condition, _ = self._filter_from(match.group(1))
        function = "avg" if match.group(2) == "average" else "sum"
        measure = self._resolve_measure(match.group(3))
        group = self._resolve_dimension(match.group(4))
        if condition is None or measure is None or group is None:
            return None
        interp.intent = "multi_condition"
        interp.filters = [condition]
        interp.group_by = [group.name]
        interp.aggregations = [(function, measure.name, None, f"{function}_{measure.name}")]
        interp.sort = [(f"{function}_{measure.name}", False)]
        interp.limit = 10
        return interp

    def _rule_conditional_count(self, interp, text, tokens) -> Optional[Interpretation]:
        # English: "how many records have EMI > 5000?"
        # Hinglish: "kitne records hain jahan EMI > 5000?"
        # Hindi: "kitne records hain jahan EMI > 5000?"
        patterns = [
            r"how many records (?:have|with|where) (.+?)$",
            r"how many rows (?:have|with|where) (.+?)$",
            r"how many (.+?) records have (.+?)$",
            r"kitne records (?:hain jahan|me|hai jahan) (.+?)$",
            r"jahan (.+?) kitne records",
            r"(.+?) kitne records hain$",
            r"(.+?) kitne log (?:hain|ho)?\s*(.+?)$",
            r"(.+?) se kitne records",
            r"kis (.+?) par kitne records hain",
        ]
        condition = None
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                phrase = f"{m.group(1)} {m.group(2)}" if m.lastindex and m.lastindex >= 2 else m.group(1)
                condition, _ = self._filter_from(phrase)
                if condition is not None:
                    break
        if condition is None:
            condition, _ = self._filter_from(text)
        if condition is None:
            return None
        interp.intent = "conditional_count"
        interp.filters = [condition]
        interp.aggregations = [("count", None, None, "n")]
        interp.limit = 1
        return interp

    def _rule_top_by_measure(self, interp, text, tokens) -> Optional[Interpretation]:
        match = (re.search(r"top (\d+) (.+?) by (?:total|sum) (.+?)$", text)
                 or re.search(r"total (.+?) me top (\d+) (.+?)$", text)
                 or re.search(r"top (\d+) (.+?) by (.+?)$", text))
        if not match:
            return None
        if text.startswith("total ") and " me top " in text:
            measure = self._resolve_measure(match.group(1))
            limit = int(match.group(2))
            group = self._resolve_dimension(match.group(3))
        else:
            limit = int(match.group(1))
            group = self._resolve_dimension(match.group(2))
            measure = self._resolve_measure(match.group(3))
        if group is None or measure is None:
            return None
        interp.intent = "top_n"
        interp.group_by = [group.name]
        alias = f"sum_{measure.name}"
        interp.aggregations = [("sum", measure.name, None, alias)]
        interp.sort = [(alias, False)]
        interp.limit = limit
        return interp

    def _rule_group_sum(self, interp, text, tokens) -> Optional[Interpretation]:
        match = (re.search(r"(?:show|show me|give|list|what is the)(?: me)? (?:the )?(?:total|sum|average|avg) (.+?) by (.+?)$", text)
                 or re.search(r"(.+?) wise (?:total|sum|average|avg) (.+?)(?: dikhao)?$", text)
                 or re.search(r"(?:total|sum|average|avg) (.+?) by (.+?)$", text))
        if not match:
            return None
        fn = "avg" if ("average" in text or "avg" in text or "ausat" in text) else "sum"
        if "wise " in text:
            group = self._resolve_dimension(match.group(1))
            measure = self._resolve_measure(match.group(2))
        else:
            measure = self._resolve_measure(match.group(1))
            group = self._resolve_dimension(match.group(2))
        if group is None or measure is None:
            return None
        interp.intent = "grouped_metric" if fn == "avg" else "group_sum"
        interp.group_by = [group.name]
        alias = f"{fn}_{measure.name}"
        interp.aggregations = [(fn, measure.name, None, alias)]
        interp.sort = [(alias, False)]
        interp.limit = 10
        return interp

    def _rule_group_count(self, interp, text, tokens) -> Optional[Interpretation]:
        match = (re.search(r"how many records are there per (.+?)$", text)
                 or re.search(r"(.+?) wise (?:record )?count", text)
                 or re.search(r"(.+?) wise count dikhao", text))
        if not match:
            return None
        group = self._resolve_dimension(match.group(1))
        if group is None:
            return None
        interp.intent = "grouped_count"
        interp.group_by = [group.name]
        interp.aggregations = [("count", None, None, "metric")]
        interp.sort = [("metric", False)]
        interp.limit = 50
        return interp

    def _rule_top_bottom_count(self, interp, text, tokens) -> Optional[Interpretation]:
        # English: "which airline has the highest number of cancellations?"
        # Hinglish: "sabse zyada cancellation kis airline me ho raha hai?"
        # Hindi: "sabse zyada radd k gayi udan kis airline me?"
        # Every pattern carries its own group map. Indexing groups positionally
        # across patterns of different arity raised IndexError on the Hinglish
        # phrasing, whose pattern defines two groups, not three.
        patterns = [
            (r"which (.+?) has the (highest|lowest|most|least) number of records",
             {"group": 1, "order": 2}),
            (r"sabse (zyada|kam|jyada) records kis (.+?) (?:ke|me) hain",
             {"order": 1, "group": 2}),
            (r"kis (.+?) me records? sabse (zyada|jyada|kam) h(?:e|ai|ain)",
             {"group": 1, "order": 2}),
            (r"(.+?) with the (most|least) (?:number of )?records",
             {"group": 1, "order": 2}),
        ]
        for pattern, groups in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            order = match.group(groups["order"]) or ""
            group = self._resolve_dimension(match.group(groups["group"]) or "")
            if group is None:
                continue
            ascending = order in {"lowest", "least", "kam"}
            interp.intent = "top_n" if not ascending else "bottom_n"
            interp.group_by = [group.name]
            interp.aggregations = [("count", None, None, "metric")]
            interp.sort = [("metric", ascending)]
            interp.limit = 1
            return interp
        return None

    def _rule_distinct(self, interp, text, tokens) -> Optional[Interpretation]:
        if not (tokens & DISTINCT_WORDS):
            return None
        match = re.search(r"(?:distinct|unique) (.+?) values", text)
        target = self._resolve_dimension(match.group(1)) if match else None
        if target is None:
            remainder = " ".join(t for t in self.tokens if t not in DISTINCT_WORDS)
            target = self._resolve_dimension(remainder)
        if target is None:
            if self.schema.identifiers:
                target = self.schema.identifiers[0]
            else:
                interp.clarification = "Which column should I count distinct values for?"
                return interp
        interp.intent = "distinct_count"
        interp.aggregations = [("count_distinct", target.name, None, "distinct_count")]
        interp.limit = 1
        return interp

    def _rule_scalar_average(self, interp, text, tokens) -> Optional[Interpretation]:
        if not (tokens & AVG_WORDS):
            return None
        if self._has_unresolved_filter_hint(text):
            return None
        match = (re.search(r"average (?:of )?(.+?)$", text)
                 or re.search(r"(.+?) ka ausat", text))
        measure = self._resolve_measure(match.group(1), interp=interp) if match else None
        if measure is None:
            if len(self.schema.measures) == 1:
                measure = self._resolve_measure("", interp=interp)
            else:
                interp.clarification = self._measure_question()
                return interp
        interp.intent = "scalar_metric"
        interp.aggregations = [("avg", measure.name, None, "avg_value")]
        interp.limit = 1
        return interp

    def _rule_scalar_sum(self, interp, text, tokens) -> Optional[Interpretation]:
        if not (tokens & SUM_WORDS) and "kul " not in text:
            return None
        if self._has_unresolved_filter_hint(text):
            return None
        match = (re.search(r"total (.+?)$", text)
                 or re.search(r"kul (.+?) kitna", text))
        measure = self._resolve_measure(match.group(1), interp=interp) if match else None
        if measure is None:
            return None
        interp.intent = "scalar_metric"
        interp.aggregations = [("sum", measure.name, None, "total_value")]
        interp.limit = 1
        return interp

    def _rule_scalar_count(self, interp, text, tokens) -> Optional[Interpretation]:
        if not (tokens & COUNT_WORDS):
            return None
        if self._has_unresolved_filter_hint(text):
            return None
        interp.intent = "scalar_metric"
        interp.aggregations = [("count", None, None, "total_records")]
        interp.limit = 1
        return interp

    # ------------------------------------------------------------------
    # Loose structural fallback
    # ------------------------------------------------------------------
    def _rule_loose(self, interp, text, tokens) -> Optional[Interpretation]:
        measure, mscore = self.schema.find_column(text, roles=("measure",))
        dims = [c for c in self.schema.dimensions
                if {t for t in c.tokens if len(t) >= 3} & tokens]
        condition, filter_col = self._filter_from(text)
        wants_group = bool(re.search(r"\b(by|wise|per|hisab)\b", text)) and bool(dims)

        if condition is not None and not dims:
            interp.intent = "conditional_count"
            interp.filters = [condition]
            interp.aggregations = [("count", None, None, "n")]
            interp.limit = 1
            return interp

        if measure is not None and mscore >= 0.5:
            function = "avg" if tokens & AVG_WORDS else "sum"
            interp.aggregations = [(function, measure.name, None, f"{function}_value")]
            interp.intent = "scalar_metric"
            interp.limit = 1
            if wants_group:
                group = dims[0]
                interp.group_by = [group.name]
                interp.intent = "grouped_metric"
                interp.sort = [(f"{function}_value", False)]
                interp.limit = 10
            interp.confidence -= 0.15
            if filter_col is not None:
                interp.filters = [condition]
            return interp

        if dims and (tokens & (RANK_DESC | RANK_ASC)):
            group = dims[0]
            interp.group_by = [group.name]
            interp.aggregations = [("count", None, None, "metric")]
            interp.sort = [("metric", bool(tokens & RANK_ASC) and not tokens & RANK_DESC)]
            interp.limit = 10
            interp.intent = "grouped_count"
            interp.confidence -= 0.2
            return interp
        return None

    def _measure_question(self) -> str:
        names = [c.name for c in self.schema.measures[:6]]
        return "Which measure should I use for that? Options include: " + ", ".join(names) + "."


# ---------------------------------------------------------------------------
# Interpretation -> AnalysisPlan
# ---------------------------------------------------------------------------

class GenericPlanner:
    """Translates an Interpretation into a plan the existing executor can run.

    The plan contract (planning/schemas.py) and its executor (PlanValidator +
    QueryCompiler) support filters, group_by, aggregations, sort, limit and joins.
    Derived ratios, HAVING, per-group ranking and date grouping are not expressible
    yet, so an interpretation needing them is refused with UnsupportedPlanError
    instead of being flattened into a plan that answers a different question.
    """

    @staticmethod
    def build_plan(interpretation: Interpretation, question: str, file_ids: List[str],
                   profile: Dict[str, Any]) -> AnalysisPlan:
        if interpretation.clarification:
            raise UnsupportedPlanError(interpretation.clarification)
        if interpretation.derived:
            raise UnsupportedPlanError(
                "derived metric (ratio, share or percentage) is not supported by the plan executor"
            )
        if interpretation.having:
            raise UnsupportedPlanError("HAVING is not supported by the plan executor")
        if interpretation.rank_partition or interpretation.rank_order:
            raise UnsupportedPlanError("per-group ranking is not supported by the plan executor")
        if interpretation.date_column:
            raise UnsupportedPlanError("date grouping is not supported by the plan executor")

        datasets = [DatasetRef(file_id=fid, alias=f"ds_{index + 1}")
                    for index, fid in enumerate(file_ids)]

        filters = list(interpretation.filters)
        aggregations: List[AggregateOperation] = []
        for function, column, condition, alias in interpretation.aggregations:
            if function not in EXECUTABLE_AGGREGATES:
                raise UnsupportedPlanError(
                    f"aggregate '{function}' is not supported by the plan executor"
                )
            if condition is not None:
                # AggregateOperation carries no per-aggregate predicate, so a
                # conditional aggregate can only be expressed by hoisting the
                # condition to the whole query - valid only for a single aggregate.
                if len(interpretation.aggregations) > 1:
                    raise UnsupportedPlanError(
                        "a per-aggregate filter with multiple aggregations is not supported "
                        "by the plan executor"
                    )
                if condition not in filters:
                    filters.append(condition)
            aggregations.append(
                AggregateOperation(function=function, column=column, alias=alias)
            )

        return AnalysisPlan(
            intent=interpretation.intent,
            question=question,
            datasets=datasets,
            filters=filters,
            group_by=list(interpretation.group_by),
            aggregations=aggregations,
            sort=[SortRule(column=column, ascending=ascending)
                  for column, ascending in interpretation.sort],
            limit=interpretation.limit or 100,
        )
