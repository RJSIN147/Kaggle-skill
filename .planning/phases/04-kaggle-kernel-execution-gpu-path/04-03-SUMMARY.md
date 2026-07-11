---
phase: 04-kaggle-kernel-execution-gpu-path
plan: 03
subsystem: kernel-gpu-path-poll-pull
tags: [nyquist, wave-3, exp-05, poll, pull, backoff, detach-not-cancel, provenance, tdd]
requires:
  - "04-02 (the kernel_run.json handoff schema this reads; the RED poll tests this turns GREEN)"
provides:
  - "scripts/poll_kernel.py (status-enum classify + exponential/capped/jittered backoff + detach-not-cancel; D-08/09/10)"
  - "scripts/pull_kernel.py (kernels output + logs→kernel_log.txt + pull -m image-provenance merge; D-14)"
  - "experiments/exp-NNN/kernel_log.txt (untrusted execution log, staged by PATH for the recorder's silent-failure scan)"
  - "gitignore.tmpl kernel-artifact block (ignore kernel_log.txt + *.npy; keep kernel_run.json tracked)"
  - "poll_kernel exit-code semantics (0 COMPLETE / 2 terminal-fail / 3 DETACHED / 4 transient-fail)"
affects:
  - "04-04 (recorder wires --kernel-log <exp-dir>/kernel_log.txt; consumes the terminal status + provenance)"
  - "04-05 (SKILL sequencing: convert → push → poll → pull → record; the D-09 detach/resume human loop)"
tech-stack:
  added: []
  patterns:
    - "bounded exponential-with-cap FULL-jitter backoff loop with injected now/sleep/rng (deterministic, testable)"
    - "VERIFIED-enum regex status classify (no case-insensitive grep — the shepsci anti-pattern)"
    - "detach-not-cancel on our-side budget expiry (write DETACHED back, distinct exit code, never a cancel argv)"
    - "gateway-routed no-echo CLI calls; untrusted log written to file and handed forward by PATH only (V5/V7)"
    - "record-don't-pin provenance: best-effort image/shape merge that degrades to null, never blocks the pull (D-14)"
key-files:
  created:
    - scripts/poll_kernel.py
    - scripts/pull_kernel.py
  modified:
    - scripts/templates/gitignore.tmpl
decisions:
  - "poll_kernel exit codes are DISTINCT per outcome (0/2/3/4) so the SKILL/caller branches; 124/127 pass through from the gateway."
  - "pull treats output+logs as REQUIRED (fail-closed) but image provenance as NON-BLOCKING (D-14 record-don't-pin) — a provenance hiccup degrades to a null image rather than discarding the already-pulled output."
  - "Added experiments/*/*.npy to the workspace gitignore (Rule 2): pulled oof.npy lands FLAT at the exp root (not under artifacts/), so the existing Phase-3 patterns did not cover it — a heavy binary would otherwise be git-tracked."
metrics:
  duration: ~7min
  tasks: 2
  files: 3
  completed: 2026-07-12
---

# Phase 04 Plan 03: Kernel-Path Middle (poll + pull) Summary

Built the middle of the kernel loop — a bounded, 429-safe status poller that DETACHES (never
cancels) on our-side timeout, and a fetcher that pulls the same `result.json` + `artifacts/`
contract the local runner uses plus the execution log and image provenance. Reads the
`kernel_run.json` handoff 04-02 wrote (re-derives the slug, never re-pushes). Turns the 04-01 poll
RED tests GREEN (4 nodes) and stages `kernel_log.txt` for 04-04's silent-failure scan.

## What Was Built

**Task 1 — `scripts/poll_kernel.py` (commit 79e08f8):**
- `classify_status(text) -> str | None` — the VERIFIED `KernelWorkerStatus` regex
  (`status\s+"(?:KernelWorkerStatus\.)?([A-Z_]+)"`), anchored on the literal `status "…"` token so a
  `Failure message:` body embedding COMPLETE/RUNNING can NEVER yield a false terminal (Pitfall 2).
  `TERMINAL = {COMPLETE, ERROR, CANCEL_ACKNOWLEDGED}`, `IN_FLIGHT = {QUEUED, RUNNING, NEW_SCRIPT,
  CANCEL_REQUESTED}`. `None` ⇒ transient/unparseable ⇒ retry (D-10) — NOT a case-insensitive grep.
- `compute_delay(attempt, rng=None) -> float` — exponential from `BASE_DELAY=10s`, `×2`, capped at
  `MAX_DELAY=120s`; with an RNG returns FULL jitter `rng.uniform(0, base)` so a sleep is always in
  `(0, base]` and can never exceed the cap (429-safe, budget-safe, decorrelated).
- `poll_loop(status_fn, *, now, sleep, rng, budget_s, max_consecutive_errors, cancel_fn=None)` —
  injected clock/sleep/rng for deterministic tests. Tolerates transient `rc!=0`/unparseable blips up
  to `MAX_CONSECUTIVE_ERRORS=5` consecutive (counter resets on any clean parse — a single blip is
  never kernel death, Pitfall 3). Stops with a distinct `reason`: `terminal` (a TERMINAL token),
  `budget` (our budget expired with the kernel in-flight ⇒ `DETACHED`, `cancel_fn` NEVER called,
  D-09), or `transient` (threshold hit ⇒ fail-closed, `last_out` carried for quarantine).
- `main()` reads `kernel_run.json` fail-clear for `kernel_slug` (never re-pushes), polls via
  `run_kaggle("kernels","status",slug,…)` (no-echo), writes the terminal/detached status back, and
  returns a DISTINCT exit code per outcome.

**Task 2 — `scripts/pull_kernel.py` (commit d59fc97):**
- Three gateway calls, each via `run_kaggle`: (1) `kernels output <slug> -p <exp-dir> --force` —
  flat `result.json` + `oof.npy` + rendered `.ipynb` (no archive extraction — kernel output is not
  compressed; download_data's zip-slip logic is NOT reused); (2) `kernels logs <slug>` — the log
  string written to `exp-dir/kernel_log.txt` and NEVER echoed (untrusted, possibly token-shaped —
  V5/V7); (3) `kernels pull <slug> -m -p <tmp>` — regenerated metadata's `docker_image` +
  `machine_shape` MERGED into `kernel_run.json`, preserving every existing key (D-14).
- output+log are REQUIRED (reserved 127/124 remediation + `dump_last_error` fail-closed, raw buffer
  never printed); provenance is NON-BLOCKING (`_merge_provenance` swallows every failure → null image
  stays, record-don't-pin). The final next-step print hands `--kernel-log <exp-dir>/kernel_log.txt`
  forward to the recorder. Runtime gitignore retrofit of the log + `*.npy` ignores via
  `_append_line_if_absent` BEFORE any pulled file is written.

**Task 2 — `scripts/templates/gitignore.tmpl` (commit d59fc97):**
Added a Phase-4 block: ignore `experiments/*/kernel_log.txt` + `experiments/*/*.npy`; keep
`!experiments/*/kernel_run.json` TRACKED (small provenance, D-03). Pulled heavy binaries land FLAT
at the experiment root, so the numpy dump is covered explicitly.

## Interface / Contract for Downstream (04-04, 04-05)

**`experiments/exp-NNN/kernel_log.txt`** — the pulled execution log. UNTRUSTED Kaggle text: it is
handed to the recorder by PATH only (`record_experiment.py --kernel-log <exp-dir>/kernel_log.txt`);
its content is pattern-matched (the D-11 marker scan 04-04 adds), never echoed and never used to
derive an executed path/command.

**`poll_kernel.py` exit-code semantics** (for the SKILL's detach/resume loop):

| Exit | Meaning | kernel_run.json.status written |
|------|---------|--------------------------------|
| 0 | COMPLETE | `COMPLETE` → run pull_kernel.py |
| 2 | ERROR / CANCEL_ACKNOWLEDGED (terminal, non-success) | the terminal token → pull the log for the reason |
| 3 | DETACHED — our budget expired, kernel still in-flight | `DETACHED` → re-run poll_kernel.py to reattach (never cancelled, D-09) |
| 4 | transient errors exceeded the threshold (fail-closed) | unchanged → raw output quarantined; re-run to retry |
| 124 / 127 | gateway timeout / CLI-missing (pass-through) | unchanged |

**`kernel_run.json` after pull** — `status` flipped by poll; `docker_image` + `machine_shape` filled
by pull's `-m` merge when present (else stay null, D-14). All 12 push-written keys preserved.

## Deviations from Plan

### Auto-added (Rule 2 — repo hygiene / correctness)

**1. [Rule 2 - Missing critical ignore] `experiments/*/*.npy` added to gitignore.tmpl**
- **Found during:** Task 2
- **Issue:** The plan directed adding the `kernel_log.txt` ignore and confirming "pulled artifacts
  are covered by the existing patterns." But pulled kernel output is FLAT — `oof.npy` lands at the
  experiment root, and the existing Phase-3 block ignores only `artifacts/` + `*.csv|*.zip|*.pkl|
  *.parquet`. A heavy numpy array would have been git-tracked at the root.
- **Fix:** Added `experiments/*/*.npy` to the Phase-4 ignore block (consistent with the
  "ignore heavy binaries, keep small provenance" philosophy; small `result.json`/`kernel_run.json`
  stay tracked).
- **Files modified:** scripts/templates/gitignore.tmpl
- **Commit:** d59fc97

## Notes for Downstream Plans

- **04-04 (recorder):** wire `--kernel-log <exp-dir>/kernel_log.txt` as the NEW FIRST RUNG of the
  classification block (kernel path only); a marker hit ⇒ `status=FAILED`, `failure_reason=
  kernel_error` BEFORE `result.json` is read. Merge `kernel_slug` / `backend` / `enable_internet` /
  `docker_image` / `machine_shape` provenance from `kernel_run.json` into the meta. The exit codes
  above let the SKILL pre-classify a non-COMPLETE poll without reading the log.
- **04-05 (SKILL):** the poll→pull sequencing holds the human loop between poll re-runs on a DETACHED
  (exit 3) result — re-invoking poll_kernel.py reattaches from the same handoff (D-09). Document
  `convert → push → poll → pull → record`, each `python3 scripts/<x>.py --workspace <cwd> --exp-dir
  experiments/exp-NNN`.
- **Assumptions still pending the 04-05 live-push checkpoint:** the exact `kernels status` render (A2
  — the regex tolerates both `KernelWorkerStatus.NAME` and bare `NAME`) and the regenerated-metadata
  key names for `docker_image`/`machine_shape` (D-14 merge is tolerant — absent keys leave null).

## Verification

- `uv run pytest tests/test_poll_kernel.py -x -q` → **4 passed** (`test_status_classify`,
  `test_backoff_budget`, `test_detach_not_cancel`, `test_source_routes_through_gateway`).
- Task 2 automated verify: `tests/test_push_kernel.py tests/test_poll_kernel.py` → **8 passed**;
  gitignore assertion (`kernel_log.txt` + `!experiments/*/kernel_run.json`) passes; `pull_kernel.py`
  contains `run_kaggle` and NO `unzip`; neither script `print`s a raw `out`/`combined` buffer.
- Full suite: **195 passed, 4 failed, 1 skipped, 9 deselected**. The 4 failures are exclusively
  `test_record_kernel.py` (04-04) RED nodes — the downstream wave, out of this plan's scope. No
  regression: Wave 2 reported 191 passed / 8 failed; this plan turned the 4 poll RED nodes GREEN
  (+4 passed), leaving only the 4 record_kernel RED nodes.

## TDD Gate Compliance

The RED poll tests (`tests/test_poll_kernel.py`) were shipped in Wave 0 (04-01); this plan is the
GREEN implementation. Confirmed RED before implementation (4 failing on `ModuleNotFoundError`), GREEN
after (`feat(04-03)` commits 79e08f8, d59fc97). No `test(...)` gate commit is expected here — the
failing tests predate this plan. `pull_kernel.py` has no dedicated unit RED node; its contract is
pinned by the plan's source-invariant + gitignore automated verify (all GREEN).

## Self-Check: PASSED
