---
phase: 02-competition-context-data
plan: 05
subsystem: testing
tags: [kaggle-cli, pytest, live-integration, egress, gate-flow, skill-md, competition-context]

# Dependency graph
requires:
  - phase: 02-01
    provides: kaggle_gateway (run_kaggle, preflight_entered, classify_gate, UI_GATE=77, LIMIT_NEEDS_USER=78); egress allowlist (api.kaggle.com)
  - phase: 02-02
    provides: capture_competition.py (constitution capture, untrusted-prose quarantine, daily-limit provenance)
  - phase: 02-03
    provides: download_data.py (credential gate → rules-gate preflight → download → zip-slip-safe extract)
  - phase: 02-04
    provides: analyze_data.py + cv_evidence.py (schema/CV evidence, real adversarial validation degrading to AV SKIPPED)
provides:
  - "SKILL.md operator flow: three-stage capture → download → analyze (D-08 order, D-09 idempotent entry points) + exit-77/78 gate protocol with the SKILL as the only waiter"
  - "SKILL.md Scripts table rows for all five Phase 2 scripts + explicit-path control/raw staging caution"
  - "tests/test_competition_live.py: opt-in (-m live) CLI-shape assertions (pages/files/list/download/403) + token-leak guard + phone-gate skip placeholder"
  - "Live proof: api.kaggle.com reachability end-to-end (02-01 allowlist fix) + competition.md provenance-tagged daily-limit line"
  - "kaggle_gateway.preflight_entered fixed to parse the pretty-printed list JSON (rules-gate classifier now actually works)"
  - "Confirmed phone-verification URL (https://www.kaggle.com/settings) recorded with honest provenance; assumption A3 RESOLVED"
affects: [phase-03-experiment-loop, phase-05-scoring-submission]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Opt-in live suite isolated via pytest addopts `-m 'not live'` — the mock suite is the default run; live conditions can never redden it; a command-line `-m live` overrides"
    - "Live token-leak guard: reuse _TOKEN_SHAPED on FRAMEWORK-authored transcripts only (not raw JSON payloads, whose HTML legitimately carries long runs); assert OAuth prefixes absent even on raw buffers"
    - "Pin observed CLI shapes against a REAL call, not just a hand-built fixture (the pretty-printed JSON bug was invisible to the compact json.dumps mock)"

key-files:
  created:
    - tests/test_competition_live.py
    - .planning/phases/02-competition-context-data/02-05-SUMMARY.md
  modified:
    - SKILL.md
    - scripts/kaggle_gateway.py
    - references/kaggle-cli-behavior.md
    - references/egress-allowlist.md
    - pyproject.toml
    - tests/test_gate.py
    - tests/test_gateway.py

key-decisions:
  - "Added pytest addopts `-m 'not live'` so 'live excluded from default' is literally true and the mock suite stays green independent of live conditions"
  - "Fixed preflight_entered (Rule 1) rather than deferring — it returned None for every slug, defeating the D-10 rules-gate classifier that the whole phase premise rests on"
  - "Recorded the confirmed phone URL only AFTER human confirmation (never auto-approved the blocking human-action gate); /settings/phone 404s → /settings"

patterns-established:
  - "Live suite isolation via addopts + per-test credential skip guard (reused from test_credentials_live.py)"
  - "Banner-tolerant full-payload JSON parse for CLI --format json output (CLI 2.2.3 pretty-prints)"

requirements-completed: [COMP-01, COMP-02, COMP-03]

# Metrics
duration: 46min
completed: 2026-07-10
---

# Phase 2 Plan 05: Competition Context & Data Integration Summary

**Operator-facing three-stage flow (capture → download → analyze) + exit-77/78 gate protocol in SKILL.md, an opt-in live suite pinning the real CLI-2.2.3 shapes, and live proof that the api.kaggle.com allowlist fix works end to end — plus a found-and-fixed rules-gate parser bug and the human-confirmed phone-settings URL.**

## Performance

- **Duration:** ~46 min (spans a blocking human-action checkpoint for the browser rules/phone confirmation)
- **Started:** 2026-07-10T20:50:38+05:30
- **Completed:** 2026-07-10T21:36:56+05:30
- **Tasks:** 3 (2 automatable + 1 human-action gate, resolved)
- **Files modified:** 7 (+1 created test, +1 SUMMARY)

## Accomplishments
- SKILL.md now documents the operator flow: three idempotent entry points in D-08 order, the exit-77 (rules gate → surface URL, re-invoke; the re-invocation's preflight IS the verification) and exit-78 (ask the user for the daily limit) protocol with the SKILL as the ONLY waiter, the untrusted-prose quarantine, the AV-SKIPPED degrade, and the explicit-path `control/raw/` staging caution (never `git add -A`). Scripts table lists all five Phase 2 scripts.
- `tests/test_competition_live.py` (`@pytest.mark.live`) pins the VERIFIED-LIVE shapes on the read-only `titanic` slug: `pages → [{name, content:HTML}]`, `files → [{name, size:int, creationDate}]`, `list --search → userHasEntered`, a real download → single `titanic.zip`, and an un-entered slug → generic 403 (exit 1). Reuses `_TOKEN_SHAPED` to assert no secret leaks; carries a documented phone-gate skip placeholder.
- **Live verification (Claude ran it, not the user):** `capture_competition.py` reached `api.kaggle.com` and exited 0 (NOT blocked/prompted) — the end-to-end proof of the 02-01 allowlist fix — and populated `competition.md` with `**Daily submission limit:** 10/day (provenance: extracted).`. The `-m live` suite ran **6 passed / 1 skipped** with no token-shaped string in any transcript.
- Found and fixed a load-bearing rules-gate bug (see Deviations) and resolved the last human-only gap: the confirmed phone-settings URL.

## Task Commits

Each task was committed atomically:

1. **Task 1: opt-in live CLI-shape suite + token-leak guard** - `e2c0489` (test) — includes the supporting `pyproject.toml` addopts
2. **Task 2: SKILL three-stage flow + exit-77/78 gate protocol** - `5beeaeb` (docs)
3. **Task 2 (deviation): preflight_entered parses full pretty-printed list JSON** - `c1d3df9` (fix)
4. **Task 3 (human-action resolved): correct phone-settings URL to /settings, A3 RESOLVED** - `79779e8` (fix)

## Files Created/Modified
- `tests/test_competition_live.py` - opt-in live CLI-shape assertions + token-leak guard + phone-gate skip placeholder (created)
- `SKILL.md` - "Competition context & data" section (three-stage flow, exit-77/78 gate protocol, staging caution) + five Scripts-table rows
- `scripts/kaggle_gateway.py` - `_parse_json_array` (banner-tolerant full-payload parse); `preflight_entered` fixed; `_PHONE_URL` → `https://www.kaggle.com/settings`
- `references/kaggle-cli-behavior.md` - recorded the pretty-printed-JSON finding + its fix; CONFIRMED phone-URL provenance (A3 resolved)
- `references/egress-allowlist.md` - human-facing `/settings/phone` → `/settings` (no allowlist entry change — still `www.kaggle.com`)
- `pyproject.toml` - `addopts = -m 'not live'` (mock suite is the default run; live isolated)
- `tests/test_gate.py`, `tests/test_gateway.py` - updated the two pinned-URL assertions to `/settings`

## Decisions Made
- **addopts `-m 'not live'`:** realizes the plan's documented "live suite excluded by default" model literally, so the default `uv run pytest tests/` is the mock suite (83 green) and live conditions can never turn it red. A command-line `-m live` overrides it to run the live suite explicitly.
- **Token-leak guard scope:** apply `_TOKEN_SHAPED` to framework-authored transcripts (short, secret-free by contract); apply only the OAuth-prefix checks to raw CLI buffers, whose HTML content legitimately contains ≥32-char runs. This keeps the guard meaningful without false positives.
- **Fix over defer for the preflight bug:** it is the exact mechanism the phase's D-10 gate flow depends on; documenting the CLI shape as "verified" while shipping a preflight that never resolves would be dishonest.
- **Never auto-approved the human-action gate:** stopped at Task 3, returned the checkpoint, and recorded the phone URL only after the user confirmed `/settings/phone` 404s.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `preflight_entered` returned `None` for every slug (rules-gate classifier dead)**
- **Found during:** Task 2 (live `-m live` run — `test_list_search_exposes_user_has_entered` failed: `preflight_entered("titanic")` was `None` though the row carried `userHasEntered`)
- **Issue:** CLI 2.2.3 **pretty-prints** `competitions list --search <slug> --format json` across many lines (a live `titanic` result is 162 lines, `[` … `]`). The 02-01 gateway parsed only `json.loads(out.splitlines()[-1])` — i.e. the closing `]` — which raises, so it returned `None` unconditionally. This silently defeated the D-10 positive rules-gate classification (the phase's entire premise): un-entered competitions would never emit the clean pre-download exit-77 with the rules URL; they degraded to the download-attempt fail-closed path. The 02-01 mock stub used compact `json.dumps(rows)`, so the multi-line shape only surfaced under a real call.
- **Fix:** Added banner-tolerant `_parse_json_array` (parse the whole payload; retry from the first `[`); `preflight_entered` now parses the full output. `preflight_entered("titanic")` live: `None` → `True`.
- **Files modified:** `scripts/kaggle_gateway.py`, `references/kaggle-cli-behavior.md`
- **Verification:** Full mock suite still green (83 passed; gateway/gate mock tests 12 passed — backward-compatible with the compact stubs); live suite then 6 passed / 1 skipped. Re-pinned by `tests/test_competition_live.py::test_list_search_exposes_user_has_entered`.
- **Committed in:** `c1d3df9`

**2. [Rule 1 - Bug / A3] Phone-verification URL was a dead link (`/settings/phone` 404s)**
- **Found during:** Task 3 (human-action checkpoint — user confirmed in a browser)
- **Issue:** `_PHONE_URL = "https://www.kaggle.com/settings/phone"` is surfaced to a user hitting an unclassifiable 403, but that path 404s. The working phone-verification settings page is `https://www.kaggle.com/settings` (exactly the fallback the plan pre-authorized).
- **Fix:** `_PHONE_URL → https://www.kaggle.com/settings`; updated the two tests that pin it (`test_gate.PHONE_URL`, the `test_gateway` classify_gate assertion), the operator mention in `SKILL.md`, and the human-facing references in `kaggle-cli-behavior.md` + `egress-allowlist.md`. No allowlist entry changed (still `www.kaggle.com`). Recorded CONFIRMED provenance; assumption A3 RESOLVED.
- **Files modified:** `scripts/kaggle_gateway.py`, `tests/test_gate.py`, `tests/test_gateway.py`, `SKILL.md`, `references/kaggle-cli-behavior.md`, `references/egress-allowlist.md`
- **Verification:** Non-live suite green (83 passed, 8 deselected); the mock `test_classify_gate_fails_closed_names_both_urls` confirms `/settings` appears in the fail-closed message.
- **Committed in:** `79779e8`

### Config change (supports Task 1 acceptance)

- **[Rule 3 - Blocking] `pyproject.toml` addopts `-m 'not live'`** — required to make "excluded from the default run" literally true (the repo previously ran live tests in the default suite whenever a credential was present) and to isolate live tests so they cannot redden the mock suite. Committed with Task 1 (`e2c0489`).

---

**Total deviations:** 2 auto-fixed bugs (both Rule 1) + 1 supporting config change (Rule 3). One (preflight) touched an out-of-declared-scope file (`scripts/kaggle_gateway.py`) — justified: it is the load-bearing mechanism this plan exists to verify, and the live run surfaced it.
**Impact on plan:** No scope creep. The preflight fix makes the phase's D-10 gate flow actually function; the phone-URL fix removes a user-facing dead link; the addopts change realizes the plan's documented test model. All within COMP-01/02/03.

## Issues Encountered
- The account had already entered `titanic`, so `download_data.py` exited 0 (downloaded) rather than emitting exit 77. The rules-gate mechanism was still proven via the live un-entered-slug test (generic 403) and the corrected `preflight_entered` returning `False` for an un-entered competition. The browser rules-acceptance half of the Task 3 gate was therefore moot for `titanic`; only the phone-URL confirmation required the human.

## User Setup Required
None beyond the existing Kaggle credential (`~/.kaggle/access_token`, already validated). The live suite is opt-in (`uv run pytest -m live tests/test_competition_live.py`) and skips cleanly without a credential.

## Next Phase Readiness
- Phase 3 (experiment loop) can rely on a populated `competition.md` (metric + provenance-tagged daily limit), a working three-stage capture/download/analyze flow, and a functioning rules-gate preflight.
- Phase 5 (scoring/submission) inherits `submission.daily_limit` + `limit_provenance` (here: `10`, `extracted`) and the confirmed phone-settings URL for its gate messaging.
- No blockers. Live api.kaggle.com reachability and the gate flow are proven; no further live calls needed to proceed.

## Live Verification Results (proof)
- **api.kaggle.com reachability:** CONFIRMED — `capture_competition.py --workspace <sandbox>` exited 0, reached `api.kaggle.com`, not blocked/prompted (02-01 allowlist fix proven end to end). Sandbox lived OUTSIDE the repo; no `data/`/`control/` or token entered the repo or any output.
- **competition.md provenance line:** `**Daily submission limit:** 10/day (provenance: extracted).`
- **`-m live tests/test_competition_live.py`:** 6 passed, 1 skipped (phone-gate placeholder); no token-shaped string leaked.
- **default `uv run pytest tests/`:** 83 passed, 8 deselected (mock suite green, live isolated).

## Self-Check: PASSED
- Files verified present: `tests/test_competition_live.py`, `SKILL.md`, `scripts/kaggle_gateway.py`, `references/kaggle-cli-behavior.md`, `references/egress-allowlist.md`, `pyproject.toml` — all FOUND.
- Commits verified in history: `e2c0489`, `5beeaeb`, `c1d3df9`, `79779e8` — all FOUND.
- No `control/`, `data/`, or competition data in the repo/worktree; no token or token-shaped string in any file or output; STATE.md/ROADMAP.md untouched.

---
*Phase: 02-competition-context-data*
*Completed: 2026-07-10*
