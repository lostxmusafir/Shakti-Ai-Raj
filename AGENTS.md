# MAIN BRANCH PRESERVATION — ABSOLUTE RULE

`main` is the protected production baseline and is authoritative.
`test-raj` is an experimental laboratory only.

`test-raj` must never replace, rewrite, or overwrite working `main` functionality.

The correct direction is:

```
MAIN EXISTING FUNCTIONALITY
+ ONLY VERIFIED GENERIC IMPROVEMENTS FROM TEST-RAJ
= NEW MAIN
```

Never:

```
TEST-RAJ REPLACES MAIN
```

---

## 1. Branch model

| Branch | Role | Rules |
| --- | --- | --- |
| `main` | Production baseline | Authoritative. Only additive, verified, generic changes. |
| `test-raj` | Experiment branch | May contain datasets, checkpoints, blind-test answers, temporary artifacts. |
| `origin/main` | Remote baseline | Never force-pushed. |

Never delete or overwrite working `main` functionality merely to make an experiment easier to merge.

---

## 2. Commit classification

Every commit considered for integration carries exactly one tag in its subject:

- `[CODE]` — a generic production code improvement. The **only** category eligible for `main`.
- `[EXP-DATA]` — downloaded public raw datasets, temporary synthetic datasets, experimental QA,
  blind-test answers, benchmark snapshots, learning-window logs, temporary aliases,
  test-only generated schemas. **Never enters `main`.**
- `[CHECKPOINT]` — checkpoint JSON, experiment manifests with bulky data, temporary performance
  outputs. **Never enters `main`.**

Untagged commits are treated as ineligible until classified.

Even `[CODE]` is **not** automatically approved. It becomes `MAIN_INTEGRATION_ELIGIBLE` only after
passing every gate in section 3.

---

## 3. Eligibility gates for `[CODE]`

Before a `[CODE]` commit may be marked `MAIN_INTEGRATION_ELIGIBLE`:

- focused tests for the changed module pass
- full deterministic regression suite passes
- hard-question tests pass
- schema-generalization tests pass
- multilingual tests pass where relevant
- security tests pass
- lifecycle tests pass
- no benchmark leakage (no golden answer, fixture, or blind-test answer is read by production code)
- no dataset-specific production hacks (no branching on a dataset name, file name, row count, or known question text)

Verification must be re-run against the resulting `main` candidate, not only against `test-raj`.

---

## 4. No destructive merge

**Never** run a blind whole-branch merge:

```bash
git merge test-raj          # FORBIDDEN
```

Never mix experiment history or experimental data into `main` through a whole-branch merge.

### Required sequence

1. Update local knowledge of `main` (`git fetch origin`; inspect `origin/main`).
2. Compare `main...test-raj` and `test-raj...main` — the delta is bidirectional; `main` may be ahead.
3. Identify only `[CODE]` commits that passed every gate in section 3.
4. Inspect every changed file in those commits.
5. Integrate only the smallest verified code changes.
6. Preserve unrelated code and behavior already present in `main`.
7. Exclude all experiment-only artifacts.
8. Run the complete test suite against the resulting `main` candidate.
9. Finalize only if no existing functionality regresses.

### Preferred strategies

- **Option A — selective cherry-pick.** Use when a `[CODE]` commit is clean and self-contained.
  Cherry-pick only that verified commit, then resolve conflicts conservatively in favor of `main` behavior.
- **Option B — manual minimal patch.** Use when a `test-raj` commit mixes concerns.
  Port only the verified generic code changes; do not import unrelated experimental changes.

---

## 5. No delete-to-fix

Do not resolve conflicts by deleting existing `main` files, and do not accept a `test-raj`
version wholesale when it removes code present in `main`.

For every conflict:

1. Understand what `main` currently does.
2. Understand what the verified `test-raj` change improves.
3. Combine them with the smallest safe patch.
4. Preserve both existing functionality and the verified improvement.

Deletion is permitted **only** when all of the following are true:

- the file/code is proven obsolete
- no references remain
- tests prove the removal is safe
- removal is necessary for the verified improvement
- an explicit integration report identifies the removal

Otherwise preserve it.

---

## 6. Main baseline that must not regress

Establish and record this baseline before integration, and verify every item still exists afterwards:

- existing routes
- existing frontend features
- existing backend services
- existing tests
- existing AI orchestration
- existing MongoDB behavior
- existing Mistral provider
- existing lifecycle functionality
- existing security/RBAC
- existing datasets required by production
- existing skills
- existing policy functionality
- existing learning pipeline

If any previously working `main` feature disappears or regresses, **the integration fails** — stop.

---

## 7. Main-delta audit

Before any integration, generate `main_preservation_audit.json` containing:

- current `main` commit SHA
- target `[CODE]` commit SHAs
- files added
- files modified
- files deleted (highlighted separately)
- production behavior affected
- existing tests impacted
- experimental files excluded
- known risks

Default expectation:

```json
{ "files_deleted_from_main": 0 }
```

If `files_deleted_from_main > 0`, integration must stop for manual review unless the deletion was
explicitly authorized.

---

## 8. Post-integration gate

After any integration into `main`, run:

- complete existing `main` backend suite
- new generic planner tests
- schema resolver tests
- hard-question tests
- multilingual tests
- adversarial tests
- lifecycle/security tests
- frontend validation if the frontend changed

Compare against the pre-integration baseline. Requirements:

- no previously passing test becomes failing
- no existing route disappears
- no existing feature disappears
- no production data/config disappears
- no security control weakens
- no experimental dataset enters `main`

On any regression: **do not push `main`.** Revert only the attempted integration changes, or fix the
conflict while preserving `main`. Do not reset or discard unrelated `main` work.

---

## 9. Acceptance criteria

Integration is acceptable only when:

1. Existing `main` functionality remains intact.
2. Verified `test-raj` improvements are added.
3. `main` loses no required code.
4. `main` loses no required production data.
5. Experiment-only data stays on `test-raj`.
6. Full regression remains green.
7. No benchmark answer is changed to manufacture success.
8. No dataset-specific production hacks are introduced.
9. No secrets enter `main`.
10. The diff has been explicitly reviewed.

---

## 10. Recorded state

Snapshot taken 2026-11-24. Treat as informational — refresh SHAs before acting.

| Ref | SHA |
| --- | --- |
| `main` | `79279fa13730` |
| `origin/main` | `6615a6625c1d` |
| `test-raj` | `05a950882088` |
| merge-base | `6615a6625c1d` |

Divergence at snapshot: `main` ahead by 11, `test-raj` ahead by 2.
`test-raj` is currently **behind** `main`; it is not a superset of production.

A `[CODE]` tag in a commit subject is a category label, not an eligibility claim. `05a9508` carries
`[CODE]` and is nevertheless `TEST_RAJ_ONLY`: it does not import, is unwired, and mis-plans several
question forms. Never promote a commit on the strength of its own message; verify it.

`test-raj`-only commits:

| Commit | Tag | Content |
| --- | --- | --- |
| `05a9508` | `TEST_RAJ_ONLY` | adds `backend/app/ai/planning/generic_planner.py` (new file, 924 lines, no `main` code removed). Subject says `[CODE]` but the commit is **ineligible**: see `docs/GENERIC_PLANNER_INTEGRATION_STATUS.md`. |
| `b0f58bb` | `[EXP-DATA]` | `data/benchmark/golden/golden_examples_300.json`, `training_pack_ingestion_manifest.json`, `learning_run_report.json` — **excluded from `main`** |
