---
phase: 01-workspace-credentials-egress-guardrails
plan: 04
subsystem: auth
tags: [kaggle, credentials, cli, subprocess, exit-code, masking, consent-gate, chmod-600, dotenv, egress, d-04, d-06, d-07, setup-03, setup-04]

# Dependency graph
requires:
  - phase: 01-01
    provides: "RED pytest suite pinning the credential contract (test_credentials.py: test_precedence/test_kaggle_missing/test_chmod_600/test_chmod_600_requires_consent/test_env_population_requires_consent/test_subprocess_output_no_secret; test_no_credential_leak.py; test_credentials_live.py -m live)"
  - phase: 01-02
    provides: "init_workspace.py scaffolder + control/state.json {credentials:UNVALIDATED, next_exp_id:1} + workspace .env stub this checker flips/populates"
  - phase: 01-03
    provides: "www.kaggle.com allowlisted for the live call; leak_scan.py feeds test_no_credential_leak.py::test_scripts_exist; criterion-5 egress split carried forward"
provides:
  - "scripts/check_credentials.py — stdlib-only credential source detection (CLI 2.x precedence) + token-type + masking + consent-gated chmod-600 self-heal + consent-gated normalize-to-.env + LIVE exit-code validation + 4 secret-free remediation branches; writes control/state.json.credentials"
  - "references/kaggle-cli-behavior.md — checked-in fixture of REAL observed kaggle CLI 2.2.3 exit codes / output signatures / source precedence, incl. the VERIFIED success path (exit 0, access_token file) from the Task 3 checkpoint"
  - "kaggle>=2.2 declared as a dev/live-only dependency (pyproject.toml + uv.lock) so the -m live test is reproducible from a clean checkout"
affects: ["Phase 2 (data download uses the same credential + storage.googleapis.com egress)", "Phase 4 (kernel push/submit reuse the validated credential)", "Phase 5 (submission auth)"]

# Tech tracking
tech-stack:
  added:
    - "kaggle>=2.2 (DEV/LIVE-only test dependency — never a runtime import; check_credentials.py shells out to the CLI via subprocess when present, D-07 degrades if absent)"
  patterns:
    - "Live validation by EXIT CODE only (kaggle competitions list): never infer success from stdout text (T-01-10 anti-spoofing)"
    - "Captured subprocess stdout+stderr are buffered and NEVER surfaced raw; remediation derived by pattern-matching the combined buffer, so a token-shaped string inside it cannot leak (T-01-02)"
    - "Consent-gated mutations (D-03/D-06): without --yes, chmod-600 self-heal and .env population are only reported/offered; applied only with --yes"
    - "Credential FILES (access_token/kaggle.json) detected by EXISTENCE/mode only; content read solely under --yes (to populate .env) — a plain check never reads a real secret file off disk"
    - "Honest read-status messaging: each source label accurately states whether THIS tool reads the value; the kaggle.json line is consent-conditional (it IS read under --yes)"

key-files:
  created:
    - scripts/check_credentials.py
    - references/kaggle-cli-behavior.md
  modified:
    - pyproject.toml
    - uv.lock

key-decisions:
  - "SETUP-03 MET: live exit-code validation proven end-to-end at the Task 3 checkpoint (real ~/.kaggle/access_token file source, exit 0, state.json->VALIDATED, no leak); the previously-UNVERIFIED success path is now VERIFIED in references/kaggle-cli-behavior.md"
  - "SETUP-04 COMPLETE: the CREDENTIAL half (never echoed, masked, chmod/.env consent-gated, secrets gitignored, live exit-code validation) is MET here; the EGRESS half was closed by the 2026-07-10 discriminating probe (5/5 off-allowlist hosts prompted, no silent-allow path — the example.com result was an auto-accepted prompt, not a bypass). Standing caveat: auto-accept mode defeats the allowlist."
  - "Legacy KAGGLE_USERNAME+KAGGLE_KEY end-to-end validation remains UNVERIFIED (the real-token run used the access_token file source; the pair was never tested with a real credential) — recorded honestly, not smoothed over"
  - "kaggle declared as a dev/live-only dependency (not runtime): check_credentials.py never imports kaggle; it invokes the CLI via subprocess and degrades gracefully when absent (D-07). Declaring it keeps the -m live test reproducible without a bare runtime pip install (CLAUDE.md)"

patterns-established:
  - "Exit-code-is-truth: the live source label is advisory; pass/fail is decided strictly by the CLI's exit code"
  - "Nyquist/Wave-0 finding: a pre-authored RED suite can encode a stale assumption that the plan's own field research later refutes — fix the test to match observed reality without weakening its assertion"

requirements-completed: [SETUP-03, SETUP-04]  # SETUP-04 credential half MET here; egress half closed by the 2026-07-10 probe (see 01-03-SUMMARY)

# Metrics
duration: ~40min (across the Task 3 human-verify checkpoint pause)
completed: 2026-07-10
---

# Phase 1 Plan 04: Kaggle Credential Detection & Live Validation Summary

**`check_credentials.py` detects the Kaggle credential across the CLI 2.x precedence chain, masks it, consent-gates the chmod-600 self-heal and `.env` normalization, and LIVE-validates by exit code (`kaggle competitions list`) — flipping `control/state.json.credentials` to `VALIDATED` with four secret-free remediation branches — now proven end-to-end against a real `~/.kaggle/access_token` at the Task 3 checkpoint with no secret leak.**

## Performance

- **Duration:** ~40 min (Tasks 1-2 + pre-checkpoint test fix in the prior session; Task 3 human-verify checkpoint pause; post-checkpoint fix this session)
- **Completed:** 2026-07-10
- **Tasks:** 3 (2× `type=auto tdd=true`; 1× `checkpoint:human-verify` gate=blocking) + 1 pre-checkpoint test-defect fix + 1 post-checkpoint accuracy fix
- **Files created:** 2 (`scripts/check_credentials.py`, `references/kaggle-cli-behavior.md`); **modified:** 2 this session (`pyproject.toml`, `uv.lock`)

## Accomplishments

- **Credential detection + precedence (D-04, SETUP-03):** stdlib-only, self-locating checker reads sources in CLI 2.x precedence — `~/.kaggle/access_token` → `KAGGLE_API_TOKEN` env → `KAGGLE_USERNAME`+`KAGGLE_KEY` env → `~/.kaggle/kaggle.json` — and reports the ACTIVE one (env beats a file). Token type classified from prefix (`kagat_`/`kagrt_`/`KGAT_`/32-hex); every value is `_mask`ed or shown as an env-var name only. Files are detected by existence/mode; content is never read except under `--yes`.
- **Consent-gated fixes (D-03/D-06):** a world/group-readable `kaggle.json` is chmod-600'd ONLY with `--yes` (otherwise the fix is reported, mode untouched); `.env` is populated from a `kaggle.json` ONLY with `--yes` (otherwise offered); with nothing set, it prints set-`KAGGLE_*`/fill-`.env` instructions — never a secret.
- **Live exit-code validation (SETUP-03):** `shutil.which("kaggle")` guard FIRST (absent → `UNVALIDATED` + `uv pip install kaggle` remediation, no crash — D-07); else `kaggle competitions list`, capturing BOTH streams to a buffer, deciding STRICTLY by exit code. Exit 0 → `state.json.credentials=VALIDATED`; non-zero → one of four secret-free remediation branches (wrong/missing env var · readable credential file · 401/Unauthorized · unknown). The captured buffer is never echoed.
- **Observed-behavior fixture (Open Q1):** `references/kaggle-cli-behavior.md` records REAL CLI 2.2.3 signatures captured with a fabricated token in a throwaway venv — key finding that the CLI writes its "Authentication required" guidance to **stdout** (stderr empty), which is why the checker matches the **combined** buffer. The **success path is now VERIFIED** (see checkpoint).
- **Dependency hygiene (this session):** declared `kaggle>=2.2` in the dev/live group + refreshed `uv.lock` so the `-m live` test is reproducible from a clean checkout, honoring CLAUDE.md's "declare deps; no bare runtime pip install".

## Task Commits

1. **Task 1 — Credential detection + precedence + masking + consent-gated chmod/.env:** `661b32e` (feat)
2. **Task 2 — Live exit-code validation + 4 remediation branches + observed-behavior fixture:** `4208da0` (feat)
3. **Task 3 — Live credential validation with a real token (`checkpoint:human-verify`, gate=blocking):** PASSED; performed with explicit user consent; no code commit — see Checkpoint Outcome below.

**Pre-checkpoint test-defect fix:** `4082681` (fix) — hermetic `test_kaggle_missing` + file-based credential acceptance in the live test (see Nyquist finding below).

**Post-checkpoint accuracy fix:** `fad7426` (fix) — consent-conditional credential-read messaging + declare `kaggle` dep + record the now-VERIFIED success path.

## Checkpoint Outcome (Task 3 — live credential validation, PASSED)

The blocking `checkpoint:human-verify` was executed by the orchestrator **with the user's explicit consent**. All results below are REAL and observed on 2026-07-10:

- `uv pip install kaggle` → installed **Kaggle CLI 2.2.3** into the project `.venv`.
- `uv run pytest tests/test_credentials_live.py -m live` → **1 passed**.
- **FULL suite WITH kaggle installed:** `uv run pytest tests/ -q` → **26 passed, 0 failed** — the real proof the `4082681` hermeticity fix works: `test_kaggle_missing` passes even with a `kaggle` binary present.
- **End-to-end on a fresh scaffold:** `init_workspace.py --slug titanic` → `control/state.json` `credentials=UNVALIDATED`; then `check_credentials.py --workspace <ws>` printed the `access_token` source line and `[VALIDATED] kaggle credential works (kaggle competitions list exit 0).` and `state.json` flipped to `credentials=VALIDATED`.
- **LEAK CHECK on that transcript:** the raw token substring does NOT appear; no ≥32-char token-shaped run appears. **PASS.**
- **Credential source used:** the `~/.kaggle/access_token` FILE (mode 600, already correct). The chmod-600 self-heal branch therefore did NOT fire on the real credential (nothing to heal) — it is covered by unit test + the fabricated-token spot-check below.

**D-06b/c consent gates — spot-checked LIVE** with a FABRICATED `kaggle.json` (mode 644) in an isolated HOME, kaggle off PATH:
- WITHOUT `--yes`: printed `[proposed-fix]` (chmod) and `[offer]` (.env populate); mode stayed 644; `.env` NOT populated — no mutation. CORRECT.
- WITH `--yes`: `[fix-applied]` chmod 600; `[fix-applied]` `.env` populated from `kaggle.json`; values written to the gitignored `.env`, never printed to stdout. CORRECT.
- **D-07 command-not-found** fired correctly under a scrubbed PATH: `[UNVALIDATED] kaggle CLI not found on PATH` + `uv pip install kaggle` remediation; workspace unaffected.

**SUCCESS PATH NOW VERIFIED:** `kaggle competitions list` exit **0** on a valid token. This resolves the row previously marked `UNVERIFIED — Task 3 checkpoint` in `references/kaggle-cli-behavior.md`.

## Nyquist / Wave-0 finding — the RED suite encoded a legacy assumption its own field research refuted

Two pre-checkpoint defects (fixed in `4082681`; neither assertion weakened):

1. **`test_kaggle_missing` was a FALSE GREEN.** It relied on `kaggle`'s ambient ABSENCE on the dev host to exercise the command-not-found branch. The moment the Task 3 checkpoint installed `kaggle`, that test would have flipped RED (taking the auth-failure branch instead of command-not-found). Fixed by scrubbing the subprocess `PATH` to an empty dir (so `shutil.which("kaggle")` deterministically returns `None`) and pointing `HOME` at an empty dir — the UNVALIDATED + install-remediation assertions are unchanged.
2. **`test_credentials_live.py` silently SKIPPED for file-based credentials.** Its env-only guard (`KAGGLE_USERNAME`/`KAGGLE_KEY`/`KAGGLE_API_TOKEN`) could not see `~/.kaggle/access_token` — the very source `check_credentials.py` ranks FIRST. Fixed to also accept the `access_token`/`kaggle.json` FILE sources (existence-only; contents never read) and to thread the real `HOME` through so both the checker and the CLI can find `~/.kaggle`.

This is a genuine Nyquist/Wave-0 finding: the RED suite authored in 01-01 encoded a legacy env-pair assumption that 01-04's own field research (recorded in `references/kaggle-cli-behavior.md`: CLI 2.2.3 foregrounds `KAGGLE_API_TOKEN`/`access_token`/OAuth and does not even mention the legacy pair) later refuted. The tests now match observed reality without loosening any check.

## Requirements Status (honest split)

- **SETUP-03 — MET.** Credential connected and live-validated by exit code (real `access_token` file, exit 0, `state.json=VALIDATED`), four secret-free remediation branches, failure flags `UNVALIDATED` without aborting (D-07), observed CLI behavior recorded in `references/kaggle-cli-behavior.md`. Marked complete.
- **SETUP-04 (credential half) — MET.** Credential never echoed (masked / env-var-name-only output; `test_no_credential_leak.py` + `test_subprocess_output_no_secret` green; live-transcript leak check PASS); world-readable token self-healed to 600 with consent; `.env` normalization consent-gated; secrets gitignored (from 01-03).
- **SETUP-04 (egress half) — MET (closed 2026-07-10, see 01-03-SUMMARY).** The discriminating probe (auto-accept OFF, all prompts declined) had 5/5 off-allowlist hosts prompt for approval and 0 silently allowed, establishing there is no undocumented baseline allowlist and no silent-allow path. The earlier `example.com` result was an auto-accepted prompt, not a bypass. **SETUP-04 is therefore complete** — both halves of the compound requirement (credentials AND egress) are satisfied.

## Decisions Made

- **Exit code is the single source of truth** for live validation; the detected source label is advisory (T-01-10 anti-spoofing). The success path was confirmed via the `access_token` FILE source, so CLI 2.2.3 provably honors `~/.kaggle/access_token`.
- **Legacy `KAGGLE_USERNAME`+`KAGGLE_KEY` end-to-end validation stays UNVERIFIED** — never tested with a real pair (the real run used the file source; the fabricated pair failed auth like every fabricated input). The checker still detects it (D-04) but the live truth is the exit code.
- **`kaggle` is a dev/live-only dependency, not runtime** — `check_credentials.py` never imports it; it subprocesses the CLI and degrades gracefully when absent (D-07). Declared in `pyproject.toml`/`uv.lock` for reproducibility, not wired into the stdlib-only runtime path (D-14 preserved).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Misleading credential-read messaging in `check_credentials.py`**
- **Found during:** Post-checkpoint accuracy audit
- **Issue:** The `kaggle.json` source line ALWAYS printed "value not read without --yes" — but when `--yes` IS passed and env creds are absent, the content IS read (to populate `.env`). The tool asserted something FALSE about whether it read a secret.
- **Fix:** Made the `kaggle.json` line consent-conditional (`_kaggle_json_label`): without `--yes` it says "value not read (no --yes)"; with `--yes` it says "value read under your --yes consent (to populate the workspace .env); never printed." Audited the other labels too — `access_token` now says "value not read by this tool (the kaggle CLI reads + validates it)" (always true, content never read); the two env labels now note "value read to classify + mask it, never shown raw" (accurate — env value IS read to mask/report). All messages stay secret-free.
- **Files modified:** scripts/check_credentials.py
- **Verification:** `uv run pytest tests/ -q` → 26 passed (no label string is pinned by a test; masking/leak assertions unaffected).
- **Committed in:** `fad7426` (fix)

**2. [Rule 3 - Blocking / hygiene] `kaggle` used at the checkpoint but undeclared**
- **Found during:** Post-checkpoint dependency-hygiene review
- **Issue:** `kaggle` was installed via `uv pip install kaggle` at the checkpoint but was NOT declared in `pyproject.toml`, so the `-m live` test was not reproducible from a clean checkout (CLAUDE.md forbids bare runtime pip installs and mandates declared deps).
- **Fix:** Added `kaggle>=2.2` to the `dev` dependency group (alongside `pytest`), refreshed `uv.lock`; documented in a comment that it is dev/live-only (never a runtime import).
- **Files modified:** pyproject.toml, uv.lock
- **Verification:** `uv sync` + `uv run pytest tests/ -q` → 26 passed (incl. the hermetic `test_kaggle_missing`, green even with kaggle present).
- **Committed in:** `fad7426` (fix)

**3. [Rule 1 - Bug] Pre-checkpoint test defects (false green + silent skip)** — see the Nyquist finding above.
- **Committed in:** `4082681` (fix, prior session)

---

**Total deviations:** 3 auto-fixed (2 accuracy/hygiene this session, 1 test-defect pre-checkpoint). No architectural change; no scope creep — all tighten correctness/security honesty of the exact SETUP-03/04 surface.

## Issues Encountered

- **CLI writes auth guidance to stdout, not stderr:** a naive stderr-only matcher would have missed every failure. Resolved by capturing + matching the COMBINED buffer (recorded in `references/kaggle-cli-behavior.md`); `test_subprocess_output_no_secret` pins the inverse (stderr-landing) shape so both spots are covered.
- **Legacy env-pair precedence contradiction:** CLI 2.2.3's own guidance omits `KAGGLE_USERNAME`+`KAGGLE_KEY`; whether a real pair validates end-to-end remains UNVERIFIED. Recorded honestly rather than assumed.

## Threat Model Compliance

| Threat ID | Category | Disposition | Status |
|-----------|----------|-------------|--------|
| T-01-02 | Information Disclosure (any print of a credential incl. captured subprocess stderr) | mitigate | ✅ `_mask` + env-var-name-only output; captured buffer never surfaced raw; `test_no_credential_leak.py` + `test_subprocess_output_no_secret` green; live-transcript leak check PASS (no token, no ≥32-char run). |
| T-01-03 | Information Disclosure (world/group-readable kaggle.json) | mitigate | ✅ `_ensure_mode_600` consent-gated via `--yes`; no filesystem change without consent (unit-pinned + fabricated-token spot-check). Did not fire on the real credential (already 600). |
| T-01-05 | Tampering (silent kaggle install) | mitigate | ✅ `shutil.which` guard + consent-based `uv pip install kaggle` remediation; never auto-installs; the checkpoint install was explicit user consent. |
| T-01-10 | Spoofing (false-pass on failed auth) | mitigate | ✅ Decides strictly by exit code; real 401/"authentication required" strings captured in `references/kaggle-cli-behavior.md`; success never inferred from stdout text. Success path now VERIFIED (exit 0). |

## Known Stubs

None. `check_credentials.py` performs real detection + a real live call; no placeholder/mock data flows to any output. `state.json.credentials` is written from the real exit code.

## TDD Gate Compliance

RED suite pre-authored in 01-01 (Nyquist Wave 0); Tasks 1-2 are `tdd="true"`. RED→GREEN verified: the 8 credential nodes (`test_credentials.py` ×6 + `test_no_credential_leak.py` ×2) were RED before 01-04 and GREEN after. GREEN commits: `661b32e` (Task 1), `4208da0` (Task 2). Task 3 is a verification gate (no code). Pre-checkpoint `4082681` and post-checkpoint `fad7426` are `fix` commits that keep the suite GREEN (26/26 with kaggle present). No REFACTOR commit needed.

## Next Phase Readiness

- **Full non-live suite green** and the `-m live` test now reproducible from a clean checkout (`kaggle>=2.2` declared). A valid credential validates end-to-end (`state.json=VALIDATED`).
- **Phase 2 (data):** reuses the validated credential + the `storage.googleapis.com` egress already on the 01-03 allowlist for `kaggle competitions download`.
- **Carry-forward RESOLVED (2026-07-10):** the discriminating egress probe was run — `example.org`, `example.net`, `wikipedia.org`, `google.com`, `httpbin.org`, declining every prompt. **All five prompted; none was silently allowed.** No undocumented pre-allowed set exists for the local CLI sandbox; the `example.com` result was an auto-accepted prompt; denial is a prompt (an unanswered one stalls the CONNECT, which is a deny). **SETUP-04's egress half is MET and SETUP-04 is complete.** What carries forward instead is an operational caveat, not a gap: **auto-accept mode defeats the egress allowlist**, because enforcement for a non-allowlisted host *is* an approval prompt. See `references/egress-allowlist.md`.
- **Carry-forward (this plan):** legacy `KAGGLE_USERNAME`+`KAGGLE_KEY` end-to-end validation UNVERIFIED; the chmod-600 self-heal did not fire on the real (already-600) credential — covered by unit test + fabricated-token spot-check only.

## Self-Check: PASSED

- Created/modified files verified present: `scripts/check_credentials.py`, `references/kaggle-cli-behavior.md`, `pyproject.toml`, `uv.lock`, `.planning/phases/01-workspace-credentials-egress-guardrails/01-04-SUMMARY.md`.
- Commits verified in git log: `661b32e` (Task 1 feat), `4208da0` (Task 2 feat), `4082681` (pre-checkpoint test fix), `fad7426` (post-checkpoint accuracy fix).
- `uv run pytest tests/ -q` (kaggle present) → **26 passed, 0 failed** — incl. hermetic `test_kaggle_missing` and the live-transcript leak check.

---
*Phase: 01-workspace-credentials-egress-guardrails*
*Completed: 2026-07-10*
