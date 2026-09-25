---
phase: 04-kaggle-kernel-execution-gpu-path
reviewed: 2026-07-12T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - scripts/record_experiment.py
  - tests/test_record_kernel.py
findings:
  critical: 1
  warning: 1
  info: 0
  total: 2
resolved:
  critical: 1
  warning: 0
status: resolved
resolution_note: >-
  CR-01 crash BLOCKER (non-string kernel_run.json.status) fixed in commit aaab35a via an
  isinstance(str) guard + regression test test_non_string_status_does_not_crash; full suite
  205 passed. WR-01 WARNING (DETACHED/PENDING reaching SUCCESS) left as a documented, deliberate
  scope-out of plan 04-06 (which specified matching ONLY ERROR/CANCEL_ACKNOWLEDGED) — tracked for
  a later hardening pass alongside CR-02/WR-04/WR-01.
---

# Phase 4: Code Review Report (gap-closure re-review)

**Reviewed:** 2026-07-12T00:00:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Gap-closure re-review of the CR-01 status rung, the WR-03 unreadable-log fail-closed
rung, the `meta["kernel"]["status"]` audit copy, and five new regression tests, all in
the `--kernel-log` classification path of `scripts/record_experiment.py`.

The core fix is directionally correct and the property tests pass (9/9): the status
membership test is an **exact set literal** (`in {"ERROR", "CANCEL_ACKNOWLEDGED"}`) with
no substring/regex/eval; rung 1 fires **before** `result.json` is read so a confirmed
`ERROR`/`CANCEL_ACKNOWLEDGED` run cannot be rescued by a stale valid result; WR-03 fails
closed on an unreadable/missing log; and the local (non-kernel) path is untouched (both
new kernel blocks stay gated behind `args.kernel_log is not None`).

However, the fix imports a **crash-on-malformed-input** defect via that same set-membership
test, directly contradicting the code's own stated guarantee that a "garbage kernel_run.json
simply does not trigger rung 1 (fail-clear)". A second, softer gap: the authoritative-failure
set enumerates only the two confirmed-FAILED terminal tokens and treats every other
non-`COMPLETE` state (notably the poller's `DETACHED` / `PENDING`, i.e. *outcome-unknown*) as
non-failing, so such a run can still fall through to SUCCESS off a stale/partial `result.json`.

## Critical Issues

### CR-01: Malformed `kernel_run.json` status (JSON array/object) crashes the recorder — breaks the fail-clear guarantee

**File:** `scripts/record_experiment.py:347-349`

**Issue:** Rung 1 evaluates `kernel_run.get("status") in {"ERROR", "CANCEL_ACKNOWLEDGED"}`.
Set membership hashes the left operand. If `kernel_run.json` parses to a `dict` but its
`status` field is a JSON **array** or **object**, `.get("status")` returns an unhashable
`list`/`dict` and the `in`-test raises an unhandled `TypeError: unhashable type: 'list'`,
crashing the recorder with a stack trace and exit code 1.

This violates the guarantee written three lines above the code
(`record_experiment.py:334`): *"A missing/garbage kernel_run.json simply does not trigger
rung 1 (fail-clear via _read_json)."* `_read_json` only guards *parse* failures; it happily
returns a dict whose `status` value is the wrong shape, and the membership test — not
`_read_json` — is what actually crashes.

Impact: an experiment cycle with a corrupt/hand-edited handoff file is **not recorded at
all** — no finalized `meta.json`, no `ledger.jsonl` row, no `VERDICT` stub. That is the
loop-breaking, record-losing failure mode this phase exists to prevent, and it is triggered
by exactly the "malformed kernel_run.json" input the review targets. (Reproduced end-to-end:
`status: []` → `TypeError` at line 347, RC 1.) No new regression test exercises a non-string
`status`, which is why it slipped through — the five new tests only feed valid string tokens.

Note: this does not flip a failure to SUCCESS (it crashes rather than mis-classifies), but
it is a data-loss / robustness BLOCKER and defeats the stated fail-clear contract.

**Fix:** Constrain the value to a string before the membership test (mirrors the
`isinstance(...dict)` fail-clear guard already used when reading `kernel_run`):

```python
status_val = kernel_run.get("status") if kernel_run is not None else None
if isinstance(status_val, str) and status_val in {"ERROR", "CANCEL_ACKNOWLEDGED"}:
    status, failure_reason, kernel_error_hit = "FAILED", "kernel_error", True
```

Add a regression test writing `kernel_run.json` with `"status": []` (and `{}`) and assert
the recorder returns 0 and records a normal classification rather than crashing.

## Warnings

### WR-01: Failure set treats every non-`COMPLETE` outcome-unknown status (`DETACHED`/`PENDING`) as non-failing — stale `result.json` can still reach SUCCESS

**File:** `scripts/record_experiment.py:347-349`

**Issue:** `poll_kernel.py` writes one of `COMPLETE`, `ERROR`, `CANCEL_ACKNOWLEDGED`, or
`DETACHED` (`TERMINAL = {"COMPLETE","ERROR","CANCEL_ACKNOWLEDGED"}`; budget-expired ⇒
`DETACHED`), and `push_kernel.py` seeds `status="PENDING"`. Rung 1 only classifies the two
confirmed-FAILED tokens. `DETACHED` and `PENDING` mean the outcome was **never confirmed**
(kernel still in-flight / poll gave up), yet they are treated identically to "no failure":
the run falls through to the log scan + result ladder. If such a run has a readable,
marker-free log and a stale or partially-written `result.json` on disk, the recorder records
**SUCCESS** — the same stale-result-rescues-an-unverified-run silent failure CR-01 set out
to close, just through the "unknown outcome" door instead of the "confirmed error" door.

The WR-03 fail-closed rung only catches the *unreadable-log* case; it does not catch a
`DETACHED`/`PENDING` run that happens to have a clean readable log next to a stale result.

**Fix:** Make SUCCESS require positive confirmation rather than mere absence of a failed
token. On the kernel path, treat any status that is present-and-not-`COMPLETE` as
non-success, so only a `COMPLETE` poll can proceed to the SUCCESS ladder:

```python
status_val = kernel_run.get("status") if kernel_run is not None else None
if isinstance(status_val, str) and status_val != "COMPLETE":
    # ERROR / CANCEL_ACKNOWLEDGED / DETACHED / PENDING / any non-success token
    status, failure_reason, kernel_error_hit = "FAILED", "kernel_error", True
```

(If a deliberate design choice keeps `DETACHED` recordable, document why an unconfirmed run
may be recorded SUCCESS off an on-disk result.)

---

_Reviewed: 2026-07-12T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
