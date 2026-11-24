import os
import json
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GOLDEN_FILE = os.path.join(BASE_DIR, "data", "benchmark", "golden", "golden_examples_300.json")

def validate_golden_benchmark():
    if not os.path.exists(GOLDEN_FILE):
        print(f"[-] Benchmark file not found: {GOLDEN_FILE}")
        sys.exit(1)

    with open(GOLDEN_FILE, "r", encoding="utf-8") as f:
        examples = json.load(f)

    print(f"[*] Validating {len(examples)} Golden Examples against Section 7 Schema...")
    
    required_keys = [
        "example_id", "dataset_id", "dataset_checksum", "question",
        "language", "intent", "semantic_target", "column_mapping",
        "sql_query", "expected_plan", "expected_answer", "verification",
        "source_type", "approval_status", "split"
    ]

    invalid_count = 0
    for idx, ex in enumerate(examples, start=1):
        for k in required_keys:
            if k not in ex:
                print(f"[-] Ex {idx} ({ex.get('example_id')}) missing key: {k}")
                invalid_count += 1
        if not ex.get("sql_query"):
            print(f"[-] Ex {idx} missing sql_query")
            invalid_count += 1
        if not ex.get("expected_answer") or ex["expected_answer"].get("row_count") is None:
            print(f"[-] Ex {idx} missing expected_answer row_count")
            invalid_count += 1
        if ex.get("verification", {}).get("status") != "verified":
            print(f"[-] Ex {idx} verification status is not 'verified'")
            invalid_count += 1

    if invalid_count == 0:
        print(f"[+] All {len(examples)} Golden Examples passed 100% schema & verification validation!")
    else:
        print(f"[-] Found {invalid_count} validation errors!")
        sys.exit(1)

if __name__ == "__main__":
    validate_golden_benchmark()
