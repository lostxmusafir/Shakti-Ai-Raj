import os
import re
import json
import uuid
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
GOLDEN_FILE = os.path.join(BASE_DIR, "data", "benchmark", "golden", "golden_examples_300.json")
TRAINING_PACK_GOLDEN_FILE = os.path.join(BASE_DIR, "data", "benchmark", "golden", "golden_examples_training_pack.json")

class ExampleRetriever:
    """
    Retrieves relevant, verified Golden Q&A examples based on semantic intent,
    keyword matching, and schema similarity without fine-tuning model weights.
    """
    _cached_examples: Optional[List[Dict[str, Any]]] = None
    _last_loaded_mtime: float = 0.0

    @classmethod
    def clear_cache(cls) -> None:
        """Clears in-memory cached examples to allow reloading."""
        cls._cached_examples = None
        cls._last_loaded_mtime = 0.0

    @classmethod
    def _get_artifacts_mtime(cls) -> float:
        """Returns the newest modification time among golden artifact files."""
        mtimes = [0.0]
        for p in [GOLDEN_FILE, TRAINING_PACK_GOLDEN_FILE]:
            if os.path.exists(p):
                mtimes.append(os.path.getmtime(p))
        return max(mtimes)

    @classmethod
    def load_examples(cls, force_reload: bool = False) -> List[Dict[str, Any]]:
        current_mtime = cls._get_artifacts_mtime()
        if cls._cached_examples is not None and not force_reload and current_mtime <= cls._last_loaded_mtime:
            return cls._cached_examples

        all_examples: Dict[str, Dict[str, Any]] = {}

        # 1. Load baseline golden benchmark examples
        if os.path.exists(GOLDEN_FILE):
            try:
                with open(GOLDEN_FILE, "r", encoding="utf-8") as f:
                    base_data = json.load(f)
                    for item in base_data:
                        eid = item.get("example_id") or str(uuid.uuid4())
                        all_examples[eid] = item
                logger.info(f"Loaded {len(base_data)} base golden examples into memory.")
            except Exception as e:
                logger.error(f"Failed to load golden examples from {GOLDEN_FILE}: {e}")

        # 2. Load training pack golden examples (Milestone 1)
        if os.path.exists(TRAINING_PACK_GOLDEN_FILE):
            try:
                with open(TRAINING_PACK_GOLDEN_FILE, "r", encoding="utf-8") as f:
                    tp_data = json.load(f)
                    for item in tp_data:
                        eid = item.get("example_id") or str(uuid.uuid4())
                        all_examples[eid] = item
                logger.info(f"Loaded {len(tp_data)} training pack golden examples into memory.")
            except Exception as e:
                logger.error(f"Failed to load golden examples from {TRAINING_PACK_GOLDEN_FILE}: {e}")

        cls._cached_examples = list(all_examples.values())
        cls._last_loaded_mtime = current_mtime
        return cls._cached_examples

    @classmethod
    def retrieve(
        cls,
        question: str,
        columns: List[str],
        user_unit_id: str = "default_unit",
        user_role: str = "employee",
        top_k: int = 2
    ) -> List[Dict[str, Any]]:
        if top_k <= 0:
            return []

        examples = cls.load_examples()
        if not examples:
            return []

        q_lower = str(question or "").lower()
        q_tokens = set(re.findall(r"\w+", q_lower))
        cols_lower = set(str(c).lower() for c in (columns or []) if c is not None)

        scored = []
        for ex in examples:
            # Respect tenancy and approval status
            if ex.get("approval_status") != "approved":
                continue
            if ex.get("source_type") == "private_tenant" and ex.get("unit_id") != user_unit_id and user_role not in ["super_admin", "tech_admin"]:
                continue

            ex_q = str(ex.get("question") or "").lower()
            ex_tokens = set(re.findall(r"\w+", ex_q))
            
            # 1. Lexical overlap score
            token_overlap = len(q_tokens & ex_tokens) / max(1, len(q_tokens | ex_tokens))
            
            # 2. Key phrase bonus (e.g. "sabse zyada", "blocked", "split", "gmail", "profit")
            phrase_bonus = 0.0
            for phrase in [
                "sabse zyada", "blocked", "split", "internal vs external", "revenue", "profit",
                "cad", "password", "missing", "highest", "flight", "airline", "fare", "booking",
                "credit score", "loan", "savings", "emi", "song", "remake", "youtube", "views"
            ]:
                if phrase in q_lower and phrase in ex_q:
                    phrase_bonus += 0.35

            # 3. Schema similarity bonus
            col_map = ex.get("column_mapping") or {}
            ex_cols = set(str(k).lower() for k in col_map.values() if k is not None)
            schema_overlap = len(cols_lower & ex_cols) / max(1, len(cols_lower | ex_cols)) if ex_cols else 0.0

            total_score = (token_overlap * 0.4) + phrase_bonus + (schema_overlap * 0.25)
            if total_score > 0.05:
                scored.append((total_score, ex))

        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:top_k]]

    @classmethod
    def format_for_prompt(cls, examples: List[Dict[str, Any]]) -> str:
        if not examples:
            return ""

        formatted_blocks = ["### REUSABLE ANALYTICAL EXAMPLES (LEARNED PATTERNS):"]
        for idx, ex in enumerate(examples, start=1):
            q_text = ex.get('question', '')
            formatted_blocks.append(
                f"Example {idx}:\n"
                f"- Question: \"{q_text}\"\n"
                f"- Language: {ex.get('language', 'hinglish')}\n"
                f"- Intent: {ex.get('intent', 'data_analysis')}\n"
                f"- Target Concept: {ex.get('semantic_target', 'N/A')}\n"
                f"- SQL Pattern: {ex.get('sql_query', 'N/A')}"
            )
        return "\n\n".join(formatted_blocks)
