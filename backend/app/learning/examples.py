from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from pydantic import BaseModel, Field


class GoldenExample(BaseModel):
    schema_version: str = "1.0"
    example_id: str = Field(default_factory=lambda: f"qa-{uuid.uuid4().hex[:12]}")
    dataset_id: str
    dataset_checksum: str
    question: str
    language: str
    intent: str
    semantic_target: str
    column_mapping: Dict[str, str] = Field(default_factory=dict)
    sql_query: Optional[str] = None
    expected_plan: Dict[str, Any]
    expected_answer: Dict[str, Any]
    evidence_ids: List[str] = Field(default_factory=list)
    verification: Dict[str, Any]
    source_type: str
    approval_status: str = "pending"
    approved_by: Optional[str] = None
    split: str = "train"
    skill_selection: List[str] = Field(default_factory=list)
    access_scope: str = "global"


class GoldenExampleStore:
    """Versioned JSONL store with deterministic local retrieval fallback."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, example: GoldenExample) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(example.model_dump_json() + "\n")

    def load(self, approved_only: bool = False) -> List[GoldenExample]:
        if not self.path.exists():
            return []
        examples: List[GoldenExample] = []
        raw = self.path.read_text(encoding="utf-8")
        try:
            parsed = json.loads(raw)
            records = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            records = [line for line in raw.splitlines() if line.strip()]
        for record in records:
            try:
                example = GoldenExample.model_validate_json(record) if isinstance(record, str) else GoldenExample.model_validate(record)
            except Exception:
                continue
            if not approved_only or example.approval_status == "approved":
                examples.append(example)
        return examples

    def retrieve(self, question: str, limit: int = 5, access_scope: str = "global") -> List[GoldenExample]:
        query_terms = set(re.findall(r"[a-z0-9]+", question.lower()))
        scored = []
        for example in self.load(approved_only=True):
            if example.access_scope not in {"global", access_scope}:
                continue
            terms = set(re.findall(r"[a-z0-9]+", example.question.lower()))
            score = len(query_terms & terms)
            score += 2 if example.language.lower() in question.lower() else 0
            if score:
                scored.append((score, example.example_id, example))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in scored[:limit]]

    def promote_verified(self, example: GoldenExample, approved_by: str) -> GoldenExample:
        if example.verification.get("status") != "verified":
            raise ValueError("Only independently verified examples may be promoted.")
        if not approved_by.strip():
            raise ValueError("An approving identity is required.")
        promoted = example.model_copy(update={
            "approval_status": "approved",
            "verification": {**example.verification, "approved_by": approved_by},
        })
        self.append(promoted)
        return promoted


def render_retrieval_context(examples: Sequence[GoldenExample]) -> str:
    if not examples:
        return "No approved examples matched this question."
    lines = ["Approved example patterns (numbers must be recalculated for the current dataset):"]
    for example in examples:
        lines.append(
            f"- {example.question} | intent={example.intent} | "
            f"target={example.semantic_target} | mapping={json.dumps(example.column_mapping, sort_keys=True)}"
        )
    return "\n".join(lines)
