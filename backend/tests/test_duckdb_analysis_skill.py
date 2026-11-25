import os
import pytest
import duckdb
import polars as pl
from pathlib import Path

from app.ai.planning.schemas import (
    AnalysisPlan,
    DatasetRef,
    Condition,
    AggregateOperation,
    SortRule,
    JoinRule,
)
from app.ai.planning.validator import PlanValidator
from app.analysis.execution.compiler import QueryCompiler
from app.analysis.execution.duckdb_engine import DuckDBEngine
from app.analysis.execution.sanitizer import SQLSanitizer
from app.analysis.profiling.profiler import DataProfiler
from app.ai.skills.registry import SkillRegistry, SOURCE_COMMIT, skill_source_path
from app.ai.verification.verifier import ResultVerifier
from app.core.exceptions import PlanValidationError, ExecutionError
from app.models.file import StoredFile


def _create_test_csv(path: Path) -> StoredFile:
    content = (
        "region,customer,revenue,status,quantity\n"
        "North,Acme Corp,1000,Completed,10\n"
        "North,Beta LLC,1500,Completed,15\n"
        "South,Acme Corp,2000,Completed,20\n"
        "South,Gamma Inc,500,Cancelled,5\n"
        "East,Delta Co,3000,Completed,30\n"
        "West,Echo Ltd,800,Cancelled,8\n"
    )
    path.write_text(content, encoding="utf-8")
    profile = DataProfiler.profile_file(str(path), path.name)
    return StoredFile(
        id="file-csv-1",
        owner_user_id="user-1",
        original_name=path.name,
        content_type="text/csv",
        size_bytes=path.stat().st_size,
        storage_key=path.name,
        schema_profile=profile,
    )


def _create_test_parquet(path: Path) -> StoredFile:
    df = pl.DataFrame({
        "airline": ["Delta", "Delta", "Delta", "United", "United", "Southwest"],
        "flight_id": [101, 102, 103, 201, 202, 301],
        "status": ["Completed", "Cancelled", "Completed", "Cancelled", "Cancelled", "Completed"],
        "bookings": [50, 45, 60, 30, 25, 40],
    })
    df.write_parquet(path)
    profile = DataProfiler.profile_file(str(path), path.name)
    return StoredFile(
        id="file-parquet-1",
        owner_user_id="user-1",
        original_name=path.name,
        content_type="application/vnd.apache.parquet",
        size_bytes=path.stat().st_size,
        storage_key=path.name,
        schema_profile=profile,
    )


def test_duckdb_skill_manifest_registered():
    """Verify data-analysis-with-duckdb is discovered and metadata is correctly pinned."""
    manifest = SkillRegistry.get("data-analysis-with-duckdb")
    assert manifest is not None
    assert manifest.name == "data-analysis-with-duckdb"
    assert manifest.category == "analytics"
    assert "https://mcpmarket.com/tools/skills/data-analysis-with-duckdb" in manifest.source
    assert manifest.source_commit == SOURCE_COMMIT
    assert "columnar_sql_analysis" in manifest.runtime_capabilities
    assert "fast_csv_scan" in manifest.runtime_capabilities
    assert "fast_parquet_scan" in manifest.runtime_capabilities
    assert "external_database_federation" in manifest.guidance_only_capabilities

    # Source markdown playbook existence and integrity
    path = skill_source_path("data-analysis-with-duckdb")
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "name: data-analysis-with-duckdb" in text
    assert "DuckDB" in text
    assert "Universal AI Analyst Pipeline" in text


def test_routing_total_sales_region_wise(tmp_path):
    """Test 1: 'Total sales region-wise batao' -> DuckDB skill selected and primary."""
    csv_file = _create_test_csv(tmp_path / "sales.csv")
    files_map = {csv_file.id: csv_file}
    route = SkillRegistry.route("Total sales region-wise batao", files_map)

    assert "data-analysis-with-duckdb" in route["skills"]
    assert route["skills"][0] == "data-analysis-with-duckdb"
    assert any("analytical SQL" in r for r in route["reasons"])


def test_routing_top_5_customers_by_revenue(tmp_path):
    """Test 2: 'Top 5 customers by revenue' -> DuckDB skill selected and primary."""
    csv_file = _create_test_csv(tmp_path / "customers.csv")
    files_map = {csv_file.id: csv_file}
    route = SkillRegistry.route("Top 5 customers by revenue", files_map)

    assert "data-analysis-with-duckdb" in route["skills"]
    assert route["skills"][0] == "data-analysis-with-duckdb"


def test_routing_compare_employees_and_payroll(tmp_path):
    """Test 3: 'Compare employees file and payroll file' -> DuckDB + multi-file join capability."""
    emp_file = _create_test_csv(tmp_path / "employees.csv")
    pay_file = _create_test_csv(tmp_path / "payroll.csv")
    files_map = {emp_file.id: emp_file, pay_file.id: pay_file}
    route = SkillRegistry.route("Compare employees file and payroll file", files_map)

    assert "data-analysis-with-duckdb" in route["skills"]
    assert "schema-mapper" in route["skills"]
    assert "metric-reconciliation" in route["skills"]


def test_routing_company_policy_pure_qa(tmp_path):
    """Test 4: 'Company policy kya kehti hai?' -> DuckDB skill should NOT be primary skill."""
    csv_file = _create_test_csv(tmp_path / "policy_doc.csv")
    files_map = {csv_file.id: csv_file}
    route = SkillRegistry.route("Company policy kya kehti hai?", files_map)

    # For pure policy Q&A, duckdb should NOT be the primary skill
    assert route["skills"] == [] or route["skills"][0] != "data-analysis-with-duckdb"


def test_large_csv_plan_native_scan(tmp_path):
    """Test 5: Large CSV analytical plan uses native DuckDB scan without pandas bloat."""
    csv_path = tmp_path / "large_orders.csv"
    csv_file = _create_test_csv(csv_path)
    files_map = {csv_file.id: csv_file}
    file_paths_map = {csv_file.id: str(csv_path)}

    plan = AnalysisPlan(
        question="Total revenue by region",
        datasets=[DatasetRef(file_id=csv_file.id, alias="ds_1")],
        group_by=["region"],
        aggregations=[AggregateOperation(column="revenue", function="sum", alias="total_rev")],
        sort=[SortRule(column="total_rev", ascending=False)],
    )

    validated = PlanValidator.validate_plan(plan, files_map)
    result = DuckDBEngine.execute(validated, files_map, file_paths_map)

    assert result["engine"] == "duckdb"
    assert result["row_count"] == 4  # North, South, East, West (4 regions)
    assert "total_rev" in result["columns"]
    assert result["recompute"]["total_rev"] == 8800.0


def test_native_parquet_columnar_scan(tmp_path):
    """Test: Parquet file profiling and direct DuckDB native columnar scan."""
    parquet_path = tmp_path / "flights.parquet"
    parquet_file = _create_test_parquet(parquet_path)
    files_map = {parquet_file.id: parquet_file}
    file_paths_map = {parquet_file.id: str(parquet_path)}

    assert parquet_file.schema_profile["row_count"] == 6
    assert any(c["name"] == "airline" for c in parquet_file.schema_profile["columns"])

    plan = AnalysisPlan(
        question="Total bookings by airline",
        datasets=[DatasetRef(file_id=parquet_file.id, alias="ds_1")],
        group_by=["airline"],
        aggregations=[
            AggregateOperation(column="bookings", function="sum", alias="total_bookings"),
            AggregateOperation(column="flight_id", function="count", alias="flights_count"),
        ],
        sort=[SortRule(column="total_bookings", ascending=False)],
    )

    validated = PlanValidator.validate_plan(plan, files_map)
    result = DuckDBEngine.execute(validated, files_map, file_paths_map)

    assert result["engine"] == "duckdb"
    assert result["row_count"] == 3
    # Delta (50+45+60 = 155), United (30+25 = 55), Southwest (40)
    top_row = result["rows"][0]
    assert top_row["airline"] == "Delta"
    assert top_row["total_bookings"] == 155


def test_count_distinct_and_conditional_aggregation(tmp_path):
    """Test: COUNT DISTINCT and conditional aggregation with FILTER clause."""
    csv_path = tmp_path / "orders.csv"
    csv_file = _create_test_csv(csv_path)
    files_map = {csv_file.id: csv_file}
    file_paths_map = {csv_file.id: str(csv_path)}

    plan = AnalysisPlan(
        question="Unique customers and completed orders by region",
        datasets=[DatasetRef(file_id=csv_file.id, alias="ds_1")],
        group_by=["region"],
        aggregations=[
            AggregateOperation(column="customer", function="count_distinct", alias="unique_customers"),
            AggregateOperation(
                column="revenue",
                function="sum",
                alias="completed_revenue",
                filter_condition=Condition(column="status", operator="equals", value="Completed"),
            ),
        ],
        sort=[SortRule(column="unique_customers", ascending=False)],
    )

    validated = PlanValidator.validate_plan(plan, files_map)
    sql, params = QueryCompiler.compile(validated)
    assert "COUNT(DISTINCT" in sql
    assert "FILTER (WHERE" in sql

    result = DuckDBEngine.execute(validated, files_map, file_paths_map)
    assert result["row_count"] > 0
    # Verification gate V3 arithmetic check should pass
    verification = ResultVerifier.verify(validated, result, files_map)
    assert verification["passed"] is True


def test_having_clause_and_anti_join(tmp_path):
    """Test: HAVING clause and ANTI JOIN support."""
    # 1. HAVING clause
    csv_path = tmp_path / "sales.csv"
    csv_file = _create_test_csv(csv_path)
    files_map = {csv_file.id: csv_file}
    file_paths_map = {csv_file.id: str(csv_path)}

    plan = AnalysisPlan(
        question="Regions with total revenue greater than 2000",
        datasets=[DatasetRef(file_id=csv_file.id, alias="ds_1")],
        group_by=["region"],
        aggregations=[AggregateOperation(column="revenue", function="sum", alias="total_rev")],
        having=[Condition(column="total_rev", operator="greater_than", value=2000)],
    )

    validated = PlanValidator.validate_plan(plan, files_map)
    sql, params = QueryCompiler.compile(validated)
    assert "HAVING \"total_rev\" > ?" in sql

    result = DuckDBEngine.execute(validated, files_map, file_paths_map)
    # North=2500, South=2500, East=3000, West=800 -> West excluded
    regions = [r["region"] for r in result["rows"]]
    assert "West" not in regions
    assert len(regions) == 3

    # 2. ANTI JOIN
    p1 = tmp_path / "master.csv"
    p1.write_text("id,name\n1,Alice\n2,Bob\n3,Charlie\n", encoding="utf-8")
    f1 = StoredFile(id="f1", owner_user_id="u1", original_name="master.csv", content_type="text/csv", size_bytes=50, storage_key="m.csv", schema_profile=DataProfiler.profile_file(str(p1), p1.name))

    p2 = tmp_path / "payroll.csv"
    p2.write_text("id,salary\n1,5000\n3,6000\n", encoding="utf-8")
    f2 = StoredFile(id="f2", owner_user_id="u1", original_name="payroll.csv", content_type="text/csv", size_bytes=40, storage_key="p.csv", schema_profile=DataProfiler.profile_file(str(p2), p2.name))

    join_plan = AnalysisPlan(
        question="Missing employees from payroll",
        datasets=[DatasetRef(file_id="f1", alias="ds_1"), DatasetRef(file_id="f2", alias="ds_2")],
        joins=[JoinRule(left_dataset="ds_1", right_dataset="ds_2", left_column="id", right_column="id", join_type="anti")],
    )

    j_val = PlanValidator.validate_plan(join_plan, {"f1": f1, "f2": f2})
    j_res = DuckDBEngine.execute(j_val, {"f1": f1, "f2": f2}, {"f1": str(p1), "f2": str(p2)})
    assert j_res["row_count"] == 1
    assert j_res["rows"][0]["id"] == 2  # Bob is missing from payroll!


def test_unsupported_operation_does_not_bypass_validator(tmp_path):
    """Test 6: Unsupported operations & SQL injections are rejected by validator and sanitizer."""
    csv_path = tmp_path / "data.csv"
    csv_file = _create_test_csv(csv_path)
    files_map = {csv_file.id: csv_file}
    file_paths_map = {csv_file.id: str(csv_path)}

    # A) Unsupported aggregate function
    bad_plan = AnalysisPlan(
        question="Invalid aggregate",
        datasets=[DatasetRef(file_id=csv_file.id, alias="ds_1")],
        aggregations=[AggregateOperation(column="revenue", function="UNSUPPORTED_UDF_AGG")],
    )
    with pytest.raises(PlanValidationError):
        PlanValidator.validate_plan(bad_plan, files_map)

    # B) Unsupported filter operator
    bad_filter_plan = AnalysisPlan(
        question="Invalid operator",
        datasets=[DatasetRef(file_id=csv_file.id, alias="ds_1")],
        filters=[Condition(column="revenue", operator="REGEXP_MATCH", value=".*")],
    )
    with pytest.raises(PlanValidationError):
        PlanValidator.validate_plan(bad_filter_plan, files_map)

    # C) Attempted arbitrary SQL injection with forbidden keywords
    injection_plan = AnalysisPlan(
        question="Malicious SQL query",
        datasets=[DatasetRef(file_id=csv_file.id, alias="ds_1")],
        sql_query="ATTACH 'malicious.db' AS ext; SELECT * FROM ext.secrets;",
    )
    with pytest.raises(PlanValidationError):
        PlanValidator.validate_plan(injection_plan, files_map)

    # D) Attempted DDL statement
    ddl_plan = AnalysisPlan(
        question="Drop table attack",
        datasets=[DatasetRef(file_id=csv_file.id, alias="ds_1")],
        sql_query="DROP TABLE \"ds_1\";",
    )
    with pytest.raises(PlanValidationError):
        PlanValidator.validate_plan(ddl_plan, files_map)

    # E) Attempted unauthorized table access outside allowed aliases
    unauth_plan = AnalysisPlan(
        question="Unauthorized table read",
        datasets=[DatasetRef(file_id=csv_file.id, alias="ds_1")],
        sql_query="SELECT * FROM secret_system_passwords",
    )
    with pytest.raises(PlanValidationError):
        PlanValidator.validate_plan(unauth_plan, files_map)
