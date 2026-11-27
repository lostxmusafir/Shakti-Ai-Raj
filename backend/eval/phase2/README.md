# Phase 2 curated benchmark slice

This directory is benchmark-only. It is not imported by the production planner and does not train model weights.

The slice contains 12 base questions expanded into 48 language and shorthand variants over finance, DLP incidents, and HR/payroll. The question file contains plan-shape expectations but no SQL or answer values. The answer key is separate and is executed independently with DuckDB by `run.py`.

The separate HITL corpus contains four ambiguity cases. It verifies that the workflow asks for a binding or clarification instead of returning an unverified guess.

Run from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe backend/eval/phase2/run.py
.\backend\.venv\Scripts\python.exe backend/eval/phase2/run_interactions.py
.\backend\.venv\Scripts\python.exe backend/eval/phase2/audit_phase2.py
```

The runner reads only existing local benchmark files, reports every result, and exits non-zero on a missing file, SQL failure, row-shape mismatch, or result mismatch.

The production fallback evaluation is run separately:

```powershell
.\backend\.venv\Scripts\python.exe backend/eval/phase2/run_production.py
```

The current curation baseline is 48/48 for independent DuckDB ground truth, 4/4 for HITL safety, and 36/48 for the unchanged deterministic production planner. The 12 planner misses remain visible in `phase3_production_planner_report.json`; they are not patched or promoted during this benchmark-only phase.

This slice must not be copied into production retrieval until it passes held-out evaluation and leakage review.
