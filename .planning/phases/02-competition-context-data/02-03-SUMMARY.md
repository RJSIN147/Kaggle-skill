---
phase: 02-competition-context-data
plan: 03
subsystem: api
tags: [kaggle, zip-slip, zipfile, safe-extract, ui-gate, exit-code, tdd, security]

# Dependency graph
requires:
  - phase: 02-01
    provides: "kaggle_gateway.py (run_kaggle, preflight_entered, classify_gate, dump_last_error, UI_GATE=77)"
  - phase: 01-workspace-credentials-egress-guardrails
    provides: "check_credentials.py (MalformedStateJSON, state.json.credentials==VALIDATED gate)"
provides:
  - "scripts/safe_extract.py — UnsafeArchiveMember + safe_extract() zip-slip reject-and-raise guard"
  - "scripts/download_data.py — credential gate → rules-gate preflight → download → safe extract into data/"
  - "tests/test_extract.py — four zip-slip vectors refused + benign extract + no-file-escapes (C4)"
  - "tests/test_gate.py — exit-77 gate, probe-once, sleep-not-called, re-probe proceeds, unclassified-403 fail-closed (C3)"
affects: [02-02, 03-experiment-loop, 04-kernel-path, 05-scoring-submission]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Validate-before-write extraction: reject every archive member before a single extractall (no partial write)"
    - "Never-busy-loop UI gate: one cheap preflight probe → exit reserved code; the re-invocation IS the verification"
    - "Fail-closed 403 classification: unclassifiable gate names BOTH rules+phone URLs; raw output quarantined, never echoed"

key-files:
  created:
    - scripts/safe_extract.py
    - scripts/download_data.py
    - tests/test_extract.py
    - tests/test_gate.py
  modified: []

key-decisions:
  - "safe_extract validates ALL members (absolute/.. /symlink/realpath-escape) before extractall — a rejected archive writes nothing (D reject-and-raise, criterion 4)"
  - "download_data runs a single preflight_entered probe before download; on the rules gate it exits UI_GATE(77) with no poll/backoff/blocking-read (D-10)"
  - "preflight None/True → attempt download; a surviving 403 is unclassifiable → classify_gate names both URLs, dump_last_error quarantines raw output (D-11/D-12)"
  - "slug comes from config.json/argv only, never from competition text (D-02); credential gate refuses unless state.json.credentials==VALIDATED (Phase 1 D-07)"

patterns-established:
  - "Pattern 1: stdlib-only, self-locating, --workspace argparse, non-interactive entry point routing every CLI call through the D-16 gateway"
  - "Pattern 2: in-test lazy import (importlib.import_module) so pytest collection never crashes on a not-yet-built script"

requirements-completed: [COMP-02, COMP-03]

# Metrics
duration: ~18min
completed: 2026-07-10
---

# Phase 2 Plan 03: Local Data Download + Zip-Slip-Safe Extraction Summary

**download_data clears the UI-only rules gate without ever busy-looping (single preflight probe → exit 77 + exact rules URL), then downloads and extracts the competition data into data/ through a reject-and-raise zip-slip guard that refuses absolute/../symlink/out-of-tree members before writing a single byte.**

## Performance

- **Duration:** ~18 min
- **Tasks:** 3
- **Files created:** 4 (2 scripts, 2 test modules)
- **Test result:** 54 passed (full suite); 12 passed for this plan's two modules

## Accomplishments
- `scripts/safe_extract.py` — `UnsafeArchiveMember` + `safe_extract(zip_path, dest)` refuses every zip-slip vector (absolute/drive path, `..` component, symlink member via `S_ISLNK(external_attr>>16)`, realpath-escape) and validates ALL members before `extractall`, so a malicious archive leaves the filesystem untouched (T-02-PATH-01).
- `scripts/download_data.py` — credential gate (`VALIDATED`, fail-clear on corrupt state.json) → single `preflight_entered` probe → download via the gateway → `safe_extract` the single `<slug>.zip` into `data/`. On the rules gate it exits `UI_GATE`(77) printing the exact rules URL with no poll/backoff/blocking-read; an unclassifiable 403 fails closed naming both the rules and phone URLs and quarantines the raw CLI output to the gitignored `control/raw/last-error.txt`.
- Behavior-pinning tests: `test_extract.py` (four malicious vectors + no-file-escapes aggregate + benign control) and `test_gate.py` (exit-77 + rules URL + probe-once + sleep-not-called, re-probe True proceeds to extract, unclassified-403 fail-closed + no raw-buffer leak, credential refusal before any probe, malformed-state fail-clear).

## Task Commits

Each task was committed atomically:

1. **Task 1: RED tests — malicious-archive fixture + gate flow** - `7382935` (test)
2. **Task 2: safe_extract.py — zip-slip reject-and-raise guard** - `7469369` (feat, GREEN)
3. **Task 3: download_data.py — credential gate → preflight → download → safe extract** - `737a3fc` (feat, GREEN)

_TDD gate order verified in git log: `test(...)` (RED) → `feat(...)` (GREEN) → `feat(...)` (GREEN)._

## Files Created/Modified
- `scripts/safe_extract.py` - stdlib-only zip-slip guard: `UnsafeArchiveMember` + `safe_extract()`; never imports shutil (no `unpack_archive` path).
- `scripts/download_data.py` - non-interactive `--workspace` entry point; credential gate → preflight → download → safe extract; routes all CLI calls through `kaggle_gateway`.
- `tests/test_extract.py` - parametrized malicious-archive refusal + no-file-escapes + benign extract + stdlib-only guard.
- `tests/test_gate.py` - never-busy-loop gate flow, fail-closed 403, credential gate, fail-clear state.

## Decisions Made
- **Monkeypatch the shared `kaggle_gateway` module, not per-name imports.** `download_data` calls `gw.preflight_entered/run_kaggle/classify_gate/dump_last_error` by attribute, so tests stub the single gateway module and the REAL `classify_gate` runs against a stubbed `preflight_entered` — deterministic, and no real Kaggle CLI call is ever made (kaggle IS on PATH in the test venv, so this matters).
- **`-p data/` then extract in place.** The zip lands directly in `data/` and is extracted there; the archive is left on disk (Claude's-discretion per D-09/CONTEXT — keeping it makes a re-run idempotent and the pull re-inspectable).
- **Archive-name fallback.** Prefer `<slug>.zip`; if absent, fall back to the sole `*.zip` in `data/` (some competitions name the archive differently).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_extract source-grep false-positive on the shutil docstring mention**
- **Found during:** Task 2 (GREEN run of test_extract.py)
- **Issue:** The Task-1 assertion `"shutil.unpack_archive" not in getsource(module)` tripped because `safe_extract.py`'s docstring *mentions* `shutil.unpack_archive` to explain WHY it is deliberately avoided. The intent was "does not USE shutil", not "does not mention it".
- **Fix:** Replaced the brittle source-grep with a namespace check — `assert not hasattr(module, "shutil")` (and `hasattr` for zipfile/os/stat). Not importing shutil is a stronger, non-brittle guarantee that `unpack_archive` is unreachable, and it preserves the explanatory docstring.
- **Files modified:** tests/test_extract.py
- **Verification:** `uv run pytest tests/test_extract.py -q` → 7 passed.
- **Committed in:** `7469369` (part of Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1× Rule 1). **Impact on plan:** Corrected a self-inflicted test assertion; no production-code or scope change. All acceptance criteria met.

## Issues Encountered
None beyond the deviation above.

## Threat Model Coverage
All `mitigate` dispositions in the plan's STRIDE register are implemented and tested:
- **T-02-PATH-01** (zip-slip EoP) → reject-and-raise on absolute/../symlink + realpath containment; validate-before-write → `test_no_file_escapes_across_all_vectors`.
- **T-02-DOS-01** (busy-loop) → single preflight, exit `UI_GATE`, no poll/backoff/blocking-read → `test_gate_false_..._without_busy_loop` (probe-count==1, sleep-not-called).
- **T-02-GUESS-01** (repudiation) → generic 403 fail-closed naming BOTH URLs → `test_unclassified_403_fails_closed_naming_both_urls`.
- **T-02-LEAK-01** (info disclosure) → raw output quarantined to gitignored `last-error.txt`, never echoed → same test asserts sentinel absent from stdout, present in the dump file.
- **T-02-AUTHZ-01** (credential EoP) → refuse unless `credentials==VALIDATED`, fail-clear on corrupt → `test_refuses_without_validated_credentials`, `test_malformed_state_fails_clear`.

No new threat surface beyond the plan's `<threat_model>` was introduced.

## User Setup Required
Per plan `user_setup`: Kaggle's rules-acceptance (and phone-verification) gates are UI-only — there is no API to accept them. When `download_data.py` surfaces a `UI_GATE`(77) with the rules URL, the operator must accept the competition rules in a browser at `https://www.kaggle.com/competitions/<slug>/rules`, then re-run. The re-invocation's preflight probe is the verification.

## Next Phase Readiness
- `data/` is populated with safely-extracted competition CSVs, ready for `analyze_data.py` (plan 02-02's schema/CV-evidence step) and Phase 3's experiment loop.
- No blockers introduced. Note: the plan's `<interfaces>` calls out the egress finding that `api.kaggle.com` must be on the allowlist for live CLI calls — that allowlist migration is plan 02-02's scope (touches `settings.json.tmpl`), not this plan's; this plan is verified via mock-backed unit tests and does not modify egress config.

---
*Phase: 02-competition-context-data*
*Completed: 2026-07-10*
