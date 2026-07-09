---
phase: 01-workspace-credentials-egress-guardrails
verified: 2026-07-09T23:49:50Z
status: gaps_found
score: 4/5 must-haves verified
overrides_applied: 0
gaps:
  - truth: "Network egress is restricted to a Kaggle + package-source allowlist in .claude/settings.json — an off-allowlist fetch is refused, not silently allowed (ROADMAP Success Criterion 5 / SETUP-04 egress half)"
    status: partial
    reason: >-
      Generated-settings correctness (Half A) is fully verified: sandbox.enabled=true,
      sandbox.failIfUnavailable=true, allowedDomains is a superset of the 5 required hosts,
      the deep-merge preserves user keys while forcing the security flags, and a malformed
      settings.json fails clear. But host-enforcement (Half B) is only PARTIALLY demonstrated
      per the phase's own recorded checkpoint evidence (01-03-SUMMARY.md,
      references/egress-allowlist.md): of 3 off-allowlist hosts probed, 2 (neverssl.com,
      icanhazip.com) were correctly denied (stalled proxy CONNECT / timeout), but one
      (example.com) reached its real origin with genuine content — cause UNKNOWN. This is a
      direct, empirically-observed exception to the literal wording of criterion 5 ("an
      off-allowlist fetch is refused, not silently allowed"). The named follow-up
      ("discriminating probe": example.org, example.net, wikipedia.org, google.com,
      httpbin.org, declining every prompt) has not been run. This verifier confirmed its own
      Bash tool environment has NO active sandbox proxy (https_proxy/HTTP_PROXY unset;
      curl to neverssl.com and example.com both returned HTTP 200 unrestricted), so the
      anomaly cannot be further diagnosed from this verification session — it requires a
      live, interactive Claude Code session with the sandbox (socat + bubblewrap) active.
    artifacts:
      - path: "references/egress-allowlist.md"
        issue: "Documents the anomaly honestly (empirical evidence table + UNVERIFIED flag) but does not resolve it"
      - path: ".claude/settings.json (generated in scaffolded workspaces)"
        issue: "The generated artifact itself is correct (Half A MET) — the gap is in live host enforcement, not the generated file"
    missing:
      - "Run the discriminating probe (curl to example.org, example.net, wikipedia.org, google.com, httpbin.org, declining every prompt) in a live Claude Code session with the sandbox active, to determine whether an undocumented pre-allowed set exists for the local CLI sandbox or the example.com result was a one-off anomaly."
      - "Either explain and fix the example.com pass-through, or have a human explicitly accept the residual risk (e.g. via a VERIFICATION.md override entry naming who accepted it and why) before Phase 1 is considered fully closed."
---

# Phase 1: Workspace, Credentials & Egress Guardrails — Verification Report

**Phase Goal:** A single init turns an empty folder into a valid, git-tracked experiment workspace with a live-validated Kaggle connection and a locked-down network egress allowlist.
**Verified:** 2026-07-09T23:49:50Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

These are the 5 ROADMAP.md Success Criteria for Phase 1 (the roadmap contract) — each independently re-tested against the actual codebase in this session, not taken from SUMMARY.md claims.

| # | Truth (ROADMAP Success Criterion) | Status | Evidence |
|---|---|---|---|
| 1 | Running init on an empty folder produces the full workspace layout — control plane (config.json, ledger.jsonl, state.json), context-file stubs, .gitignore, and an initialized git repo | ✓ VERIFIED | Scaffolded a throwaway workspace (`init_workspace.py --workspace <tmp> --slug titanic`): produced `control/{config.json,state.json,ledger.jsonl}`, `competition.md`/`strategy.md`/`README.md`, `.env`, `.gitignore`, `.claude/settings.json`, `pyproject.toml`, `data/`, `experiments/`, and a git repo on `main` with exactly one `chore: scaffold workspace` commit (10 files staged, none stray). Re-run created zero new files (idempotent). |
| 2 | User can set execution target to local (default) or kernel at init and change it later — globally in config.json — and the setting is honored | ✓ VERIFIED | Fresh scaffold: `config.json.execution_target == "local"`. `--set-execution-target kernel` flipped it to `"kernel"`. `--set-execution-target banana` was rejected by argparse (exit 2, no write — enum stayed `kernel`). A plain re-run without the setter left `kernel` untouched (no-overwrite-outside-setter). |
| 3 | The framework validates the Kaggle credential with a live call and reports a clear pass/fail, with exact remediation for each common failure (wrong env var, missing chmod 600, 401, command-not-found) | ✓ VERIFIED | Code-level: `run_kaggle_list()` decides strictly by exit code, now has a 60s timeout (WR-01 fixed, confirmed in `scripts/check_credentials.py:342-369`), never surfaces captured stdout/stderr raw. Independently spot-checked (fabricated creds, no real token used): command-not-found branch fires correctly with PATH scrubbed; chmod-600 and `.env`-population consent gates behave exactly as specified (see Behavioral Spot-Checks). The live end-to-end pass (`state.json → VALIDATED`, real `access_token` file, exit 0, no leak) is documented in 01-04-SUMMARY.md/references/kaggle-cli-behavior.md as independently performed at the Task 3 checkpoint; this verifier did not re-run it (per security instructions, must never touch the real credential), but the mechanism it depends on (exit-code-only decision, masked output, timeout bound) is directly verified in code and via fabricated-input spot-checks. |
| 4 | Credentials are chmod 600 and never echoed, logged, or committed (.gitignore covers .env/kaggle.json/access_token); a credential-leak check passes | ✓ VERIFIED | `.gitignore` confirmed to cover `.env`, `kaggle.json`, `access_token` (plus `**/kaggle.json`, `**/access_token`). Staged a fabricated `KAGGLE_KEY=<32 chars>` in a non-gitignored file (`notes.txt`) inside a real scaffolded workspace and ran `git commit` — the installed `.githooks/pre-commit` hook (wired via `core.hooksPath`) BLOCKED the commit for real. CR-01 (leak scanner failed OPEN on non-ASCII filenames / any git error) independently re-verified fixed: a `café.env` file containing a fabricated `KAGGLE_KEY` is now correctly BLOCKED (previously silently skipped); running the scanner outside a git repo now fails closed (BLOCKED) instead of exiting 0. Consent-gated chmod-600 self-heal verified with a fabricated 644 kaggle.json: unchanged without `--yes`, flipped to 600 only with `--yes`; `.env` population from a fabricated kaggle.json likewise offered-only vs. applied-only-with-consent, values never printed to stdout. |
| 5 | Network egress is restricted to a Kaggle + package-source allowlist in `.claude/settings.json` — an off-allowlist fetch is refused, not silently allowed | ✗ FAILED (partial) | **Half A (generated settings) — MET:** verified `sandbox.enabled=true`, `sandbox.failIfUnavailable=true`, `allowedDomains` ⊇ {www.kaggle.com, storage.googleapis.com, pypi.org, files.pythonhosted.org, github.com}; deep-merge preserves an unrelated user key while unioning hosts and forcing the security flags; a malformed pre-existing settings.json is left byte-for-byte unchanged with a non-zero exit (all re-tested directly in this session). **Half B (host enforcement) — NOT fully met:** per the phase's own recorded checkpoint (01-03-SUMMARY.md / references/egress-allowlist.md), 2 of 3 off-allowlist hosts were denied (neverssl.com, icanhazip.com — stalled-CONNECT timeout) but one off-allowlist host (example.com) reached its real origin with genuine content, cause UNKNOWN. The discriminating probe that would help isolate this was never run. This is a literal contradiction of the criterion as worded ("an off-allowlist fetch is refused, not silently allowed") — one specific off-allowlist fetch was in fact silently allowed. See Gaps Summary. |

**Score:** 4/5 truths verified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `SKILL.md` | Guided-then-scaffold init contract, `allowed-tools` incl. `Bash(python3 scripts/*)`, documents D-01/D-03/D-07 | ✓ VERIFIED | Read in full; frontmatter has all required `allowed-tools`; body documents guided-init, consent gating, flag-on-fail, egress + leak-guard sections. |
| `pyproject.toml` (skill's own) | `[tool.pytest.ini_options]` with `live` marker; `requires-python>=3.11` | ✓ VERIFIED | `uv run pytest --markers` lists `live: requires a real Kaggle API token (excluded from default runs)`. |
| `scripts/init_workspace.py` | Self-locating slug-gated D-10 scaffolder, deep-merge, git init, egress deep-merge | ✓ VERIFIED | Exercised directly: D-01 gate, D-02 deep-merge + nested-edit preservation, malformed-JSON fail-clear, git init on `main`, scaffold-scoped commit, idempotency. |
| `scripts/templates/*.tmpl` (10 files) | config/state/settings/gitignore/pre-commit/env/pyproject/competition/strategy/README templates | ✓ VERIFIED | All 10 present on disk; content inspected for settings.json.tmpl and gitignore.tmpl; produced correct output in live scaffold test. |
| `scripts/leak_scan.py` | Stdlib pre-commit content scanner, fail-closed | ✓ VERIFIED | CR-01 fix re-verified empirically (non-ASCII filename leak now blocked; git errors now fail closed); real `git commit` blocked via the installed hook. |
| `scripts/check_credentials.py` | Credential detect/precedence/mask/consent-gated fixes/live validation | ✓ VERIFIED | WR-01 (timeout), WR-02 (state.json fail-clear), WR-03 (precedence reorder) all re-verified in code and empirically (fabricated inputs only). |
| `references/egress-allowlist.md` | Portability doc + honest enforcement caveats | ✓ VERIFIED | Present, detailed, and — notably — honestly documents its own unresolved anomaly rather than smoothing it over. |
| `references/kaggle-cli-behavior.md` | Observed kaggle CLI exit codes/precedence fixture | ✓ VERIFIED | Present; records fabricated-credential captures + the one live VERIFIED success path; honest provenance notes. |
| `tests/conftest.py` + 8 `test_*.py` | Full RED→GREEN suite incl. review-driven pins | ✓ VERIFIED | 32 test nodes collected; `uv run pytest tests/ -q` → 32 passed (re-run in this session, matches orchestrator claim). |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `SKILL.md` | `scripts/init_workspace.py` | documented `python3 scripts/init_workspace.py --workspace` invocation | ✓ WIRED | Literal string present in SKILL.md body; script runs exactly as documented. |
| `scripts/init_workspace.py` | `scripts/templates/` | `Path(__file__).resolve().parent / "templates"` | ✓ WIRED | Templates read and substituted correctly in live scaffold test. |
| `scripts/init_workspace.py` | `.claude/settings.json` | deep-merge union of allowedDomains + permissions.allow | ✓ WIRED | Directly tested: pre-existing settings with unrelated key + partial allowlist → user key preserved, hosts unioned, security flags forced. |
| `scripts/init_workspace.py` | `git config core.hooksPath` | installs `.githooks/pre-commit`, then stages + commits | ✓ WIRED | `core.hooksPath` = `.githooks`; hook is executable (0755); hook actually fires on `git commit` and blocks a real fabricated-secret commit. |
| `.githooks/pre-commit` | `scripts/leak_scan.py` | hook body is the copied scanner | ✓ WIRED | Confirmed by content + by triggering a real block via `git commit`. |
| `scripts/check_credentials.py` | `kaggle competitions list` | exit-code live validation | ✓ WIRED | Code path confirmed; live pass documented in 01-04-SUMMARY.md (not independently re-run here — no real credential touched, per instructions). |
| `scripts/check_credentials.py` | `control/state.json` | writes `credentials` VALIDATED\|UNVALIDATED | ✓ WIRED | Directly tested: command-not-found path writes `UNVALIDATED`; malformed state.json now fails clear (WR-02) instead of resetting `next_exp_id`. |

### Behavioral Spot-Checks

All commands below were executed directly in this verification session (not read from SUMMARY.md), against a throwaway workspace in the session scratchpad, using only fabricated credential values.

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full suite green | `uv run pytest tests/ -q` | `32 passed` | ✓ PASS |
| Non-live suite green | `uv run pytest tests/ -q -m "not live"` | `31 passed, 1 deselected` | ✓ PASS |
| Fresh scaffold produces D-10 layout | `init_workspace.py --workspace <tmp> --slug titanic` | Full layout created, exit 0, one scaffold commit | ✓ PASS |
| Idempotent re-run | same command again | Exit 0, no new commit, no new files | ✓ PASS |
| D-01 gate (no slug on fresh dir) | `init_workspace.py --workspace <fresh>` (no `--slug`) | Exit 2, zero files created | ✓ PASS |
| CR-01 fix: non-ASCII filename leak | staged `café.env` containing fabricated `KAGGLE_KEY=...`, ran `leak_scan.py` | `[BLOCKED]` exit 1 (previously silently skipped) | ✓ PASS |
| CR-01 fix: fail-closed on git error | ran `leak_scan.py` outside a git repo | `[BLOCKED] could not enumerate staged files...` exit 1 (previously exit 0) | ✓ PASS |
| Clean content passes | staged a secret-free file, ran `leak_scan.py` | exit 0 | ✓ PASS |
| Real commit blocked by installed hook | staged fabricated secret in `notes.txt` (not gitignored) in a real scaffolded repo, ran `git commit` | `[BLOCKED]`, commit exit 1, no commit created | ✓ PASS |
| settings.json deep-merge preserves user keys | pre-seeded settings with `env.FOO` + partial allowlist, re-ran init | user key preserved, hosts unioned, `failIfUnavailable` forced true | ✓ PASS |
| settings.json malformed fail-clear | pre-seeded corrupt settings.json, re-ran init | exit 1, bytes byte-for-byte unchanged (md5 match) | ✓ PASS |
| Execution-target setter + enum guard | `--set-execution-target kernel` then `--set-execution-target banana` | kernel applied; banana rejected (exit 2), value stayed `kernel` | ✓ PASS |
| Consent-gated chmod-600 (WR-fix independent spot-check) | fabricated 644 `kaggle.json`, checker run without/with `--yes` | unchanged without consent; chmod 600 applied only with `--yes` | ✓ PASS |
| Consent-gated `.env` population | same fabricated kaggle.json, checker run without/with `--yes` | `.env` untouched without consent; populated (fabricated values only) with `--yes`, never printed to stdout | ✓ PASS |
| WR-02 fix: malformed state.json fail-clear | corrupted `control/state.json`, ran checker | `[BLOCKED]` exit 1, bytes unchanged (md5 match), `next_exp_id` not reset | ✓ PASS |
| No raw secret in static scan | `grep` over `scripts/*.py` for credential-value prints | No raw-secret prints found (only instructional text) | ✓ PASS |
| Egress sandbox active in verifier's own tool env? | `echo $https_proxy`; `curl` to neverssl.com / example.com from this session | No proxy configured; both hosts returned HTTP 200 unrestricted | ℹ️ Confirms this verifier's Bash tool has no active sandbox — the egress anomaly cannot be further diagnosed from here (requires a live, interactive Claude Code session with the sandbox active). |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| SETUP-01 | 01-01 (RED), 01-02, 01-03 | Initialize workspace (layout, config, git init, context-file stubs) | ✓ SATISFIED | D-10 layout + git-on-main + scaffold-scoped idempotent commit all directly verified. REQUIREMENTS.md marks Complete — consistent with evidence. |
| SETUP-02 | 01-01 (RED), 01-02 | Choose/change execution target | ✓ SATISFIED | Default `local`, setter, enum validation, no-overwrite-outside-setter all directly verified. REQUIREMENTS.md marks Complete — consistent. |
| SETUP-03 | 01-01 (RED), 01-04 | Connect Kaggle account, live-validate credential | ✓ SATISFIED | Exit-code-only validation, 4 remediation branches, timeout bound (WR-01), fail-clear state write (WR-02) all verified in code + fabricated-input spot-checks; real live pass independently documented at the 01-04 checkpoint. REQUIREMENTS.md marks Complete — consistent. |
| SETUP-04 | 01-01 (RED), 01-03, 01-04 | Credentials stored securely/never echoed; egress scoped | ⚠️ BLOCKED (partial) | Credential half fully MET (masking, consent-gating, gitignore, leak-guard fail-closed after CR-01 fix — all independently re-verified). Egress half NOT fully met (SC5 above). REQUIREMENTS.md marks this **Pending** — this verifier confirms that is the honest, accurate state; it should NOT be flipped to Complete yet. |

No orphaned requirements: SETUP-01 through SETUP-04 are the full Phase 1 requirement set per REQUIREMENTS.md traceability, and all four are claimed (with correct partial/complete status) across the 4 plans.

### Anti-Patterns Found

All Critical and 5 of 6 Warning findings from `01-REVIEW.md` were independently re-verified as fixed in this session (not merely trusted from commit messages):

| File | Finding | Severity (original) | Status now | Evidence |
|---|---|---|---|---|
| `scripts/leak_scan.py` | CR-01: fails open on non-ASCII filenames / any git error | 🛑 Critical | ✓ FIXED (verified) | Empirically re-triggered both failure modes in this session; both now fail closed. |
| `scripts/check_credentials.py` | WR-01: no subprocess timeout | ⚠️ Warning | ✓ FIXED (verified) | Code shows `timeout=60` + `TimeoutExpired` handling, mapped to non-zero UNVALIDATED. |
| `scripts/check_credentials.py` | WR-02: malformed state.json silently clobbered, resets `next_exp_id` | ⚠️ Warning | ✓ FIXED (verified) | Empirically re-triggered; now raises `MalformedStateJSON`, bytes preserved, exit non-zero. |
| `scripts/check_credentials.py` | WR-03: precedence ranked access_token above env, contradicting "env-canonical" | ⚠️ Warning | ✓ FIXED (verified) | Code shows `KAGGLE_API_TOKEN` → env pair → `access_token` → `kaggle.json`, with an honest UNVERIFIED annotation for the legacy-pair-vs-file ordering. |
| `tests/test_settings.py` | WR-05: no test pinned `sandbox.failIfUnavailable` | ⚠️ Warning | ✓ FIXED (verified) | `grep` confirms assertions in both `test_egress_allowlist` and `test_egress_allowlist_merges_existing`. |
| `tests/test_credentials.py` | WR-06: non-hermetic tests could hit the live API | ⚠️ Warning | ✓ FIXED (verified) | `grep` confirms PATH-scrubbing (`extra_env={"PATH": str(empty_bin), ...}`) added to the four named tests. |
| `scripts/leak_scan.py` | WR-04: legacy 32-hex key evades scanner outside `"key":`/`KAGGLE_KEY=` context | ℹ️ Info (documented tradeoff) | Not fixed — accepted tradeoff | Review itself said "acceptable to keep as a documented tradeoff." Not a phase blocker. |
| `scripts/check_credentials.py` | IN-01: unused `import sys` / `SCRIPT_DIR` | ℹ️ Info | Not fixed | Cosmetic; confirmed still present (`grep` line 42/45). Non-blocking. |
| `scripts/check_credentials.py` | IN-02: `_mask` discloses last 4 chars | ℹ️ Info | Not fixed | Documented conventional choice; non-blocking. |
| `scripts/init_workspace.py` | IN-03: `--slug` unvalidated (safe today, injection risk in later phases) | ℹ️ Info | Not fixed | Non-blocking for Phase 1; worth a cheap format guard before Phase 4/5 build kernel-metadata/download commands on the slug. |
| `scripts/leak_scan.py` | IN-04: docstring says "renamed file" rationale but `--diff-filter` used to exclude R | ℹ️ Info | Fixed as a side effect of CR-01 | CR-01's fix changed the filter to `ACMR` (renames now included), resolving the doc/filter mismatch. |

No `TBD`/`FIXME`/`XXX` unresolved debt markers found in any file touched by this phase.

### Gaps Summary

Phase 1 delivers a genuinely solid, independently-verified scaffolder, credential checker, and leak guard — SETUP-01, SETUP-02, and SETUP-03 are fully met, and the credential half of SETUP-04 (never-echoed, masked, consent-gated chmod/.env, secrets gitignored, leak-guard now fail-closed after the CR-01 fix) is also fully met. This is not a rubber-stamp: every claim above was independently re-executed against the actual code in this session (fresh scaffold, idempotency, D-01 gate, deep-merge, malformed-JSON fail-clear ×2, real `git commit` blocked by the installed hook, consent-gating with fabricated credentials, and all 6 review-driven fixes) rather than trusted from SUMMARY.md prose.

The one blocking gap is the **egress-enforcement half of SETUP-04** (ROADMAP Success Criterion 5). The generated `.claude/settings.json` is correct and well-tested (Half A). But the phase's own checkpoint evidence — which this verifier reviewed and could not further diagnose, since this verifier's own Bash tool has no active sandbox proxy (confirmed: unrestricted HTTP 200 to neverssl.com and example.com from this session) — shows one off-allowlist host reaching real origin content unexplained. Criterion 5 as literally worded ("an off-allowlist fetch is refused, not silently allowed") is not universally true today. REQUIREMENTS.md's own traceability table already reflects this honestly (SETUP-04 = Pending), and this verification confirms that is the correct, non-optimistic state — it should not be advanced to "Complete" until either the anomaly is explained/fixed via the named discriminating probe, or a human explicitly and knowingly accepts the residual risk.

This is not a fabricated or manufactured gap: it is the same gap the phase's own plan authors flagged, carried forward honestly through three SUMMARY.md files and never silently dropped. This verification's contribution is confirming (a) the credential/scaffolding side is genuinely solid, (b) the review-driven fixes actually landed and work, and (c) the egress-enforcement anomaly remains genuinely unresolved and requires a live human-in-the-loop probe to close — not a code fix this verifier or the executor can make blind.

---

_Verified: 2026-07-09T23:49:50Z_
_Verifier: Claude (gsd-verifier)_
