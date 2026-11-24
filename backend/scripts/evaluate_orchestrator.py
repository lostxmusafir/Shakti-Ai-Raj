import os
import sys
import json

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai.learning.evaluation_service import evaluation_service

def main():
    print("=" * 60)
    print("UNIVERSAL AI ANALYST — OFFLINE ORCHESTRATOR EVALUATION")
    print("=" * 60)
    
    # Run evaluation on held-out test split (93 examples)
    results = evaluation_service.evaluate(split="test")
    
    print(f"\nEvaluation Split: {results.get('evaluation_split')}")
    print(f"Total Evaluated Test Cases: {results.get('total_evaluated')}")
    print(f"Intent Classification Accuracy: {results.get('intent_accuracy')}%")
    print(f"Column Mapping Accuracy: {results.get('column_mapping_accuracy')}%")
    print(f"Execution Success Rate: {results.get('execution_success_rate')}%")
    print(f"Deterministic Numerical Accuracy: {results.get('numerical_accuracy')}%")
    print(f"Execution Latency P50: {results.get('latency_p50_ms')} ms")
    print(f"Execution Latency P95: {results.get('latency_p95_ms')} ms")
    print(f"Total Failures: {results.get('failures_count')}")

    out_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "benchmark", "reports", "evaluation_report.json"))
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nDetailed evaluation report saved to: {out_file}")
    print("=" * 60)

if __name__ == "__main__":
    main()
