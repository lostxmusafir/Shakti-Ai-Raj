# Generic Planner — Integration Status

**Verdict: `TEST_RAJ_ONLY`. Not eligible for `main`. Integration prohibited until every gate below passes.**

This document is the authoritative record for the commit below. It supersedes the commit's own
message, which is treated as a historical artifact and is **not** trusted as a description of the
change or as an eligibility claim.

---

## 1. Subject commit

| Field | Value |
| --- | --- |
| Commit | `05a95088208864ea4b441eaaad72ab828d259eb3` |
| Branch | `test-raj` only (not present on `main`, `origin/main`, or `origin/test-raj`) |
| Tag in subject | `[CODE]` |
| Commit message | `[CODE] improve multilingual question understanding and schema mapping in QuestionEngine` |
| Files changed | 1 file, +924 / −0 |
| File | `backend/app/ai/planning/generic_planner.py` (new file) |
| Removes `main` code | No |
| Touches `main` files | No |
| Status | `TEST_RAJ_ONLY` |
| `MAIN_INTEGRATION_ELIGIBLE` | **No** |

**The commit message is wrong on two counts.** There is no `QuestionEngine` on `main` or anywhere
else in the tree, so nothing was "improved"; and the commit adds a single new module that cannot be
imported, is not referenced by any code path, and mis-plans several ordinary questions.

```bash
git grep "class QuestionEngine" main     # -> no output
git show --stat --oneline 05a9508        # -> generic_planner.py | 924 +++
```

The `[CODE]` tag is accurate only as a *category* label (it is production-shaped source, not
experimental data). It is not an eligibility claim, and per `AGENTS.md` §3 a `[CODE]` commit is
ineligible until all gates pass.

---

## 2. Import fails — the module has never executed

```bash
python -c "import app.ai.planning.generic_planner"
# ImportError: cannot import name 'DateGroup' from 'app.ai.planning.schemas'
```

Failure is import-time, not compile-time: `python -m py_compile` succeeds, so the file *looks*
healthy in CI. `backend/app/ai/planning/schemas.py` is byte-identical on `main` and `test-raj`
(`git diff main -- backend/app/ai/planning/schemas.py` is empty), so the mismatch is not a merge
artifact — the planner was added against schemas that do not exist in this repository.

### 2.1 Schema incompatibilities (7)

| # | Expected by `generic_planner.py` | Present in `schemas.py` |
| --- | --- | --- |
| 1 | `DateGroup` (class) | missing |
| 2 | `DerivedMetric` (class) | missing |
| 3 | `HavingRule` (class) | missing |
| 4 | `RankSpec` (class) | missing |
| 5 | `AggregateOperation.filter` (field) | missing |
| 6 | `AnalysisPlan.derived_metrics`, `.having`, `.rank`, `.date_group` | missing |
| 7 | `AnalysisPlan.clarification`, `.confidence`, `.assumptions` | missing |

`schemas.py` currently defines only `Condition`, `AggregateOperation`, `SortRule`, `JoinRule`,
`DatasetRef`, `AnalysisPlan`.

Note that #6 and #7 are **plan-contract** gaps, not just import gaps: even after the four classes
are added, `AnalysisPlan` must carry these fields before `PlanValidator` / `QueryCompiler` /
`skills` can consume a plan produced by this module. Adding the classes alone would move the
failure from import-time to validation-time, which is worse.

### 2.2 Not wired anywhere

```bash
git grep -n "generic_planner" -- . ':!backend/app/ai/planning/generic_planner.py'
# -> no output
```

The only references to `GenericPlanner`, `QuestionEngine`, and `SchemaView` are inside the file
itself. Nothing imports it, no route calls it, no orchestrator falls back to it. It cannot affect
production behavior today — which is the only reason this commit is inert rather than an incident.

---

## 3. Behavioral defects

Probed with a stubbed `app.ai.planning.schemas` module injected into `sys.modules` (required,
because of §2), run from the repo root with `PYTHONPATH=backend`.

| # | Question | Observed plan | Correct? |
| --- | --- | --- | --- |
| 1 | `top 5 cities by emi` | `top_n`, group `city`, count metric, limit 5 | yes |
| 2 | `bottom 3 branches by total emi` | `bottom_n`, ascending | yes |
| 3 | `average emi` | scalar `avg(emi)` | yes |
| 4 | `how many distinct cities` | `distinct_count` | yes |
| 5 | `sabse zyada records kis city ke hain` | **`IndexError: no such group`** | crash |
| 6 | `how many records have emi > 5000` | scalar **total row count**, `filters=[]`, confidence `1.0` | **no — silent** |
| 7 | `percentage of records have cancellation = yes` | `percentage` intent, **`filters=[]`** | **no — silent** |
| 8 | `monthly total emi trend` | `scalar_metric`, not a time series | **no — silent** |

### 3.1 Hinglish capture-group crash

`_rule_top_bottom_count` (line ~727) tries five patterns with **different group counts** (2 and 3)
and then indexes groups positionally:

```python
match = (re.search(r"which (.+?) has the (highest|lowest|most|least) number of records", text)
         or re.search(r"sabse (zyada|kam|jyada) records kis (.+?) ke hain", text)   # 2 groups
         or ...
         or re.search(r"sabse (.+?) (.+?) (.+?)$", text))                          # 3 groups
...
if match.group(1) and match.group(2) and text.startswith("sabse "):
    ...
    group = self._resolve_dimension(match.group(3))   # IndexError on the 2-group pattern
```

For `sabse zyada records kis city ke hain` the second pattern wins with 2 groups, the first branch
is taken because the text starts with `sabse `, and `match.group(3)` raises `IndexError`.

Adjacent bug in the same function: the third branch evaluates `... and not ascending` before
`ascending` has been assigned on that path, so inputs reaching it can raise `UnboundLocalError`
instead of returning `None`.

### 3.2 Numeric filters are silently dropped

`_filter_from` (line ~392) only resolves **observed categorical values**:

```python
column, value, score = self.schema.find_value(phrase)
if column is None or value is None:
    return None, None
```

`emi > 5000` is neither a column nor an observed value, so `_filter_from` returns `(None, None)`.
Nothing checks that a condition was required, and the caller proceeds with `filters=[]` — producing
an unfiltered total while reporting `confidence=1.0`.

### 3.3 Percentage conditions never reach `filters`

`_rule_overall_percentage` (line ~589) extracts a condition and then discards it into an aggregation
tuple; `interp.filters` is never populated. A question asking for the percentage of rows where
`cancellation = yes` produces a percentage plan with no predicate — i.e. 100% by construction.

### 3.4 Temporal questions misclassify

`monthly total emi trend` matches a scalar aggregation rule before the time-series rule, yielding
`scalar_metric`. `TREND_WORDS` (including `monthly`, `mahina`, `trend`) is present in the lexicon but
does not gate rule ordering, so trend intent is lost.

### 3.5 Confidence is not a function of evidence

Every successful rule path clamps confidence to `1.0` regardless of whether the measure, dimension
or condition was actually grounded. The only downgrade is `clarification` → `0.4`. A plan built on
zero resolved filters is therefore indistinguishable from a fully grounded plan.

---

## 4. Why the silent failures are the critical issue

The crash in §3.1 is loud, isolated to one phrasing, and fixable in minutes. The failures in §3.2,
§3.3 and §3.4 are worse in kind:

- they return a well-formed `AnalysisPlan`,
- they carry `confidence=1.0`,
- and they answer a **different question** than the one asked.

A user receives a confident, plausible, wrong number — the worst failure mode for an analyst
product, and one that no type check, import check or "does it run" smoke test detects. Any repair
must therefore be driven by asserted expected plans, not by "it returned something".

---

## 5. Benchmark leakage

**None found.** The file contains no dataset names, no golden answers, no fixture paths, no
branching on file names, row counts, or known question text. Lexicon entries are generic
English/Hinglish/Roman-Hindi function words and analytics vocabulary, including for example
`NEGATION_WORDS`, `TREND_WORDS` and `DATE_GROUPS`. This gate passes, and it is the only gate that
currently does.

---

## 6. Overlap with existing `main` behavior

`main` already performs multilingual schema mapping by two routes:

- `backend/app/ai/learning/semantic_mapping.py` — `SemanticMapper` with English / Hindi / Hinglish
  concept keywords.
- `backend/app/ai/orchestration/orchestrator.py` — prompt-driven column matching via Mistral /
  Gemini.

`generic_planner.py` re-implements the same responsibility deterministically. This is a **design
decision to settle before any code is written**: adding a second, independent engine that must be
kept in sync with `SemanticMapper` and the orchestrator multiplies maintenance and divergence risk.
If the overlap is large, the safer end state is to reuse the planner's useful deterministic pieces
(`SchemaView` role classification, fuzzy column/value resolution, token repair) inside the existing
flow rather than to ship it as a parallel engine.

---

## 7. Ruling

| Decision | Value |
| --- | --- |
| Retag `05a9508` | `TEST_RAJ_ONLY` |
| Trust the commit message | **No** — historical artifact |
| Mark `MAIN_INTEGRATION_ELIGIBLE` | **Never**, until §9 passes |
| Cherry-pick into `main` | **Prohibited** |
| Replace `main` orchestrator with this module | **Prohibited** |
| Treat `generic_planner.py` as | a prototype |
| Where further work happens | `test-raj` |
| `main` | untouched |

`files_deleted_from_main` for this change would be `0`, but the audit is moot: the change is
ineligible on correctness grounds before any diff-level review applies. No
`main_preservation_audit.json` is generated until a real integration is attempted.

---

## 8. Known-bad test cases (must fail on today's code, pass after repair)

These four must exist as assertions on the produced `AnalysisPlan`, not as crash-only smoke tests:

| Input | Required plan property |
| --- | --- |
| `sabse zyada records kis city ke hain` | `top_n`, `group_by=[city]`, count metric, **no exception** |
| `how many records have emi > 5000` | `filters=[emi > 5000]`, count metric |
| `percentage of records have cancellation = yes` | `filters=[cancellation == yes]` |
| `monthly total emi trend` | time-series intent with `date_group=month` |

Additionally: any plan whose `filters` were dropped must not report `confidence >= 0.9`.

---

## 9. Repair sequence (gated, in order)

1. **Import / schema compatibility** — adapt the planner to the plan contract the executor can
   already run. **Do not** add `DateGroup`, `DerivedMetric`, `HavingRule`, `RankSpec`,
   `AggregateOperation.filter` or the extra `AnalysisPlan` fields: they have no validator or compiler
   implementation, so adding them turns an import failure into a validation failure. Superseded by
   `docs/GENERIC_PLANNER_OVERLAP_AUDIT.md` §4.
2. **Regex capture-group bugs** — fix `_rule_top_bottom_count` and `_rule_per_entity_ratio` so group
   indexing is derived per matched pattern, and remove the `ascending`-before-assignment path.
3. **Numeric filters** — extend `_filter_from` to parse comparisons (`<`, `>`, `<=`, `>=`, `=`,
   `between`) against numeric and date measures, and make an unresolved *required* condition return a
   `clarification` instead of silently proceeding.
4. **Temporal queries** — gate trend/date words ahead of scalar rules; emit `DateGroup`.
5. **Confidence** — derive confidence from resolved evidence (measure grounded, dimension grounded,
   filters resolved), never a constant `1.0`.
6. **Tests** — add the §8 cases plus regression coverage for the passing cases in §3, before
   wiring anything.
7. **Feature-flag wiring** — call the planner only behind an explicit flag/fallback path; the
   existing orchestrator remains the default and must not be replaced.
8. **Blind evaluation** — evaluate on unseen schemas and phrasings, with no benchmark answers
   readable by production code.
9. **Full gate run** — all gates in `AGENTS.md` §3, re-verified against a `main`-based candidate.

Step 1 must not be done by editing the 924-line file blindly. The overlap question in §6 is settled
  in `docs/GENERIC_PLANNER_OVERLAP_AUDIT.md`: keep it as a second planner, narrowed to the executable
  contract, unreferenced by the orchestrator until the flag step.

---

## 10. Current state

- `main` — untouched, still `79279fa13730` locally.
- `test-raj` — `05a9508` plus the documentation commits (`AGENTS.md`, this document, and
  `docs/GENERIC_PLANNER_OVERLAP_AUDIT.md`).
- `05a9508` — `TEST_RAJ_ONLY`, ineligible, not to be cherry-picked.
