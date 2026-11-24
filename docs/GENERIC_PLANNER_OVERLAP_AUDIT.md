# Generic Planner — Overlap Audit and Integration Decision

**Decision: `generic_planner.py` stays on `test-raj` as a *narrowed* second planner.**

It does not get a parallel expanded plan contract, and it does not replace the existing
orchestrator. It is adapted to the plan contract the executor can already run, and grows feature by
feature only when a consumer can execute the new features.

This document supersedes step 1 of `docs/GENERIC_PLANNER_INTEGRATION_STATUS.md` §9
("add `DateGroup`, `DerivedMetric`, …"). That step is **withdrawn** — see §4.

---

## 1. What `main` already has

| Layer | File | Role |
| --- | --- | --- |
| LLM planning | `ai/orchestration/orchestrator.py` (`_plan_with_ai`) | prompt-driven plan construction, schema in prompt |
| Deterministic fallback | `ai/orchestration/orchestrator.py` (`_plan_fallback`) | keyword planner, called at two sites |
| Semantic mapping | `ai/learning/semantic_mapping.py` (`SemanticMapper`) | EN/HI/Hinglish concept → column mapping |
| Plan contract | `ai/planning/schemas.py` | `AnalysisPlan`, `Condition`, `AggregateOperation`, `SortRule`, `JoinRule`, `DatasetRef` |
| Validation | `ai/planning/validator.py` (`PlanValidator`) | column existence, operator/aggregate allowlist |
| Compilation | `analysis/execution/compiler.py` (`QueryCompiler`) | plan → parameterized DuckDB SQL |
| Execution | `analysis/execution/duckdb_engine.py` | runs SQL |

`SemanticMapper` is consumed in two ways: as **prompt context** (`_learning_context`, line ~145) and
as **plan material** inside `_plan_fallback` (line ~442). Only the second one shapes the plan.

## 2. What the planner brings that `main` lacks

| Capability | `SemanticMapper` | `generic_planner.SchemaView` |
| --- | --- | --- |
| Column resolution | hardcoded candidate name lists (`"src"`, `"is_ext"`, `"size_kb"`, …) | derived from `schema_profile`: name tokens, dtype, cardinality, observed values |
| Role classification | none | identifier / time / flag / measure / dimension / text / constant |
| Value resolution | `_profiled_value` for one hardcoded case | fuzzy match against observed `top_values` for any column |
| Typo tolerance | none | `_repair_tokens` fuzzy repair with a threshold |
| Question parsing | sentence-level keyword `in` tests | 16 ordered regex rules with EN/Hinglish/Roman-Hindi lexicon |
| Dataset assumptions | several: DLP/finance/retail column names | none |

So the planner's *genuine* value is **schema grounding** — it is the only component in the repo that
derives column roles and resolves values from the profile instead of from hardcoded names. That is
worth keeping and worth eventually reusing.

## 3. What makes a full second planner unsafe today

### 3.1 Its plan contract has no executor

`build_plan` emits `derived_metrics`, `having`, `rank`, `date_group`, `clarification`, `confidence`,
`assumptions`, and `AggregateOperation.filter`. `PlanValidator` and `QueryCompiler` implement none of
them:

- `PlanValidator.SUPPORTED_AGGREGATES = {count, sum, avg, min, max, median}`
- `QueryCompiler.compile` handles exactly `FROM/JOIN`, `SELECT` of `group_by` + aggregates, `WHERE`,
  `GROUP BY`, `ORDER BY`, `LIMIT`

Adding the six missing schema pieces therefore converts an import failure into a **validation
failure or invalid SQL**, not into working software. This is why "add the classes so the import
passes" is the wrong first move: it makes the module importable while still producing plans the
pipeline rejects, and it edits `main`'s contract for an experiment.

### 3.2 Its aggregate vocabulary is already wider than the executor's

`count_distinct` (distinct rule, ratio denominator) and the ratio/percentage aliases are not in the
validator's allowlist, and the compiler would emit `COUNT_DISTINCT("x")`, which DuckDB does not
have. So *even the four rules that looked correct in the earlier probe* produce plans the pipeline
refuses. This is a defect the earlier status report did not capture.

### 3.3 Silent-loss risk on narrowing

`build_plan` must not drop `derived`/`having`/`rank`/`date_group` and return anyway: a percentage
question flattened to a bare count is exactly the "confident wrong answer" failure mode the status
document identifies as critical. Narrowing must therefore be **loud** (`UnsupportedPlanError`), not
lossy.

## 4. Decision

1. **No expansion of `AnalysisPlan`.** `DateGroup`, `DerivedMetric`, `HavingRule`, `RankSpec`,
   `AggregateOperation.filter`, and the extra `AnalysisPlan` fields are **not** added now. They are
   added only together with a validator + compiler implementation that executes them, one feature
   per commit, each with a test that runs on DuckDB.
2. **Planner adapts to the executor, not the reverse.** `build_plan` emits only
   filter / group / aggregate / sort / limit. Anything else raises `UnsupportedPlanError` carrying
   the reason and, where available, the clarification text.
3. **One executor addition is justified now:** `count_distinct`. It is required by the distinct rule,
   by the ratio denominator, and it is a generically useful aggregation. It is additive to
   `PlanValidator` and `QueryCompiler` and changes no existing behavior.
4. **No wiring.** The planner stays unreferenced by the orchestrator. `_plan_with_ai` and
   `_plan_fallback` remain the only plan sources. Wiring happens behind a flag after the rules and
   confidence are repaired and covered by tests.
5. **`SemanticMapper` and `_plan_fallback` are not modified.** They remain `main` behavior. Whether
   the planner eventually *replaces* `_plan_fallback` is a separate, later decision requiring the
   full gate run.
6. **Order of work:** contract → capture-group parsing → numeric filters → temporal → confidence →
   flag + wiring → blind evaluation.

## 5. Separate finding: `_plan_fallback` on `main` is dataset-rigged

While auditing call sites this was found in `backend/app/ai/orchestration/orchestrator.py`
(`_plan_fallback`, lines ~273–430), which is **identical on `main` and `test-raj`**:

- a branch keyed on `is_dlp` that detects a specific dataset by its column set
  (`destination`, `policies`, `source`, `transaction size (kb)`);
- keyword branches for specific benchmark questions (`"gmail"`, `"yahoo"`, `"cad"`, `"password"`,
  `"blocked incident"`, `"peak hour"`, `"critical severity"`, …);
- hand-written SQL strings over a view named `v`, referencing columns (`src`, `is_ext`, `gmail`,
  `yahoo`, `is_mixed`, `foreign_aff`, `hr`) that are not validated against the actual file;
- it is a **fast path**, not a last resort: line ~549 calls it before the AI planner whenever the
  DLP column set is present, and line ~611 calls it as the general fallback.

This contradicts this repository's own eligibility gate ("no dataset-specific production hacks: no
branching on a dataset name, file name, row count, or known question text"). It is recorded here as
a finding, **not** fixed in this change: it is existing `main` behavior, it is out of scope for the
planner repair, and changing it is a behavior change that needs its own verified decision.

A second, smaller finding: `SemanticMapper` can emit `{"function": "sum_product"}`, which
`_plan_fallback` copies into an `AggregateOperation`; `PlanValidator` then rejects it because
`sum_product` is not in `SUPPORTED_AGGREGATES`. That path is unreachable only because the retail
`revenue` branch requires `description`, `quantity` and `unitprice` together.

## 6. Why not dissolve the planner into `SemanticMapper`

Rejected for now, on three grounds:

- `SemanticMapper` is a *concept mapper with hardcoded column names*; folding schema-role
  classification into it changes the behavior of a component that already has passing tests and a
  live prompt-context role. That is a `main` behavior change, not an additive improvement.
- The role classification and fuzzy value resolution are the reusable parts, and they are already
  separable as `SchemaView`; keeping them in `planning/` means the eventual reuse is a one-line
  import rather than a refactor of `main`.
- Dissolving it now would delete the only deterministic, schema-derived planner in the repo before
  anything replaces it — a delete-to-fix, which the policy forbids.

If, after the parser and filters are repaired and evaluated blind, the planner still adds nothing
over `SemanticMapper` + orchestrator, the right move then is to extract `SchemaView` into
`planning/schema_view.py`, wire it into the existing flow, and drop the rest. That is a decision for
after evidence, not before.
