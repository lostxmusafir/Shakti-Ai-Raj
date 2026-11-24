from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping


SOURCE_COMMIT = "3fe50c5182735117f5903b6b4731a4af68697cb1"


@dataclass(frozen=True)
class SkillManifest:
    name: str
    description: str
    category: str
    source: str
    source_commit: str
    runtime_capabilities: tuple[str, ...]
    guidance_only_capabilities: tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "source": self.source,
            "source_commit": self.source_commit,
            "runtime_capabilities": list(self.runtime_capabilities),
            "guidance_only_capabilities": list(self.guidance_only_capabilities),
        }


MICROSOFT_EXCEL = SkillManifest(
    name="microsoft-excel",
    description="Analyze Excel workbooks and generate safe Excel automation guidance.",
    category="office",
    source="https://github.com/alivirgo/Major-AI-Skills",
    source_commit=SOURCE_COMMIT,
    runtime_capabilities=(
        "workbook_profile",
        "worksheet_profile",
        "formula_inspection",
        "multi_sheet_comparison",
        "duplicate_detection",
        "missing_value_detection",
        "safe_deterministic_analysis",
        "source_row_evidence",
    ),
    guidance_only_capabilities=(
        "office_scripts_generation",
        "power_query_generation",
        "vba_guidance",
        "pivot_table_generation",
        "excel_export",
        "formula_recalculation",
    ),
)

NATIVE_SKILLS = (
    SkillManifest("programmatic-eda", "Profile and inspect datasets with the existing deterministic analytics engine.", "analytics", "native", "workspace", ("schema_profiling", "deterministic_eda"), ()),
    SkillManifest("data-quality-audit", "Audit nulls, duplicates, type issues, and malformed inputs.", "analytics", "native", "workspace", ("missing_value_detection", "input_validation"), ()),
    SkillManifest("schema-mapper", "Map natural-language concepts to actual profiled columns.", "analytics", "native", "workspace", ("schema_semantic_mapping",), ()),
    SkillManifest("metric-reconciliation", "Reconcile computed aggregates and source evidence.", "analytics", "native", "workspace", ("independent_verification",), ()),
    SkillManifest("business-metrics-calculator", "Calculate validated business aggregates using DuckDB.", "analytics", "native", "workspace", ("aggregate_calculation",), ()),
    SkillManifest("time-series-analysis", "Build deterministic time-based groupings from actual date columns.", "analytics", "native", "workspace", ("date_grouping",), ()),
    SkillManifest("insight-synthesis", "Explain verified results without inventing values.", "analytics", "native", "workspace", ("verified_narrative",), ()),
)


class SkillRegistry:
    """Small manifest registry used by the runtime orchestrator.

    The repository did not contain the previously described 31-skill registry,
    so only skills actually shipped in this checkout are returned.
    """

    _manifests = {skill.name: skill for skill in (MICROSOFT_EXCEL, *NATIVE_SKILLS)}

    @classmethod
    def discover(cls) -> List[SkillManifest]:
        return list(cls._manifests.values())

    @classmethod
    def get(cls, name: str) -> SkillManifest | None:
        return cls._manifests.get(name)

    @classmethod
    def count(cls) -> int:
        return len(cls._manifests)

    @classmethod
    def route(cls, question: str, files_map: Mapping[str, Any]) -> Dict[str, Any]:
        text = (question or "").lower()
        workbook_present = any(
            str(getattr(file, "original_name", "")).lower().endswith((".xlsx", ".xls"))
            or str(getattr(file, "content_type", "")).lower()
            in {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-excel",
            }
            for file in files_map.values()
        )
        excel_terms = (
            "excel", "workbook", "worksheet", "sheet", "formula", "pivot",
            "power query", "office script", "vba", "table", "duplicate",
            "missing value", "blank", "compare", "difference",
        )
        selected: List[str] = []
        reasons: List[str] = []
        if workbook_present or any(term in text for term in excel_terms):
            selected.append(MICROSOFT_EXCEL.name)
            if workbook_present:
                reasons.append("an uploaded workbook is in scope")
            if any(term in text for term in excel_terms):
                reasons.append("the question requests an Excel/workbook operation")
        analysis_terms = ("analyze", "count", "sum", "total", "average", "top", "highest", "most", "revenue", "profit", "expense", "data")
        if workbook_present or any(term in text for term in analysis_terms):
            selected.append("programmatic-eda")
        if any(term in text for term in ("duplicate", "duplicates", "missing", "blank", "null", "quality")):
            selected.append("data-quality-audit")
        if any(term in text for term in ("compare", "difference", "differences", "reconcile", "missing employees")):
            selected.extend(["schema-mapper", "metric-reconciliation"])
        if any(term in text for term in ("revenue", "profit", "sales", "expense", "amount", "department-wise", "summary")):
            selected.append("business-metrics-calculator")
        if any(term in text for term in ("month", "trend", "over time", "daily", "weekly", "monthly")):
            selected.append("time-series-analysis")
        if any(term in text for term in ("explain", "insight", "report", "summarize")):
            selected.append("insight-synthesis")
        selected = list(dict.fromkeys(selected))
        return {
            "skills": selected,
            "reasons": reasons,
            "guidance_only": (
                list(MICROSOFT_EXCEL.guidance_only_capabilities)
                if MICROSOFT_EXCEL.name in selected
                else []
            ),
        }


def skill_source_path() -> Path:
    return Path(__file__).resolve().parent / "microsoft-excel" / "SKILL.md"
