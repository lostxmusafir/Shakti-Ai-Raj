import os
import re
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
GOLDEN_FILE = os.path.join(BASE_DIR, "data", "benchmark", "golden", "golden_examples_300.json")

class ExampleRetriever:
    """
    Retrieves relevant, verified Golden Q&A examples based on semantic intent,
    keyword matching, and schema similarity without fine-tuning model weights.
    """
    _cached_examples: Optional[List[Dict[str, Any]]] = None

    @classmethod
    def load_examples(cls) -> List[Dict[str, Any]]:
        if cls._cached_examples is not None:
            return cls._cached_examples
            
        if os.path.exists(GOLDEN_FILE):
            try:
                with open(GOLDEN_FILE, "r", encoding="utf-8") as f:
                    cls._cached_examples = json.load(f)
                logger.info(f"Loaded {len(cls._cached_examples)} golden examples into memory.")
                return cls._cached_examples
            except Exception as e:
                logger.error(f"Failed to load golden examples from {GOLDEN_FILE}: {e}")
                
        cls._cached_examples = []
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
        examples = cls.load_examples()
        if not examples:
            return []

        q_tokens = set(re.findall(r"\w+", question.lower()))
        cols_lower = set(c.lower() for c in columns)

        scored = []
        for ex in examples:
            # Respect tenancy and approval status
            if ex.get("approval_status") != "approved":
                continue
            if ex.get("source_type") == "private_tenant" and ex.get("unit_id") != user_unit_id and user_role not in ["super_admin", "tech_admin"]:
                continue

            ex_q = ex.get("question", "").lower()
            ex_tokens = set(re.findall(r"\w+", ex_q))
            
            # 1. Lexical overlap score
            token_overlap = len(q_tokens & ex_tokens) / max(1, len(q_tokens | ex_tokens))
            
            # 2. Key phrase bonus (e.g. "sabse zyada", "blocked", "split", "gmail", "profit")
            phrase_bonus = 0.0
            for phrase in ["sabse zyada", "blocked", "split", "internal vs external", "revenue", "profit", "cad", "password", "missing", "highest"]:
                if phrase in question.lower() and phrase in ex_q:
                    phrase_bonus += 0.35

            # 3. Schema similarity bonus
            ex_cols = set(k.lower() for k in ex.get("column_mapping", {}).values())
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
            formatted_blocks.append(
                f"Example {idx}:\n"
                f"- Question: \"{ex['question']}\"\n"
                f"- Language: {ex.get('language', 'hinglish')}\n"
                f"- Intent: {ex.get('intent', 'data_analysis')}\n"
                f"- Target Concept: {ex.get('semantic_target', 'N/A')}\n"
                f"- SQL Pattern: {ex.get('sql_query', 'N/A')}"
            )
        return "\n\n".join(formatted_blocks)
