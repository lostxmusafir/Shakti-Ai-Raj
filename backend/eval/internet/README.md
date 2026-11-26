# Blind public-internet dataset evaluation

This package scores the Universal AI Analyst against **30 independently published
datasets** and **180 natural-language questions**, without adding any
dataset-specific production code.

The corpus is *blind*: the questions live in `questions.json`, the answers in a
separate sealed `ground_truth.json`, and nothing is inserted into the golden /
retrieval store before scoring.

## What is measured

* 30 datasets from NYC TLC, UCI, OpenML, World Bank and municipal open-data
  portals, sampled deterministically (reservoir sample, seed 42) and recorded in
  `data/benchmark/internet/manifest.json` with SHA-256, license and row counts.
* 150 single-turn questions plus 10 multi-turn conversations (30 follow-up
  turns), in English, Hinglish, Hindi (Devanagari), shorthand and with typos.
* 10 scoring dimensions per question: intent, schema mapping, filters,
  aggregation, result shape, SQL execution, numerical correctness, semantic
  verification, answer relevance, human readability.
* A fixed failure taxonomy including `NULL_SEMANTICS_ERROR`,
  `AMBIGUOUS_BUT_NOT_CLARIFIED`, `FOLLOWUP_CONTEXT_ERROR` and
  `FALSE_VERIFICATION_PASS`.

## Reproduce

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cd backend

# 1. download + deterministically sample the 30 sources (network required)
../.venv/bin/python -m eval.internet.acquire --force

# 2. compute the sealed answer key with DuckDB
../.venv/bin/python -m eval.internet.ground_truth

# 3. cross-check difficult / null-sensitive answers with Pandas
../.venv/bin/python -m eval.internet.independent

# 4. run the blind evaluation
../.venv/bin/python -m eval.internet.runner --mode planner
../.venv/bin/python -m eval.internet.runner --mode reference

# 5. render the Markdown report
../.venv/bin/python -m eval.internet.report
```

Results are written to `data/benchmark/internet/blind_run_<mode>.json` and the
report to `data/benchmark/reports/internet_blind_eval.md`.

## Modes

| Mode | What it runs | What it proves |
|---|---|---|
| `planner` | The production orchestrator: profiling → planning (LLM, else keyword fallback) → `PlanValidator` → `DuckDBEngine` → `ResultVerifier` → answer formatter. | End-to-end generalisation of the planner under test. |
| `reference` | Hand-written ground-truth SQL executed through the production `DuckDBEngine`, sanitizer and `ResultVerifier`. | Whether the deterministic execution + verification layer is portable to unseen schemas. This is **not** an NLU measurement. |

`planner` mode uses whatever provider is configured. With no credentials the
product falls back to its deterministic keyword planner; the run records that
fact and never reports LLM results it did not obtain.

## Blind-set rules

1. `questions.json` contains questions only — no SQL, aliases or expected values.
2. `ground_truth.json` is never loaded into a prompt or the retrieval store.
3. No question, answer or alias is written to `data/benchmark/golden/`.
4. Expected answers are computed by DuckDB from hand-written SQL, and a second
   engine (Pandas) recomputes 31 of them independently.
5. `production_code_changed_for_dataset` is recorded as `false`; the package only
   adds evaluation code.
6. Sampling is reproducible: published URL + SHA-256 + seed 42 + method string.

## Known limitations

* No model credentials exist in the evaluation VM, so `planner` mode reflects the
  deterministic keyword fallback, not the LLM planner.
* The production `SQLSanitizer` rejects CTE references it cannot resolve to a
  dataset alias, so `WITH ... AS` reference queries fail in `reference` mode.
  This is a property of the system, not of the corpus.
* Scoring of intent/filters/readability is rule-based and deliberately
  conservative; it is reported per dimension rather than collapsed into one
  accuracy number.
