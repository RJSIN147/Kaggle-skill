---
phase: 03-local-experiment-loop-ledger-strategy
plan: 04
subsystem: experiment-loop
tags: [uv, subprocess, provenance, fail-closed, ledger, cv, anti-lie, stdlib]

# Dependency graph
requires:
  - phase: 03-01
    provides: metric_registry.REGISTRY (direction + range for the result gates)
  - phase: 03-02
    provides: experiment_meta.to_ledger_row / validate_meta + meta.json/VERDICT.md templates
  - phase: 03-03
    provides: scaffold_experiment.py meta.json stub (idea/hypothesis/created/exp_id) + experiment.py harness
provides:
  - "run_local.py: bounded `uv run --no-sync` runner that captures ONLY the child exit code (EXP-03)"
  - "record_experiment.py: fail-closed recorder that validates result.json, recomputes mean(fold_scores), attaches provenance, and persists meta.json + ledger row + VERDICT stub (EXP-04)"
  - "the anti-lie guarantee: a throwing/lying/invalid run is recorded FAILED-with-verdict, never a success (criterion 3)"
  - "stub carry-forward: idea/hypothesis/created/exp_id preserved on BOTH SUCCESS and FAILED paths (D-13 tried-list)"
affects: [regen_strategy, rebuild_ledger, kernel-execution-path, SKILL.md loop wiring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "uv run --no-sync shell-out with exit-code-only capture (never scrape stdout for a score)"
    - "fail-closed validation ladder with an anti-lie mean recompute (statistics.mean vs emitted cv_mean)"
    - "stdlib provenance block (uuid4 + sha256 + git rev-parse --short + git_dirty flag)"
    - "explicit-path git staging (never a blanket stage) for provenance files"
    - "scaffold-stub carry-forward merged with tooling-written numbers on both status branches"

key-files:
  created:
    - scripts/run_local.py
    - scripts/record_experiment.py
    - tests/test_run_local.py
    - tests/test_record_experiment.py
  modified: []

key-decisions:
  - "Recording a FAILED run is a successful cycle -> the recorder exits 0 on any recorded outcome; non-zero is reserved for recorder-level errors (missing stub, corrupt config, unknown metric)."
  - "A non-zero --run-exit-code pre-classifies FAILED before reading result.json (missing_result if no result, else schema_invalid) -- a throwing run can never be upgraded to success even if a stale valid result.json exists."
  - "Seed provenance falls back to the D-09 default 42 when a failed run left no result.json, so provenance.seed is always non-empty (keeps validate_meta green for rebuild_ledger)."
  - "git_dirty is computed before staging and reflects the uncommitted experiment work at record time -- provenance never falsely claims a clean commit."

patterns-established:
  - "Runner/recorder split: run_local owns 'did it run?' (exit code), record_experiment owns 'what is the score?' (on-disk result.json) -- stdout is never a score source (D-05)."
  - "Anti-lie recompute: mean(fold_scores) is recomputed and compared to the emitted cv_mean with a 1e-6 tolerance; disagreement is schema_invalid."

requirements-completed: [EXP-03, EXP-04]

# Metrics
duration: ~18min
completed: 2026-07-11
---

# Phase 3 Plan 4: Local Run + Anti-Lie Recorder Summary

**`run_local.py` runs a scaffolded experiment under bounded `uv run --no-sync` capturing only the exit code, and `record_experiment.py` validates the on-disk result.json through a fail-closed ladder (recomputing mean(fold_scores) to catch fabrication), attaches stdlib provenance, and records a throwing/lying run as FAILED-with-verdict — never a success.**

## Performance

- **Duration:** ~18 min
- **Completed:** 2026-07-11
- **Tasks:** 2 (both TDD)
- **Files modified:** 4 created

## Accomplishments
- **run_local.py (EXP-03):** shells `uv run --no-sync python experiment.py --exp-dir ... --slug ...` inside the workspace, timeout-bounded, capturing ONLY `proc.returncode`. `uv` absent / timeout / launch-error each degrade to a clear non-zero with the `run uv sync` remediation — never a silent runtime package install (Pitfall 5). Stdout is never parsed for a score (D-05).
- **record_experiment.py (EXP-04, criterion 3 — the MVP headline):** reads the scaffold meta stub, carries idea/hypothesis/created/exp_id forward on BOTH paths, runs the D-06 fail-closed ladder (exists → keys/types/fold-count → finite → **mean recompute** → metric-match → range), attaches provenance `{run_id, artifact_hash, git_commit, git_dirty, seed}`, and persists `meta.json` + (SUCCESS only) a derived `ledger.jsonl` row + a `VERDICT.md` stub.
- **Anti-lie proven end-to-end:** a throwing run (nonzero exit, no result.json) and a lying result (cv_mean=0.99 vs fold mean 0.80) are both recorded FAILED-with-verdict with the hypothesis intact and zero success ledger rows.

## Task Commits

1. **Task 1: run_local.py** — `ec515ad` (test RED) → `07b56cb` (feat GREEN)
2. **Task 2: record_experiment.py** — `108f235` (test RED) → `e67036b` (feat GREEN)

_TDD tasks: each has a failing-test commit then an implementation commit._

## Files Created/Modified
- `scripts/run_local.py` — bounded `uv run --no-sync` runner; exit-code-only capture; env-absent/timeout degrade.
- `scripts/record_experiment.py` — fail-closed recorder: stub carry-forward + validation ladder + anti-lie recompute + provenance → meta.json + ledger row + VERDICT stub.
- `tests/test_run_local.py` — uv-shim subprocess tests: throwing→nonzero, uv-absent remediation, success→0, missing experiment.py fail-clear, source greps (`--no-sync`, no runtime install, no stdout scrape).
- `tests/test_record_experiment.py` — SUCCESS (numbers+provenance+one ledger row), FAILED(missing_result/schema_invalid/out_of_range/non_finite), nonzero-run-never-success, missing-stub fail-clear, source greps (statistics.mean, no blanket stage, no sklearn).

## Decisions Made
- Recorder exits 0 on any *recorded* outcome (SUCCESS or FAILED) — recording a failure is a successful cycle (criterion 3). Non-zero exit is reserved for recorder-level errors: missing experiment.py/stub, corrupt/unset config metric.
- `--run-exit-code` non-zero forces FAILED before reading result.json; reason is `missing_result` when no result exists, else `schema_invalid` (a run that threw but left a "valid" result is not trustworthy).
- Provenance `seed` defaults to 42 (D-09) when a failed run left no result.json, keeping provenance non-empty so a rebuilt ledger (via `validate_meta`) still includes the FAILED meta.
- `git_dirty` computed pre-staging so it honestly reflects uncommitted experiment work at record time.

## Deviations from Plan

None — plan executed exactly as written. The only in-flight adjustments were docstring wording tweaks (avoiding the literal strings `pip install` and `git add -A` in prose so the source-grep guard tests stay meaningful); no behavior changed.

## Issues Encountered
- Two source-grep guard tests initially tripped on the literal strings `pip install` / `git add -A` appearing in the scripts' own explanatory docstrings. Reworded the prose ("package fetch" / "blanket stage") — the guards now assert on real code, not documentation. Resolved within Task 1 and Task 2 respectively.
- `ruff` is not installed in this environment, so lint was skipped; the full pytest suite (166 passed, 1 skipped, 8 deselected) is the correctness signal.

## Next Phase Readiness
- The loop's integrity spine is complete: `scaffold → run_local → record_experiment` produces honest, provenance-bearing meta.json + ledger rows. Ready for `regen_strategy.py` (reads ledger.jsonl) and the kernel-execution path (which reuses the same recorder against pulled kernel output).
- No blockers. `rebuild_ledger.py` already consumes the meta.json shape this recorder writes.

## Self-Check: PASSED

All created files present (scripts/run_local.py, scripts/record_experiment.py, tests/test_run_local.py, tests/test_record_experiment.py, 03-04-SUMMARY.md). All task commits verified in git history (ec515ad, 07b56cb, 108f235, e67036b). Full offline suite: 166 passed, 1 skipped, 8 deselected.

---
*Phase: 03-local-experiment-loop-ledger-strategy*
*Completed: 2026-07-11*
