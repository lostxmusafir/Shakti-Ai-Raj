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

def test_semantic_mapper_retail_hindi():
    cols = ["InvoiceNo", "StockCode", "Description", "Quantity", "UnitPrice", "CustomerID", "Country"]
    res = SemanticMapper.resolve_semantics("Top 10 products by revenue batao", cols)
    
    assert res.suggested_sort is not None
    assert res.suggested_sort["limit"] == 10

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

def test_feedback_service_verification_and_promotion(tmp_path):
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
