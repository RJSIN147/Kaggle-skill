---
phase: 02-competition-context-data
plan: 06
subsystem: testing
tags: [cv-evidence, d-05, group-detection, adversarial-validation, stdlib, skill-md, titanic, gap-closure]

# Dependency graph
requires:
  - phase: 02-04
    provides: analyze_data.py + cv_evidence.py (schema/CV evidence, recommend_cv decision order, set_config_field cv.scheme writer, tracked control/raw/cv-evidence.json)
provides:
  - "cv.scheme is now an AI decision (D-05): analyze_data.py persists it ONLY from an explicit enum-validated --cv-scheme; no --cv-scheme leaves it reserved-null with a decision-pending competition.md section + a loud 'AI must choose' status"
  - "cv_evidence.recommend is labeled a NON-authoritative advisory hint (recommend_is_hint + recommend_note) in control/raw/cv-evidence.json"
  - "detect_group_candidates tightened: continuous-numeric features (_looks_continuous_numeric) and mostly-empty columns are never flagged as group ids — the Titanic Age/Fare/Cabin false positive is fixed and pinned"
  - "non-tabular degradation: a pair with no shared columns / empty frame yields a 'no tabular structure detected' sentinel (recommend None), never a fabricated scheme"
  - "titanic + degenerate fixtures added to tests/cv_fixtures.py; four regression tests pin the AI-decides contract"
  - "SKILL.md Analyze step documents the D-05 two-step flow (run analyze → AI reads cv-evidence.json → re-run --cv-scheme <enum>); framework never auto-picks the value"
affects: [phase-03-experiment-loop]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Advisory-vs-authoritative split: a mechanical heuristic emits a labeled non-authoritative HINT; the AI reasons and commits via an enum-validated flag; tooling persists only the AI's explicit choice (D-05)"
    - "Continuous-vs-categorical group discriminator via a fractional-value predicate (_looks_continuous_numeric) — conservative (fractional-only, not raw value-density) so pure-integer group ids are never excluded"
    - "Sentinel-over-default degradation: no analyzable tabular structure → recommend None + note, never a fabricated CV_SCHEMES value"

key-files:
  created:
    - .planning/phases/02-competition-context-data/02-06-SUMMARY.md
  modified:
    - scripts/cv_evidence.py
    - scripts/analyze_data.py
    - SKILL.md
    - tests/cv_fixtures.py
    - tests/test_cv_evidence.py

key-decisions:
  - "Altitude fix, not just detector tuning: removed the framework's auto-commit entirely (cv.scheme was written from evidence['recommend']); the scheme is now only ever the AI's explicit --cv-scheme, satisfying D-05 at the root"
  - "Continuous-numeric guard kept fractional-only (>=5% non-integer values) rather than value-density, so a legitimate integer group_id is never mis-excluded (the grouped fixture stays flagged)"
  - "Mostly-empty columns (>50% missing) excluded from group candidacy — a sparse column (Cabin) is not a dependable repeated-entity id"
  - "Non-tabular pairs degrade to a recommend=None sentinel instead of falling through to KFold, so 'no structure' is never dressed up as a real recommendation"

patterns-established:
  - "Pattern: mechanical recommendation is advisory-only (recommend_is_hint/recommend_note); the AI decides, tooling writes enum-validated"
  - "Pattern: titanic-shaped fixture (continuous fractional-repeating numerics + sparse string, no true group) as the canonical group-false-positive regression pin"

requirements-completed: [COMP-01]

# Metrics
duration: ~25min
completed: 2026-07-11
---

# Phase 2 Plan 06: CV Scheme is an AI Decision (Gap 1 Closure) Summary

**Re-wired the analyze flow so the framework never auto-commits a CV scheme: cv_evidence's recommendation is now a labeled non-authoritative advisory hint, the Titanic Age/Fare/Cabin group false positive is fixed and pinned (→ StratifiedKFold), and analyze_data.py persists cv.scheme ONLY from the AI's explicit enum-validated --cv-scheme — with SKILL.md documenting the D-05 two-step flow.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 3 (2 TDD auto + 1 docs auto)
- **Files modified:** 5 (+1 SUMMARY)
- **Tests:** tests/test_cv_evidence.py 19 passed; full suite 88 passed, 8 deselected

## Accomplishments

- **Gap 1 root cause fixed at altitude (Task 2).** The defect was not only a wrong detector — the framework *picked the value at all*: `scheme = committed or evidence["recommend"]` auto-committed the mechanical default. That fallback is gone. `analyze_data.py` now writes `config.json cv.scheme` via `set_config_field` **only** when `args.cv_scheme is not None`. With no `--cv-scheme` it leaves the reserved-null key, writes a `_cv_section_pending` decision-pending body (surfacing the advisory hint + a re-run instruction), and prints a loud `cv.scheme NOT committed — the AI must choose` status. Adversarial validation + schema still run on the no-scheme path (exit 0).
- **Advisory labeling + tightened detector (Task 1).** `cv_evidence.build_evidence` now emits `recommend_is_hint = True` and a `recommend_note` stating the recommendation is a NON-authoritative advisory hint the AI commits via `--cv-scheme`. `detect_group_candidates` gained two guards: `_looks_continuous_numeric` (fractional-numeric features like Age/Fare are measurements, not group ids) and a >50%-missing guard (a sparse Cabin is not a group id). The genuine integer `group_id` in the `grouped` fixture stays flagged (no regression).
- **Non-tabular degradation.** A resolved pair with no shared feature columns or an empty frame now returns a `non_tabular` sentinel record with `recommend = None` + a "no tabular structure detected" note, instead of falling through `recommend_cv` to a fabricated `KFold`.
- **Regression pins (Task 1).** Added `titanic` and `degenerate` shapes to `tests/cv_fixtures.py` and four tests: titanic → `StratifiedKFold` with Age/Fare/Cabin absent from `group_candidates`; grouped still → `GroupKFold`; recommendation labeled advisory; non-tabular → sentinel `None`.
- **SKILL.md D-05 flow (Task 3).** The Analyze step now documents the two-step operator path: run `analyze_data.py` (no flag) → AI reads `control/raw/cv-evidence.json` and reasons over the structural signals (treating `recommend` as a non-authoritative hint) → re-invoke `--cv-scheme <enum>`. States explicitly that the framework NEVER auto-picks `cv.scheme`. Scripts-table rows updated.

## Task Commits

Each task committed atomically (TDD RED → GREEN for Tasks 1-2):

1. **Task 1 (RED): titanic/degenerate fixtures + advisory/non-tabular tests** — `52ded6f` (test)
2. **Task 1 (GREEN): advisory label + tightened group detection + non-tabular degrade** — `8fdd6e3` (feat)
3. **Task 2 (RED): AI-decides commit contract tests** — `45900ab` (test)
4. **Task 2 (GREEN): remove cv.scheme auto-commit — AI decides, tooling writes** — `04815d7` (feat)
5. **Task 3: wire D-05 two-step Analyze flow into SKILL.md** — `bc97062` (docs)

## Files Created/Modified

- `scripts/cv_evidence.py` — `_looks_continuous_numeric` helper; tightened `detect_group_candidates` (continuous + mostly-empty guards, non-empty-based counting); `RECOMMEND_ADVISORY_NOTE` + `NON_TABULAR_NOTE`; `recommend_is_hint`/`recommend_note` on the normal path; non-tabular sentinel branch in `build_evidence`; `main` print handles the non-tabular record and labels the hint advisory. Stays stdlib-only (no pandas/sklearn).
- `scripts/analyze_data.py` — removed the `scheme = committed or evidence["recommend"]` auto-commit; write `cv.scheme` only when `--cv-scheme` given; new `_cv_section_pending`; reworded `_cv_section_body` (mechanical value labeled a non-authoritative advisory hint; dropped "matches the mechanical recommendation"); updated `--cv-scheme` help + module docstring; loud no-choice status line.
- `SKILL.md` — Analyze step rewritten as the D-05 two-step flow; framework-never-auto-picks statement; two Scripts-table rows updated.
- `tests/cv_fixtures.py` — `titanic` + `degenerate` shapes added to `SHAPES` and `_BUILDERS`.
- `tests/test_cv_evidence.py` — four new regression tests (titanic, grouped-still, advisory-hint, non-tabular); updated the two auto-commit tests to pass explicit `--cv-scheme`; added the no-scheme pending test.

## Decisions Made

- **Remove the auto-commit rather than only harden the detector.** The must-have truth is that `analyze_data.py` without `--cv-scheme` does NOT write `cv.scheme`. Even a perfect detector would still violate D-05 if the framework committed its output. Deleting the `or evidence["recommend"]` fallback is the load-bearing change; the detector tightening keeps the *advisory* hint from being egregiously wrong.
- **Conservative continuous predicate.** `_looks_continuous_numeric` requires ≥5% genuinely non-integer values, so pure-integer group ids (the `grouped` fixture) are never mis-classified as continuous — the guard only fires on fractional measurements (Age/Fare).
- **Sentinel over silent KFold for non-tabular data.** Returning `recommend = None` makes "no structure detected" explicit rather than laundering it into a plausible-looking scheme.

## Deviations from Plan

None — plan executed exactly as written. No auto-fixes, no architectural changes, no authentication gates. All three tasks landed within their declared files (`scripts/cv_evidence.py`, `scripts/analyze_data.py`, `SKILL.md`, `tests/cv_fixtures.py`, `tests/test_cv_evidence.py`).

## Threat Model

Both mitigations from the plan's STRIDE register are satisfied:
- **T-02-06-01 (Tampering — cv.scheme write):** the data-derived auto-commit is removed; `cv.scheme` is now written only from an enum-validated argv choice (`choices=cve.CV_SCHEMES`). No config value can be silently derived from data structure without an explicit AI decision.
- **T-02-06-02 (Spoofing — advisory hint):** the mechanical hint is advisory-only and explicitly labeled; the tightened detector reduces the residual misleading-hint risk. No new security-relevant surface introduced (no network endpoints, no new file access, cv_evidence stays stdlib-only, no package installs).

## Known Stubs

None. All changed code paths are wired end to end and exercised by tests.

## Verification Results

- `uv run pytest tests/test_cv_evidence.py -q` → **19 passed** (titanic StratifiedKFold + Age/Fare/Cabin not grouped, advisory labeling, AI-decides commit contract, non-tabular degrade).
- `uv run pytest tests/ -q` → **88 passed, 8 deselected** (the two former auto-commit tests updated to pass `--cv-scheme`; net test count increased; no other regression).
- SKILL.md Task-3 grep gate (`--cv-scheme` + `control/raw/cv-evidence.json` + a "framework never / AI decides" phrase) → **PASS**.

## TDD Gate Compliance

Tasks 1 and 2 each followed RED → GREEN:
- Task 1: `test(...)` `52ded6f` (3 new tests failed as expected; grouped no-regression pre-passed) → `feat(...)` `8fdd6e3` (all green).
- Task 2: `test(...)` `45900ab` (no-scheme pending test failed) → `feat(...)` `04815d7` (all green).
Both RED and GREEN gate commits are present; no REFACTOR commit was needed.

## Next Phase Readiness

- Phase 3 (experiment loop) inherits a `cv.scheme` that is an explicit AI decision — a trusted, enum-validated fact rather than a mechanical default re-read every cycle. Where the AI has not yet chosen, `cv.scheme` is honestly null with a decision-pending competition.md section, not a fabricated value.
- No blockers introduced.

## Self-Check: PASSED

- Files verified present: `scripts/cv_evidence.py`, `scripts/analyze_data.py`, `SKILL.md`, `tests/cv_fixtures.py`, `tests/test_cv_evidence.py` — all FOUND.
- Commits verified in history: `52ded6f`, `8fdd6e3`, `45900ab`, `04815d7`, `bc97062` — all FOUND.
- No `control/`, `data/`, or competition data added to the repo/worktree; no credentials; STATE.md/ROADMAP.md untouched (worktree mode — orchestrator owns those writes).

---
*Phase: 02-competition-context-data*
*Completed: 2026-07-11*
