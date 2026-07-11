---
phase: 04-kaggle-kernel-execution-gpu-path
plan: 05
subsystem: kernel-gpu-path-skill-sequencing
tags: [exp-05, wave-4, skill-md, kernel-path, sequencing, detach-resume, live-verify-deferred]
requires:
  - phase: "04-02 (convert_notebook.py + push_kernel.py invocations + kernel_run.json)"
    provides: "the push slice the SKILL sequences"
  - phase: "04-03 (poll_kernel.py detach exit codes + pull_kernel.py artifacts/logs)"
    provides: "the poll/pull slice + reserved detach exit-code semantics"
  - phase: "04-04 (record_experiment.py --kernel-log first-rung scan)"
    provides: "the kernel-path recorder the SKILL wires as step 5"
provides:
  - "SKILL.md 'Kaggle kernel loop (EXP-05, GPU path)' section: discrete resumable convert -> push -> poll -> pull -> record sequence with exact invocations"
  - "Detach/resume instruction (re-run poll to reattach WITHOUT re-pushing — D-01/D-09) with reserved exit-code table"
  - "D-13 non-blocking GPU-quota heads-up note + D-06 internet-off-by-default / effective-value-recorded note"
  - "Four new scripts-table rows (convert_notebook/push_kernel/poll_kernel/pull_kernel) + amended record_experiment row noting --kernel-log kernel_error scan"
affects:
  - "Phase 5 (submission consumes kernel output when a kernel produced the submission)"
  - "Operator-owned live GPU verification (deferred — A1/A2/A3/A4 confirmation into references/kaggle-cli-behavior.md)"
tech-stack:
  added: []
  patterns:
    - "SKILL sequences idempotent entry points (argparse in / exit code out); the SKILL holds the human/AI loop between poll re-runs (D-02)"
    - "Progressive-disclosure body kept lean — deep detail pushed to plan/references, not the SKILL.md body"
key-files:
  created:
    - .planning/phases/04-kaggle-kernel-execution-gpu-path/04-05-SUMMARY.md
  modified:
    - SKILL.md
key-decisions:
  - "Task 2 (one opt-in live GPU push) DEFERRED to operator — deliberately, not skipped/failed: the phase is fully green from fixtures (199 passed) and the plan explicitly scopes the live push as NOT a phase blocker."
  - "Kernel section placed after the local-loop section, mirroring its numbered-step / reserved-exit-code style; no unrelated SKILL.md section restructured."
patterns-established:
  - "Kernel path documented as the SAME experiment.py running unchanged (resolve_data_dir auto-selects /kaggle/input on the kernel)."
  - "DETACH is a resumable state, not a failure: SKILL re-invokes poll_kernel.py to reattach; GPU time already spent is never re-burned."
requirements-completed: []  # EXP-05 buildable scope delivered; live-verification of EXP-05 deferred to operator (see Deferred Verification)

duration: ~10min
completed: 2026-07-12
---

# Phase 04 Plan 05: SKILL.md Kernel-Path Sequencing Summary

**SKILL.md now sequences the Kaggle GPU path as a discrete, resumable convert → push → poll → pull → record loop — with the detach/resume (re-run poll without re-pushing), the D-13 quota heads-up, the D-06 internet-off note, and four new scripts-table rows — while the one opt-in live GPU push is deliberately deferred to the operator.**

## Performance

- **Duration:** ~10 min
- **Tasks:** 1 of 2 complete; 1 deferred (operator-owned live verification)
- **Files modified:** 1 (SKILL.md)

## Accomplishments

- **Task 1 (complete, commit `1acccbe`):** Added the "Kaggle kernel loop (EXP-05, GPU path)" section to SKILL.md immediately after the local-loop section, mirroring its numbered-step and reserved-exit-code style:
  - Step 0: kernel target starts from a scaffolded experiment; the same `experiment.py` runs unchanged (`resolve_data_dir` auto-selects `/kaggle/input`).
  - Step 1 `convert_notebook.py` → inspectable, regenerable `experiment.ipynb` (D-02).
  - Step 2 `push_kernel.py` → metadata gen, **non-blocking D-13 GPU-quota heads-up**, `kernel_run.json`, **D-06 internet-off-by-default with the effective value recorded in provenance**, deterministic `<username>/<slug>-exp-NNN` slug re-pushes the SAME kernel.
  - Step 3 `poll_kernel.py` → bounded jittered backoff; on our-side budget expiry it **DETACHES (never cancels)**; the SKILL instructs the user to simply **re-run poll later to reattach, then pull, WITHOUT re-pushing** (D-01/D-09). Reserved detach exit-code semantics documented in an exit-code table (exit 3 = DETACHED).
  - Step 4 `pull_kernel.py` → `result.json` + artifacts + `kernel_log.txt` + image/machine provenance.
  - Step 5 `record_experiment.py --kernel-log ...` → the log is scanned FIRST; a traceback/OOM ⇒ **FAILED(kernel_error)** even if status said COMPLETE and a valid `result.json` exists (anti-silent-failure guarantee, Success Criterion 3), then the SAME regen_strategy step as the local loop.
  - Four new "Scripts (progressive disclosure)" rows for `convert_notebook` / `push_kernel` / `poll_kernel` / `pull_kernel`, plus the `record_experiment.py` row amended to note the kernel-path `--kernel-log` scan and the `kernel_error` reason.
- **Full mocked suite reconfirmed green** before finalizing: `199 passed, 1 skipped, 9 deselected` (live tests deselected). The phase's correctness is complete and proven from fixtures independent of any live GPU spend.

## Task Commits

1. **Task 1: SKILL.md kernel-path sequencing + scripts-table rows + D-13/D-06 notes** — `1acccbe` (docs)

**Plan metadata:** committed with this SUMMARY (`docs(04-05): complete kernel-path wiring; defer opt-in live push to operator`)

## Files Created/Modified

- `SKILL.md` — Added the "Kaggle kernel loop (EXP-05, GPU path)" section (convert→push→poll→pull→record with the detach/resume, quota, and internet notes) + four scripts-table rows + amended record_experiment row. (commit `1acccbe`, +85 lines)

## Decisions Made

- **Task 2 live GPU push DEFERRED to the operator (deliberate, not skipped/failed).** The plan itself scopes the single opt-in live push as "one explicit human-verify task, NOT a phase-wide blocker — the entire default suite is already green from fixtures before this runs." The operator elected to defer: the live push spends real 30h/week GPU quota and requires Phase 1 creds + Phase 2 competition data + a Phase 3 scaffolded experiment, which the operator will set up later. The phase's buildable scope is complete and green.
- Kernel section mirrors the local-loop numbered-step / reserved-exit-code conventions; no unrelated SKILL.md section was restructured (progressive-disclosure body kept lean).

## Deferred Verification (operator-owned)

**Task 2 — One opt-in live Kaggle GPU push (A1/A2/A3/A4).** DEFERRED, not failed and not skipped. When the operator has Phase 1 creds validated, a Phase 2 competition captured with data, and a Phase 3 experiment scaffolded (`experiments/exp-001/experiment.py`), run the full live loop:

```
python3 scripts/convert_notebook.py    --workspace $(pwd) --exp-dir experiments/exp-001
python3 scripts/push_kernel.py         --workspace $(pwd) --exp-dir experiments/exp-001 [--accelerator NvidiaTeslaT4]
python3 scripts/poll_kernel.py         --workspace $(pwd) --exp-dir experiments/exp-001
python3 scripts/pull_kernel.py         --workspace $(pwd) --exp-dir experiments/exp-001
python3 scripts/record_experiment.py   --workspace $(pwd) --exp-dir experiments/exp-001 --kernel-log experiments/exp-001/kernel_log.txt
```

Or the live integration test: `uv run pytest -m live --run-live tests/test_kernel_live.py`.

**Four live-only unknowns to confirm and capture into `references/kaggle-cli-behavior.md`:**

- **A1 — T4×2 accelerator string.** Confirm the exact multi-GPU accelerator string; if confirmed, set it as the D-04 default.
- **A2 — `kaggle kernels status` render vs `_STATUS_RE`.** Confirm the exact status render (`KernelWorkerStatus.<NAME>`) against the poller's `_STATUS_RE` regex; adjust the regex if it diverges.
- **A3 — kernel-log shape + `_KERNEL_ERROR_MARKERS` coverage.** Confirm the real `kaggle kernels logs` shape (plain text vs JSON) and whether the current `_KERNEL_ERROR_MARKERS` set catches a genuine traceback/OOM; adjust the marker set if needed.
- **A4 — `kaggle kernels push` output version string vs push_kernel.py's version regex.** Confirm `kernel_run.json.kernel_version` captured the real auto-assigned version integer; adjust the regex if the output format differs.

Expected outcome once run: a completed kernel run recorded to the ledger with kernel provenance, and a deliberately-throwing kernel recorded FAILED(kernel_error) despite a COMPLETE status.

**Phase impact of the deferral: none for buildable correctness.** The mocked suite (199 passed) already exercises the untrusted-text, egress, and silent-failure paths via fixtures. The deferred live push is a confirmation of live surface shapes, not a gate on the phase's correctness.

## Deviations from Plan

None — plan executed exactly as written for Task 1. Task 2 was deferred by explicit operator decision at its human-verify checkpoint (documented above under Deferred Verification), which is the plan's own sanctioned outcome for the non-blocking live push.

## Issues Encountered

None.

## User Setup Required

The deferred live GPU push requires operator setup (see the plan's `user_setup`): validated Kaggle credentials (Phase 1), a captured competition with local data (Phase 2), and a scaffolded experiment (Phase 3). No env vars or dashboard config are added by this plan itself.

## Next Phase Readiness

- EXP-05 buildable scope delivered: the kernel path (convert → push → poll → pull → record) is fully wired into SKILL.md and green from fixtures.
- Phase 5 (submission & leaderboard) can proceed — it consumes kernel output only when a kernel produced the submission; it does not depend on the deferred live push.
- Open operator-owned item: run the one live GPU push to confirm A1/A2/A3/A4 and record findings into `references/kaggle-cli-behavior.md`.

## Self-Check: PASSED

Buildable scope verified — SKILL.md kernel section present (`convert_notebook`/`push_kernel`/`poll_kernel`/`pull_kernel`/`--kernel-log`/`kernel_error`/"without re-push" all present at commit `1acccbe`); mocked suite green (199 passed, 9 live deselected). The deferred live-verification item (Task 2) is documented as operator-owned, not a build failure.

---
*Phase: 04-kaggle-kernel-execution-gpu-path*
*Completed: 2026-07-12 (Task 1; Task 2 live push deferred to operator)*
