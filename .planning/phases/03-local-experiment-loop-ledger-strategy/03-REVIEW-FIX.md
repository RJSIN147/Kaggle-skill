---
phase: 03-local-experiment-loop-ledger-strategy
fixed_at: 2026-07-11T14:40:00Z
review_path: .planning/phases/03-local-experiment-loop-ledger-strategy/03-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 03: Code Review Fix Report

**Fixed at:** 2026-07-11T14:40:00Z
**Source review:** .planning/phases/03-local-experiment-loop-ledger-strategy/03-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4 (1 Critical + 3 Warning; Info deferred per fix_scope)
- Fixed: 4
- Skipped: 0

All fixes verified with `uv run pytest -q -m "not live"`: **182 passed, 1 skipped, 8 deselected**.
The single skip is `test_run_cv` (skips cleanly when sklearn is absent) — expected. Each fix
ships with a dedicated regression test.

## Fixed Issues

### CR-01: Config-sourced values rendered unescaped into executed Python (injection / code-integrity)

**Files modified:** `scripts/templates/experiment.py.tmpl`, `scripts/scaffold_experiment.py`, `tests/test_scaffold_experiment.py`, `tests/test_resolve_data_dir.py`
**Commits:** `3e76b90` (fix + regression tests), `c9b238e` (align the direct-render test helper with the new template contract)
**Applied fix:**
- The template now carries bare `$slug_literal` / `$exp_id_literal` / `$cv_scheme_literal` /
  `$metric_name_literal` / `$exp_dir_literal` placeholders (no hand-written quotes). The
  scaffolder passes each value as a properly quoted Python literal via `repr(...)`, exactly the
  way `registry_entry` was already emitted. Any value containing a quote/backslash/newline is now
  an inert string literal — it can no longer break out and execute when `run_local.py` shells the
  harness.
- Defense-in-depth charset gates added at scaffold (block, don't guess): a non-empty
  `competition_slug` must match `^[a-z0-9][a-z0-9-]*$`, and `cv.scheme` must be one of the four
  allowed splitters, checked before rendering. An empty slug is tolerated (renders to an inert
  `''`).
- Regression tests: (1) a slug/cv_scheme carrying `"; import os; os.system(...)` renders as an
  inert string literal and the generated file still parses (no top-level call nodes); (2) a
  malformed slug is blocked at scaffold and nothing is minted / the id cursor never advances;
  (3) an unknown cv scheme is blocked. Verified a real scaffold output compiles (`py_compile`).

### WR-03: `"custom"` metric bypassed the range gate even for a bounded config metric

**Files modified:** `scripts/record_experiment.py`, `tests/test_record_experiment.py`
**Commit:** `8fbcbd0`
**Applied fix:** The metric-match gate now honors the `"custom"` escape hatch **only when config
itself declared `custom`** (`allow_custom = metric_name == "custom"`). When config names a known
bounded metric (e.g. `roc_auc` in `[0,1]`), the result must report that same metric, so its
registered range is actually enforced — a run self-reporting `metric="custom"` with a score of
`5.0` is now correctly FAILED (`schema_invalid`), never appended as a success row. The fail-closed
ladder semantics are otherwise preserved. Regression test added.

_Note: this is a validation-logic/condition change. It passes the regression test and the full
suite, but the correctness of the condition itself warrants a human eyeball before the phase
proceeds to verification._

### WR-01: Ledger SUCCESS append was not idempotent (re-record duplicated the row)

**Files modified:** `scripts/record_experiment.py`, `tests/test_record_experiment.py`
**Commit:** `9659a1f`
**Applied fix:** The raw `open("a")` append is replaced with an idempotent, atomic rewrite: drop
any prior line for the same `exp_id`, append the fresh row, then write the whole file via
`tempfile + os.replace`. Re-recording an already-recorded SUCCESS now yields exactly one row (no
more double-counting in `regen_strategy`), and a crash mid-write leaves the previous ledger intact
(also closing the truncated-final-line hole WR-02 relies on). Unparseable existing lines are
preserved verbatim — never fabricated over, never silently dropped. Regression test records the
same SUCCESS twice and asserts a single row.

### WR-02: `regen_strategy._read_ledger` crashed on a corrupt / non-object ledger line

**Files modified:** `scripts/regen_strategy.py`, `tests/test_regen_strategy.py`
**Commit:** `91cf592`
**Applied fix:** `_read_ledger` now mirrors `rebuild_ledger`'s fail-clear posture: it wraps the
`json.loads(line)` in a try/except and skips-and-warns on `JSONDecodeError`, and skips non-object
(scalar/list) rows so a stray line like `5` can no longer raise `AttributeError` downstream in
`_current_best_body`/`_tried_list_body`. A single malformed line (e.g. a truncated final line from
an interrupted write) no longer aborts strategy regeneration. Regression test seeds a valid row
plus a scalar line and a truncated line, and asserts regen still succeeds with the good row driving
the facts.

## Skipped Issues

None — all in-scope findings were fixed.

_Info findings IN-01 (`--exp-dir` path traversal) and IN-02 (trusted artifact paths) are out of
scope for this pass (fix_scope: Critical + Warning) and were not addressed._

---

_Fixed: 2026-07-11T14:40:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
