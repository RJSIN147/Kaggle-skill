---
phase: 05-submission-leaderboard-tracking
plan: 01
subsystem: testing
tags: [nyquist-wave-0, red-suite, fixtures, slot-safety, submission, leaderboard]

requires:
  - tests/conftest.py (run_script, tmp_workspace, scripts/ on sys.path)
  - tests/test_gateway.py (the monkeypatch-the-gateway seam)
  - tests/test_poll_kernel.py (_FakeClock, _sequence, the source-guard pattern)
  - tests/test_resolve_data_dir.py (render_experiment)
  - scripts/kaggle_gateway.py (run_kaggle, _parse_json_array, dump_last_error)
provides:
  - tests/fixtures/submissions/* (8 live-captured fixture files)
  - tests/test_submissions_log.py (SUBMISSION_ROW_KEYS, parse_status, parse_score, atomic rewrite)
  - tests/test_budget.py (charged_today, parse_utc, fetch_submissions — the fail-closed contract)
  - tests/test_gate_policy.py (NOISE_K_DEFAULT, is_meaningful, decide)
  - tests/test_lb_gap.py (join_cv_lb, rank_inversions, alarm_body)
  - tests/test_check_submission.py (exit 65/69/75; the FREE gate)
  - tests/test_submit.py (argv shape, fail-open guards, read-back correlation, source guard)
  - tests/test_fetch_lb.py (poll_lb, LB_MAX_DELAY/LB_BUDGET_S; detach/resume/reconcile)
  - tests/test_submission_live.py (read-only CLI-drift canary)
affects:
  - 05-02 (run_cv D-09 emission), 05-03 (submissions_log + exit codes), 05-04 (gate),
    05-05 (submit/fetch_lb), 05-06 (lb_gap + regen_strategy), 05-07 (SKILL.md wiring)

tech-stack:
  added: []
  patterns:
    - "monkeypatch.setattr(<module>, 'run_kaggle', fake) — patched on the IMPORTING module"
    - "imports of not-yet-built modules live INSIDE test bodies (collection never crashes at RED)"
    - "fixtures TRANSCRIBED from live capture, never hand-invented"
    - "mechanical source guard for an irreversibility rule (grep test_*live*.py)"

key-files:
  created:
    - tests/fixtures/submissions/complete.json
    - tests/fixtures/submissions/pending.json
    - tests/fixtures/submissions/error.json
    - tests/fixtures/submissions/unscored.json
    - tests/fixtures/submissions/empty.json
    - tests/fixtures/submissions/mixed_today.json
    - tests/fixtures/submissions/submit_404.txt
    - tests/fixtures/submissions/submit_upload_failed.txt
    - tests/test_submissions_log.py
    - tests/test_budget.py
    - tests/test_gate_policy.py
    - tests/test_lb_gap.py
    - tests/test_check_submission.py
    - tests/test_submit.py
    - tests/test_fetch_lb.py
    - tests/test_submission_live.py
  modified:
    - tests/test_run_cv.py
    - tests/test_regen_strategy.py
    - tests/test_no_credential_leak.py

decisions:
  - "lb_gap.alarm_body(pairs, greater_is_better) -> str is the renderer regen_strategy._lb_gap_body splices (05-06); the honesty line is the exact string 'needs >=2 scored submissions (have N)'"
  - "fetch_lb exposes poll_lb(status_fn, *, now, sleep, rng, budget_s, max_consecutive_errors) + a --budget-s flag, so detach is testable on an injected clock with no real waiting"
  - "submit.py CLI surface: --exp-id, --confirm, --resubmit, --dry-run, --reason (D-07 optional)"
  - "test_no_credential_leak.py keeps Phase-1 EXPECTED_SCRIPTS green and adds a separate PHASE5_SCRIPTS list, so the extension adds RED nodes without reddening existing ones"
  - "join_cv_lb rows are keyed {exp_id, cv_mean, lb_score, gap} with gap = lb_score - cv_mean"

metrics:
  duration: ~35min
  tasks: 3
  files-created: 16
  files-modified: 3
  completed: 2026-07-12
---

# Phase 5 Plan 01: Nyquist Wave 0 RED Suite Summary

Landed the live-captured fixtures and 53 failing test nodes that pin the entire Phase-5
submission contract before any Phase-5 script exists — with a mechanical source guard proving
no test can ever spend a real submission slot.

## What Was Built

Three commits, one per task.

**Task 1 — the fixtures (`c8704d2`).** Eight files under `tests/fixtures/submissions/`,
transcribed from `05-RESEARCH.md`'s live capture against CLI 2.2.3 rather than invented (the
lesson Phase 2 recorded in `references/kaggle-cli-behavior.md`). Each `.json` carries exactly
the seven live-verified keys in order, the fully-qualified `SubmissionStatus.*` literals, the
**string** `publicScore`, and the **naive** ISO `date`. `unscored.json` pins the `""` score
that must parse to `None` and never `0.0`. `mixed_today.json` is the budget fixture: six rows
across two fixed UTC days, including a today-dated ERROR (not charged, D-13), a today-dated
PENDING (charged), and rows within two hours of *both* UTC midnight edges so a TZ-parametrized
test can actually detect a local-time day boundary. `submit_404.txt` and
`submit_upload_failed.txt` carry the two fail-open stdout literals the CLI prints *while
exiting 0*, plus a `kagat_TOKENLEAK_SENTINEL_ZZZZ` sentinel for the no-echo assertions.

**Task 2 — the data + decision tier (`91d7fc2`).** Four RED modules, 19 nodes:
`test_submissions_log.py` (anchored status parse tolerating both renders; `""` → `None`;
fixed-order 14-key `SUBMISSION_ROW_KEYS`; compact-JSONL atomic rewrite with no `.tmp`
residue), `test_budget.py`, `test_gate_policy.py` (the D-06 noise matrix in both metric
directions, strictly-greater, configurable `k`; the first-submission-is-clear baseline; D-05
block-by-default; the D-08 last-assumed-slot confirmation), and `test_lb_gap.py`
(SCORED-only gap trend; direction-aware D-10 rank inversion; the honest `<2 scored` line).

**Task 3 — the entry points (`195604d`).** Four more RED modules plus RED extensions to three
existing ones. `test_submit.py` is the slot-safety core: exact argv (and the proof that `-k`,
`-v` and `--sandbox` are never passed — `--sandbox` is a host/admin flag, not a dry run), both
fail-open guards, read-back confirmation with anchored `^exp-\d{3}\b` correlation (defended by
a prefix-colliding `exp-0071` decoy and a stale same-exp_id decoy), PENDING-row-before-poll
write ordering, double-spend refusal, `meta.json` byte-immutability, and `--dry-run`.

## Key Decisions

**The fail-closed budget contract was the sharpest thing to get right.** `charged_today`
returns the `-1` sentinel on *any* row whose status or date it cannot parse — it must **not**
silently skip an unrecognized status. Skipping would undercount the charged submissions
against a future Kaggle status literal and let the user submit past the real daily limit. Only
`FAILED` is a legitimate skip (D-13). `test_fails_closed_when_count_unavailable` states this
in the same words 05-03 Task 2 will implement it in, and the plan's own `charged_today`
pseudocode in RESEARCH Pattern 3 (which *does* `continue` on `st is None`) is superseded by
this contract — the plan flagged that conflict as a resolved BLOCKER and the test now pins the
correct side of it.

**Three interfaces the plan left underspecified had to be pinned so the tests could exist.**
`lb_gap.alarm_body()` (the renderer `regen_strategy._lb_gap_body` splices in 05-06),
`fetch_lb.poll_lb()` with injected `now`/`sleep`/`rng` plus a `--budget-s` flag (without an
injection seam the detach path cannot be tested without real waiting), and `submit.py`'s flag
surface. All three are documented in the module docstrings so 05-05/05-06 implement against
them exactly.

**`test_no_credential_leak.py` was extended additively.** Adding the Phase-5 scripts to the
existing `EXPECTED_SCRIPTS` list would have reddened the two Phase-1 nodes that are legitimately
green. A separate `PHASE5_SCRIPTS` list and separate nodes keep the old contract intact.

## Deviations from Plan

None — the plan executed as written. The three interface pins above are elaborations the plan's
own task text demanded (it specifies a renderer, an injected clock, and a `--dry-run`/`--confirm`
surface) rather than departures from it.

## Verification

| Check | Result |
|-------|--------|
| `uv run pytest --collect-only -q` (whole suite) | 259 collected, **no collection crash** |
| `uv run pytest tests/test_submit.py::test_no_live_test_ever_submits -x -q` | **1 passed** (GREEN immediately) |
| `grep -rn "competitions submit" tests/ \| grep -v test_submit.py` | **empty** |
| Full suite | **53 failed, 206 passed, 1 skipped** |
| Failing modules | all 9 are Wave-0 targets — **zero pre-existing regressions** |
| All 33 nodes named in 05-VALIDATION.md's map | **present verbatim** |

The 53 failures are the intended RED: every one is a `ModuleNotFoundError` for
`submissions_log` / `submission_gate` / `lb_gap` / `check_submission` / `submit` / `fetch_lb`,
or an assertion that a not-yet-built script is absent. Nothing passes vacuously and nothing is
silently skipped. `tests/test_run_cv.py` keeps its module-level `importorskip` gating, so the
three new D-09 nodes **SKIP** (never RED) when numpy/sklearn are absent — exactly as required.

## Slot-Safety Posture (the phase's defining constraint)

Four enforcement layers are now live, and none of them depends on anyone remembering the rule:

1. **Every unit test monkeypatches `run_kaggle`.** No CLI process is spawned anywhere in the
   suite; tests assert on the captured argv, which is how the exact command shape is proven
   without executing it.
2. **Fixtures are transcribed, not invented** — so the tests pin the real CLI, including the
   two fail-open literals that make `rc == 0` an unreliable success signal.
3. **`test_no_live_test_ever_submits` is a mechanical source guard** over every
   `tests/test_*live*.py`, and it is green from the moment it was written.
4. **`test_submission_live.py` is structurally read-only** — it lists submissions and cannot
   create one.

`test_check_submission.py::test_never_submits` additionally asserts, from the captured argv on
*every* code path (clear / blocked / validation-failed / unsupported), that the free gate never
reaches the submit subcommand.

## Known Stubs

None. This plan deliberately ships only tests and fixtures — the RED failures are the
contract, not a stub.

## Threat Flags

None. This plan adds no runtime surface: it creates test modules and fixture files only, and
installs zero dependencies (T-05-01-SC in the plan's threat register is `accept` for exactly
this reason). The three `mitigate` dispositions are all discharged: T-05-01-01 by the source
guard + universal gateway monkeypatching, T-05-01-02 by the `kagat_TOKENLEAK_SENTINEL_ZZZZ`
fixture and the no-echo assertions in `test_submit.py` and `test_no_credential_leak.py`, and
T-05-01-03 by transcribing the fixtures from live capture and adding the drift canary.

## For the Next Plan

Every downstream plan turns a named subset of these nodes GREEN:

- **05-02** → `test_run_cv.py::{test_submission_optional, test_label_aggregation_is_not_mean,
  test_test_preds_use_fold_preprocessor}`. Note the trap the tests now enforce: titanic's
  `accuracy` is a **label** metric, so fold predictions must **vote**, never mean — a mean
  emits `0.4`/`0.6` where Kaggle wants `0`/`1`, and D-02's validator would pass that file.
- **05-03** → `test_submissions_log.py`, `test_budget.py`, plus the 65/69/75 constants in
  `test_gateway.py`.
- **05-04** → `test_gate_policy.py`, `test_check_submission.py`.
- **05-05** → `test_submit.py`, `test_fetch_lb.py`, `test_no_credential_leak.py`.
- **05-06** → `test_lb_gap.py`, `test_regen_strategy.py::test_lb_block_rendered`.
- **05-07** → `test_submission_live.py` (and the blocking A1 UTC checkpoint at the first real
  submission).

## Self-Check: PASSED

All 19 declared files exist on disk; all 3 commits (`c8704d2`, `91d7fc2`, `195604d`) are
present in git history.
