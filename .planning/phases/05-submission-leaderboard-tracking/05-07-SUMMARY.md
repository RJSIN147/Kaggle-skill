---
phase: 05-submission-leaderboard-tracking
plan: 07
subsystem: skill-wiring / docs
tags: [skill-md, gate-protocol, cli-fixture, gitignore, human-in-the-loop]
status: CHECKPOINT — Task 3 (blocking human-verify) pending
requires:
  - scripts/check_submission.py (05-04)
  - scripts/submit.py (05-05)
  - scripts/fetch_lb.py (05-05)
  - scripts/lb_gap.py + regen_strategy.py CV→LB section (05-06)
  - scripts/kaggle_gateway.py reserved exit codes 65/69/75/77/78 (05-02)
provides:
  - SKILL.md submit gate protocol (exits 65/69/75) + the check → [human decides] → submit → fetch sequence
  - references/kaggle-cli-behavior.md Phase 5 fixture entries (submit fail-open + submissions shape)
  - scripts/templates/gitignore.tmpl stated submission.csv decision
affects:
  - SKILL.md
  - references/kaggle-cli-behavior.md
  - scripts/templates/gitignore.tmpl
tech-stack:
  added: []
  patterns: [progressive-disclosure, reserved-exit-code gate protocol, confirm-by-read-back]
key-files:
  created: []
  modified:
    - SKILL.md
    - references/kaggle-cli-behavior.md
    - scripts/templates/gitignore.tmpl
decisions:
  - "submission.csv STAYS gitignored by conscious decision — provenance lives in the file_sha256 in control/submissions.jsonl, not in a tracked heavy artifact"
  - "The A1 UTC assumption is NOT claimed as verified — it is gated behind the blocking human-verify checkpoint (Task 3) because it cannot be proven without spending a real slot"
metrics:
  duration: ~25m (Tasks 1–2; Task 3 blocked on a human gate)
  completed: 2026-07-12
requirements: [SCORE-01, SCORE-02, SCORE-03]
---

# Phase 05 Plan 07: Skill Wiring & CLI Behavior Fixture Summary

The three Phase-5 entry points are wired into the skill's human loop via the reserved-exit-code gate
protocol, and this phase's load-bearing live-CLI finding — `kaggle competitions submit` is **FAIL-OPEN**
on its exit code — is now checked into the fixture doc rather than living only in a planning artifact.

## What was built

**Task 1 — SKILL.md (commit `748ecc5`).** SKILL.md now holds the submit/don't-submit loop; no script
blocks on stdin.
- **Gate protocol** gains exits **65** (`VALIDATION_FAILED`), **69** (`SUBMIT_UNSUPPORTED`) and **75**
  (`GATE_BLOCKED`) alongside the existing 77/78. The exit-75 entry is the D-05 human decision point: it
  instructs Claude to present the script's decision material **verbatim** (CV ± std, best submitted CV,
  the margin vs. the noise bound with `k` stated, remaining slots, the CV→LB divergence state, any
  ASSUMED-budget warning), **ASK the user**, and re-invoke `submit.py --confirm` **only** on an explicit
  go-ahead. It states that `--reason` is **OPTIONAL** (D-07) and that the user is never to be required to
  justify spending their own slot, and that Claude must never auto-confirm.
- **New "Submission & leaderboard (SCORE-*)" section** documents the sequence
  `check_submission.py` (FREE) → **[the human decides]** → `submit.py --confirm` → `fetch_lb.py` →
  `regen_strategy.py`, and states plainly that **submit exit 3 = DETACHED, not failed** — the slot IS
  spent and the PENDING row IS recorded; re-run `fetch_lb.py`, never re-submit to "retry" a detach. It
  re-states SCORE-02 discipline: CV is the decision metric; the CV→LB gap is observed, never used to select.
- **Scripts table** gains `check_submission.py`, `submit.py`, `fetch_lb.py` and `lb_gap.py`, each naming
  what the script *guarantees* and its exit codes.
- SKILL.md is **461 lines** — inside the <500-line progressive-disclosure budget.

**Task 2 — the fixture doc + the gitignore decision (commit `6efa442`).**
- `references/kaggle-cli-behavior.md` had **no** submit/leaderboard entries; it now carries a Phase 5
  section recording: `submit`'s POSITIONAL slug, the **REQUIRED `-m`** message as the **only** exp_id↔Kaggle
  correlation channel (the CLI discards the submission `ref`), the **FAIL-OPEN exit-code table** with both
  verbatim literals (`Could not find competition`, `Could not submit to competition` — both exit **0**),
  that the success message is **server-authored and must never be parsed** (success is confirmed by
  **read-back**), and that **`--sandbox` is a host/admin flag, not a dry run**. For `submissions`: the
  exactly-seven-field allow-list, the fully-qualified `SubmissionStatus.` literals, scores are **strings**
  (`""` when unscored), `date` is **naive/tz-less**, ERROR rows ARE returned, `--page-token` is unusable,
  and **there is NO submission-quota command** (`kaggle quota` is GPU/TPU hours only) so the budget must be
  counted from rows. Provenance line states plainly that **`competitions submit` was never executed — no
  slot was spent** and no credential value was read or printed.
- **Deviation-adjacent addition (in scope, per the plan's CLI-behavior remit):** recorded the
  `submissions_log.fetch_submissions()` **namespace-binding footgun** — it resolves `run_kaggle` from its
  own module globals, so a caller's monkeypatch is silently bypassed and the real CLI shells out. Both
  05-04 and 05-05 hit it and routed around it, leaving it with zero callers. Future callers are pointed at
  the injectable `fetch_lb.read_submissions(..., runner=…)`. The function was **not deleted** — out of scope.
- `scripts/templates/gitignore.tmpl`: **comment-only** changes (verified — the diff contains no non-comment
  line). `submission.csv` **stays ignored BY DECISION**: it is a heavy derived artifact, provenance is
  preserved *better* by the `file_sha256` in `control/submissions.jsonl` (which proves exactly which bytes
  were uploaded), and reproducibility lives in the tracked `experiment.py` + seed + `git_commit`. Also
  records that `control/submissions.jsonl` is **tracked by design** and that
  `kaggle_gateway._append_line_if_absent` is the retrofit mechanism if a rule ever needs to reach an
  already-scaffolded workspace.

## Verification

- `uv run pytest -q` → **259 passed, 1 skipped, 12 deselected** (full mock suite green).
- `uvx ruff check scripts/` → **All checks passed** (`ruff` is not in the project `.venv`; invoked via `uvx`).
- `grep -rin "nominat\|final selection" SKILL.md scripts/ references/` → **nothing** (D-12 is documented nowhere).
- `grep -n "input(" SKILL.md` → **nothing** (the human loop is held by the SKILL, never by a script).
- Task 1 + Task 2 automated verify blocks → both pass.

## Deviations from Plan

**1. [Rule 3 - Blocking] `ruff` is not installed in the project `.venv`**
- **Found during:** Task 2 verification.
- **Issue:** `uv run ruff check scripts/` fails with `Failed to spawn: ruff`.
- **Fix:** invoked via `uvx ruff check scripts/` (no dependency added, nothing installed into the project env).
- **Files modified:** none.

**2. [Rule 1 - Bug] The plan's own Task-2 verify snippet self-tripped**
- **Found during:** Task 2 verification.
- **Issue:** the plan's assertion `'!experiments/*/submission.csv' not in g` is a naive substring check. My
  first draft of the rationale comment *quoted* that pattern to say it is deliberately absent — which the
  substring check read as the negation being present.
- **Fix:** reworded the comment to describe the absent negation without quoting the literal. The gitignore
  behavior is unchanged either way (it was always a `#` comment); the check now passes honestly.
- **Files modified:** `scripts/templates/gitignore.tmpl`.
- **Commit:** `6efa442`.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| A1 UTC verdict + submit success-path output | `references/kaggle-cli-behavior.md` (clearly-marked `<!-- PLACEHOLDER -->`) | **Intentional and gated.** Cannot be filled without spending one real, irreversible Kaggle submission slot. Task 3 (blocking human-verify checkpoint) fills it. The doc does **not** claim A1 is verified — it states plainly that the framework *assumes* UTC and that the assumption is unproven. |

## Checkpoint reached — Task 3 NOT executed

Task 3 (`checkpoint:human-verify`, `gate="blocking"`) requires **one real, human-supervised Kaggle
submission** against a live competition from a workspace with a scored experiment. It spends a **real,
irreversible daily slot** on the user's account. That is a human-action gate by definition — it was **not**
auto-approved and **not** executed. Phase 5 should not be marked complete until A1 is CONFIRMED (or REFUTED
and the budget's day boundary corrected).

## Self-Check: PASSED

- `SKILL.md` — FOUND (461 lines, <500 budget)
- `references/kaggle-cli-behavior.md` — FOUND (Phase 5 section present)
- `scripts/templates/gitignore.tmpl` — FOUND (comment-only diff)
- commit `748ecc5` — FOUND
- commit `6efa442` — FOUND
