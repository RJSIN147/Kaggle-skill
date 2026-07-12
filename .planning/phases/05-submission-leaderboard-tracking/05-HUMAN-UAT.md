---
status: partial
phase: 05-submission-leaderboard-tracking
source: [05-07-PLAN.md, 05-07-SUMMARY.md]
started: 2026-07-12
updated: 2026-07-12
---

## Current Test

[awaiting first real Kaggle submission — requires live credentials and spends an irreversible daily slot]

## Tests

### 1. A1 — verify `submissions.date` is UTC

The Kaggle CLI returns `submissions.date` as a **naive ISO string with no timezone
suffix**. `check_submission.py`'s budget accounting assumes it is UTC. The assumption is
recorded but **unproven** — it cannot be verified without one real submission.

Deferred deliberately at the Phase 5 checkpoint (2026-07-12): no Kaggle credentials and no
scored workspace existed on the machine, and verifying it spends a real daily slot.

**Impact if REFUTED:** the daily submission count is wrong near the day boundary. The
framework could refuse a submission the user is entitled to, or permit an attempt over the
limit (Kaggle rejects that server-side, and per project notes failed submissions do not
count). This is a day-boundary correctness bug in budget accounting, not a slot-safety
hole — no other Phase 5 behavior depends on A1.

`references/kaggle-cli-behavior.md` carries a clearly-marked `<!-- PLACEHOLDER -->` at
line ~289 and states plainly that the framework *assumes* UTC. Nothing in the codebase
claims A1 is verified.

**Procedure** (in a workspace with a scored experiment):

1. `uv run python scripts/check_submission.py --workspace <ws> --exp-id exp-NNN` —
   confirm it prints the decision material, exits 0 or 75, and submits nothing.
2. **Note the UTC wall clock** (`date -u`). This is the whole check — write it down.
3. `uv run python scripts/submit.py --workspace <ws> --exp-id exp-NNN --confirm`
4. Confirm success is reported only after **read-back confirmation** (the recovered Kaggle
   `ref`), not from `rc == 0`.
5. Confirm `control/submissions.jsonl` gained one row with `exp_id`, `kaggle_ref`,
   `file_sha256`, status PENDING/SCORED — and that `experiments/exp-NNN/meta.json` is
   byte-identical (D-11 immutability).
6. Compare the returned `date` to the UTC clock from step 2.

expected: returned `date` matches the UTC wall clock from step 2 → **A1 CONFIRMED**.
If it differs by your local UTC offset → **A1 REFUTED**, and the day-boundary handling in
`check_submission.py`'s budget accounting must be corrected.

result: [pending]

**On completion:** fill the `<!-- PLACEHOLDER -->` in `references/kaggle-cli-behavior.md`
with the observed values and the verdict.

**Scripting note:** do not use `submissions_log.fetch_submissions()` — it has zero callers
and resolves `run_kaggle` from its own module globals (see the open item below). Use
`fetch_lb.read_submissions(..., runner=…)` instead.

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps

### Open item — `submissions_log.fetch_submissions()` is dead code and a footgun

status: open
severity: low (no live caller; blocks nothing; suite is 259/259 green)

Surfaced only at post-merge integration — no individual plan agent could see it, since each
worked in an isolated worktree. Plans 05-04 and 05-05 both hit the function's
namespace-binding trap and each routed around it differently (05-04 defined a local fetch;
05-05 used the injectable `read_submissions(..., runner=)`), leaving the original with zero
callers.

The trap: it resolves `run_kaggle` from its **own** module globals, so a caller that
monkeypatches `run_kaggle` on the *importing* module is silently bypassed — and the real
Kaggle CLI shells out from inside what the author believes is a mocked test.

The trap is documented in `references/kaggle-cli-behavior.md`. Deleting the function was
out of scope for 05-07 and is left as a deliberate decision: either remove it, or give it a
`runner=` parameter so it is safe to call.
