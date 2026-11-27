import os

import pytest

from app.ai.orchestration.orchestrator import AnalysisOrchestrator
from app.analysis.profiling.profiler import DataProfiler
from app.models.file import StoredFile


def _stored(file_id: str, path: str) -> StoredFile:
    profile = DataProfiler.profile_file(path, os.path.basename(path))
    return StoredFile(
        id=file_id,
        owner_user_id="planner-test",
        unit_id="unit-test",
        original_name=os.path.basename(path),
        storage_key=os.path.basename(path),
        size_bytes=os.path.getsize(path),
        content_type="text/csv",
        status="ready",
        schema_profile=profile,
    )


@pytest.fixture
def finance_file(tmp_path):
    path = tmp_path / "finance.csv"
    path.write_text(
        "Country,Profit,Sales,Year\nIndia,10,100,2025\nFrance,20,200,2025\n",
        encoding="utf-8",
    )
    return _stored("finance", str(path))


@pytest.fixture
def dlp_file(tmp_path):
    path = tmp_path / "dlp.csv"
    path.write_text(
        "Source,Transaction Size (KB),Severity,Action,Destination,Incident Time\n"
        "A,10,High,Blocked,a@example.com,\"01 Jan 2026, 01:00:00 AM GMT+0530\"\n"
        "B,20,Low,Permitted,b@example.com,\"01 Jan 2026, 02:00:00 AM GMT+0530\"\n",
        encoding="utf-8",
    )
    return _stored("dlp", str(path))


@pytest.fixture
def employee_files(tmp_path):
    employees = tmp_path / "employees.csv"
    payroll = tmp_path / "payroll.csv"
    employees.write_text("employee_id\nE1\nE2\n", encoding="utf-8")
    payroll.write_text("employee_id\nE1\n", encoding="utf-8")
    return _stored("employees", str(employees)), _stored("payroll", str(payroll))


def test_hindi_profit_maps_to_sum(finance_file):
    plan = AnalysisOrchestrator()._plan_fallback(
        "Kul munafa kitna hai?", ["finance"], {"finance": finance_file}, "DATA_ANALYSIS"
    )
    assert plan.aggregations[0].function == "sum"
    assert plan.aggregations[0].column == "Profit"


def test_hindi_country_rank_maps_dimension_and_sort(finance_file):
    plan = AnalysisOrchestrator()._plan_fallback(
        "Sabse zyada kul profit kis desh ka hai?",
        ["finance"],
        {"finance": finance_file},
        "DATA_ANALYSIS",
    )
    assert plan.group_by == ["Country"]
    assert plan.limit == 1
    assert plan.sort and plan.sort[0].ascending is False


def test_hindi_source_rank_maps_dlp_dimension(dlp_file):
    plan = AnalysisOrchestrator()._plan_fallback(
        "Sabse adhik data kis source ne bheja?", ["dlp"], {"dlp": dlp_file}, "DATA_ANALYSIS"
    )
    assert plan.group_by == ["Source"]
    assert plan.limit == 1


def test_short_multi_file_missing_payroll_is_count(employee_files):
    left, right = employee_files
    plan = AnalysisOrchestrator()._plan_fallback(
        "Employees missing in payroll",
        ["employees", "payroll"],
        {"employees": left, "payroll": right},
        "DATA_ANALYSIS",
    )
    assert plan.intent == "anti_join_count"
    assert plan.aggregations[0].function == "count"
    assert plan.joins[0].join_type == "anti"


def test_external_transfer_detail_request_does_not_collapse_to_scalar_max(dlp_file):
    plan = AnalysisOrchestrator()._plan_fallback(
        "Sabse bada external transfer kaunsa hai (ID, sender, file, size)?",
        ["dlp"],
        {"dlp": dlp_file},
        "DATA_ANALYSIS",
    )
    assert plan.sql_query and "SELECT id" in plan.sql_query
