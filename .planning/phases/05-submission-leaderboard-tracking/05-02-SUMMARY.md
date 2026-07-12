---
phase: 05-submission-leaderboard-tracking
plan: 02
subsystem: experiment-harness
tags: [d-09, submission, run-cv, scaffold, label-aggregation, kernel-portability]

requires:
  - scripts/templates/experiment.py.tmpl (Phase 3 run_cv fold loop — the seam)
  - scripts/metric_registry.py (REGISTRY.prediction_type — the aggregation authority)
  - scripts/capture_competition.py (signals.submission_csv_in_manifest — Phase 2 heuristic)
  - tests/test_run_cv.py (the 05-01 RED contract)
provides:
  - experiments/exp-NNN/submission.csv (the file SCORE-01 submits — it did not exist before)
  - run_cv(X_test=, test_ids=, id_column=, target_column=, submission_agg=)
  - result.json["submission_path"] (always present; None when nothing was written)
  - experiment.py ID_COLUMN / TARGET_COLUMN rendered literals
affects:
  - 05-04 (check_submission validates the file this plan writes)
  - 05-05 (submit.py submits it; file_sha256 hashes it)

tech-stack:
  added: []
  patterns:
    - "type-aware fold aggregation keyed on metric_registry prediction_type (never np.mean over hard labels)"
    - "test rows transformed by THAT fold's fitted preprocessor (anti-leakage extends to test)"
    - "submission.csv written FLAT at the experiment root => pull_kernel.py needs zero changes"
    - "stdlib csv only inside run_cv (numpy stays its sole heavy import)"
    - "scaffold-time literal rendering of data-sourced values via repr() (CR-01 inert)"

key-files:
  created: []
  modified:
    - scripts/templates/experiment.py.tmpl
    - scripts/scaffold_experiment.py

decisions:
  - "ID_COLUMN/TARGET_COLUMN are rendered by REWRITING two default `= None` lines in the template rather than by adding new $-placeholders to the substitution mapping — a new placeholder would break two pre-existing test renderers that call safe_substitute/_render_text with a fixed mapping, and the plan forbids touching tests"
  - "submission.csv stays .gitignored (experiments/*/*.csv) — provenance rides the file_sha256 in submissions.jsonl (D-11), reproducibility rides the tracked experiment.py + seed + git_commit"
  - "the scaffolder BLOCKS (exit 1) if the template no longer carries the ID_COLUMN/TARGET_COLUMN lines, rather than silently minting a header-less harness"

metrics:
  duration: ~25min
  tasks: 2
  files-created: 0
  files-modified: 2
  completed: 2026-07-12
---

# Phase 5 Plan 02: run_cv Submission Emission (D-09) Summary

`run_cv` now fold-averages test predictions into `experiments/exp-NNN/submission.csv` with
**type-aware** aggregation — so titanic's `accuracy` (a `label` metric) emits `0`/`1`, never a
fold-averaged `0.6` that the validator would pass and a real submission slot would be wasted on.

## What Was Built

**Task 1 — the harness (`14803e9`).** `run_cv` gains five keyword-only args, all defaulting to
`None`: `X_test`, `test_ids`, `id_column`, `target_column`, `submission_agg`. Backward
compatibility and D-09's "optional/graceful" requirement are therefore satisfied *by
construction* — a pure-diagnostic experiment behaves exactly as before.

The mechanism is the locked D-09 one: **reuse the CV fold models.** Immediately after
`model.fit(Xtr, ytr)`, the test rows are pushed through **that same fold's fitted `pp`** and
predicted. No second training run (which on a GPU kernel is real money), and every contributing
model was actually CV-scored. The anti-leakage contract the val path enforces now covers test:
the spy transformer in `test_test_preds_use_fold_preprocessor` proves each fold's `pp` fits on
train rows only, never sees a test row at fit, and still transforms the test rows.

`_default_agg(test_preds, ptype, test_probas, classes)` branches on the metric registry's
`prediction_type`:

| `prediction_type` | Metrics | Aggregation |
|---|---|---|
| `proba` | roc_auc, logloss | mean across folds (a soft ensemble — correct) |
| `raw` | rmse, mae, rmsle, mape, r2 | mean across folds |
| `label` | **accuracy**, f1, f1_macro, precision, recall, qwk, mcc | soft-vote (mean of `predict_proba`) then `argmax` over `model.classes_`; per-row **majority vote** via `Counter` when `predict_proba` is absent |

`submission_agg=` is the AI's escape hatch (the Phase 3 D-07 flexibility tension) — it overrides
aggregation without editing the harness. The docstring states plainly that `prediction_type`
describes what the **metric** consumes, not necessarily what the **submission file** wants; that
`check_submission`'s validation against the sample file is the backstop; and that this must not
be auto-detected.

Emission is guarded on `test_preds and test_ids is not None and id_column and target_column`.
The file is written **FLAT** at `Path(exp_dir)/"submission.csv"` — *not* under `artifacts/` —
with the stdlib `csv` module, so `run_cv` stays pandas-free and the Phase 4 kernel path lands the
file in the same place as the local path with **zero changes to `pull_kernel.py`**.
`result["submission_path"]` is always present (`None` when nothing was written) and
`"submission.csv"` joins `result["artifacts"]` only when it was; `record_experiment.py`'s
result gate is presence-only, so **no recorder change was needed** (assumption A4 confirmed).

`main()`'s AI-edited block pre-loads `test.csv` *guarded* (`test = pd.read_csv(p) if p.exists()
else None`), so the common case emits a submission with zero effort and a competition without a
test file still records a valid CV result.

**Task 2 — the header (`370822e`).** The harness writes `submission.csv` *on a Kaggle kernel*,
where `control/` does not exist and no skill code is importable (D-03). So the id/target column
names are baked in as **literals at scaffold time**, exactly like `SLUG` / `EXP_ID` /
`METRIC_NAME` / `CV_SCHEME`. `scaffold_experiment.py` resolves the sample file down the R4
ladder — Phase 2's `signals.submission_csv_in_manifest` from
`control/raw/competition-type-signals.json` (**consumed, not re-derived**; `sample_submission.csv`
is never hard-coded as a guessed name), then a case-insensitive `data/*submission*.csv` scan —
reads its first line with the stdlib `csv` module, and renders column 0 / column 1 as
`repr()`-quoted literals. Unresolvable ⇒ both render `None` ⇒ the harness skips emission and
still records CV. A header is **never guessed**. The chosen file is **printed**, because the
Phase 2 heuristic takes the first manifest match and its own comment flags it as WEAK.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] ID_COLUMN/TARGET_COLUMN are rendered by line-rewrite, not by a new `$`-placeholder**
- **Found during:** Task 2
- **Issue:** The plan says to "add `ID_COLUMN` and `TARGET_COLUMN` to the substitution mapping."
  Adding `$id_column_literal` placeholders to the template breaks **two pre-existing test
  modules**, neither of which I am allowed to touch (the plan's own verification requires
  `git diff --name-only` to list only the two script files):
  `tests/test_resolve_data_dir.py::render_experiment` (used by every `test_run_cv.py` node,
  including 05-01's D-09 RED tests) calls `Template(raw).safe_substitute` with a **fixed 6-key
  mapping** — an unsubstituted `$id_column_literal` would survive into the rendered source and
  make it a `SyntaxError` on import; and `test_scaffold_experiment.py`'s CR-01 injection test
  calls `_render_text` (also `safe_substitute`) with a fixed mapping and then `ast.parse`s the
  result. That 05-01 wrote `render_experiment` *without* the new keys, while its D-09 tests pass
  `id_column=` / `target_column=` as **run_cv kwargs**, confirms the template was expected to
  stay renderable from the old mapping.
- **Fix:** the template carries `ID_COLUMN = None` / `TARGET_COLUMN = None` as valid-Python
  defaults, and `scaffold_experiment.py::_render_submission_header` rewrites those two lines with
  `repr()`-quoted literals (via a lambda replacement, so a backslash in a header can never be read
  as a regex escape). Identical CR-01 inertness, identical outcome, and the grep acceptance
  (`ID_COLUMN` / `TARGET_COLUMN` present in `scaffold_experiment.py`) still holds. If the template
  ever stops carrying those lines, the scaffolder **blocks** with exit 1 rather than silently
  minting a header-less harness.
- **Files modified:** `scripts/templates/experiment.py.tmpl`, `scripts/scaffold_experiment.py`
- **Commit:** `370822e`

## Verification

| Check | Result |
|---|---|
| `pytest tests/test_run_cv.py` (with numpy+sklearn) | **6 passed** — the 3 D-09 nodes GREEN |
| `test_submission_optional` | GREEN — flat `submission.csv`, not under `artifacts/`; `submission_path` in result + artifacts |
| `test_label_aggregation_is_not_mean` | GREEN — every `accuracy` value ∈ {0,1}; the `roc_auc` control still emits soft 0<v<1 |
| `test_test_preds_use_fold_preprocessor` | GREEN — spy sees test rows through each fold's fitted `pp`, never at fit |
| `pytest tests/test_run_local.py tests/test_resolve_data_dir.py tests/test_scaffold_experiment.py tests/test_record_experiment.py` | **all passed** — zero backward-compat regressions |
| Full suite | 53 failed, 212 passed — the **same 53** RED nodes 05-01 left for plans 05-03…05-07; no failure in any file this plan touches |
| `ruff check scripts/` | clean |
| `grep -c "^import pandas" experiment.py.tmpl` | **0** — pandas is never imported at module level; `run_cv` uses only numpy + stdlib `csv` |
| `git diff --name-only` | exactly the two planned files — `pull_kernel.py` and `record_experiment.py` untouched |

**End-to-end (beyond the unit tests).** Scaffolded into a titanic-shaped workspace whose signals
file names `gender_submission.csv`: rendered `ID_COLUMN = 'PassengerId'` / `TARGET_COLUMN =
'Survived'`, printed the source file, and the generated `experiment.py` — the **real LightGBM
starter**, unedited — ran and emitted a flat `submission.csv` of clean `0`/`1` labels with
`result["submission_path"] == "submission.csv"`. Scaffolded into a workspace with no sample file
and no `test.csv`: rendered both as `None`, and the generated experiment still ran, recorded
`cv_mean`, and emitted nothing.

## Known Stubs

None. Both files are fully wired: the harness writes the real file and the scaffolder resolves
the real header from the competition's own sample file.

## Threat Flags

None beyond the plan's register. All four `mitigate` dispositions are discharged: T-05-02-01 by
`_default_agg`'s type-aware branch (pinned by `test_label_aggregation_is_not_mean`), T-05-02-02 by
transforming test rows with the fold's own `pp` (pinned by the spy test), T-05-02-03 by reading
the header from the actual sample file, printing the chosen filename, and rendering `None` rather
than guessing when unresolvable, and T-05-02-04 by importing no skill code, writing with stdlib
`csv`, and landing the file flat. `sample_submission.csv` appears in `scaffold_experiment.py`
only inside a comment warning *against* hard-coding it — it is not a code literal.

## For the Next Plan

- **05-04** (`check_submission.py`) validates the file this plan writes. It walks the *same* R4
  resolution ladder to find the sample file; `_find_sample_submission` here is the reference
  implementation of steps 1–2 (it deliberately does **not** implement step 3's `test.csv`
  fallback, which is validation-side only).
- The header lives in the generated `experiment.py` as `ID_COLUMN` / `TARGET_COLUMN`, and in
  `result.json` as `submission_path` — 05-05's `submit.py` should read the path from
  `result.json` / `meta.json`, not re-derive it.
- `submission.csv` is **gitignored** by the workspace's existing `experiments/*/*.csv` rule. This
  is deliberate (see decisions) — 05-05 must not assume the file is committed; the `file_sha256`
  in `submissions.jsonl` is its provenance.

## Self-Check: PASSED

Both modified files exist on disk; both commits (`14803e9`, `370822e`) are present in git history.
