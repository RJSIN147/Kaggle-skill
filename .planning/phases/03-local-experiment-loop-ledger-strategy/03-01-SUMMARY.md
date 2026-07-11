---
phase: 03-local-experiment-loop-ledger-strategy
plan: 01
subsystem: infra
tags: [metric-registry, sklearn, config, uv, pyproject, D-08, stdlib-split]

# Dependency graph
requires:
  - phase: 01-setup-foundation
    provides: init_workspace.set_config_field (direct reserved-null leaf setter), config.json.tmpl, workspace pyproject.toml.tmpl
  - phase: 02-competition-context-and-data
    provides: kaggle_gateway.LIMIT_NEEDS_USER (EX_CONFIG 78 block-don't-guess convention), the AI-decides/tooling-writes setter pattern (analyze_data --cv-scheme, capture_competition --set-competition-type)
provides:
  - metric_registry.py — the single stdlib source of truth (name -> greater_is_better, prediction_type, range, sklearn_callable name)
  - set_metric.py — D-08 setter that persists config.json.metric enum-validated, direction looked up (never free-typed)
  - config.json.tmpl reserved-null "metric" key
  - workspace pyproject ML floors (numpy/lightgbm/xgboost/catboost) for uv sync
affects: [record_experiment, run_cv/experiment.py scaffold, run_local, regen_strategy, kernel path Phase 4/5]

# Tech tracking
tech-stack:
  added: [lightgbm>=4.5, xgboost>=2.1, catboost>=1.2, numpy>=1.26 (workspace floors only — operator uv sync, skill never installs)]
  patterns:
    - "D-06 stdlib/ML split applied to metrics: registry NAMES the sklearn callable as a string; stdlib plumbing imports it without pulling scikit-learn"
    - "D-08 AI-decides/tooling-writes: enum validated at argparse choices boundary; direction looked up from registry, never taken from a flag for known metrics"
    - "Block-don't-guess: custom metric requires explicit direction or exits; reserved EX_CONFIG(78) for the SKILL uncaptured-metric precondition"

key-files:
  created:
    - scripts/metric_registry.py
    - scripts/set_metric.py
    - tests/test_metric_registry.py
    - tests/test_set_metric.py
  modified:
    - scripts/templates/config.json.tmpl
    - scripts/templates/pyproject.toml.tmpl

key-decisions:
  - "config.json.metric is a single-level leaf ({name, greater_is_better}) written only by set_metric.py via set_config_field(('metric',), ...); template reserves it as `\"metric\": null`"
  - "Direction is LOOKED UP from REGISTRY for known metrics (never mistyped); only `custom` requires an explicit --greater-is-better/--no-greater-is-better"
  - "sklearn_callable stored as a NAME STRING only — the ML-env harness resolves it later; metric_registry pulls zero third-party deps"
  - "Workspace pyproject declares FLOORS not newest majors (no pandas>=3 / numpy>=2) for Kaggle-image parity; degrade-don't-install posture"

patterns-established:
  - "Metric registry as the single source read by set_metric (enum+direction), record_experiment (range+direction gate), and run_cv (callable resolution)"
  - "argparse.BooleanOptionalAction with default=None to distinguish 'direction not supplied' (block for custom) from an explicit true/false"

requirements-completed: [EXP-03, EXP-04]

# Metrics
duration: ~20min
completed: 2026-07-11
---

# Phase 03 Plan 01: Metric Foundation Summary

**Stdlib `metric_registry.py` (15-metric source of truth mapping name → direction/range/prediction-type/sklearn-callable-name) plus the `set_metric.py` D-08 setter that persists an enum-validated, direction-looked-up `config.json.metric`, with the reserved-null template key and workspace ML floors for `uv sync`.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-11
- **Tasks:** 3
- **Files modified:** 6 (4 created, 2 modified)

## Accomplishments
- `metric_registry.py`: the D-08 single source of truth — 15 entries (roc_auc, logloss, accuracy, f1, f1_macro, precision, recall, rmse, mae, rmsle, mape, r2, qwk, mcc, custom), stdlib-only (`from math import inf`), NAMES the sklearn callable so importing it never pulls scikit-learn.
- `set_metric.py`: the AI-decides/tooling-writes setter — `--metric` enum-validated at the argparse `choices=SUPPORTED` boundary; direction looked up from the registry for known names; `custom` requires an explicit direction or blocks (exit 2); reserves `METRIC_NOT_CAPTURED=78` for the SKILL uncaptured-metric precondition.
- `config.json.tmpl` reserves `"metric": null` so only `set_config_field(("metric",), ...)` can fill the leaf (the same reserved-null pattern as cv/submission/competition).
- Workspace `pyproject.toml.tmpl` declares the ML floor set (numpy/lightgbm/xgboost/catboost) for `uv sync`; skill repo pyproject untouched.

## Task Commits

Each task committed atomically (TDD tasks have test → feat commits):

1. **Task 1: metric_registry.py** — `debc8cc` (test RED) → `51a94a9` (feat GREEN)
2. **Task 2: set_metric.py + reserved-null config key** — `5b88a5b` (test RED) → `83c2039` (feat GREEN)
3. **Task 3: workspace pyproject ML floors** — `bbc5e4c` (chore)

_No REFACTOR commits needed — implementations were clean on first GREEN._

## Files Created/Modified
- `scripts/metric_registry.py` - Stdlib REGISTRY + SUPPORTED; the single metric source of truth (no ML import).
- `scripts/set_metric.py` - D-08 setter: enum-validated `--metric`, direction looked up, custom-blocks-without-direction, persists via set_config_field.
- `scripts/templates/config.json.tmpl` - Added reserved-null `"metric": null` key.
- `scripts/templates/pyproject.toml.tmpl` - Added numpy>=1.26, lightgbm>=4.5, xgboost>=2.1, catboost>=1.2 floors; updated header comment.
- `tests/test_metric_registry.py` - 23 assertions: exact entries, direction/range correctness, stdlib-only.
- `tests/test_set_metric.py` - 9 tests: direction lookup, custom block/write, choices rejection, corrupt-config fail-clear, template reserves metric.

## Decisions Made
- Used `argparse.BooleanOptionalAction` (default `None`) so "direction not supplied" is distinguishable from explicit `true`/`false` — the clean way to enforce "custom requires a direction, known metrics ignore the flag."
- Reused `kaggle_gateway.LIMIT_NEEDS_USER` (EX_CONFIG 78) as `METRIC_NOT_CAPTURED` rather than a fresh magic number, keeping one "ask-the-user/block" convention across the skill.

## Deviations from Plan

**Minor — import surface:** The plan's `<interfaces>` listed importing `MalformedControlJSON` from `init_workspace`. It was intentionally NOT imported: `set_config_field` catches corrupt JSON internally and returns non-zero (never raises), so `set_metric.py` fully satisfies the "corrupt config left byte-intact, non-zero exit" behavior by delegating — importing the exception would be dead code. Verified by `test_corrupt_config_left_untouched`. No functional impact; the block-don't-guess and fail-clear contracts are met.

Otherwise: plan executed exactly as written.

## Issues Encountered
None. Full suite (122 tests) passes with no regressions after the shared config template gained the `metric` key.

## User Setup Required
None for this plan. The workspace ML deps (lightgbm/xgboost/catboost) are declared floors installed by the operator via `uv sync` in the scaffolded workspace — the skill never runtime-installs; the local runner (03-04) degrades if the env is absent.

## Next Phase Readiness
- The result-contract foundation is in place: 03-02/03/04 can read `config.json.metric` (direction + valid-range gate) and `metric_registry.REGISTRY[name]["sklearn_callable"]` (harness resolution) from one source, never re-deriving.
- `custom` prediction_type is `None` — the scaffold's `run_cv` must accept an AI-supplied metric callable for that path (already anticipated in 03-RESEARCH Pattern 3).

---
*Phase: 03-local-experiment-loop-ledger-strategy*
*Completed: 2026-07-11*
