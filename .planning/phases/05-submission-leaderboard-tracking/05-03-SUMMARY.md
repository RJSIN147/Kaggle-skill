---
phase: 05-submission-leaderboard-tracking
plan: 03
subsystem: submissions-schema
tags: [wave-2, submissions-log, exit-codes, budget, fail-closed, utc, stdlib-plumbing]

requires:
  - scripts/kaggle_gateway.py (run_kaggle, _parse_json_array — the D-16 gateway)
  - scripts/experiment_meta.py (the module contract this file is the twin of)
  - scripts/rebuild_ledger.py (_atomic_write + the compact-JSONL render)
  - scripts/poll_kernel.py (the anchored-regex / None-is-transient posture)
  - scripts/regen_strategy.py (_read_ledger — the fail-clear JSONL read)
  - tests/test_submissions_log.py, tests/test_budget.py (the 05-01 RED contract)
provides:
  - scripts/submissions_log.py (SUBMISSION_ROW_KEYS, SUB_STATUSES, parse_status,
    parse_score, parse_utc, validate_row, new_row, file_sha256, charged_today,
    COUNT_UNAVAILABLE, remaining_slots, fetch_submissions, find_by_exp_id,
    read_rows/write_rows/append_row/upsert_row, SUBMISSIONS_REL)
  - scripts/kaggle_gateway.py::VALIDATION_FAILED=65, SUBMIT_UNSUPPORTED=69, GATE_BLOCKED=75
  - scripts/templates/config.json.tmpl::submission.noise_k = 1.0
affects:
  - 05-04 (check_submission + submission_gate import the schema, budget and 65/69/75)
  - 05-05 (submit + fetch_lb import new_row/append_row/upsert_row/find_by_exp_id)
  - 05-06 (lb_gap + regen_strategy read the SCORED rows for the CV→LB join)

tech-stack:
  added: []
  patterns:
    - "one schema module imported by every entry point (the experiment_meta.py contract)"
    - "anchored full-value regex over an enum literal; None == TRANSIENT, never a terminal"
    - "-1 sentinel = COUNT_UNAVAILABLE => the caller fails closed, never guesses"
    - "injected tz-aware now_utc — the module reads no clock"
    - "tempfile + os.replace full rewrite (crash-safe in-place status transition)"

key-files:
  created:
    - scripts/submissions_log.py
  modified:
    - scripts/kaggle_gateway.py
    - scripts/templates/config.json.tmpl

decisions:
  - "charged_today implements the TEST's fail-closed contract, not RESEARCH Pattern 3's pseudocode: an unparseable status returns -1, it is NOT `continue`d"
  - "COUNT_UNAVAILABLE = -1 is a named constant, not a bare magic number, so callers branch on the name"
  - "validate_row requires all 14 keys PRESENT but only 6 non-empty — a PENDING row's null scores are legitimate"
  - "upsert_row raises KeyError on an unknown update key — the schema is closed"
  - "cv_mean/cv_std stay OUT of the row (joinable on exp_id; denormalizing creates the second source of truth D-11 prevents)"

metrics:
  duration: ~20min
  tasks: 2
  files-created: 1
  files-modified: 2
  completed: 2026-07-12
---

# Phase 5 Plan 03: Submissions Schema Foundation Summary

Built `submissions_log.py` — the ONE module owning the `submissions.jsonl` row schema, the
three Kaggle parse traps, and the fail-closed daily-budget count — plus the three reserved
sysexits-aligned exit codes the D-14 entry points branch on.

## What Was Built

**Task 1 — exit codes + `noise_k` (`7619de4`).** Three constants beside the existing 77/78
table in `kaggle_gateway.py`, each carrying its sysexits name and exact meaning:
`VALIDATION_FAILED = 65` (EX_DATAERR, D-02 pre-submit validation), `SUBMIT_UNSUPPORTED = 69`
(EX_UNAVAILABLE, D-01 code/unknown competition — a code competition submits a *kernel*, not a
file), `GATE_BLOCKED = 75` (EX_TEMPFAIL, D-05 block-by-default — deliberately *not* an error:
the gate declined to spend a scarce, irreversible slot and the human may retry immediately).
The five app codes {65, 69, 75, 77, 78} are pairwise distinct and disjoint from the reserved
{124, 126, 127, 128+}. `run_kaggle` / `classify_gate` / `dump_last_error` / `preflight_entered`
are behaviorally untouched.

`config.json.tmpl` gains `submission.noise_k: 1.0`. **The rationale, for whoever renders the
recommendation:** `cv_std` from `run_cv` is the **population** std of the fold scores, not the
standard error of the mean (which would be ~2.2x smaller at 5 folds), so requiring a gain to
exceed one full fold-std is a deliberately **conservative** bar. That is correct when the
protected resource is a scarce, irreversible daily slot: the cost of a false "submit" (a wasted
slot) exceeds the cost of a false "blocked" (the human overrides in one keystroke — D-05
guarantees they can). Readers must tolerate the key being **absent** (an already-scaffolded
workspace has no `noise_k`) and fall back to `NOISE_K_DEFAULT = 1.0`.

**Task 2 — `scripts/submissions_log.py` (`38d817f`).** The structural twin of
`experiment_meta.py`: stdlib-only, importable, no `main()`, no import side effects — so
importing it never drags in the ML stack. It owns:

- **Schema.** `SUBMISSION_ROW_KEYS`, a fixed-order 14-key tuple (the order is load-bearing: it
  is what makes a full atomic rewrite byte-stable), `SUB_STATUSES = (PENDING, SCORED, FAILED)`,
  `new_row`, and `validate_row` (returns error strings; `[]` == valid; the *caller* decides to
  skip/block — a bad row is never fabricated into a plausible one). `cv_mean`/`cv_std` are
  **deliberately excluded**: they are joinable from `ledger.jsonl` on `exp_id`, and
  denormalizing them would create exactly the second source of truth D-11 exists to prevent.
- **The three parse traps.** `parse_status` is an *anchored* full-value regex over the
  fully-qualified `SubmissionStatus.*` literal (never a substring grep — the `error.json`
  fixture's description literally contains the word COMPLETE and must still classify FAILED);
  unparseable → `None` == TRANSIENT, never a false terminal. `parse_score("")` → `None`, never
  `0.0` (a defensive `float(x or 0)` would record a fabricated LB score of zero, poisoning the
  CV→LB gap and firing a bogus divergence alarm). `parse_utc` reads Kaggle's naive ISO `date`
  as UTC.
- **The budget** (`charged_today`, `remaining_slots`, `COUNT_UNAVAILABLE = -1`) — see below.
- **Kaggle read** (`fetch_submissions`, `find_by_exp_id`) — every call routes through
  `run_kaggle` (D-16); the raw buffer is parsed, never printed.
- **File I/O** (`read_rows` / `write_rows` / `append_row` / `upsert_row`) — fail-clear
  skip-and-warn read, compact-JSONL byte-stable render (byte-*empty* when there are no rows),
  and a crash-safe `tempfile` + `os.replace` full rewrite. `upsert_row` is the in-place
  PENDING → SCORED|FAILED transition (RESEARCH R5 option (a)), which preserves ONE ROW PER
  SUBMISSION — what the D-11 join and the D-10 alarm actually want.

## Key Decisions

**The fail-closed budget contract — the sharpest thing in this plan, and a deliberate
override of the plan's own upstream source.** 05-01's summary flagged that RESEARCH's Pattern 3
pseudocode does `continue` when `parse_status` returns `None`. I implemented the **test's**
contract instead: `charged_today` returns the `-1` sentinel on **any** row with an unparseable
`status` **or** an unparseable `date`. Silently skipping an unrecognized status (e.g. a *future*
Kaggle status literal like the `SubmissionStatus.QUARANTINED` the test injects) would
**undercount** the charged submissions and let the user spend past Kaggle's real daily limit —
precisely the silent-failure class this project fails closed against everywhere else. `FAILED`
is the **only** legitimate skip (D-13: Kaggle never charged a processing-error submission, so
the arithmetic comes free with no special-casing elsewhere). `PENDING` **is** counted: the slot
was accepted and is being scored. The sentinel is a named constant (`COUNT_UNAVAILABLE`) so
downstream callers branch on the name, and `remaining_slots` returns `None` on it rather than
letting `-1` leak into arithmetic.

**The clock is always injected.** The module reads no clock at all (`grep "datetime.now()"` is
empty by design); callers pass a tz-aware `now_utc`. `test_utc_day_boundary` proves it: the
count is identical under `TZ=Pacific/Kiritimati` (UTC+14) and `TZ=Pacific/Midway` (UTC-11),
which it could not be if the day boundary were computed locally — the fixture carries rows
within two hours of *both* UTC midnight edges specifically to catch that.

**Assumption A1 is documented at the point of use.** `parse_utc` treats Kaggle's naive `date`
as UTC. This is unverified until the first real submission and 05-07 gates it behind a
human-verify checkpoint; the docstring says so rather than leaving a silent assumption in the
code.

## Deviations from Plan

None. The plan executed as written. Two elaborations its task text implied but did not spell
out: `COUNT_UNAVAILABLE` was named as a constant rather than left as a bare `-1`, and
`file_sha256(path)` was added as a helper (the plan specifies the row's `file_sha256` uses
`record_experiment`'s `"sha256:" + hexdigest` format — `tests/test_submit.py` pins that exact
format, so 05-05 needs the helper here rather than re-deriving it).

One wording adjustment to satisfy an acceptance criterion literally: the plan requires
`grep -n "subprocess" scripts/submissions_log.py` to return **nothing** (proving no direct
shell-out). My first draft used the word only in prose ("this module never spawns a subprocess
itself"). The prose was rephrased so the mechanical grep guard is honest — the guard is checking
the module never shells out, and a docstring mentioning the word would have failed it for no
semantic reason.

## Verification

| Check | Result |
|-------|--------|
| `uv run pytest tests/test_submissions_log.py tests/test_budget.py -q` | **9 passed** (was 9 RED) |
| `uv run pytest tests/test_gateway.py tests/test_config.py tests/test_init_workspace.py -q` | **16 passed** (no regression from the new codes) |
| `uvx ruff check scripts/` | **All checks passed** |
| Full suite | **215 passed, 44 failed** (was 206 passed / 53 failed) |
| Net change | **+9 passed, −9 failed** — exactly this plan's RED nodes, **zero regressions** |
| Remaining failures | all in `test_check_submission` / `test_gate_policy` (05-04), `test_submit` / `test_fetch_lb` / `test_no_credential_leak` (05-05), `test_lb_gap` / `test_regen_strategy` (05-06) — **none in this plan's scope** |
| Exit codes | `65 69 75`; {65,69,75,77,78} pairwise distinct, disjoint from {124,126,127,128} |
| Negative greps on `submissions_log.py` | `datetime.now()`, `subprocess`, `def main`, `import pandas`, `import numpy` — **all absent** |
| Positive greps | `run_kaggle`, `os.replace`, `timezone.utc`, `SUBMISSION_ROW_KEYS` — **all present** |
| Import purity | `python3 -c "import submissions_log"` — silent, no side effects |

## Known Stubs

None. Every function this plan declares is fully implemented and exercised by a passing test,
with the exception of `file_sha256` / `new_row` / `upsert_row` / `find_by_exp_id` / `fetch_submissions`,
which are implemented and lint-clean but whose *callers* arrive in 05-05 (`test_submit.py` and
`test_fetch_lb.py` already pin their expected behavior and will exercise them then).

## Threat Flags

None. No new security surface beyond what the plan's threat register anticipated. All six
`mitigate` dispositions are discharged: T-05-03-01 (`fetch_submissions` routes through the
no-echo, timeout-bounded `run_kaggle` and never prints `out`), T-05-03-02 (`find_by_exp_id`
matches untrusted Kaggle text with a strict anchored `^exp-\d{3}\b`; no path and no argv is
derived from it), T-05-03-03 (anchored `parse_status`; `None` is transient, never a false
terminal), T-05-03-04 (`parse_score("")` → `None`, never `0.0`), T-05-03-05 (injected tz-aware
`now_utc`, Kaggle-authoritative count, `-1` sentinel → caller fails closed), T-05-03-06 (full
atomic rewrite via `tempfile` + `os.replace`). Zero dependencies were installed.

## For the Next Plan

- **05-04** imports `submissions_log` for `charged_today` / `remaining_slots` / `fetch_submissions`
  and `kaggle_gateway` for `VALIDATION_FAILED` / `SUBMIT_UNSUPPORTED` / `GATE_BLOCKED`. Note
  `remaining_slots` returns `None` (not `0`) when the count is unknowable — the gate must treat
  `None` as **block**, never as "plenty left".
- **05-05** builds rows with `new_row(...)`, writes the PENDING row with `append_row` *before*
  polling (the D-08 write-ordering rule), transitions with `upsert_row(ws, kaggle_ref, ...)`, and
  correlates the read-back with `find_by_exp_id(rows, exp_id, since=...)` — pass `since` to defeat
  the stale same-exp_id decoy that `test_submit.py` plants.
- **05-04's** `NOISE_K_DEFAULT = 1.0` must fall back when `config.json` has no
  `submission.noise_k` (an already-scaffolded workspace predates the template change).

## Self-Check: PASSED

`scripts/submissions_log.py`, `scripts/kaggle_gateway.py` and `scripts/templates/config.json.tmpl`
all exist on disk with the claimed content; both commits (`7619de4`, `38d817f`) are present in
git history.
