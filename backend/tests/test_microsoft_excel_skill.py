import hashlib
import os

import pytest
from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo

from app.ai.orchestration.context import AIContext
from app.ai.orchestration.orchestrator import AnalysisOrchestrator
from app.ai.planning.schemas import AnalysisPlan, DatasetRef
from app.ai.skills.registry import SOURCE_COMMIT, SkillRegistry, skill_source_path
from app.analysis.excel.workbook import ExcelWorkbookError, ExcelWorkbookService
from app.models.file import StoredFile


def _make_workbook(path):
    workbook = Workbook()
    first = workbook.active
    first.title = "Sheet1"
    first.append(["Employee ID", "Employee", "Department", "Amount", "Calculated"])
    first.append([1, "Alice", "Engineering", 10, "=D2*2"])
    first.append([2, "Bob", "Sales", 20, "=D3*2"])
    first.append([1, "Alice", "Engineering", 10, "=D4*2"])
    first.append([3, "Cara", None, 30, "=D5*2"])
    table = Table(displayName="Employees", ref="A1:E5")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    first.add_table(table)

    second = workbook.create_sheet("Sheet2")
    second.append(["Employee ID", "Employee", "Department", "Amount", "Calculated"])
    second.append([1, "Alice", "Engineering", 10, "=D2*2"])
    second.append([2, "Bob", "Sales", 25, "=D3*2"])
    second.append([3, "Cara", "Operations", 30, "=D4*2"])
    second.append([4, "Dan", "Finance", 40, "=D5*2"])
    workbook.save(path)


def _stored_file(path):
    return StoredFile(
        id="xlsx-test",
        owner_user_id="user-1",
        original_name=os.path.basename(path),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=os.path.getsize(path),
        storage_key="xlsx-test.xlsx",
        schema_profile=DataProfiler.profile_file(path, os.path.basename(path)),
    )


from app.analysis.profiling.profiler import DataProfiler


def test_excel_skill_is_discovered_and_metadata_is_pinned():
    skills = SkillRegistry.discover()
    assert "microsoft-excel" in [skill.name for skill in skills]
    assert SkillRegistry.count() == 9
    assert SkillRegistry.get("microsoft-excel").source_commit == SOURCE_COMMIT
    assert skill_source_path().is_file()
    assert "name: microsoft-excel" in skill_source_path().read_text(encoding="utf-8")


def test_excel_profile_and_routing(tmp_path):
    path = tmp_path / "employees.xlsx"
    _make_workbook(path)
    stored = _stored_file(str(path))
    profile = stored.schema_profile

    assert profile["sheets"] == ["Sheet1", "Sheet2"]
    assert profile["sheet_profiles"][0]["tables"] == ["Employees"]
    assert profile["formula_count"] == 8
    route = SkillRegistry.route("Compare Sheet1 and Sheet2 and explain formulas", {stored.id: stored})
    assert route["skills"][:2] == ["microsoft-excel", "programmatic-eda"]
    assert "office_scripts_generation" in route["guidance_only"]


def test_excel_operations_are_deterministic_and_keep_source_unchanged(tmp_path):
    path = tmp_path / "employees.xlsx"
    _make_workbook(path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    profile = DataProfiler.profile_file(str(path), path.name)

    duplicate = ExcelWorkbookService.run_question(str(path), "identify duplicate employees", profile)
    assert duplicate["workbook_operation"] == "duplicate_detection"
    assert duplicate["evidence_rows"] == [2, 4]
    assert duplicate["engine"] == "openpyxl"

    missing = ExcelWorkbookService.run_question(str(path), "find missing values", profile)
    assert missing["rows"][0]["missing_counts"]["Department"] == 1

    comparison = ExcelWorkbookService.run_question(str(path), "compare Sheet1 and Sheet2", profile)
    assert comparison["workbook_operation"] == "multi_sheet_comparison"
    assert comparison["rows"][0]["changed_count"] == 3
    assert comparison["rows"][0]["right_only_count"] == 1

    formulas = ExcelWorkbookService.run_question(str(path), "inspect formulas", profile)
    assert formulas["workbook_operation"] == "formula_inspection"
    assert formulas["rows"][0]["formula_count"] == 4
    assert "without executing" in formulas["rows"][0]["note"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.asyncio
async def test_excel_runtime_orchestrator_returns_provenance(tmp_path, monkeypatch):
    path = tmp_path / "employees.xlsx"
    _make_workbook(path)
    stored = _stored_file(str(path))
    orchestrator = AnalysisOrchestrator()

    async def fake_plan(*args, **kwargs):
        return AnalysisPlan(
            question="find duplicate employees",
            datasets=[DatasetRef(file_id=stored.id, alias="ds_1")],
        )

    async def fake_finalize(analysis_id, ctx, question, explanation, **kwargs):
        return {"explanation": explanation, **kwargs}

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(orchestrator, "_plan_with_ai", fake_plan)
    monkeypatch.setattr(orchestrator, "_finalize_success", fake_finalize)
    monkeypatch.setattr(orchestrator.analysis_repo, "update", noop)
    monkeypatch.setattr(orchestrator, "_emit_event", noop)

    result = await orchestrator._handle_data_analysis(
        "analysis-1",
        AIContext(user_id="user-1", unit_id="default_unit", role="employee", chat_id="chat-1", file_ids=[stored.id]),
        "find duplicate employees",
        [stored.id],
        {stored.id: stored},
        {stored.id: str(path)},
        "DATA_ANALYSIS",
    )
    assert result["result"]["workbook_operation"] == "duplicate_detection"
    assert result["provenance"]["skills"][:2] == ["microsoft-excel", "programmatic-eda"]
    assert "data-quality-audit" in result["provenance"]["skills"]
    assert result["provenance"]["engine"] == "openpyxl"


def test_malformed_workbook_and_export_formula_injection_are_rejected(tmp_path):
    bad_path = tmp_path / "bad.xlsx"
    bad_path.write_bytes(b"not an xlsx")
    with pytest.raises(ExcelWorkbookError):
        ExcelWorkbookService.profile(str(bad_path))
    assert ExcelWorkbookService.sanitize_export_value("=1+1") == "'=1+1"
    assert ExcelWorkbookService.sanitize_export_value("safe") == "safe"
