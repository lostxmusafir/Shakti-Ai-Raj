import os
import pytest
from app.ai.planning.schemas import (
    AnalysisPlan, DatasetRef, Condition, AggregateOperation, SortRule, JoinRule
)
from app.ai.planning.validator import PlanValidator
from app.analysis.execution.compiler import QueryCompiler
from app.analysis.execution.duckdb_engine import DuckDBEngine
from app.models.file import StoredFile

def test_query_compiler_syntax():
    plan = AnalysisPlan(
        question="How many incidents by department where severity is Critical?",
        datasets=[DatasetRef(file_id="f1", alias="incidents")],
        filters=[Condition(column="severity", operator="equals", value="Critical")],
        group_by=["department"],
        aggregations=[AggregateOperation(function="count", column="*", alias="critical_count")],
        limit=10
    )
    sql, params = QueryCompiler.compile(plan)
    assert 'COUNT(*) AS "critical_count"' in sql
    assert 'FROM "incidents"' in sql
    assert 'WHERE "severity" = ?' in sql
    assert 'GROUP BY "department"' in sql
    assert 'LIMIT 10' in sql
    assert params == ["Critical"]

def test_duckdb_deterministic_execution():
    incidents_path = os.path.abspath("data/samples/incidents.csv")
    f1 = StoredFile(
        id="f1",
        owner_user_id="user_1",
        original_name="incidents.csv",
        content_type="text/csv",
        size_bytes=1000,
        storage_key="incidents.csv",
        schema_profile={
            "columns": [
                {"name": "incident_id", "inferred_type": "string"},
                {"name": "department", "inferred_type": "string"},
                {"name": "severity", "inferred_type": "string"},
                {"name": "resolution_hours", "inferred_type": "float"}
            ]
        }
    )

    plan = AnalysisPlan(
        question="Count critical incidents by department",
        datasets=[DatasetRef(file_id="f1", alias="incidents")],
        filters=[Condition(column="severity", operator="equals", value="Critical")],
        group_by=["department"],
        aggregations=[AggregateOperation(function="count", column="*", alias="count")],
        limit=10
    )

    # Validate
    PlanValidator.validate_plan(plan, {"f1": f1})

    # Execute
    res = DuckDBEngine.execute(plan, {"f1": f1}, {"f1": incidents_path})
    assert res["engine"] == "duckdb"
    assert res["row_count"] > 0
    # IT should have 3 critical incidents (INC-1001, INC-1004, INC-1008)
    dept_map = {r["department"]: r["count"] for r in res["rows"]}
    assert dept_map["IT"] == 3

def test_duckdb_multi_file_join():
    incidents_path = os.path.abspath("data/samples/incidents.csv")
    depts_path = os.path.abspath("data/samples/departments.csv")
    
    f1 = StoredFile(
        id="f1",
        owner_user_id="user_1",
        original_name="incidents.csv",
        content_type="text/csv",
        size_bytes=1000,
        storage_key="incidents.csv",
        schema_profile={"columns": [{"name": "department"}, {"name": "severity"}]}
    )
    f2 = StoredFile(
        id="f2",
        owner_user_id="user_1",
        original_name="departments.csv",
        content_type="text/csv",
        size_bytes=500,
        storage_key="departments.csv",
        schema_profile={"columns": [{"name": "department"}, {"name": "division"}, {"name": "headcount"}]}
    )

    plan = AnalysisPlan(
        question="Incidents by division",
        datasets=[
            DatasetRef(file_id="f1", alias="incidents"),
            DatasetRef(file_id="f2", alias="departments")
        ],
        joins=[JoinRule(
            left_dataset="incidents",
            right_dataset="departments",
            left_column="department",
            right_column="department"
        )],
        group_by=["division"],
        aggregations=[AggregateOperation(function="count", column="*", alias="total_incidents")]
    )

    PlanValidator.validate_plan(plan, {"f1": f1, "f2": f2})
    res = DuckDBEngine.execute(plan, {"f1": f1, "f2": f2}, {"f1": incidents_path, "f2": depts_path})
    assert res["row_count"] > 0
    div_map = {r["division"]: r["total_incidents"] for r in res["rows"]}
    assert "Engineering" in div_map
