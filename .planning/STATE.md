---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Kaggle-general
status: planning
last_updated: "2026-09-25T02:09:13.000Z"
last_activity: 2026-09-25
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-25)

**Core value:** One clean end-to-end experiment cycle — empty folder to an idea run, its result and reasoning logged to the ledger, and the strategy doc updated.
**Current focus:** Phase 6 — kx Core & Live Kernel Loop (milestone v2.0 Kaggle-general, Phases 6-10)

## Current Position

Phase: 6 of 10 (kx Core & Live Kernel Loop), the first of the 5 v2.0 phases
Plan: Not planned yet
Status: Ready to plan (the v2.0 roadmap is created and awaiting user approval)
Last activity: 2026-09-25 — v2.0 roadmap created: Phases 6-10, 38/38 requirements mapped

Progress: [░░░░░░░░░░] 0% (v2.0)

## Performance Metrics

**Velocity:**

- Total plans completed: 29
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 4 | - | - |
| 02 | 7 | - | - |
| 03 | 5 | - | - |
| 04 | 6 | - | - |
| 05 | 7 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01-01 | ~15min | 3 tasks | 13 files |
| Phase 01 P01-02 | ~25min | 2 tasks | 9 files |
| Phase 01 P01-03 | ~35min | 3 tasks | 5 files |
| Phase 01 P01-04 | ~40min | 3 tasks | 2 files |
| Phase 04 P06 | ~3min | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: Local-loop-first vertical MVP — prove the full CV-only cycle (Phases 1-3) before spending Kaggle GPU or submission budget.
- Roadmap: The machine-checked result contract (tooling writes scores, never the AI) is established in Phase 3 and only extended for kernels in Phase 4 — never re-derived.
- Roadmap: Security guardrails thread through phases — egress + credential hygiene (Phase 1), untrusted-content wrapping + zip-slip (Phase 2).
- Roadmap: v2 AI-loop hardening/analysis (ANLY-*) deliberately excluded from the v1 roadmap.
- [Phase 01]: 01-01: pytest declared as a dev-dependency-group (uv.lock committed) for reproducible test runs; skill scripts stay stdlib-only (D-14).
- [Phase 01]: 01-01: Nyquist Wave 0 RED suite (25 nodes) pins all locked Phase-1 decisions before implementation; SETUP-01..04 go GREEN in 01-02/03/04.
- [Phase ?]: 01-02: init_workspace.py scaffolder — D-01 slug gate + D-02 create-if-absent/deep-merge safe-merge, stdlib-only, self-locating
- [Phase ?]: 01-02: test_full_layout forced .gitignore + .claude/settings.json creation; wrote final .gitignore + empty {} settings stub, keeping 01-03 settings/git/leak nodes RED
- [Phase ?]: 01-03: egress enforced via sandbox.network.allowedDomains (OS-level, constrains CLI subprocesses) + fail-closed sandbox.failIfUnavailable=true; NOT WebFetch theater
- [Phase ?]: 01-03: criterion 5 split — Half A (generated settings) MET, Half B (host enforcement) PARTIALLY demonstrated (example.com off-list reached origin, UNVERIFIED); criterion 5 + SETUP-04 NOT fully validated
- [Phase 01]: 01-04: SETUP-03 MET — live exit-code credential validation proven end-to-end at Task 3 checkpoint (real access_token file source, exit 0, state.json=VALIDATED, no leak); success path now VERIFIED in kaggle-cli-behavior.md
- [Phase 01]: 01-04: SETUP-04 NOT complete — credential half MET (masked/never-echoed, chmod+.env consent-gated, secrets gitignored), egress half still PARTIAL (01-03 example.com anomaly). Legacy KAGGLE_USERNAME/KAGGLE_KEY end-to-end validation UNVERIFIED. kaggle declared dev/live-only dep.
- [Phase 04]: 04-05: kernel path (convert→push→poll→pull→record) wired into SKILL.md with detach/resume (re-run poll without re-pushing — D-01/D-09), D-13 non-blocking quota heads-up, and D-06 internet-off/effective-value notes + four scripts-table rows. Task 1 complete (commit 1acccbe).
- [Phase 04]: 04-05: the one opt-in live GPU push DEFERRED to operator (deliberate, not skipped/failed) — the plan scopes it as NOT a phase blocker; phase is green from fixtures (199 passed) independent of the live run. Operator to confirm A1 (T4×2 accelerator string), A2 (kernels-status render vs _STATUS_RE), A3 (kernel-log shape + _KERNEL_ERROR_MARKERS coverage), A4 (kernels-push version string vs push_kernel.py regex) into references/kaggle-cli-behavior.md.
- [Phase 04]: 04-06: kernel_run.json.status is authoritative — status in {ERROR, CANCEL_ACKNOWLEDGED} classifies FAILED(kernel_error) BEFORE result.json validation (CR-01); exact membership only, never echoed.
- [Phase 04]: 04-06: WR-03 — an unreadable/missing --kernel-log fails CLOSED to FAILED(kernel_error) instead of deferring to a stale result.json; kernel_error reused, local path unchanged.
- Roadmap v2.0: Phases 6-10 continue v1's numbering. Every phase is `**Mode:** mvp` with a user-story goal, and its vertical slice is a real `kx` invocation driving real Kaggle calls end to end. All phases are non-frontend (UI-SPEC gate N/A).
- Roadmap v2.0: Every phase carries at least one LIVE success criterion on a real competition, run inside the phase, never deferred to an operator step (the v1 retrospective lesson). Live submits are human-run with `!`, go only to closed competitions still open to late submissions or to perpetual sandboxes, and never to rsna-knee-abnormality-detection or cooked-or-not.
- Roadmap v2.0: The basic script-kernel run (RUN-01), the pass-1 profile facts (PROF-01), the tabular template (TMPL-01) and the standard OOF/test format (ENS-01) all land in Phase 6, because the first live cycle needs them. Fixing ENS-01 with the first template avoids retrofitting later templates.
- Roadmap v2.0: CORE-05 (lean SKILL.md with per-type references) moves to Phase 7, because type guidance loads only for the confirmed type (PROF-04). TMPL-03 moves to Phase 7 to give TMPL-06's override path a real second template. RUN-03 (the unified resolver) goes to Phase 8 with local runs (RUN-06).

### Pending Todos

None.

### Blockers/Concerns

Research flags to resolve during phase planning:

- ~~Phase 4: exact `kaggle kernels status` output shape unconfirmed; verify against a live run before finalizing the poller. Known API bugs #473/#509.~~ RESOLVED (live-verified 2026-09-25: `KernelWorkerStatus.<NAME>` render, see references/kaggle-cli-behavior.md).
- ~~Phase 5: the code-competition submission path needs validation for the target competition type.~~ RESOLVED by spike 003 (2026-09-25): `submit <ref> -k -v -f` with a script kernel version scores, including API-served competitions. The competition type now comes from the SDK profile (spike 001).
- Phase 2: `competitions download --unzip` reliability on CLI 2.x needs direct verification.
- Outstanding human verification (01-03): run discriminating egress probe (example.org/example.net/wikipedia.org/google.com/httpbin.org, declining prompts) to settle whether an undocumented pre-allowed set exists for the local CLI sandbox — the example.com anomaly

v2.0 research flags (spike frontier). Each is noted as a risk on the phase that touches it, not as a requirement:

- Phase 7: download the bundle once and extract it safely. Per-file downloads hit 429, and `--unzip` is unreliable; this is the v2 home of the Phase 2 concern above. `artifact_upload` and writeup have no submit path in v2 (SUB-F1 is future).
- Phase 8: the mount paths for `dataset_sources`/`model_sources` are unverified, and internet-off pretrained weights depend on them. `kernel_sources` pins are silently dropped. It is unverified how a run resumes from a cancelled version's checkpoint. `docker_image` pinning (RUN-F2) and the T4×2 accelerator string (RUN-F3) are future. Live-probe early in the phase.
- Phase 9: csv_upload through a v2 profile has never run live end to end, and writeup guidance has never been exercised live.
- Phase 10: RES-04 runs host metric code, a trust boundary, so run it on Kaggle via `kernel_sources` and only after the AI confirms the match.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260925-5z0 | Fix SKILL.md script paths (${CLAUDE_SKILL_DIR}), docstring escapes, unused test imports, stale planning docs | 2026-09-25 | 2951a70 | [260925-5z0-fix-skill-md-script-paths-docstring-esca](./quick/260925-5z0-fix-skill-md-script-paths-docstring-esca/) |
| 260925-66x | Fix kernel path live bugs: notebook kernelspec, ipykernel argv/exit, flat /kaggle/working output, resolve_data_dir hardening; record A2/A3/A4 + T4 default live-verified | 2026-09-25 | fbfaa33 | [260925-66x-fix-kernel-path-notebook-kernelspec-ipyk](./quick/260925-66x-fix-kernel-path-notebook-kernelspec-ipyk/) |

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Live verification (EXP-05) | One opt-in live Kaggle GPU push (convert→push→poll→pull→record) to confirm A1 T4×2 string / A2 status render / A3 log+marker coverage / A4 push version regex, findings into references/kaggle-cli-behavior.md. Needs Phase 1 creds + Phase 2 data + Phase 3 scaffolded experiment. | Live-verified 2026-09-25 (A2/A3/A4 + T4 default; T4x2 string still unverified) — 4 bugs fixed in quick 260925-66x | 04-05 (2026-07-12) |

Items acknowledged at the v1.0 milestone close on 2026-09-25:

| Category | Item | Status |
|----------|------|--------|
| quick_task | 260925-5z0-fix-skill-md-script-paths-docstring-esca | False positive: the task is complete (commit 2951a70), but its summary is named `260925-5z0-SUMMARY.md` and the audit expects `SUMMARY.md` |
| quick_task | 260925-66x-fix-kernel-path-notebook-kernelspec-ipyk | False positive: the task is complete (commit fbfaa33), same file-naming mismatch |

## Session Continuity

Last session: 2026-09-25
Stopped at: v2.0 roadmap created (Phases 6-10, 38/38 requirements mapped); awaiting user approval
Resume file: None

## Operator Next Steps

- Review and approve the v2.0 roadmap in `.planning/ROADMAP.md` (the orchestrator commits after approval).
- Then start Phase 6 with `/gsd-discuss-phase 6`, or go straight to `/gsd-plan-phase 6`.
