---
phase: 01-workspace-credentials-egress-guardrails
plan: 02
subsystem: scaffolder
tags: [setup, scaffolder, control-plane, safe-merge, deep-merge, execution-target, stdlib, d-01, d-02, d-10, d-14]

# Dependency graph
requires:
  - phase: 01-01
    provides: "SKILL.md init contract + RED pytest suite (test_init_workspace.py, test_config.py) pinning D-01/D-02/D-10/D-14"
provides:
  - "scripts/init_workspace.py — self-locating stdlib scaffolder: slug-gated D-10 layout, control-plane, docs/.env/pyproject stubs, deep-merge safe-merge, execution-target setter"
  - "scripts/templates/*.tmpl — control-plane JSON, doc, .env, workspace-pyproject, and .gitignore templates"
  - "A complete, edit-safe, re-runnable D-10 workspace scaffold (SETUP-01/SETUP-02)"
affects: [01-03, 01-04]

# Tech tracking
tech-stack:
  added: []   # stdlib-only (D-14); no new dependency
  patterns:
    - "Self-locating script: SCRIPT_DIR = Path(__file__).resolve().parent; TEMPLATES = SCRIPT_DIR/'templates' (portability, no ${CLAUDE_SKILL_DIR})"
    - "D-02 safe-merge = create-if-absent for flat files + recursive add-missing-only deep-merge for control JSON; fail-clear (raise, don't overwrite) on corrupt JSON"
    - "JSON templates parsed to dict then field-substituted (no brace-escaping); text templates via string.Template.safe_substitute"

key-files:
  created:
    - scripts/init_workspace.py
    - scripts/templates/config.json.tmpl
    - scripts/templates/state.json.tmpl
    - scripts/templates/competition.md.tmpl
    - scripts/templates/strategy.md.tmpl
    - scripts/templates/README.md.tmpl
    - scripts/templates/env.tmpl
    - scripts/templates/pyproject.toml.tmpl
    - scripts/templates/gitignore.tmpl
  modified: []

key-decisions:
  - "test_full_layout (a mandated 01-02 GREEN target) asserts .gitignore AND .claude/settings.json exist, contradicting the plan prose that assigns both to 01-03. Resolved in favor of the mechanical test contract: write a final-content .gitignore (D-12/D-13) and an EMPTY {} settings.json stub. Both keep all 01-03 settings/git/leak nodes RED; 01-03 adds git init + egress deep-merge + leak guard on top."
  - "JSON control-plane templates carry placeholder sentinels (__SLUG__/__CREATED__) and are parsed-then-substituted, so the deep-merge operates on real dicts and no brace-escaping is needed."
  - "Setter runs as a distinct mode BEFORE the slug gate — --set-execution-target needs no --slug and is the sole overwrite path; argparse choices reject a non-enum value before any file is touched."

patterns-established:
  - "Deep-merge add-missing-only: existing keys (even type-mismatched) are never mutated; only missing keys/subkeys are added — hand edits (cv.scheme) survive re-runs"
  - "Fail-clear on corrupt control JSON: raise a typed exception, print the offending path + parse error, exit non-zero, leave bytes byte-for-byte intact"

requirements-completed: [SETUP-01, SETUP-02]

# Metrics
duration: ~25min
completed: 2026-07-10
---

# Phase 1 Plan 02: Workspace Scaffolder (SETUP-01/02) Summary

**A single self-locating, stdlib-only `init_workspace.py` turns an empty folder into the D-10 workspace — slug-gated at creation (D-01), idempotent and edit-preserving under re-run via create-if-absent + add-missing-only deep-merge (D-02), fail-clear on corrupt control JSON, with an enum-validated global execution-target setter (SETUP-02).**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-07-10
- **Tasks:** 2 (both `type=auto tdd=true`; RED suite pre-authored in 01-01)
- **Files created:** 9 (init_workspace.py + 8 templates)

## Accomplishments

- **`scripts/init_workspace.py`** — self-locating (`Path(__file__)`), `--workspace`-driven, stdlib-only (D-14):
  - **D-01 mechanical slug gate:** a FRESH workspace (no `control/config.json`) invoked without `--slug` prints a guided-flow message to stderr, exits non-zero, and creates **nothing** — the guided-then-scaffold contract is enforced by the script, not just SKILL convention. A re-run reads the slug from the existing config so `--slug` may be omitted (D-02 repair).
  - **D-10 layout:** `control/{config.json,state.json,ledger.jsonl}`, `competition.md`/`strategy.md`/`README.md`, `.env`, `pyproject.toml`, `.gitignore`, `.claude/settings.json`, and `data/` + `experiments/` dirs.
  - **D-02 safe-merge:** flat files are create-if-absent (never overwritten); control-plane JSON is create-or-**deep-merge** (recursively add missing keys/subkeys, never mutate an existing value); a **malformed** control JSON is left untouched with a fail-clear non-zero exit naming the offending path.
  - **D-14 workspace pyproject stub:** `requires-python = ">=3.11"` + uv skeleton, `dependencies = []` — clearly the competition-workspace stub, NOT the skill's own pyproject; ML deps deferred to Phase 3.
  - **D-05 `.env` stub:** placeholder `KAGGLE_USERNAME=` / `KAGGLE_KEY=` (+ commented `KAGGLE_API_TOKEN`), no real values.
- **SETUP-02 execution target:** default `local`; `--set-execution-target {local|kernel}` is the sole overwrite path (explicit user change), enum-validated by argparse `choices`; a plain re-run never resets a manually changed target.
- **Templates** (`scripts/templates/*.tmpl`): control-plane JSON schemas, human doc stubs (naming the `exp-NNN` convention, D-11), `.env`, workspace pyproject, and the final `.gitignore`.

## Test Results

Ran `uv run pytest tests/ -q -m "not live"`: **7 passed, 18 failed, 1 deselected**.

The **7 GREEN** are exactly this plan's targets (flipped RED→GREEN):

| Node | Requirement |
|------|-------------|
| `test_init_workspace.py::test_full_layout` | SETUP-01 (D-10 layout + slug recorded) |
| `test_init_workspace.py::test_safe_merge_idempotent` | SETUP-01 (D-02 idempotency) |
| `test_init_workspace.py::test_refuses_creation_without_slug` | SETUP-01 (D-01 slug gate) |
| `test_init_workspace.py::test_safe_merge_deep_preserves_nested` | SETUP-01 (D-02 deep-merge) |
| `test_init_workspace.py::test_safe_merge_malformed_json_fails_clearly` | SETUP-01 (D-02 fail-clear) |
| `test_config.py::test_execution_target` | SETUP-02 (default + setter + enum) |
| `test_config.py::test_no_overwrite_outside_setter` | SETUP-02 (no-overwrite-outside-setter) |

The **18 RED remain RED by design** — they belong to later plans: `test_settings.py` (3, egress allowlist — 01-03), `test_gitignore.py` + `test_init_workspace.py::test_git_init` + `::test_scaffold_commit_excludes_stray_files` (git init — 01-03), `test_leak_scan.py` (4, leak guard — 01-03), `test_no_credential_leak.py` (2, needs check_credentials.py + leak_scan.py — 01-03/04), `test_credentials.py` (7 — 01-04). The 1 deselected is the `-m live` credential test.

## Task Commits

1. **Task 1 — Scaffolder core (slug gate, layout, control-plane, deep-merge):** `4714fda` (feat)
2. **Task 2 — Execution-target setter (SETUP-02):** `5a642f0` (feat)

## Decisions Made

- **Mechanical test contract wins the `.gitignore`/`settings.json` conflict** (see Deviations). Both files are created here (final `.gitignore`, empty `{}` settings stub) purely so the mandated `test_full_layout` node flips GREEN, while keeping every 01-03 settings/git/leak node RED.
- **Parse-then-substitute JSON templates** (placeholder sentinels `__SLUG__`/`__CREATED__`) rather than text `str.format`, avoiding `{}`-brace escaping and letting deep-merge operate on real dicts.
- **`.gitignore` written with its FINAL content now** (D-13: anticipate Phase 3 artifacts) because it is create-if-absent — 01-03 will `git init` on top of it rather than rewrite it, flipping `test_gitignore.py` GREEN without touching the file.
- **`settings.json` is an empty `{}` stub**, not a partial allowlist, because 01-03 owns the DEEP-MERGE of the egress allowlist (D-08/D-09) — an empty base merges cleanly and cannot accidentally satisfy the allowlist-shape test early.
- **No `git init` here** (per plan): git init, the leak-guard hook, and the scaffold commit are 01-03. This keeps `test_git_init` / `test_scaffold_commit_excludes_stray_files` correctly RED.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created `.gitignore` + minimal `.claude/settings.json` to satisfy the mandated `test_full_layout` node**
- **Found during:** Task 1
- **Issue:** The plan prose (task action + `<interfaces>`) states "01-02 does NOT write `.claude/settings.json`" and "Do NOT write .gitignore … those are 01-03." But `test_full_layout` — explicitly listed in Task 1's `<automated>` verify (with `-x`) and `<acceptance_criteria>` as a REQUIRED GREEN target — asserts `(ws/'.gitignore').is_file()` and `(ws/'.claude'/'settings.json').is_file()`. The plan's own verification cannot pass without these files. This is a plan-internal contradiction between the RED contract (authored in 01-01) and the ownership prose (01-02).
- **Fix:** `init_workspace.py` create-if-absent writes (a) `.gitignore` with its final D-12/D-13 content (from `gitignore.tmpl`) and (b) `.claude/settings.json` as an empty `{}` stub. Chosen to honor the phase's stated philosophy ("locked decisions are mechanically pinned by tests"). Both are minimal enough that ALL 01-03 nodes stay RED: `test_gitignore.py` still fails its `git check-ignore` step (no git repo yet), and `test_settings.py` still fails the `sandbox.network.allowedDomains ⊇ REQUIRED_HOSTS` check (empty stub). 01-03 layers git init + the egress deep-merge onto these files with no rework of `.gitignore` and a clean `{}`→allowlist merge for settings.
- **Files modified:** scripts/init_workspace.py, scripts/templates/gitignore.tmpl
- **Verification:** `test_full_layout` PASSES; all `test_settings.py`/`test_gitignore.py`/`test_git_init` nodes remain RED.
- **Committed in:** `4714fda` (Task 1)

**2. [Rule 3 - Blocking] Added `scripts/templates/gitignore.tmpl` (a 9th template beyond the plan's declared file surface)**
- **Found during:** Task 1
- **Issue:** The plan's `files_modified` lists 7 templates; `.gitignore` needs a content source, and its `<interfaces>` safe-merge policy lists `.gitignore` among the create-if-absent files this plan writes.
- **Fix:** Added `gitignore.tmpl` (static, no substitution) for maintainability, consistent with the other templates.
- **Files modified:** scripts/templates/gitignore.tmpl
- **Committed in:** `4714fda` (Task 1)

**Note (guidance for 01-03):** `init_workspace.py` currently create-if-absents `.claude/settings.json` as `{}`. 01-03's egress work should REPLACE that stub write with the D-09 deep-merge (union `allowedDomains` + `permissions.allow`, preserve user keys, fail-clear on corrupt settings), and add `git init -b main` + the pre-commit leak guard + the `chore: scaffold workspace` commit.

**Total deviations:** 2 auto-fixed (both Rule 3, driven by the mandated `test_full_layout` contract). No architectural changes; no scope creep beyond the two stub files the test requires.

## Known Stubs

| Stub | File | Reason / Resolver |
|------|------|-------------------|
| `.claude/settings.json` written as empty `{}` | `scripts/init_workspace.py` (`scaffold()`) | Intentional per plan boundary: 01-03 owns the egress allowlist and DEEP-MERGES it (D-08/D-09). The empty stub exists only so the D-10 layout / `test_full_layout` is complete; `test_settings.py` stays RED until 01-03. |

Doc/config templates (`competition.md`, `strategy.md`) contain `_TODO (Phase 2)_` placeholders by design — the competition constitution and CV scheme are Phase 2 (COMP-*), and `config.json.cv.scheme` is `null` until then. These are correctly-scoped later-phase stubs, not defects.

## Threat Model Compliance

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-01-07 (execution-target tampering) | mitigate | ✅ argparse `choices` enum-validates `--execution-target`/`--set-execution-target`; `banana` rejected with no write. |
| T-01-08 (safe-merge re-run) | mitigate | ✅ create-if-absent + add-missing-only deep-merge; only `--set-execution-target` overwrites, and only that key. |
| T-01-11 (malformed control JSON) | mitigate | ✅ fail-clear: raise `MalformedControlJSON`, print path + parse error, exit non-zero, bytes intact. |
| T-01-12 (scaffolding before slug / D-01 bypass) | mitigate | ✅ slug gate runs before any write; a fresh workspace without `--slug` creates nothing. |
| T-01-05 (env mutation) | accept | ✅ only writes inside `--workspace`; no home/global mutation; no installs. |

## TDD Gate Compliance

RED suite pre-authored in 01-01 (Nyquist Wave 0); both tasks are `tdd="true"`. RED→GREEN verified: the 7 target nodes were RED before implementation (confirmed for `test_full_layout`/`test_execution_target`) and GREEN after. GREEN commits: `4714fda` (Task 1 feat), `5a642f0` (Task 2 feat). No REFACTOR commit needed — implementation was clean on first GREEN.

## Next Phase Readiness

- **01-03** (egress/git/leak): extend `init_workspace.py` — replace the `{}` settings stub with the D-09 egress deep-merge (+ fail-clear), add `git init -b main` + `core.hooksPath` pre-commit leak guard + `leak_scan.py`, and the `chore: scaffold workspace` commit. `.gitignore` content is already final (no rewrite). Targets: `test_settings.py`, `test_gitignore.py`, `test_leak_scan.py`, `test_init_workspace.py::test_git_init`/`::test_scaffold_commit_excludes_stray_files`.
- **01-04** (credentials): `check_credentials.py` (+ install `kaggle` behind its consent gate). Targets: `test_credentials.py`, `test_credentials_live.py`, and (with 01-03) `test_no_credential_leak.py`.

## Self-Check: PASSED
- All 9 created files verified present on disk (init_workspace.py + 8 templates) plus this SUMMARY.
- Both task commits verified in git log: `4714fda` (Task 1, feat), `5a642f0` (Task 2, feat).
- `uv run pytest tests/ -q -m "not live"` re-run: 7 passed (the plan's target nodes), 18 failed (01-03/01-04 nodes, RED by design), 1 deselected (live).
