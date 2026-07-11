---
phase: 04-kaggle-kernel-execution-gpu-path
plan: 04
subsystem: kernel-gpu-path-record
tags: [nyquist, wave-3, exp-05, recorder, silent-failure, kernel_error, provenance, tdd]
requires:
  - "04-01 (the RED record_kernel tests this turns GREEN)"
  - "04-02 (the kernel_run.json handoff schema whose provenance is merged into meta.json)"
provides:
  - "scripts/record_experiment.py extended: scan_kernel_log first rung + kernel_error reason + --kernel-log flag + kernel provenance merge"
  - "The headline anti-lie property: a COMPLETE-but-threw kernel is FAILED(kernel_error) even with a valid result.json"
affects:
  - "04-05 (SKILL sequencing documents `... -> pull -> record --kernel-log`; live-push checkpoint finalizes the D-11 marker set A3)"
tech-stack:
  added: []
  patterns:
    - "NEW-FIRST-RUNG extension of an existing fail-closed ladder (kernel path gated on a flag; local path byte-for-byte unchanged)"
    - "untrusted-content no-derive scan (pure `marker in text`, never echoed, no path/command derived — V5/V7)"
    - "provenance merge from a sibling handoff JSON (kernel_run.json -> meta.json) via fail-clear _read_json"
key-files:
  created:
    - .planning/phases/04-kaggle-kernel-execution-gpu-path/04-04-SUMMARY.md
  modified:
    - scripts/record_experiment.py
decisions:
  - "Exactly ONE new enum reason (kernel_error); missing/invalid kernel result.json keeps mapping to the EXISTING missing_result/schema_invalid (D-12, no proliferation)."
  - "A missing/unreadable --kernel-log file is fail-clear: no kernel_error evidence => defer to the existing result.json ladder (never blocks the record)."
  - "meta['kernel'] block is emitted ONLY on the kernel path (--kernel-log set); local meta shape is untouched. A kernel run with no kernel_run.json still records backend='kernel' so it is never mistaken for a local run."
metrics:
  duration: ~4min
  tasks: 1
  files: 1
  completed: 2026-07-12
---

# Phase 04 Plan 04: Kernel Silent-Failure Recorder Extension Summary

Extended the ONE anti-lie recorder so the headline correctness property of Phase 4 holds: a
Kaggle kernel that reports COMPLETE but actually threw is recorded FAILED(kernel_error) — never
a success — even when a valid `result.json` came back, because the pulled log is scanned as the
NEW FIRST RUNG of the fail-closed ladder BEFORE `result.json` is ever trusted. One recorder, one
ladder, exactly one new reason (D-12). Turns the 04-01 `test_record_kernel.py` RED nodes GREEN;
fixture-driven, no live GPU required.

## What Was Built

**Task 1 — `scripts/record_experiment.py` extended in place (commit 7f2b951):**

- **One new enum reason.** `FAILURE_REASONS` gains exactly `"kernel_error"` (D-12). Missing or
  invalid kernel `result.json` still maps to the EXISTING `missing_result`/`schema_invalid`
  reasons — no `kernel_traceback`/`kernel_timeout`/… proliferation.
- **`scan_kernel_log(log_text) -> bool`** + a module-level `_KERNEL_ERROR_MARKERS` tuple of the
  six D-11 markers (`Traceback (most recent call last)`, `\nError:`, `\nException:`,
  `Your notebook tried to allocate more memory than is available`, `Killed`,
  `Notebook Exceeded`). Pure `marker in text` pattern-match. Handles Assumption A3: it tries
  `json.loads`; when the log is a JSON array of `{stream_name, data}` records it concatenates the
  `data` fields (newline-joined so `\n`-anchored markers still match across records) and scans
  that, otherwise it scans the raw text. The log is NEVER echoed and NO executed path/command is
  derived from its content (V5/V7).
- **`--kernel-log` optional flag** added alongside `--run-exit-code`. Absent ⇒ the local path,
  existing behavior byte-for-byte.
- **NEW FIRST RUNG in `main()`.** When `--kernel-log` is set, the log file is read fail-clear and
  `scan_kernel_log` runs FIRST; on a hit it sets `status="FAILED"`, `failure_reason="kernel_error"`,
  `valid_result=None` and short-circuits the rest of the ladder — BEFORE `result.json` is read. No
  hit (or an unreadable log, or no `--kernel-log` at all) ⇒ falls through to the EXISTING
  `run_failed` / `_read_json(result_path)` / `_validate_result` ladder completely unchanged. All
  downstream (`_build_provenance`, meta merge, `rebuild_ledger_file`, `_stage_provenance`, VERDICT
  stub) is reused untouched.
- **Kernel provenance merge (D-06).** On the kernel path, `kernel_run.json` is read fail-clear and a
  `meta["kernel"]` block is merged in: `backend`, `kernel_slug`, `competition_slug`, the EFFECTIVE
  `enable_internet`, `accelerator`, `docker_image`, `machine_shape`, `kernel_version`. So an
  internet-ON kernel run is a VISIBLE, auditable exception rather than a silent one. A kernel run
  with no handoff file still records `{"backend": "kernel"}` so it is never mistaken for a local run.
  The local path emits no `kernel` block — its meta shape is unchanged.

## Verification

- `uv run pytest tests/test_record_kernel.py tests/test_record_experiment.py -x -q` → **18 passed**
  (`test_traceback_beats_valid_result`, `test_clean_log_success`, `test_oom_marker`,
  `test_source_has_kernel_error_rung`, plus all pre-existing local recorder tests GREEN — no
  regression on the local path).
- Plan's source assertion passes: `record_experiment.py` contains `scan_kernel_log` and
  `--kernel-log`, and `kernel_error` is inside the `FAILURE_REASONS` tuple (exactly one new reason).
- Full suite: **195 passed, 4 failed, 1 skipped, 9 deselected**. The 4 failures are exclusively
  `test_poll_kernel.py` — plan **04-03**'s RED nodes (`poll_kernel.py` does not exist yet;
  `ModuleNotFoundError`), a sibling wave-3 plan, out of this plan's scope. Wave 2 reported 8
  failures (poll + record_kernel); this plan turned the 4 `record_kernel` nodes GREEN, leaving only
  04-03's 4. No regression to any pre-existing test.

## TDD Gate Compliance

- RED gate: `test(...)` — the `test_record_kernel.py` RED nodes were shipped by the Wave 0 / 04-01
  test scaffold (this plan is the GREEN turn of that RED). The failing state was confirmed before
  implementation (`--kernel-log` unrecognized + `kernel_error` absent from source).
- GREEN gate: `feat(04-04): scan kernel log first rung ...` (commit 7f2b951).
- REFACTOR gate: none needed — the extension is minimal and the local path is untouched.

## Deviations from Plan

None — plan executed exactly as written. All five plan-mandated pieces (one enum reason, scan
helper + markers, `--kernel-log` flag, new first rung, kernel provenance merge) landed as specified;
no auto-fixes or architectural changes were required.

## Notes for Downstream Plans

- **04-05 (SKILL):** document the record step as
  `python3 scripts/record_experiment.py --workspace <cwd> --exp-dir experiments/exp-NNN --kernel-log experiments/exp-NNN/kernel_log.txt`
  for the kernel path (the local path stays flagless). Surface the D-06 internet-effective note: an
  internet-ON kernel run now shows up as `meta.kernel.enable_internet=true`, the auditable exception.
- The D-11 marker set is finalized against fixtures; the exact live Kaggle log shape (A3: plain text
  vs. JSON `{stream_name,data}` array) is confirmed at the 04-05 live-push checkpoint — `scan_kernel_log`
  already handles both.

## Self-Check: PASSED

- `scripts/record_experiment.py` — FOUND (modified, committed 7f2b951).
- Commit 7f2b951 — FOUND in git log.
- `.planning/phases/04-kaggle-kernel-execution-gpu-path/04-04-SUMMARY.md` — FOUND (this file).
