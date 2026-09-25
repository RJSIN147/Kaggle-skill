---
phase: 04-kaggle-kernel-execution-gpu-path
plan: 01
subsystem: kernel-gpu-path-tests
tags: [nyquist, wave-0, red-suite, exp-05, fixtures, pytest]
requires: []
provides:
  - "tests/fixtures/kernel_logs/* (D-11 silent-failure marker fixtures)"
  - "tests/fixtures/status/* (KernelWorkerStatus parse-contract fixtures)"
  - "tests/fixtures/kernel-metadata.golden.json (generated-metadata golden)"
  - "tests/test_{convert_notebook,push_kernel,poll_kernel,record_kernel}.py (RED contract)"
  - "tests/test_kernel_live.py (opt-in live loop stub)"
affects:
  - "04-02 (convert+push+poll turn these GREEN)"
  - "04-03 (pull samples against these fixtures)"
  - "04-04 (recorder kernel_error rung turns record_kernel GREEN)"
tech-stack:
  added: []
  patterns:
    - "import-script-inside-test-body (conftest discipline; collection never crashes)"
    - "PATH-shim mocking for uv (jupytext emulator) and kaggle (config view/quota/push)"
    - "injectable clock + full-jitter backoff contract for deterministic poll tests"
key-files:
  created:
    - tests/fixtures/kernel_logs/complete_but_threw.txt
    - tests/fixtures/kernel_logs/clean.txt
    - tests/fixtures/kernel_logs/oom.txt
    - tests/fixtures/kernel_logs/nonzero.txt
    - tests/fixtures/status/queued.txt
    - tests/fixtures/status/running.txt
    - tests/fixtures/status/complete.txt
    - tests/fixtures/status/error.txt
    - tests/fixtures/status/cancel_acknowledged.txt
    - tests/fixtures/kernel-metadata.golden.json
    - tests/test_convert_notebook.py
    - tests/test_push_kernel.py
    - tests/test_poll_kernel.py
    - tests/test_record_kernel.py
    - tests/test_kernel_live.py
  modified: []
decisions:
  - "Pinned poll_kernel API by name: classify_status + TERMINAL/IN_FLIGHT sets, compute_delay(attempt, rng) with MAX_DELAY cap + full-jitter, and poll_loop(status_fn, *, now, sleep, rng, budget_s, max_consecutive_errors, cancel_fn) — downstream 04-02 implements to satisfy."
  - "Pinned recorder extension as a NEW --kernel-log flag + kernel_error reason (D-11/D-12), driven by synthetic fixture logs so the headline property needs no live GPU."
  - "Metadata + internet-provenance tests drive push_kernel.py as a subprocess behind a kaggle PATH shim and locate outputs by glob (kernel-metadata.json) / D-03 path (kernel_run.json), avoiding over-coupling to internal function names."
metrics:
  duration: ~20min
  tasks: 2
  files: 15
  completed: 2026-07-12
---

# Phase 04 Plan 01: Nyquist Wave 0 RED Suite (kernel GPU path) Summary

Landed the Wave 0 RED suite for Phase 4: synthetic fixtures + five failing test modules that
pin the EXP-05 kernel-path contract BEFORE any of the four new scripts (or the recorder
extension) exists — the headline silent-failure property (a kernel that reports COMPLETE but
actually threw is recorded FAILED(`kernel_error`)) is now expressed as a fixture-driven test
needing no live GPU.

## What Was Built

**Task 1 — fixtures (commit 6d4ceb1):**
- `tests/fixtures/kernel_logs/` — `complete_but_threw.txt` (embeds `Traceback (most recent call
  last)` inside otherwise-normal output), `clean.txt` (none of the six D-11 markers), `oom.txt`
  (Kaggle OOM banner + `Killed`), `nonzero.txt` (`Notebook Exceeded`).
- `tests/fixtures/status/` — one capture per `KernelWorkerStatus` token
  (`queued/running/complete/error/cancel_acknowledged`); `error.txt` carries a `Failure message:`
  body that deliberately embeds the substrings `COMPLETE` and `RUNNING` so a parser that matched
  a body substring instead of the status token would be caught (Pitfall 2).
- `tests/fixtures/kernel-metadata.golden.json` — the exact expected generated metadata for
  (username=`testuser`, slug=`titanic`, exp=`exp-001`): `id=testuser/titanic-exp-001`,
  `is_private=true`, `enable_internet=false`, `competition_sources=["titanic"]`, GPU on, TPU off.

**Task 2 — RED test modules + live stub (commit f575cfd):**
- `test_convert_notebook.py::test_reconvert_idempotent` — D-02 non-destructive/regenerable
  convert, driven through a `uv`-on-PATH jupytext emulator.
- `test_push_kernel.py::{test_metadata_golden,test_internet_provenance}` — golden metadata
  equality + D-06 effective-internet provenance in `kernel_run.json`, behind a `kaggle` PATH shim
  (no live call).
- `test_poll_kernel.py::{test_status_classify,test_backoff_budget,test_detach_not_cancel}` —
  enum-token classify (never a body substring), exponential+capped+full-jittered backoff, and
  budget-timeout DETACH that never calls a cancel hook (D-08/09/10).
- `test_record_kernel.py::{test_traceback_beats_valid_result,test_clean_log_success,test_oom_marker}`
  — the D-11/D-12 log-scan rung: a traceback/OOM beats a valid `result.json`; a clean log passes
  through to SUCCESS.
- `test_kernel_live.py` — opt-in `@pytest.mark.live` full push→poll→pull→record stub, deselected
  from the default suite (documents the three live-only unknowns A1/A2/A3).
- Source-invariant guards (`run_kaggle` routing, `--no-sync`, `kernel_error` reason) that go GREEN
  once the scripts land.

## Verification

- `pytest --collect-only -q` for all five modules: **13 collected, 1 deselected** (live) — no
  collection crash despite the scripts not existing (imports live inside test bodies).
- Four mocked modules run **RED** now (13 failing/erroring nodes); `test_kernel_live.py` is
  **deselected** (never a failure) without `-m live`.
- Full default suite: **185 passed, 13 failed (only the new RED nodes), 1 skipped** — no
  regression to any pre-existing test.
- Task 1 fixture assertions (Traceback/OOM/Notebook-Exceeded presence, clean-log marker absence,
  golden JSON field checks) all pass.

## Deviations from Plan

None — plan executed exactly as written. Every node name in the 04-VALIDATION.md Per-Task
Verification Map is present with the exact name.

## Notes for Downstream Plans

- The `poll_kernel` API surface (`classify_status`, `TERMINAL`, `IN_FLIGHT`, `compute_delay`,
  `poll_loop`) is pinned by these tests; 04-02 should implement to those names/signatures (or
  adjust the tests as an intentional, documented deviation).
- `record_experiment.py` gains a NEW `--kernel-log` flag whose scan is the FIRST rung of the
  fail-closed ladder (04-04); `kernel_error` is the single new reason (D-12).
- Live confirmation of the T4×2 accelerator string, real log format, and status render (A1/A2/A3)
  remains a manual `-m live` checkpoint at the phase gate.

## Self-Check: PASSED
