---
phase: 02-competition-context-data
plan: 07
subsystem: competition-context-data
tags: [download, exit-codes, gate-classification, security, gap-closure]
requires:
  - scripts/kaggle_gateway.py (run_kaggle 127/124 contract, UI_GATE, dump_last_error, classify_gate)
  - scripts/capture_competition.py (_gateway_failure — the source-of-truth branch pattern)
provides:
  - "download_data.py: rc==127/124 → tailored remediation + mirrored exit code, reserved before the 403 UI-gate branch"
affects:
  - scripts/download_data.py
  - tests/test_gate.py
tech-stack:
  added: []
  patterns:
    - "Mirror sibling gateway-failure branch logic (capture_competition._gateway_failure) into download_data so reserved codes get identical, correct handling"
key-files:
  created: []
  modified:
    - scripts/download_data.py
    - tests/test_gate.py
decisions:
  - "127/124 print framework-authored, secret-free messages and return the raw code; only the else-branch (403) quarantines via dump_last_error + classify_gate — matching _gateway_failure exactly (no busy-loop, no echo)."
metrics:
  duration: ~10min
  completed: 2026-07-10
  tasks: 1
  files: 2
requirements: [COMP-02]
---

# Phase 2 Plan 07: download_data exit-code classification (WR-01 Gap 2) Summary

Closed Gap 2 (review WR-01): `download_data.main` routed EVERY non-zero download
return — including rc=127 (kaggle CLI missing) and rc=124 (timeout), both RESERVED
by `kaggle_gateway.run_kaggle` — into the exit-77 UI-gate branch, misreporting
"accept the rules in a browser" and looping the human forever when the real fix is
"install the CLI" / "check egress". The rc==127 / rc==124 branches from the sibling
`capture_competition._gateway_failure` are now mirrored into `download_data.main`,
placed immediately after the `run_kaggle` call and BEFORE the `if rc != 0:` UI-gate
fallthrough, with no sleep/poll introduced.

## What Was Built

- **`scripts/download_data.py`** — After `rc, combined = gw.run_kaggle("competitions", "download", ...)`:
  - `if rc == 127:` prints `[BLOCKED] the kaggle CLI was not found on PATH. Install it (uv pip install kaggle) and re-run.` to stderr and `return rc` (127).
  - `if rc == 124:` prints `[BLOCKED] the kaggle CLI timed out (a stalled/blocked egress). Check the egress allowlist and re-run.` to stderr and `return rc` (124).
  - Both print framework-authored, secret-free messages only — no `gw.dump_last_error` / `gw.classify_gate` for these codes (their run_kaggle markers are fixed and secret-free, matching `_gateway_failure`).
  - The existing 403 fail-closed branch (`dump_last_error` + `classify_gate` + `return gw.UI_GATE`) is unchanged for all other non-zero rc.
- **`tests/test_gate.py`** — Two regression tests reusing the `_set_credentials` + `time.sleep`-monkeypatch idioms:
  - `test_missing_cli_rc127_reports_install_not_ui_gate`: preflight None, run_kaggle → (127, ...) → main returns 127 (not 77); output has "not found on path" + "install"; no rules URL / "accept the rules" / "[ui_gate]" text; `dump_last_error`/`classify_gate` stubbed to raise (proving they are NOT called); `slept["n"] == 0`.
  - `test_timeout_rc124_reports_egress_not_ui_gate`: run_kaggle → (124, ...) → main returns 124 (not 77); output has "timed out" + "egress"; same no-UI-gate + no-quarantine + no-sleep assertions.

## Verification

- `uv run pytest tests/test_gate.py -q` → 7 passed (2 new 127/124 tests + 5 pre-existing exit-77 / credential / fail-clear paths all green).
- `uv run pytest tests/ -q` → 85 passed, 8 deselected (net +2 tests; no pre-existing mock test regressed).
- `grep -vE '^\s*#' scripts/download_data.py | grep -c 'sleep('` → 0 (never-busy-loop guarantee holds).

## TDD Gate Compliance

- RED: `test(02-07): add failing rc==127/124 remediation regression tests` (fabf24f) — 2 new tests failed (127/124 hit `dump_last_error`), 5 existing passed.
- GREEN: `fix(02-07): route rc==127/124 to correct remediation, not exit-77 UI-gate` (cf7b100) — 7/7 gate tests + 85/85 suite pass.
- REFACTOR: none needed (minimal, clean mirror of the sibling branch).

## Deviations from Plan

None - plan executed exactly as written.

## Threat Model Compliance

- T-02-07-01 (Information disclosure): the 127/124 branches print fixed framework-authored messages and `return rc`; they do NOT echo the raw combined buffer. The 403 path still quarantines via `dump_last_error`. Tests stub `dump_last_error`/`classify_gate` to raise, proving the raw buffer never flows for 127/124.
- T-02-07-02 (DoS / busy-loop): no sleep/poll/retry added; asserted via the monkeypatched `time.sleep` (`slept["n"] == 0`) and the grep.
- T-02-07-03 (Spoofing / misleading remediation): rc 127/124 now get correct, distinct remediation instead of the misleading "accept the rules" UI-gate instruction — the WR-01 fix.

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: scripts/download_data.py (modified, rc==127/124 branches present)
- FOUND: tests/test_gate.py (modified, 2 new tests present)
- FOUND: commit fabf24f (RED)
- FOUND: commit cf7b100 (GREEN)
