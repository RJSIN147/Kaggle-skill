---
phase: 05-submission-leaderboard-tracking
plan: 05
subsystem: submission-entry-points
tags: [wave-3, slot-safety, fail-open, read-back, detach, reconcile, irreversible]

requires:
  - scripts/submissions_log.py (05-03 — new_row/append_row/upsert_row/find_by_exp_id/file_sha256/parse_*)
  - scripts/kaggle_gateway.py (run_kaggle, classify_gate, dump_last_error, UI_GATE/65/69/75)
  - scripts/poll_kernel.py (compute_delay — the tested full-jitter backoff math)
  - experiments/exp-NNN/submission.csv (05-02 — the file this plan submits)
  - tests/test_submit.py, tests/test_fetch_lb.py (the 05-01 RED contract)
provides:
  - scripts/submit.py (the ONE slot-spending entry point; --exp-id/--confirm/--resubmit/--dry-run/--reason)
  - scripts/fetch_lb.py (poll_lb, LB_* constants, record_outcome, read_submissions, by_ref, cv_mean, --reconcile)
  - scripts/poll_kernel.py::compute_delay(attempt, rng, *, base, multiplier, cap)
affects:
  - 05-06 (lb_gap joins the SCORED rows submit/fetch_lb write)
  - 05-07 (SKILL.md wires the --dry-run -> --confirm human gate; the A1 UTC checkpoint fires at the first real submission)

tech-stack:
  added: []
  patterns:
    - "rc == 0 is ADVISORY: a fail-open CLI is caught by MATCHING its output, then success is proven by READ-BACK"
    - "write-ordering: persist the irreversible side effect's provenance BEFORE the bounded wait that can crash"
    - "widen a tested function with keyword-only DEFAULTED params instead of forking its math"
    - "inject the gateway reference (runner=) so a shared helper is monkeypatchable from either caller"

key-files:
  created:
    - scripts/submit.py
    - scripts/fetch_lb.py
  modified:
    - scripts/poll_kernel.py

decisions:
  - "poll_lb lives in fetch_lb.py and submit.py IMPORTS it (with record_outcome/read_submissions/cv_mean) — the loop and the row-transition are written once, so the two entry points cannot drift"
  - "fetch_lb.py was committed BEFORE submit.py (task order swapped) so every commit is independently importable"
  - "read_submissions takes runner= (defaulting to the module's own run_kaggle) — submit.py passes ITS reference, which is the seam the tests monkeypatch; without it a shared fetch would bypass the patch and shell out for real"
  - "the confirming read-back doubles as the first poll tick: an already-COMPLETE confirmation short-circuits the poll entirely (zero extra reads, zero sleeps)"
  - "--budget-s is the flag (05-01's pin), with --budget kept as an alias (the plan's spelling) — both scripts accept both"
  - "an out-of-band --reconcile row gets file=None and file_sha256=None: the local bytes are genuinely unknown and a hash we did not compute is never invented"

metrics:
  duration: ~40min
  tasks: 3
  files-created: 2
  files-modified: 1
  completed: 2026-07-12
---

# Phase 5 Plan 05: submit.py + fetch_lb.py Summary

The irreversible surface now exists — and a submission that did not land can never be
reported as success, because `rc == 0` is treated as advisory and the proof is a read-back.

## What Was Built

**Task 1 — `compute_delay` widened (`bba1d86`).** Three keyword-only params
(`base` / `multiplier` / `cap`) defaulting to the kernel constants. Backward compatibility
is therefore true *by construction*: every existing caller passes nothing and gets
byte-identical behavior (all four Phase-4 poller tests, including `test_backoff_budget`,
stay green). `poll_loop`, `classify_status`, `_STATUS_RE`, `TERMINAL`, `IN_FLIGHT` and
`main` were not touched. This is what lets the leaderboard poll reuse the already-tested
full-jitter math at a *different time scale* rather than forking it — LB scoring takes
seconds-to-minutes, so a 10s first tick wastes the common case and a 2-minute sleep is
absurd against a 30-second scorer.

**Task 3 — `scripts/fetch_lb.py` (`a76902d`).** Committed *before* `submit.py` (see
Deviations). It owns:

- **`poll_lb(status_fn, *, now, sleep, rng, budget_s, max_consecutive_errors, select=None)`** —
  the `poll_kernel.poll_loop` shape at LB constants (`LB_BASE_DELAY=5.0`,
  `LB_MAX_DELAY=30.0`, `LB_BUDGET_S=600`, `MAX_CONSECUTIVE_ERRORS=5`). Budget is checked
  **before** the sleep; an unparseable status is TRANSIENT (never a false terminal) and the
  blip counter resets on any clean parse. The injected `now`/`sleep`/`rng` seam is what
  makes the detach path testable with zero real waiting.
- **The resume path** — re-read the `submissions.jsonl` handoff row and transition it
  **in place** (`upsert_row`) to `SCORED`/`FAILED`. It resumes by re-reading the handoff,
  **never by re-doing the side effect** — exactly as `poll_kernel` resumes from
  `kernel_run.json`. A second run is a byte-identical no-op.
- **`--reconcile`** — back-fills rows present on Kaggle but absent locally (out-of-band
  submissions from the website or another machine). `exp_id` is recovered only via the
  anchored `^exp-\d{3}\b` regex (else `null`), `file_sha256` is `null`, no local row is
  ever deleted, and the write is a full atomic rewrite. It is byte-idempotent because
  `_apply_kaggle` returns *whether the row changed* — so `scored_at` is stamped once and
  then kept, and a second reconcile touches nothing.
- **`record_outcome`** — the ONE recorder both entry points share.

**Task 2 — `scripts/submit.py` (`e47eaab`).** The slot-spending entry point. The whole file
is organized around the fail-open table: the two client-hardcoded literals
(`Could not find competition`, `Could not submit to competition`) are **matched** while the
CLI exits **0**, the server-authored success string is **never parsed**, and success is
established only by read-back — `find_by_exp_id(rows, exp_id, since=started)`, anchored on
`^exp-\d{3}\b` and gated on `date >= started`, which defeats both decoys the test plants (a
prefix-colliding `exp-0071` and a stale same-`exp_id` row from three days ago). The
read-back is simultaneously the proof, the source of the Kaggle `ref` the submit call
discards, and the first poll tick.

Write ordering is the other spine: the PENDING row (`exp_id` + `ref` + `file_sha256`) is
appended **before** `poll_lb` is entered, so a crash mid-poll leaves a spent slot fully
traceable rather than invisible. Also: a double-spend guard (same `exp_id` + same file hash,
non-`FAILED` ⇒ refuse *before* the gateway, pointing at `fetch_lb.py`, overridable with
`--resubmit`), a TOCTOU re-hash immediately before the argv is built, `--dry-run` (the only
safe rehearsal — the CLI has none), `--confirm` block-by-default, and `meta.json` never
written.

## Key Decisions

**`submit.py` imports the loop from `fetch_lb.py` rather than duplicating it.** The plan
asked for the loop to be *shared, not forked*, and 05-01 pinned `poll_lb` onto the
`fetch_lb` module namespace — so `fetch_lb` is the home, and `submit` imports `poll_lb`,
`record_outcome`, `read_submissions`, `by_ref` and `cv_mean` from it. The two entry points
therefore transition a row, report a score, and pick an exit code through *the same code*,
and cannot drift. `fetch_lb` importing `submit` would have been the wrong direction (the
read-only script must never even be able to reach the submit argv); this direction keeps
`grep -n '"submit"' scripts/fetch_lb.py` empty.

**The gateway reference is injected, not imported, into the shared fetch.** This was a real
trap. `submissions_log.fetch_submissions` already exists and issues the exact right argv —
but it calls `run_kaggle` bound in *`submissions_log`'s* namespace, while every test
monkeypatches `run_kaggle` on the *importing* module (`submit` / `fetch_lb`). Calling it
would have silently bypassed the patch and shelled out to the real CLI. So
`fetch_lb.read_submissions(slug, *, timeout, runner=None)` takes the caller's own gateway
reference (defaulting to its own), and `submit.py` passes `runner=run_kaggle` — one copy of
the argv, and the monkeypatch seam holds from both callers.

**The confirming read-back short-circuits the poll when Kaggle already scored.** If the
confirmation row is already `COMPLETE`/`ERROR`, `poll_lb` is never entered — no redundant
read and, crucially, no sleep. That is also why `test_pending_row_written_before_poll`
(whose fake explodes on the *second* read-back) completes instantly rather than waiting out
a real 5-second backoff: the first poll tick is the exploding call, and it happens before
any sleep.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 3 was committed before Task 2 (file order, not scope)**
- **Found during:** Task 2
- **Issue:** `submit.py` imports `poll_lb` / `record_outcome` from `fetch_lb.py` (the plan's
  own instruction: "share the loop via a small helper rather than duplicating it", and
  05-01 pinned `poll_lb` onto the `fetch_lb` namespace). Committing `submit.py` first would
  have produced a commit whose module cannot be imported.
- **Fix:** `fetch_lb.py` (Task 3) landed in `a76902d`, then `submit.py` (Task 2) in
  `e47eaab`. Both tasks were executed and verified in full; only their commit order swapped,
  so every commit in the history is independently importable and test-green.
- **Files modified:** none beyond the planned three.
- **Commits:** `a76902d`, `e47eaab`

**2. [Rule 2 - Missing critical functionality] `--budget-s` accepted alongside `--budget`**
- **Found during:** Task 3
- **Issue:** The plan specifies `--budget`; 05-01's RED suite pins `--budget-s` (and
  `test_detach_preserves_pending` invokes it). A single spelling would have broken one of
  the two contracts.
- **Fix:** both scripts declare `ap.add_argument("--budget-s", "--budget", dest="budget_s", ...)`,
  so both spellings work and the tests and the plan text are simultaneously honored.

**3. [Rule 2 - Missing critical functionality] A crashed poll is caught, not propagated**
- **Found during:** Task 2
- **Issue:** If `poll_lb` raises (network death mid-poll), an uncaught exception would exit
  with a traceback — leaving a user who just spent an irreversible slot with no idea that
  the slot survived.
- **Fix:** the poll is wrapped; on any exception `submit.py` prints that the submission WAS
  accepted, names the `ref`, states that the PENDING row is already on disk and nothing was
  lost, points at `fetch_lb.py`, and returns 4. The row is never rolled back.

No architectural changes; no dependencies installed.

## Verification

| Check | Result |
|---|---|
| `pytest tests/test_submit.py -q` | **10 passed** (was 10 RED) |
| `pytest tests/test_fetch_lb.py -q` | **4 passed** (was 4 RED) |
| `pytest tests/test_poll_kernel.py -q` | **4 passed** — the widened signature regressed nothing |
| Full suite | **229 passed, 30 failed, 1 skipped** (was 215 / 44) |
| Net change | **+14 passed, −14 failed** — exactly this plan's RED nodes, **zero regressions** |
| Remaining 30 failures | `test_check_submission` (14) + `test_gate_policy` (7) → **05-04**; `test_lb_gap` (3) + `test_regen_strategy` (3) → **05-06**; `test_no_credential_leak` (3) → blocked on 05-04's `check_submission.py` (see below) |
| `uvx ruff check scripts/` | **All checks passed** |
| `grep -n '"-k"\|"-v"\|"--sandbox"' scripts/submit.py` | **empty** — no code-competition flag, no host/admin flag |
| `grep -c 'Could not find competition'` / `'Could not submit to competition'` | **1 / 1** — both fail-open literals are matched |
| `grep -n "subprocess\|input(\|print(out\|print(combined"` (both scripts) | **empty** |
| `grep -n '"submit"' scripts/fetch_lb.py` | **empty** — fetch_lb structurally cannot spend a slot |
| `grep -rn "competitions submit" tests/ \| grep -v test_submit.py` | **empty** — the source guard holds |
| `pytest tests/test_no_credential_leak.py` with a stub `check_submission.py` | **6 passed** — proving my two scripts pass the static scan *and* the behavioral token-quarantine node |

**The 3 `test_no_credential_leak` failures are not mine and are not a regression.** That
module's `PHASE5_SCRIPTS` list includes `check_submission.py`, which is **05-04's** file
(built concurrently in another worktree). Its three nodes assert *all four* Phase-5 scripts
exist. I verified the scan passes against my scripts by temporarily stubbing that file: all
6 nodes pass, including `test_submit_quarantines_a_token_shaped_buffer` (the `kagat_`
sentinel is quarantined to `control/raw/last-error.txt`, never printed). The stub was
removed; those nodes go green on merge with 05-04.

## Known Stubs

None. Both scripts are fully wired end-to-end.

## Threat Flags

None beyond the plan's register. All eight `mitigate` dispositions are discharged:
T-05-05-01 (rc==0 advisory + both fail-open literals matched + read-back confirmation;
pinned by three tests), T-05-05-02 (double-spend refusal before the gateway), T-05-05-03
(TOCTOU re-hash before the argv; the hash is persisted in the row), T-05-05-04 (PENDING row
written before the poll; `--reconcile` as the second net), T-05-05-05 (the buffer is matched
then quarantined via `dump_last_error`; a 403 goes through `classify_gate` → 77),
T-05-05-06 (anchored `^exp-\d{3}\b`; no path and no argv is derived from Kaggle text —
`--reconcile` deliberately does not even use Kaggle's `fileName`), T-05-05-07 (bounded
budget checked before each sleep, full jitter capped at 30s, detach-not-cancel),
T-05-05-08 (the host/admin flag is never passed; `--dry-run` is the real rehearsal).
T-05-05-SC: zero dependencies installed.

## For the Next Plan

- **05-06** joins the `SCORED` rows these scripts write. `public_score` is always a parsed
  `float` or `None` — never Kaggle's `""` and never a fabricated `0.0` — so a `None` means
  "not scored", not "scored zero".
- **05-07** wires the human gate: the SKILL.md loop should run `submit.py --dry-run` first
  (it prints the exact command and touches nothing), then `--confirm`. Exit **3** means
  DETACHED — the slot is spent and safe; tell the user to run `fetch_lb.py`. Exit **75**
  means the gate declined (not an error). `--reason` is optional and is only recorded when
  supplied (D-07).
- **Assumption A1 (Kaggle's naive `date` is UTC) is now load-bearing in a second place:**
  the read-back's `since=started` comparison. 05-07's human-verify checkpoint at the first
  real submission should confirm it there too.

## Self-Check: PASSED

`scripts/submit.py`, `scripts/fetch_lb.py` and `scripts/poll_kernel.py` all exist on disk
with the claimed content; all three commits (`bba1d86`, `a76902d`, `e47eaab`) are present in
git history.
