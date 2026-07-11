---
phase: 03-local-experiment-loop-ledger-strategy
plan: 05
subsystem: experiment-loop
tags: [strategy, ledger, jsonl, regen, never-repeat, skill, stdlib, atomic-write]

# Dependency graph
requires:
  - phase: 03-02
    provides: experiment_meta.to_ledger_row schema + rebuild_ledger (the ledger.jsonl regen reads)
  - phase: 03-04
    provides: record_experiment.py (produces the ledger rows + VERDICT stubs regen renders)
provides:
  - "scripts/regen_strategy.py — facts-from-ledger (current-best by direction + tried-list digest) + AI --reasoning-file splice, full atomic overwrite of strategy.md (D-12)"
  - "SKILL.md Local experiment loop section sequencing set_metric -> scaffold (never-repeat first) -> run_local -> record -> regen"
  - "strategy.md.tmpl header aligned to D-12 (regenerated/overwritten each cycle)"
affects: [phase-04-kaggle-kernel, submission-loop, strategy-consumers]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tooling-renders-FACTS / AI-authors-REASONING split (D-11): the current-best number comes only from the ledger, never AI-typed"
    - "Full atomic overwrite (D-12) as the deliberate opposite of competition.md's section-safe-merge — strategy.md is a pure function of ledger + reasoning-file"
    - "Prompt-driven never-repeat check (D-13): the tried-list digest is a by-product of regen, the check lives in SKILL prose (no new tooling)"

key-files:
  created:
    - scripts/regen_strategy.py
    - tests/test_regen_strategy.py
  modified:
    - scripts/templates/strategy.md.tmpl
    - SKILL.md

key-decisions:
  - "greater_is_better read from tooling-written config.json.metric (not the per-row ledger value) so direction cannot drift (T-03-05-04)"
  - "Reasoning fragment spliced verbatim under a single Reasoning section; --reasoning-file is REQUIRED (tool blocks rather than author reasoning)"
  - "Atomic write mirrors rebuild_ledger._atomic_write (tmp with .md.tmp suffix + os.replace)"

patterns-established:
  - "FACT section-body builders (_current_best_body / _tried_list_body) mirror analyze_data's _..._section_body renderers"
  - "Fail-clear config read (_read_greater_is_better) mirrors record_experiment._read_config_metric"

requirements-completed: [MEM-02, MEM-03]

# Metrics
duration: 18min
completed: 2026-07-11
---

# Phase 3 Plan 05: Living Strategy Regeneration + Loop Wiring Summary

**`regen_strategy.py` regenerates `strategy.md` as a pure function of `control/ledger.jsonl` (tooling FACTS: current-best by metric direction + tried-list digest) spliced with an AI `--reasoning-file`, fully overwritten atomically (D-12); SKILL.md now sequences the whole scaffold→run→record→regen loop with a prompt-driven never-repeat check.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-07-11
- **Completed:** 2026-07-11
- **Tasks:** 2
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `scripts/regen_strategy.py`: tooling renders the FACTS (current-best picked `max`/`min` by `config.json.metric.greater_is_better` over `status=="SUCCESS"` rows; tried-list digest one line per row — the D-13 never-repeat surface), splices the AI `--reasoning-file` verbatim, and FULLY OVERWRITES `strategy.md` atomically (tmp + `os.replace`). Empty ledger renders "None yet."; a missing reasoning file blocks (the tool never authors reasoning).
- 10-test suite (`tests/test_regen_strategy.py`) pinning direction-aware current-best, empty-ledger, verbatim splice, facts-not-from-reasoning, D-12 hand-edit clobber, atomicity (no `.tmp` residue), reasoning-file-required block, and no-`replace_section`.
- `SKILL.md` "Local experiment loop (EXP-*/MEM-*)" section sequencing `set_metric` (precondition, exit-78 block-don't-guess) → never-repeat check → `scaffold_experiment` → `run_local` → `record_experiment` → `regen_strategy`, plus six new Scripts rows. Stays within budget at 302 lines.
- `strategy.md.tmpl` header note aligned to D-12 so a fresh workspace is honest before the first cycle.

## Task Commits

1. **Task 1 (RED): failing test for regen_strategy** - `5945898` (test)
2. **Task 1 (GREEN): regen_strategy.py + template header** - `6d11880` (feat)
3. **Task 2: SKILL.md loop wiring + Scripts rows** - `179a583` (docs)

_TDD Task 1: test → feat (no refactor needed)._

## Files Created/Modified
- `scripts/regen_strategy.py` - Facts-from-ledger + AI reasoning splice, atomic full overwrite of strategy.md (stdlib only, self-locating, `--workspace`/`--reasoning-file`)
- `tests/test_regen_strategy.py` - 10 subprocess tests pinning the D-11/D-12/D-13 contract
- `scripts/templates/strategy.md.tmpl` - Header note now states the doc is regenerated/overwritten each cycle by regen_strategy.py
- `SKILL.md` - Local experiment loop section + six new Scripts (progressive disclosure) rows

## Decisions Made
- Read `greater_is_better` from the tooling-written `config.json.metric` (fail-clear block if unset) rather than the per-row ledger value — the direction that orders current-best must be authoritative and un-drifted (T-03-05-04).
- `--reasoning-file` is required; the reasoning fragment is spliced verbatim under a single `## Reasoning (hypothesis queue & next action)` section. This satisfies "spliced into the hypothesis-queue + next-action sections verbatim" while keeping the tool from ever authoring reasoning.
- Best-effort read of `competition_slug` for the doc title (defaults to a bare `# Strategy` when absent) — non-fatal.

## Deviations from Plan

None - plan executed exactly as written. (One in-task adjustment: the initial docstring referenced the `replace_section` symbol by name, which the plan's own verification greps must NOT find in the file; reworded the docstring to name "competition.md's section-safe-merge helper" without the literal token. This is a wording fix within Task 1, not a scope change.)

## Issues Encountered
- `ruff` is not installed in the worktree venv, so the lint step could not run here. Not blocking — `ruff` is a dev-only tool; the code is stdlib-only and the full pytest suite (176 passed, 1 skipped) confirms syntax/behavior. Lint can run in the main environment.

## Threat Flags

None - no new security surface. The plan's threat register (T-03-05-01..04) is fully mitigated: current-best + tried-list are tooling-rendered from `ledger.jsonl`, the file is atomically overwritten each cycle (a hand edit is clobbered), the never-repeat check is documented in SKILL prose, and `greater_is_better` is read from the tooling-written config.

## Next Phase Readiness
- The full local loop (`set_metric → scaffold → run_local → record → regen_strategy`) is now documented and sequenced in SKILL.md — Phase 3's core cycle is code-complete.
- Phase 4 (Kaggle Kernel / submission) can build on the same `meta.json`/`ledger.jsonl` schema; `regen_strategy.py` is target-agnostic (reads the ledger regardless of where a run executed).

## Self-Check: PASSED
- Files verified present: `scripts/regen_strategy.py`, `tests/test_regen_strategy.py`, `scripts/templates/strategy.md.tmpl`, `SKILL.md`
- Commits verified in git log: `5945898`, `6d11880`, `179a583`
- `uv run pytest tests/test_regen_strategy.py -q` → 10 passed; full suite → 176 passed, 1 skipped
- `grep -n "replace_section" scripts/regen_strategy.py` → no matches (full overwrite, not merge)

---
*Phase: 03-local-experiment-loop-ledger-strategy*
*Completed: 2026-07-11*
