import json
import pytest
from app.ai.learning.semantic_mapping import SemanticMapper
from app.ai.learning.example_retrieval import ExampleRetriever
from app.ai.learning.feedback_service import FeedbackService, FeedbackSubmission

def test_semantic_mapper_hinglish_dlp():
    cols = ["Source", "Destination", "Policies", "Transaction Size (KB)", "Action", "Severity"]
    res = SemanticMapper.resolve_semantics("Bahar sabse zyada data kisne bheja?", cols)
    
    assert "entity" in res.mapped_columns
    assert res.mapped_columns["entity"] == "Source"
    assert "data_size" in res.mapped_columns
    assert res.mapped_columns["data_size"] == "Transaction Size (KB)"
    assert res.suggested_sort is not None
    assert res.suggested_sort["ascending"] is False

def test_semantic_mapper_finance():
    cols = ["Country", "Product", "Units Sold", "Sales", "Profit", "Date"]
    res = SemanticMapper.resolve_semantics("Which country generated the highest profit?", cols)
    
    assert "profit" in res.mapped_columns
    assert res.mapped_columns["profit"] == "Profit"
    assert any(a["column"] == "Profit" for a in res.suggested_aggregates)
    assert res.suggested_sort is not None
    assert res.suggested_sort["column"] in {a["alias"] for a in res.suggested_aggregates}


def test_semantic_mapper_finance_column_order_invariance():
    cols = ["Profit", "Country", "Product", "Units Sold", "Sales", "Date"]
    res = SemanticMapper.resolve_semantics("Which country generated the highest profit?", cols)

    assert res.suggested_group_by == ["Country"]
    assert res.mapped_columns["dimension"] == "Country"
    assert res.mapped_columns["measure"] == "Profit"
    assert res.mapped_columns["profit"] == "Profit"
    assert res.suggested_aggregates == [{"function": "sum", "column": "Profit", "alias": "total_profit"}]
    assert res.suggested_sort == {"column": "total_profit", "ascending": False, "limit": 1}


def test_semantic_mapper_ignores_temporal_column_as_dimension_without_profile():
    cols = ["Date", "Country", "Profit"]
    res = SemanticMapper.resolve_semantics("Which country generated the highest profit to date?", cols)

    assert res.suggested_group_by == ["Country"]
    assert res.mapped_columns["dimension"] == "Country"


def test_semantic_mapper_ranking_bottom():
    cols = ["Country", "Product", "Units Sold", "Sales", "Profit", "Date"]
    res1 = SemanticMapper.resolve_semantics("Which product generated the lowest profit?", cols)
    assert res1.intent == "top_n"
    assert res1.suggested_group_by == ["Product"]
    assert res1.mapped_columns["profit"] == "Profit"
    assert res1.suggested_sort is not None
    assert res1.suggested_sort["ascending"] is True
    assert res1.suggested_sort["limit"] == 1
    assert res1.suggested_sort["column"] in {a["alias"] for a in res1.suggested_aggregates}

    res2 = SemanticMapper.resolve_semantics("Sabse kam sales kis country me hai?", cols)
    assert res2.suggested_group_by == ["Country"]
    assert res2.mapped_columns["sales"] == "Sales"
    assert res2.suggested_sort is not None
    assert res2.suggested_sort["ascending"] is True
    assert res2.suggested_sort["limit"] == 1


def test_semantic_mapper_avg_vs_sum_and_non_monetary_measure():
    cols = ["Country", "Product", "Units Sold", "Sales", "Profit", "Date"]
    res_avg = SemanticMapper.resolve_semantics("Which country generated the highest average profit?", cols)
    assert res_avg.suggested_aggregates[0]["function"] == "avg"
    assert res_avg.suggested_aggregates[0]["column"] == "Profit"
    assert res_avg.suggested_sort is not None
    assert res_avg.suggested_sort["column"] == res_avg.suggested_aggregates[0]["alias"]

    res_wise = SemanticMapper.resolve_semantics("Country wise average sales", cols)
    assert res_wise.intent == "grouped_distribution"
    assert res_wise.suggested_group_by == ["Country"]
    assert res_wise.mapped_columns["sales"] == "Sales"
    assert res_wise.suggested_aggregates[0]["function"] == "avg"
    assert res_wise.suggested_aggregates[0]["column"] == "Sales"

    reordered_cols = ["Units Sold", "Country", "Product", "Sales", "Profit", "Date"]
    res_units = SemanticMapper.resolve_semantics("Which country had the highest units sold?", reordered_cols)
    assert res_units.suggested_group_by == ["Country"]
    assert res_units.mapped_columns["units sold"] == "Units Sold"
    assert res_units.suggested_aggregates[0]["function"] == "sum"
    assert res_units.suggested_aggregates[0]["column"] == "Units Sold"

def test_semantic_mapper_retail_hindi():
    cols = ["InvoiceNo", "StockCode", "Description", "Quantity", "UnitPrice", "CustomerID", "Country"]
    res = SemanticMapper.resolve_semantics("Top 10 products by revenue batao", cols)
    
    assert res.suggested_sort is not None
    assert res.suggested_sort["limit"] == 10

    # Even when Product and Revenue exist as explicit columns, "by revenue" specifies the ranking metric
    res_direct = SemanticMapper.resolve_semantics("Top 10 products by revenue batao", ["Product", "Revenue"])
    assert res_direct.intent == "top_n"
    assert res_direct.suggested_group_by == ["Product"]
    assert res_direct.suggested_sort == {"column": "total_revenue", "ascending": False, "limit": 10}
    assert res_direct.limit == 10


def test_semantic_mapper_exact_dim_precedence_over_measure_subtoken():
    cols = ["Unit", "Country", "Units Sold", "Profit"]
    res_country = SemanticMapper.resolve_semantics("Which country had the highest units sold?", cols)
    assert res_country.suggested_group_by == ["Country"]
    assert res_country.mapped_columns["dimension"] == "Country"
    assert res_country.mapped_columns["measure"] == "Units Sold"

    profile = {
        "columns": [
            {"name": "Unit", "role": "dimension", "inferred_type": "string"},
            {"name": "Country", "role": "dimension", "inferred_type": "string"},
            {"name": "Units Sold", "role": "measure", "inferred_type": "integer"},
            {"name": "Profit", "role": "measure", "inferred_type": "float"},
        ]
    }
    res_country_prof = SemanticMapper.resolve_semantics("Which country had the highest units sold?", cols, profile)
    assert res_country_prof.suggested_group_by == ["Country"]
    assert res_country_prof.mapped_columns["dimension"] == "Country"

    res_unit = SemanticMapper.resolve_semantics("Which unit had the highest profit?", cols)
    assert res_unit.suggested_group_by == ["Unit"]
    assert res_unit.mapped_columns["dimension"] == "Unit"
    assert res_unit.mapped_columns["measure"] == "Profit"


def test_semantic_mapper_generic_grouped_by_per_har_and_ausat():
    cols_dpcp = ["Date", "Profit", "Country", "Product"]
    res_har_prod = SemanticMapper.resolve_semantics("Har product ka profit dikhao", cols_dpcp)
    assert res_har_prod.intent == "grouped_distribution"
    assert res_har_prod.result_shape == "grouped_rows"
    assert res_har_prod.suggested_group_by == ["Product"]
    assert res_har_prod.suggested_aggregates == [{"function": "sum", "column": "Profit", "alias": "total_profit"}]

    res_by_prod = SemanticMapper.resolve_semantics("Profit by product", ["Country", "Product", "Profit", "Sales"])
    assert res_by_prod.intent == "grouped_distribution"
    assert res_by_prod.result_shape == "grouped_rows"
    assert res_by_prod.suggested_group_by == ["Product"]
    assert res_by_prod.suggested_aggregates[0]["column"] == "Profit"

    res_ausat = SemanticMapper.resolve_semantics("Har country ka ausat profit dikhao", cols_dpcp)
    assert res_ausat.intent == "grouped_distribution"
    assert res_ausat.result_shape == "grouped_rows"
    assert res_ausat.suggested_group_by == ["Country"]
    assert res_ausat.suggested_aggregates == [{"function": "avg", "column": "Profit", "alias": "avg_profit"}]
    assert res_ausat.target_concept == "avg_profit"


def test_semantic_mapper_per_dimension_counts():
    cols = ["Profit", "Country", "Product", "Sales"]
    for q, expected_dim in [
        ("How many orders per country?", "Country"),
        ("How many orders per product?", "Product"),
    ]:
        res = SemanticMapper.resolve_semantics(q, cols)
        assert res.intent == "grouped_distribution"
        assert res.result_shape == "grouped_rows"
        assert res.suggested_group_by == [expected_dim]
        assert res.suggested_aggregates[0]["function"] == "count"


def test_semantic_mapper_multiword_dimension_and_combined_ranking_breakdown():
    res_region = SemanticMapper.resolve_semantics("Which sales region had the highest profit?", ["Sales Region", "Profit"])
    assert res_region.intent == "top_n"
    assert res_region.result_shape == "ranked_rows"
    assert res_region.suggested_group_by == ["Sales Region"]
    assert res_region.suggested_aggregates == [{"function": "sum", "column": "Profit", "alias": "total_profit"}]

    res_bottom = SemanticMapper.resolve_semantics("Country wise bottom 3 profit", ["Country", "Product", "Profit", "Sales"])
    assert res_bottom.intent == "top_n"
    assert res_bottom.suggested_group_by == ["Country"]
    assert res_bottom.suggested_sort == {"column": "total_profit", "ascending": True, "limit": 3}
    assert res_bottom.limit == 3


def test_semantic_mapper_does_not_treat_candidate_as_temporal():
    res = SemanticMapper.resolve_semantics("Which candidate received the highest score?", ["Candidate", "Score"])
    assert res.intent == "top_n"
    assert res.suggested_group_by == ["Candidate"]
    assert res.mapped_columns["dimension"] == "Candidate"
    assert res.mapped_columns["score"] == "Score"
    assert res.suggested_aggregates == [{"function": "sum", "column": "Score", "alias": "total_score"}]

    # Integer-typed temporal column lacking explicit role must still not be treated as a measure
    partial_profile = {
        "columns": [
            {"name": "OrderDate", "inferred_type": "integer"},
            {"name": "Region", "inferred_type": "string"},
            {"name": "Profit", "inferred_type": "float"},
        ]
    }
    res_date = SemanticMapper.resolve_semantics("Which region had the highest order date profit?", ["OrderDate", "Region", "Profit"], partial_profile)
    assert res_date.suggested_group_by == ["Region"]
    assert res_date.suggested_aggregates[0]["column"] == "Profit"


def test_semantic_mapper_r2_regression_probes():
    # 1-3: Unprofiled multi-word dimension ("Cost Center") must resolve as dimension, not measure
    res1 = SemanticMapper.resolve_semantics("Which cost center had the highest profit?", ["Cost Center", "Profit"])
    assert res1.intent == "top_n"
    assert res1.suggested_group_by == ["Cost Center"]
    assert res1.suggested_aggregates[0]["column"] == "Profit"

    res2 = SemanticMapper.resolve_semantics("Amount by cost center", ["Cost Center", "Amount"])
    assert res2.intent == "grouped_distribution"
    assert res2.suggested_group_by == ["Cost Center"]
    assert res2.suggested_aggregates[0]["column"] == "Amount"

    res3 = SemanticMapper.resolve_semantics("How many orders per cost center?", ["Cost Center", "Amount"])
    assert res3.intent == "grouped_distribution"
    assert res3.suggested_group_by == ["Cost Center"]
    assert res3.suggested_aggregates[0]["function"] == "count"

    # 4-5: Pluralized full column names must beat earlier compound columns
    res4 = SemanticMapper.resolve_semantics("Profit by categories", ["SubCategory", "Category", "Profit"])
    assert res4.suggested_group_by == ["Category"]

    res5 = SemanticMapper.resolve_semantics("How many orders per cities?", ["Home City", "City", "Amount"])
    assert res5.suggested_group_by == ["City"]

    # 6: Longest-first measure matching ("Gross Profit" over "Profit")
    res6 = SemanticMapper.resolve_semantics("Which country had the highest gross profit?", ["Profit", "Gross Profit", "Country"])
    assert res6.suggested_aggregates[0]["column"] == "Gross Profit"

    # 7: -y/-ies plural morphology in measure matching ("salaries" -> "Salary")
    res7 = SemanticMapper.resolve_semantics("Which department had the highest salaries?", ["Department", "Salary"])
    assert res7.suggested_aggregates[0]["column"] == "Salary"

    # 8: Sibilant -es plural morphology in dimension matching ("branches" -> "Branch")
    res8 = SemanticMapper.resolve_semantics("How many orders per branches?", ["Branch", "Amount"])
    assert res8.suggested_group_by == ["Branch"]

def test_example_retriever_load_and_retrieve():
    examples = ExampleRetriever.load_examples()
    assert len(examples) >= 300, f"Expected at least 300 examples, found {len(examples)}"
    
    retrieved = ExampleRetriever.retrieve(
        question="Bahar sabse zyada data kisne bheja?",
        columns=["src", "dest", "size_kb"],
        user_unit_id="default_unit",
        user_role="employee",
        top_k=2
    )
    assert len(retrieved) > 0
    prompt_str = ExampleRetriever.format_for_prompt(retrieved)
    assert "REUSABLE ANALYTICAL EXAMPLES" in prompt_str
    assert "Question:" in prompt_str

def test_example_retriever_tenant_isolation():
    # If example has unit_id and is private_tenant, unauthorized user cannot access
    retrieved = ExampleRetriever.retrieve(
        question="test private query",
        columns=["col1"],
        user_unit_id="unit_b",
        user_role="employee"
    )
    for ex in retrieved:
        if ex.get("source_type") == "private_tenant":
            assert ex.get("unit_id") == "unit_b"

def test_feedback_service_verification_and_promotion(tmp_path, monkeypatch):
    # Isolation guard: promotion must write to a temporary corpus, never the tracked one.
    isolated_golden = tmp_path / "golden_examples_isolated.json"
    isolated_golden.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("GOLDEN_EXAMPLES_PATH", str(isolated_golden))

    # Create small CSV for verification test
    test_csv = tmp_path / "test.csv"
    test_csv.write_text("id,val\n1,100\n2,200\n")

    sub = FeedbackSubmission(
        analysis_id="an_test1",
        user_id="user_admin",
        unit_id="unit_1",
        user_role="unit_admin",
        question="Total value kitna hai?",
        category="incorrect_calculation",
        comment="Needs sum of val",
        correction_sql="SELECT SUM(val) as total FROM dataset",
        dataset_path=str(test_csv)
    )

    rec = FeedbackService.record_feedback(sub)
    assert rec.verification_status == "verified"
    assert rec.verified_rows == [{"total": 300}]
    # A unit_admin correction is promoted, but only into the isolated corpus
    promoted = json.loads(isolated_golden.read_text(encoding="utf-8"))
    assert [ex["example_id"] for ex in promoted] == [f"ex-fb-{rec.feedback_id}"]
