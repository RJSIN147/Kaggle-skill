---
phase: 02-competition-context-data
plan: 01
subsystem: infra
tags: [kaggle-cli, egress-allowlist, sandbox, subprocess, gateway, security, pytest]

# Dependency graph
requires:
  - phase: 01-workspace-credentials-egress-guardrails
    provides: "check_credentials.run_kaggle_list (no-echo/timeout/exit-code pattern), branch_remediation (match-don't-echo), init_workspace.merge_settings/_union_list (allowlist union-merge), settings.json.tmpl allowlist, leak_scan.py pre-commit guard, pytest conftest (run_script/tmp_workspace)"
provides:
  - "scripts/kaggle_gateway.py — the single Kaggle CLI gateway (D-16): run_kaggle / preflight_entered / classify_gate / dump_last_error"
  - "UI_GATE=77 and LIMIT_NEEDS_USER=78 reserved exit-code constants for downstream import (02-02+)"
  - "api.kaggle.com on the egress allowlist template (auto-retrofits existing workspaces via union-merge)"
  - "control/raw/last-error.txt gitignore hygiene (template + line-level retrofit helper)"
  - "recorded 403 gate signature + two live CLI facts (pages --content exists; download has no --unzip) in kaggle-cli-behavior.md"
affects: [02-02-capture-competition, 02-03-download-data, 02-04-analyze-data, 05-scoring-submission]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One gateway owns every Kaggle CLI call (D-16): timeout-bounded, both-stream capture, exit-code-only decisions, no-echo, gate classification, reserved exit codes"
    - "Fail-closed gate classification (D-12): positively classify only the rules gate via a cheap userHasEntered preflight; name BOTH rules + phone URLs otherwise, never guess"
    - "Quarantine-not-echo (D-11): raw CLI output goes to a gitignored control/raw/last-error.txt, never the terminal"
    - "Line-level append-if-absent gitignore retrofit (analog of create_if_absent) for an already-scaffolded workspace"

key-files:
  created:
    - "scripts/kaggle_gateway.py"
    - "tests/test_gateway.py"
    - "tests/test_egress_allowlist.py"
  modified:
    - "scripts/templates/settings.json.tmpl"
    - "scripts/templates/gitignore.tmpl"
    - "references/egress-allowlist.md"
    - "references/kaggle-cli-behavior.md"

key-decisions:
  - "api.kaggle.com added narrow (single host, no wildcard) — it is the CLI 2.2.3 kagglesdk PROD endpoint host for pages/files/list/download (VERIFIED-LIVE); the Phase 1 'Not api.kaggle.com' claim was VERIFIED WRONG and corrected with a Correction-history row"
  - "Gate classification is positive for the rules gate ONLY (userHasEntered preflight); any 403 that survives entered/indeterminate state fails closed naming both rules + phone URLs (D-12)"
  - "Reserved exit codes 77=UI_GATE (EX_NOPERM) / 78=LIMIT_NEEDS_USER (EX_CONFIG); 124 reserved for TimeoutExpired, 126/127/128+ avoided"
  - "Transient error dumps (last-error.txt) are gitignored (may embed token-shaped strings); provenance JSON under control/raw/ stays TRACKED (D-03)"

patterns-established:
  - "Kaggle Gateway (D-16): every Phase 2 entry point routes CLI calls through run_kaggle; no forking the subprocess/no-echo/exit-code contract"
  - "preflight_entered matches the EXACT slug via ref.rsplit('/',1)[-1] over a FUZZY search — never rows[0]"

requirements-completed: [COMP-01, COMP-02]

# Metrics
duration: 7min
completed: 2026-07-10
---

# Phase 2 Plan 01: Kaggle Gateway + Egress Prerequisite Summary

**Single Kaggle CLI gateway (D-16) — run_kaggle / preflight_entered / classify_gate / dump_last_error with fail-closed 403 handling — plus the blocking `api.kaggle.com` egress fix that unblocks all of Phase 2.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-10T11:36:52Z
- **Completed:** 2026-07-10T11:43:49Z
- **Tasks:** 3
- **Files modified:** 7 (3 created, 4 modified)

## Accomplishments
- Built `scripts/kaggle_gateway.py`, the one gateway all three Phase 2 entry points route through: `run_kaggle` (generalises Phase 1's `run_kaggle_list`; 127 if CLI absent, 124 on timeout, combined stdout+stderr never echoed), `preflight_entered` (exact-slug `userHasEntered` over a fuzzy search; True|False|None; never busy-loops), `classify_gate` (D-12 fail-closed, names both gates, never echoes the raw buffer), `dump_last_error` (D-11 quarantine to a gitignored file), and the `UI_GATE=77` / `LIMIT_NEEDS_USER=78` constants.
- Landed the phase's blocking egress prerequisite: added `api.kaggle.com` (narrow, no wildcard) to `settings.json.tmpl`; because `merge_settings` unions `allowedDomains`, re-running `init` auto-retrofits existing workspaces.
- Corrected the stale `references/egress-allowlist.md` claim (rewrote the `www.kaggle.com` row, added an `api.kaggle.com` host row, recorded a 2026-07-10 Correction-history row citing the CLI 2.2.3 / kagglesdk PROD host probe).
- Recorded the observed generic 403 gate signature and the two live-verified CLI facts (`competitions pages --content` exists; `competitions download` has no `--unzip`) in `kaggle-cli-behavior.md` with the same sanitized-capture provenance.
- Added `control/raw/last-error.txt` gitignore hygiene for new workspaces plus a line-level retrofit helper for existing ones; provenance JSON stays tracked.

## Task Commits

Each task was committed atomically:

1. **Task 1: RED tests — egress allowlist membership + gateway pure-function contract** - `e48a68d` (test)
2. **Task 2: BLOCKING egress fix — add api.kaggle.com; correct the stale allowlist claim** - `96180db` (fix)
3. **Task 3: Kaggle Gateway (D-16) + gitignore hygiene + CLI-behavior reference** - `daf73a9` (feat)

_TDD gate (Task 3, `tdd="true"`): RED `test(02-01)` (e48a68d) → GREEN `feat(02-01)` (daf73a9). No refactor commit needed._

## Files Created/Modified
- `scripts/kaggle_gateway.py` - The D-16 gateway: run_kaggle / preflight_entered / classify_gate / dump_last_error, UI_GATE/LIMIT_NEEDS_USER constants, no-echo + fail-closed.
- `tests/test_gateway.py` - Unit coverage for preflight exact-slug fuzzy match (True|False|None), exit-code constants, classify_gate fail-closed naming both URLs and never echoing the raw buffer.
- `tests/test_egress_allowlist.py` - Asserts api.kaggle.com on the generated allowlist, Phase 1 required hosts intact, no wildcard broadening.
- `scripts/templates/settings.json.tmpl` - Added `api.kaggle.com` to allowedDomains.
- `scripts/templates/gitignore.tmpl` - Ignore `control/raw/last-error.txt`; provenance `control/raw/*.json` stays tracked.
- `references/egress-allowlist.md` - Rewrote www.kaggle.com row, added api.kaggle.com host row, added a Correction-history row.
- `references/kaggle-cli-behavior.md` - Added the 403 gate signature table + two live CLI facts.

## Decisions Made
- Added only the single verified host `api.kaggle.com` (no wildcard) — narrow allowlist per T-02-EGRESS.
- `classify_gate` positively classifies only the rules gate (via preflight); all other 403s fail closed naming both rules + phone URLs (D-12), never pattern-matching "phone" into the generic 403 string.
- Reserved exit codes align with sysexits.h (77=EX_NOPERM, 78=EX_CONFIG); 124 left to the TimeoutExpired mapping.
- Transient error dumps are gitignored; provenance JSON stays tracked (D-03/D-11).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Two of the plan's Task 2 constraints were in tension: the action said to record the stale claim verbatim in the Correction-history row, while an acceptance criterion required the file to no longer contain the exact substring `` **Not** `api.kaggle.com` ``. Resolved by paraphrasing the quoted old claim in the correction row (documents what was wrong without reproducing the forbidden asserted substring). Both constraints are now satisfied — the correction is recorded and the exact substring is absent.

## User Setup Required
None - no external service configuration required. (`api.kaggle.com` retrofits automatically on the next `init` re-run because `merge_settings` unions the allowlist; a live human-checkpoint that a sandboxed capture/download actually reaches `api.kaggle.com` is deferred to the phase's integration/UI gate, per RESEARCH fix step 4.)

## Next Phase Readiness
- The gateway is ready for `capture_competition.py` (02-02), `download_data.py` (02-03), and `analyze_data.py` (02-04) to import: they call `run_kaggle` / `preflight_entered` / `classify_gate` / `dump_last_error` rather than forking the CLI contract, and branch on `UI_GATE` / `LIMIT_NEEDS_USER`.
- Egress is unblocked: `api.kaggle.com` is on the template and auto-retrofits.
- Concern (non-blocking): live enforcement that a sandboxed CLI call reaches `api.kaggle.com` is UNVERIFIED here (unit tests assert generated-settings correctness only); confirm at the phase's live/human checkpoint.

## Self-Check: PASSED
- All 3 created + 4 modified files present on disk.
- All 3 task commits (e48a68d, 96180db, daf73a9) present in git log.
- Verification: `uv run pytest tests/test_egress_allowlist.py tests/test_gateway.py -q` → 10 passed; `uv run pytest tests/ -x -q` → 42 passed (no Phase 1 regression).

---
*Phase: 02-competition-context-data*
*Completed: 2026-07-10*
