---
phase: 04-kaggle-kernel-execution-gpu-path
plan: 06
subsystem: kernel-execution / anti-lie recorder
tags: [gap-closure, CR-01, WR-03, fail-closed, kernel_error, TDD]
gap_closure: true
requires:
  - scripts/record_experiment.py (kernel-path classification ladder, 04-04)
  - scripts/poll_kernel.py (authoritative kernel_run.json.status writer, 04-03)
provides:
  - "kernel_run.json.status classification rung (ERROR/CANCEL_ACKNOWLEDGED => FAILED(kernel_error))"
  - "WR-03 unreadable-log fail-closed rung"
  - "meta['kernel']['status'] audit copy on SUCCESS and FAILED paths"
affects:
  - the record step of the D-02 loop (kernel path only; local path unchanged)
tech-stack:
  added: []
  patterns:
    - "authoritative-source-first classification (poll-written status beats stale result.json)"
    - "fail-closed on unreadable evidence (WR-03)"
    - "read-once, reuse (kernel_run.json read a single time for classification + provenance)"
key-files:
  created: []
  modified:
    - scripts/record_experiment.py
    - tests/test_record_kernel.py
decisions:
  - "kernel_run.json.status is authoritative and consulted BEFORE result.json validation; exact membership {ERROR, CANCEL_ACKNOWLEDGED} only (no substring/regex/eval), never echoed."
  - "An unreadable/missing --kernel-log fails CLOSED to FAILED(kernel_error) rather than deferring to a possibly-stale result.json (WR-03)."
  - "kernel_error reason REUSED (no new FAILURE_REASONS entry); local path left byte-for-byte unchanged."
metrics:
  duration: ~3min
  completed: 2026-07-11
  tasks: 2
  files: 2
---

# Phase 04 Plan 06: Kernel-Failure Fail-Closed Hardening (CR-01 + WR-03) Summary

Closed the phase's status-driving BLOCKER (CR-01) and its in-scope fail-closed hardening (WR-03) in the anti-lie recorder: the kernel-path classification ladder now consults the authoritative poll-written `kernel_run.json.status` BEFORE it validates `result.json`, so a Kaggle-confirmed terminal failure (`ERROR`/`CANCEL_ACKNOWLEDGED`) that left a stale valid `result.json` behind can never be recorded SUCCESS — delivering truth 11 ("silent kernel failure caught") for real, with a regression test that would catch any future reopening.

## What Was Built

- **CR-01 status rung** (`scripts/record_experiment.py`): on the kernel path only, `kernel_run.json` is read once via the existing fail-clear `_read_json`; if its `status` is exactly in `{"ERROR", "CANCEL_ACKNOWLEDGED"}` the run is classified `FAILED(kernel_error)` unconditionally, before any log read or `_validate_result` call. Exact membership test only — never substring/regex/eval, never printed.
- **WR-03 fail-closed rung**: an unreadable/missing `--kernel-log` now yields `FAILED(kernel_error)` instead of setting `log_text = None` and deferring to the (possibly stale) result ladder.
- **Status audit copy**: `meta["kernel"]["status"]` is populated from `kernel_run.json.status` on BOTH the SUCCESS and FAILED paths; the provenance merge reuses the already-parsed `kernel_run` object (read once, not twice).
- **Five regression tests** (`tests/test_record_kernel.py`): status=ERROR + clean log + valid result ⇒ FAILED; status=CANCEL_ACKNOWLEDGED ⇒ FAILED; the audit copy on the FAILED path; unreadable/missing `--kernel-log` ⇒ FAILED; and status=COMPLETE ⇒ SUCCESS with the audit copy firing. Plus a `_write_kernel_run` helper mirroring poll_kernel's terminal statuses.

## Task-by-Task

| Task | Name | Gate | Commit | Files |
| ---- | ---- | ---- | ------ | ----- |
| 1 | RED regression tests | test | `9534edc` | tests/test_record_kernel.py |
| 2 | GREEN status rung + WR-03 + audit copy | fix | `d4684f1` | scripts/record_experiment.py |

TDD gate sequence honored: RED (`test(04-06)`) — 5 new tests failing against unfixed code (Tests A/B/D recorded SUCCESS, C/E found no `status` key) — landed before GREEN (`fix(04-06)`).

## Verification

- `uv run pytest tests/test_record_kernel.py -q` → 9 passed (5 new + 3 kernel + 1 source-invariant), exit 0.
- `uv run pytest -q` → 204 passed, 1 skipped, 9 deselected (>=199 requirement met).
- Scope guard: `git diff --stat` per commit touched ONLY `scripts/record_experiment.py` and `tests/test_record_kernel.py` — push_kernel.py, poll_kernel.py, SKILL.md, and the CR-02/WR-04/WR-01 surfaces untouched.
- `grep -n status scripts/record_experiment.py` confirms `kernel_run.json.status` consulted in the classification section AND copied into `meta["kernel"]`.

## Threat Mitigations Applied

- T-4-06-01 (Tampering): exact-allowlist membership on untrusted `status` — a crafted string can only ever force a FAILED, never a SUCCESS.
- T-4-06-02 (Info-Disclosure): status/log used for classification and written to meta.json only, never echoed (truth 5 preserved).
- T-4-06-03 (DoS): malformed/missing `kernel_run.json` read via fail-clear `_read_json` (returns None, never raises; does not trigger the fail rung).
- T-4-06-04 (Spoofing): both authoritative rungs decide before `_validate_result`, so a stale valid `result.json` off a re-pushed slug can never rescue a confirmed/unverifiable failure.
- T-4-06-SC: stdlib-only edit; `uv run pytest` uses already-declared dev deps; no runtime pip install.

## Deviations from Plan

None — plan executed exactly as written. Rules 1-4 not triggered.

## Deferred / Out of Scope (unchanged, per plan scope discipline)

CR-02 (exp_id charset gate in push_kernel.py), WR-04 (first-line `\nError:` marker), and WR-01 (--exp-dir path confinement) remain documented WARNINGs for a later hardening pass — deliberately untouched here.

## Self-Check: PASSED

- FOUND: scripts/record_experiment.py (modified)
- FOUND: tests/test_record_kernel.py (modified)
- FOUND commit: 9534edc (RED)
- FOUND commit: d4684f1 (GREEN)
