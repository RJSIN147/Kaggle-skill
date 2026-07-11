---
phase: 4
slug: kaggle-kernel-execution-gpu-path
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-11
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Headline correctness property: a kernel that reports `COMPLETE` but actually threw is recorded
> FAILED(`kernel_error`) — fully testable WITHOUT a live GPU using synthetic fixture logs.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (dev dependency-group; `uv.lock` committed since Phase 1 01-01) |
| **Config file** | `pyproject.toml` (skill repo) + existing `tests/` |
| **Quick run command** | `uv run pytest tests/test_kernel_*.py -x -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~30 seconds (all mocked; no live kernel in default suite) |

**Live-only marker:** reuse the Phase 1/2 live marker (`-m live --run-live`) for a real push — OUT of the default suite.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_kernel_*.py -x -q` (all mocked, < 30s)
- **After every plan wave:** Run `uv run pytest -q` (full suite must be green)
- **Before `/gsd:verify-work`:** Full suite green; ONE opt-in live push at a human-verify checkpoint to (a) confirm the T4×2 accelerator string, (b) pin the real log format + marker set, (c) confirm the status render
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01 (metadata gen) | 01 | 1 | EXP-05 | T-4-03 | internet=false unless explicitly overridden; effective value recorded | unit (golden) | `uv run pytest tests/test_push_kernel.py::test_metadata_golden -x` | ❌ W0 | ⬜ pending |
| 04-01 (internet provenance) | 01 | 1 | EXP-05 | T-4-03 | effective internet flag recorded in kernel_run.json → meta | unit | `uv run pytest tests/test_push_kernel.py::test_internet_provenance -x` | ❌ W0 | ⬜ pending |
| 04-01 (convert idempotent) | 01 | 1 | EXP-05 | — | convert regenerable from experiment.py, non-destructive (D-02) | unit (mock uv) | `uv run pytest tests/test_convert_notebook.py::test_reconvert_idempotent -x` | ❌ W0 | ⬜ pending |
| 04-02 (status classify) | 02 | 2 | EXP-05 | T-4-01 | untrusted status text pattern-matched, never executed | unit | `uv run pytest tests/test_poll_kernel.py::test_status_classify -x` | ❌ W0 | ⬜ pending |
| 04-02 (backoff budget) | 02 | 2 | EXP-05 | — | exponential+capped+jittered, budget-bounded; transient errors tolerated to threshold | unit (seeded, mocked clock) | `uv run pytest tests/test_poll_kernel.py::test_backoff_budget -x` | ❌ W0 | ⬜ pending |
| 04-02 (detach not cancel) | 02 | 2 | EXP-05 | — | our-side timeout with RUNNING ⇒ DETACH (PENDING), never cancel | unit (mock run_kaggle) | `uv run pytest tests/test_poll_kernel.py::test_detach_not_cancel -x` | ❌ W0 | ⬜ pending |
| 04-02 (traceback beats result) | 02 | 2 | EXP-05 | T-4-02 | log scan pure pattern-match; no path/command derived from log | unit (fixture log) | `uv run pytest tests/test_record_kernel.py::test_traceback_beats_valid_result -x` | ❌ W0 | ⬜ pending |
| 04-02 (clean log success) | 02 | 2 | EXP-05 | — | clean log + valid result ⇒ SUCCESS on kernel path | unit | `uv run pytest tests/test_record_kernel.py::test_clean_log_success -x` | ❌ W0 | ⬜ pending |
| 04-02 (oom marker) | 02 | 2 | EXP-05 | T-4-02 | OOM / process-killed log ⇒ kernel_error | unit | `uv run pytest tests/test_record_kernel.py::test_oom_marker -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Task IDs are provisional (mapped to the two suggested plans); finalize against the planner's actual task numbering during execution.*

---

## Wave 0 Requirements

- [ ] `tests/fixtures/kernel_logs/complete_but_threw.txt` — contains `Traceback (most recent call last)`
- [ ] `tests/fixtures/kernel_logs/clean.txt` — no error markers
- [ ] `tests/fixtures/kernel_logs/oom.txt` — Kaggle OOM / `Killed`
- [ ] `tests/fixtures/kernel_logs/nonzero.txt` — process exit / `Notebook Exceeded`
- [ ] `tests/fixtures/status/*.txt` — one capture per `KernelWorkerStatus` enum token (`has status "…"`)
- [ ] `tests/fixtures/kernel-metadata.golden.json` — expected generated metadata
- [ ] `tests/test_record_kernel.py`, `tests/test_poll_kernel.py`, `tests/test_push_kernel.py`, `tests/test_convert_notebook.py` — test stubs for EXP-05
- [ ] Framework: pytest already present — no install needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full push→poll→pull→record loop against a real kernel | EXP-05 | Requires live Kaggle GPU compute + a real competition mount; burns GPU quota | `uv run pytest -m live --run-live tests/test_kernel_live.py` at the human-verify checkpoint; confirm T4×2 accelerator string, real log format/marker set, and status render |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (fixtures + test files)
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
