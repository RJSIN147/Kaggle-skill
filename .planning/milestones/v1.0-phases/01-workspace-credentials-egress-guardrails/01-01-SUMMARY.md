---
phase: 01-workspace-credentials-egress-guardrails
plan: 01
subsystem: testing
tags: [pytest, skill-md, tdd, nyquist-wave-0, kaggle, egress, credentials, red-suite]

# Dependency graph
requires:
  - phase: (none — first implementation plan of Phase 1)
    provides: locked decisions D-01..D-15 (01-CONTEXT.md), validation map (01-VALIDATION.md), cross-AI review pins (01-REVIEWS.md)
provides:
  - "SKILL.md — the kaggle-exp init/invocation contract (allowed-tools + guided-then-scaffold orchestration)"
  - "pyproject.toml — skill-package metadata + pytest [tool.pytest.ini_options] with the `live` marker"
  - "tests/conftest.py + 8 RED test files — the behavioral contract (25 unit/security nodes + 1 live) that 01-02/03/04 turn GREEN"
  - "pytest installed (dev dependency group + uv.lock)"
affects: [01-02, 01-03, 01-04]

# Tech tracking
tech-stack:
  added: [pytest>=8.0 (dev-only)]
  patterns:
    - "Subprocess-driven RED tests against the documented `python3 scripts/<name>.py --workspace <dir>` contract (no top-level import of unbuilt modules -> clean collection)"
    - "Hermetic credential subprocess env (KAGGLE_* stripped; injected per-test) + throwaway git-repo fixture"
    - "Skill-package pyproject.toml (repo root) kept distinct from the scaffolded workspace pyproject.toml.tmpl"

key-files:
  created:
    - SKILL.md
    - pyproject.toml
    - .gitignore
    - uv.lock
    - tests/conftest.py
    - tests/test_init_workspace.py
    - tests/test_config.py
    - tests/test_credentials.py
    - tests/test_credentials_live.py
    - tests/test_no_credential_leak.py
    - tests/test_gitignore.py
    - tests/test_settings.py
    - tests/test_leak_scan.py
  modified: []

key-decisions:
  - "pytest declared in a [dependency-groups] dev group (+ committed uv.lock) so `uv run pytest` is reproducible; kept out of runtime deps (scripts stay stdlib-only, D-14)"
  - "kaggle package legitimacy approved (Task 1) but install DEFERRED to 01-04 per D-07 — only pytest installed here"
  - "RED negative-tests assert a decision-specific signal (e.g. 'slug' / 'config.json' / 'settings.json' in output) so a missing-script crash cannot masquerade as correct refusal"
  - "requirements SETUP-01..04 NOT marked complete: this is the interface+RED-test plan; the suite proves they are unimplemented. They go GREEN in 01-02/03/04."

patterns-established:
  - "Nyquist Wave 0: full failing suite authored before any implementation; every downstream GREEN task has a concrete pinned test"
  - "Locked decisions are mechanically pinned by tests — a decision without a test cannot silently slip"

requirements-completed: []  # interface/RED-test plan; SETUP-01..04 turn GREEN in 01-02/03/04

# Metrics
duration: ~15min (continuation — Tasks 2-3)
completed: 2026-07-09
---

# Phase 1 Plan 01: Skill Skeleton + Nyquist Wave 0 RED Suite Summary

**SKILL.md init contract + skill-package pyproject (pytest `live` marker) + a 25-node RED pytest suite that mechanically pins every locked Phase-1 decision (D-01 slug gate, D-02 deep-merge/fail-clear, D-09 settings merge, D-03/D-06 consent, git-staging scope, D-15 leak scan) before any script is written.**

## Performance

- **Duration:** ~15 min (continuation agent; Tasks 2-3 after the approved Task 1 gate)
- **Started:** 2026-07-09 (continuation)
- **Completed:** 2026-07-09T18:59:23Z
- **Tasks:** 3 (Task 1 = approved blocking-human package-legitimacy gate; Tasks 2-3 executed)
- **Files created:** 13

## Accomplishments
- **SKILL.md** declares the full guided-then-scaffold init contract: `allowed-tools` includes `Bash(python3 scripts/*)` (invocation-path consistency), and the body documents D-01 (prompt-first + script-level `--slug` gate), D-03 consent, and D-07 flag-on-fail, with the `init_workspace.py --workspace` invocation contract.
- **pyproject.toml** (the skill's OWN, repo root — distinct from the workspace `pyproject.toml.tmpl`) carries `requires-python = ">=3.11"` and `[tool.pytest.ini_options]` with the registered `live` marker.
- **pytest installed** (Task 1 approved) as a dev-only dependency; `uv.lock` pins the dev/test env.
- **Nyquist Wave 0 RED suite**: `conftest.py` + 8 `test_*.py` files (25 unit/security nodes + 1 `live`), all RED, collecting cleanly (no collection-abort errors), wired to `01-VALIDATION.md` and pinning the cross-AI-review decisions.

## Task Commits

Each task was committed atomically:

1. **Task 1: Package legitimacy gate** — no commit (blocking-human checkpoint; approved by user for `pytest` + `kaggle`; threat T-01-SC recorded mitigated)
2. **Task 2: Skill package skeleton + install pytest** — `1603a7b` (feat)
3. **Task 3: Nyquist Wave 0 RED test suite** — `aae004a` (test)

**Plan metadata:** (this SUMMARY + STATE + ROADMAP) — final docs commit

## Files Created/Modified
- `SKILL.md` — kaggle-exp skill frontmatter + guided-then-scaffold init/credential/egress orchestration contract
- `pyproject.toml` — skill-package metadata + pytest config (`live` marker)
- `.gitignore` — skill-repo hygiene (pycache/test caches/.venv); distinct from the scaffolded workspace `.gitignore`
- `uv.lock` — pins the dev/test environment (pytest)
- `tests/conftest.py` — `run_script` / `seeded_workspace` / `git_repo` / `tmp_workspace` fixtures; hermetic KAGGLE_* isolation
- `tests/test_init_workspace.py` — SETUP-01/02 layout, idempotency, git init + D-01 slug gate, deep-merge, malformed-fail-clear, scaffold-commit scope
- `tests/test_config.py` — SETUP-02 execution-target schema + no-overwrite-outside-setter
- `tests/test_credentials.py` — SETUP-03/04 precedence, command-not-found, chmod (+consent), .env-population consent, no-secret-in-subprocess
- `tests/test_credentials_live.py` — `@pytest.mark.live` real-token validation
- `tests/test_no_credential_leak.py` — SETUP-04 no-echo static scan
- `tests/test_gitignore.py` — SETUP-04 secrets ignored (+functional `git check-ignore`)
- `tests/test_settings.py` — SETUP-04 egress allowlist shape + D-09 merge + fail-clear
- `tests/test_leak_scan.py` — SETUP-04 pre-commit scanner: blocks staged secret, dotenv variants, 32-hex false-positive guard

## Decisions Made
- **pytest via dev dependency group + committed uv.lock** (not a bare ad-hoc install): makes `uv run pytest` reproducible while keeping the skill's own scripts stdlib-only (D-14). `[tool.uv] package = false` marks the repo as a non-distributable skill package so uv only manages the env.
- **kaggle install deferred to 01-04** (D-07): Task 1 approved kaggle's legitimacy, but only pytest is installed in this plan; the CONSENT SCOPE for this continuation was pytest-only.
- **Negative tests assert decision-specific output signals** so a missing-script crash cannot be mistaken for correct behavior (keeps them genuinely RED now and meaningful when GREEN).
- **requirements SETUP-01..04 NOT marked complete** — this plan is the behavioral contract + RED suite that proves those requirements are unimplemented. They are completed as the suite goes GREEN in 01-02/03/04.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Reproducible test env + repo hygiene**
- **Found during:** Task 2 (skill package skeleton + pytest install)
- **Issue:** The plan states `uv pip install pytest`, but `uv pip install` needs a target env and a bare install is not reproducible; also `uv run` treats a `[project]` as a buildable package by default (would fail — there is no importable package), and generated `.venv`/`uv.lock`/caches would otherwise be untracked.
- **Fix:** Created `.venv` (`uv venv`), ran the consented `uv pip install pytest`, additionally declared `pytest>=8.0` in `[dependency-groups] dev` and set `[tool.uv] package = false` so `uv run pytest` is reproducible and does not attempt to build the skill; committed `uv.lock`; added a repo-root `.gitignore` for `__pycache__`/`.pytest_cache`/`.venv`.
- **Files modified:** pyproject.toml, uv.lock, .gitignore
- **Verification:** `uv run pytest --markers` lists `live`; RED suite runs and exits non-zero; `git status` shows caches ignored.
- **Committed in:** `1603a7b` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing-critical: reproducible test env + hygiene)
**Impact on plan:** Necessary to make the plan's own verification (`uv run pytest`) reliable and reproducible and to keep generated artifacts out of git. No scope creep — all within the "skill package skeleton" task boundary.

## Issues Encountered
- The `uv venv` selected CPython 3.13 (satisfies the `>=3.11` floor); no action needed. `kaggle` CLI remains uninstalled, which is exactly the command-not-found path `test_credentials.py::test_kaggle_missing` will exercise GREEN in 01-04.

## Threat Model Compliance
- **T-01-SC (mitigate):** satisfied — Task 1 blocking-human legitimacy gate was completed with explicit user approval for `pytest` and `kaggle`; recorded mitigated.
- **T-01-05 (mitigate):** satisfied — only `pytest` was installed (kaggle install deferred to 01-04 behind its own consent gate).
- **T-01-11 (accept):** `allowed-tools` narrowed to the loop's minimal commands; `python3` scoped to `scripts/*` (not blanket).

## TDD Gate Compliance
This is a Nyquist Wave 0 plan (type: execute): it authors the RED suite for the phase. RED gate satisfied — `uv run pytest tests/ -q -m "not live"` exits non-zero with 25 failing nodes and clean collection. GREEN/REFACTOR gates belong to the downstream implementation plans (01-02/03/04), each with the specific test nodes pinned here.

## User Setup Required
None new in this plan. A real Kaggle token is required only to run the `-m live` credential test manually (SETUP-03 live validation), exercised in 01-04.

## Next Phase Readiness
- The invocation contract (SKILL.md) and the behavioral contract (RED tests) both exist, so 01-02/03/04 are pure GREEN work with concrete targets.
- **01-02** (scaffolder core): targets `test_init_workspace.py` (layout/idempotency/D-01 slug gate/deep-merge/malformed) + `test_config.py`.
- **01-03** (egress/git/leak hardening): targets `test_settings.py` (merge + fail-clear), `test_gitignore.py`, `test_leak_scan.py`, `test_init_workspace.py::test_git_init`/`test_scaffold_commit_excludes_stray_files`.
- **01-04** (credentials): targets `test_credentials.py` + `test_credentials_live.py` (+ install `kaggle` behind its consent gate).
- Reviewer note (01-REVIEWS.md): success criterion 5 (host enforcement) still depends on `socat` at the 01-03 human-verify checkpoint; generated-settings correctness is covered here by `test_settings.py`.

## Self-Check: PASSED
- All 13 created files verified present on disk (SKILL.md, pyproject.toml, .gitignore, uv.lock, tests/conftest.py + 8 test files).
- Both task commits verified in git log: `1603a7b` (Task 2, feat), `aae004a` (Task 3, test).
- Verifications re-run: `uv run pytest --markers` lists `live`; `uv run pytest tests/ -q -m "not live"` exits non-zero (25 failed, 1 deselected) with no collection errors.

---
*Phase: 01-workspace-credentials-egress-guardrails*
*Completed: 2026-07-09*
