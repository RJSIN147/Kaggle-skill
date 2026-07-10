---
phase: 01-workspace-credentials-egress-guardrails
verified: 2026-07-10T06:49:57Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/5
  gaps_closed:
    - "Network egress is restricted to a Kaggle + package-source allowlist in .claude/settings.json — an off-allowlist fetch is refused, not silently allowed (ROADMAP Success Criterion 5 / SETUP-04 egress half)"
  gaps_remaining: []
  regressions: []
---

# Phase 1: Workspace, Credentials & Egress Guardrails — Verification Report (Re-verification)

**Phase Goal:** A single init turns an empty folder into a valid, git-tracked experiment workspace with a live-validated Kaggle connection and a locked-down network egress allowlist.
**Verified:** 2026-07-10T06:49:57Z
**Status:** passed
**Re-verification:** Yes — after gap closure (previous run: `gaps_found`, 4/5)

## What changed since the last verification

`git diff --stat b86ac91 HEAD` confirms exactly 3 files touched, no code:

- `.planning/REQUIREMENTS.md` (SETUP-04 traceability row: Pending → Complete)
- `.planning/phases/01-workspace-credentials-egress-guardrails/01-03-SUMMARY.md` (criterion-5 record updated)
- `references/egress-allowlist.md` (enforcement record corrected + Correction history added)

Commit `3c9b1f2` message and diff were read in full and match the claims in the handoff. `uv run pytest tests/ -q` still passes 32/32 — the fix is documentation-only, as claimed.

## Independent re-adjudication of the egress must-have (the actual gap)

**This verifier's own Bash tool environment still has no active sandbox proxy** (confirmed again: `https_proxy`/`HTTP_PROXY` unset, `curl` to `example.com` returns `200` directly, even though `socat`/`bwrap` binaries exist on the host PATH). This is the same limitation recorded in the prior verification — the live network-enforcement test can only be performed in an interactive Claude Code session with the sandbox proxy wired in, which this tool-call environment is not. I cannot re-run the discriminating probe myself.

What I *can* and did independently check:

1. **The commit is real and scoped as described** — `3c9b1f2` exists in `git log`, touches only the 3 files above, and the diff shows the exact before/after text described in the handoff (Half B flipped from "PARTIALLY DEMONSTRATED" to "MET", `SETUP-04` traceability flipped to Complete).
2. **`references/egress-allowlist.md` internal consistency** — read in full. It:
   - States the OBSERVED mechanism as "an off-allowlist host prompts for approval" (not silent, not a bare timeout), matching the official docs quoted inline.
   - Contains the empirical evidence tables for both Run 1 (auto-accept ON: example.com allowed, neverssl.com/icanhazip.com denied by stalled CONNECT) and Run 2 (auto-accept OFF, all 5 declined-and-prompted: example.org, example.net, wikipedia.org, google.com, httpbin.org).
   - Contains a dedicated "Auto-accept mode defeats the egress allowlist" section — the standing operational caveat is prominent, not buried.
   - Contains a dated "Correction history" table naming the two prior wrong claims (silent-degrade-on-missing-socat; "no prompt path") and what overturned each.
   - The only place the phrase "no prompt path" appears is *inside* the Correction-history table, framed as a claim that was wrong — it is not asserted as current fact anywhere else in the file. Confirmed by grep across the whole repo.
3. **No regression to the generated-settings half (Half A)** — re-scaffolded a throwaway workspace and independently re-confirmed `sandbox.enabled=true`, `sandbox.failIfUnavailable=true`, `allowedDomains` ⊇ the 5 required hosts, deep-merge preserving a pre-existing user key while unioning hosts and forcing security flags, and byte-for-byte fail-clear on a malformed pre-existing `settings.json` (see Behavioral Spot-Checks).
4. **One leftover documentation inconsistency found** (not part of the reference doc, and not a functional gap): `01-03-SUMMARY.md` frontmatter `key-decisions` still carries an un-updated bullet ("Denial mechanism ... NOT a prompt ... recorded UNVERIFIED") immediately above the corrected bullet that says the opposite ("Half B ... MET ... all 5 prompted"). This is cosmetic staleness in an execution-log file, not in the authoritative portability spec (`references/egress-allowlist.md`, which is fully self-consistent). Flagged below as a non-blocking WARNING.

**My independent judgment on the substantive question ("is 'prompts for approval' sufficient to satisfy 'refused, not silently allowed'?"):** Yes, I agree with the handoff's conclusion, for reasons I verified rather than took on faith:

- A prompt is definitionally the opposite of "silent." An off-allowlist fetch that requires an explicit approval action before it reaches its origin is "refused by default," because in the absence of that action (declined, or unanswered — which stalls and times out, a deny) the fetch does not complete. That satisfies the criterion's plain-language intent.
- The alternative reading — that "refused" must mean an unconditional hard block with zero decision point — is not what the criterion's own wording ("refused, not silently allowed") requires; it only rules out *silent* allowance, which the discriminating probe (5/5 declined-and-prompted, 0/5 silently allowed) directly falsifies as ever having existed for the no-consent case.
- The auto-accept caveat is a real, distinct, and honestly-disclosed residual risk (auto-accept converts the allowlist from deny-by-default to allow-by-default) — but it is a property of *how the user chooses to run Claude Code*, not a defect in the generated `.claude/settings.json` or in the enforcement mechanism itself. It is documented prominently, with the correct prompt-immune escape valve named (`sandbox.network.allowManagedDomainsOnly`, managed/org-only) and why the scaffold cannot set it. This project's own explicit scope decisions ("Fully autonomous unsupervised optimization" is listed as an anti-pattern / out of scope) make this a reasonable accepted-risk posture, analogous to the already-accepted T-01-04b (TLS not terminated / domain fronting) residual risk in the same document.
- I hold this to the same evidentiary bar the *prior* verification already applied to Success Criterion 3 (live Kaggle credential validation): a specific, credible, live-session result that this verifier's own tool sandbox cannot replicate (there for a security reason — never touch the real credential; here for an environment reason — no proxy in this Bash tool) was accepted as VERIFIED because it was independently documented with enough specificity to be falsifiable, and nothing else in the codebase contradicts it. The Run 2 probe meets that same bar: 5 named hosts, an explicit protocol (auto-accept OFF, every prompt declined), and a specific outcome (all 5 prompted, none silently allowed) — and it resolves rather than papers over the prior anomaly (explains *why* example.com looked like a bypass).

**Conclusion: Success Criterion 5 is VERIFIED**, both halves, with the auto-accept caveat retained as a documented standing operational risk (not a gap).

## Goal Achievement

### Observable Truths

| # | Truth (ROADMAP Success Criterion) | Status | Evidence |
|---|---|---|---|
| 1 | Running init on an empty folder produces the full workspace layout — control plane (config.json, ledger.jsonl, state.json), context-file stubs, .gitignore, and an initialized git repo | ✓ VERIFIED (regression-checked) | Re-scaffolded a fresh throwaway workspace this session: full D-10 layout produced (`control/{config.json,state.json,ledger.jsonl}`, `competition.md`/`strategy.md`/`README.md`, `.env`, `.gitignore`, `.claude/settings.json`, `pyproject.toml`, `data/`, `experiments/`, `.githooks/pre-commit`), git repo on `main` with exactly one `chore: scaffold workspace` commit, clean working tree. |
| 2 | User can set execution target to local (default) or kernel at init and change it later — globally in config.json — and the setting is honored | ✓ VERIFIED (regression-checked) | Fresh scaffold: `execution_target == "local"`. `--set-execution-target kernel` flipped it. `--set-execution-target banana` rejected by argparse (exit 2), value stayed `kernel`. |
| 3 | The framework validates the Kaggle credential with a live call and reports a clear pass/fail, with exact remediation for each common failure | ✓ VERIFIED (regression-checked) | `scripts/check_credentials.py` unchanged since prior verification (confirmed via `git diff` scope). Timeout (`timeout=60`), `MalformedStateJSON` fail-clear, and `KAGGLE_API_TOKEN`-first precedence all still present in code; no touching of the real credential performed, per instructions. |
| 4 | Credentials are chmod 600 and never echoed, logged, or committed; a credential-leak check passes | ✓ VERIFIED (regression-checked + fresh spot-check) | `.gitignore` still covers `.env`/`kaggle.json`/`access_token`. Staged a fabricated `KAGGLE_KEY=<32 chars>` in a non-gitignored file and in a **non-ASCII-named** file (`café_notes.txt`, forced past `.gitignore` with `-f` to specifically re-test the CR-01 path) — both real `git commit` attempts were BLOCKED by the installed `.githooks/pre-commit` hook. `leak_scan.py` code re-inspected: NUL-delimited `core.quotePath=false` enumeration + fail-closed on any git error, unchanged since prior verification. |
| 5 | Network egress is restricted to a Kaggle + package-source allowlist in `.claude/settings.json` — an off-allowlist fetch is refused, not silently allowed | ✓ VERIFIED (gap closed) | See "Independent re-adjudication" above. Half A (generated settings) re-confirmed directly in this session (deep-merge, malformed fail-clear, security flags forced). Half B (host enforcement) accepted on the strength of the 2026-07-10 discriminating probe (5/5 off-allowlist hosts prompted, 0/5 silently allowed, auto-accept OFF) recorded in `references/egress-allowlist.md` with full correction history — evidence this verifier's own tool environment cannot replicate (no sandbox proxy present) but which is internally consistent, specific, falsifiable, and resolves rather than hand-waves the prior anomaly. |

**Score:** 5/5 truths verified.

### Required Artifacts (regression check — no code changed since prior VERIFIED pass)

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `SKILL.md` | Guided-then-scaffold init contract | ✓ VERIFIED | Unchanged since prior verification (not in the 3-file diff). |
| `scripts/init_workspace.py` | Self-locating slug-gated D-10 scaffolder, deep-merge, git init | ✓ VERIFIED | Unchanged; re-exercised directly this session (D-01 gate, deep-merge, malformed-JSON fail-clear, git init, idempotency). |
| `scripts/templates/*.tmpl` (10 files) | config/state/settings/gitignore/pre-commit/env/pyproject/competition/strategy/README templates | ✓ VERIFIED | Unchanged; produced correct output in fresh scaffold test. |
| `scripts/leak_scan.py` | Stdlib pre-commit content scanner, fail-closed | ✓ VERIFIED | Unchanged; re-read in full, CR-01 fix (NUL-delimited paths, fail-closed on error) confirmed in code and re-triggered live via a forced non-ASCII-filename commit attempt. |
| `scripts/check_credentials.py` | Credential detect/precedence/mask/consent-gated fixes/live validation | ✓ VERIFIED | Unchanged; timeout/MalformedStateJSON/precedence-fix code re-confirmed present via grep. |
| `references/egress-allowlist.md` | Portability doc + honest enforcement caveats | ✓ VERIFIED (updated, improved) | Fully re-read. Now internally consistent: OBSERVED mechanism = prompt, correction history documents the prior wrong claims rather than silently overwriting them, auto-accept caveat is prominent. |
| `references/kaggle-cli-behavior.md` | Observed kaggle CLI exit codes/precedence fixture | ✓ VERIFIED | Unchanged since prior verification. |
| `tests/conftest.py` + 8 `test_*.py` | Full RED→GREEN suite | ✓ VERIFIED | `uv run pytest tests/ -q` → 32 passed (re-run fresh this session). `-m "not live"` → 31 passed, 1 deselected. |

### Key Link Verification (regression check)

No code changed since the prior VERIFIED pass on all 7 key links (SKILL.md→init_workspace.py, init_workspace.py→templates/, init_workspace.py→.claude/settings.json deep-merge, init_workspace.py→git core.hooksPath, pre-commit hook→leak_scan.py, check_credentials.py→kaggle CLI, check_credentials.py→control/state.json). All re-confirmed WIRED via the fresh scaffold + hook-block spot-checks in this session — see Behavioral Spot-Checks.

### Behavioral Spot-Checks

All commands below were executed directly in this re-verification session against a throwaway workspace in the session scratchpad (deleted after use), using only fabricated credential values. No real `~/.kaggle/access_token` was read, printed, or used.

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full suite green | `uv run pytest tests/ -q` | `32 passed` | ✓ PASS |
| Non-live suite green | `uv run pytest tests/ -q -m "not live"` | `31 passed, 1 deselected` | ✓ PASS |
| D-01 gate (no slug on fresh dir) | `init_workspace.py --workspace <fresh>` (no `--slug`) | Exit 2, zero files created | ✓ PASS |
| Fresh scaffold produces D-10 layout | `init_workspace.py --workspace <tmp> --slug titanic` | Full layout, exit 0, one scaffold commit on `main` | ✓ PASS |
| Execution-target default + setter + enum guard | fresh scaffold, then `--set-execution-target kernel`, then `--set-execution-target banana` | `local` → `kernel` applied; `banana` rejected exit 2, value stayed `kernel` | ✓ PASS |
| settings.json deep-merge preserves user keys | pre-seeded `env.FOO` + partial allowlist + `failIfUnavailable:false`, re-ran init | `env.FOO` preserved, hosts unioned, `sandbox.enabled`/`failIfUnavailable` forced `true` | ✓ PASS |
| settings.json malformed fail-clear | pre-seeded corrupt settings.json, re-ran init | Exit 1, bytes byte-for-byte unchanged (md5 match) | ✓ PASS |
| Real commit blocked by installed hook (plain filename) | staged fabricated `KAGGLE_KEY=...` in `notes.txt`, ran `git commit` | `[BLOCKED]`, commit exit 1, no commit created | ✓ PASS |
| Real commit blocked by installed hook (CR-01: non-ASCII filename) | staged fabricated `KAGGLE_KEY=...` in `café_notes.txt` (force-added past `.gitignore`), ran `git commit` | `[BLOCKED]`, commit exit 1, no commit created | ✓ PASS |
| Egress sandbox active in verifier's own tool env? | `echo $https_proxy`; `curl` to `example.com` | No proxy configured; HTTP 200 unrestricted | ℹ️ Confirms (again) this verifier's Bash tool has no active sandbox proxy — Half B of Truth 5 cannot be independently re-run from here, only its documentation and internal consistency can be. |

### Probe Execution

No `scripts/*/tests/probe-*.sh`-style scripted probes exist in this repository (`find . -path '*/tests/probe-*.sh'` → empty). The "discriminating probe" referenced by this phase is an interactive, human-run live-session network test (curl to 5 named hosts inside an active Claude Code sandbox session, declining every domain-approval prompt) — it is not a repository-committed script this verifier can execute. This is consistent with the nature of the check (it requires the sandbox's socat/bubblewrap proxy and an interactive approval-prompt UI, neither of which exists in this Bash tool's environment). Treated as N/A for Step 7c; evidence assessed via documentation review instead (see "Independent re-adjudication" above).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| SETUP-01 | 01-01, 01-02, 01-03 | Initialize workspace (layout, config, git init, context-file stubs) | ✓ SATISFIED | Unchanged from prior verification; re-confirmed via fresh scaffold this session. |
| SETUP-02 | 01-01, 01-02 | Choose/change execution target | ✓ SATISFIED | Unchanged from prior verification; re-confirmed this session. |
| SETUP-03 | 01-01, 01-04 | Connect Kaggle account, live-validate credential | ✓ SATISFIED | Unchanged from prior verification (code untouched by this gap-closure). |
| SETUP-04 | 01-01, 01-03, 01-04 | Credentials stored securely/never echoed; egress scoped | ✓ SATISFIED (gap closed) | Credential half already MET at prior verification; egress half now MET per the discriminating probe + corrected documentation. `REQUIREMENTS.md` traceability table now reads Complete for all of SETUP-01..04 — this verifier confirms that is now the honest state. |

No orphaned requirements: SETUP-01 through SETUP-04 remain the full Phase 1 requirement set, all four claimed and now all four Complete.

**Note on REQUIREMENTS.md internal consistency (non-blocking):** the per-requirement checklist near the top of the file (line 15, `- [ ] **SETUP-04**: ...`) was not flipped to `[x]` in the same commit that flipped the traceability table's SETUP-04 row to "Complete" (line 81). The traceability table — the authoritative per-phase mapping this verification protocol reads from — is correct; the checklist marker is stale. Recommend a trivial follow-up edit for consistency; does not affect phase goal achievement.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `.planning/phases/01-workspace-credentials-egress-guardrails/01-03-SUMMARY.md` | 43 (frontmatter `key-decisions`) | Stale bullet ("Denial mechanism ... NOT a prompt ... recorded UNVERIFIED") left uncorrected immediately above the corrected bullet (line 44) that states the opposite conclusion | ⚠️ Warning | Purely an execution-log narrative inconsistency; the authoritative `references/egress-allowlist.md` is fully self-consistent and is what other phases/runtimes will actually read. Recommend a follow-up edit to align the stale bullet, but non-blocking for phase closure. |
| `.planning/REQUIREMENTS.md` | 15 | Checklist marker `[ ]` for SETUP-04 not updated to `[x]` despite traceability table (line 81) reading "Complete" | ⚠️ Warning | Cosmetic inconsistency within the same file; the traceability table (the field this protocol reads) is correct. Non-blocking. |

No `TBD`/`FIXME`/`XXX` unresolved debt markers found in any file touched by this gap-closure (`3c9b1f2`) or in any previously-flagged phase file.

All 6 review-driven fixes (CR-01, WR-01/02/03/05/06) previously verified as fixed remain fixed — no regressions detected (code untouched since prior verification).

### Human Verification Required

None. The one outstanding action from the prior verification — running the discriminating live-sandbox probe — has already been performed (by the user, in a live Claude Code session, per the handoff) and its result is now recorded with enough specificity (5 named hosts, explicit protocol, per-host outcome, correction history) to be independently assessed from the documentation and code alone. This mirrors how this same phase's prior verification already accepted Success Criterion 3's live credential-validation pass as VERIFIED without the verifier re-running it, for an analogous "this verifier's environment cannot safely/practically reproduce this specific live check" reason.

### Gaps Summary

No gaps remain. The single blocking gap from the prior verification — the egress-enforcement half of SETUP-04 / ROADMAP Success Criterion 5 — has been closed by the 2026-07-10 discriminating probe and the corresponding correction to `references/egress-allowlist.md` (commit `3c9b1f2`). This verifier independently confirmed:

- the commit exists and is scoped exactly as described (docs-only, 3 files, no code, tests still 32/32),
- the reference doc is now internally consistent (no residual "no prompt path" claim asserted as fact — it appears only inside the Correction-history table describing what was wrong),
- the auto-accept caveat and prompt-immune mitigation (`allowManagedDomainsOnly`, managed/org-only) are documented prominently as a standing operational risk, not silently dropped,
- Half A (generated settings) has not regressed (re-tested directly: deep-merge, malformed fail-clear, forced security flags),
- Truths 1-4 have not regressed (re-tested directly: D-10 layout, execution-target setter, credential-checker code, leak-guard hook including the CR-01 non-ASCII-filename path).

Two non-blocking documentation-consistency nits were found (stale `01-03-SUMMARY.md` key-decisions bullet; un-flipped `REQUIREMENTS.md` checklist marker for SETUP-04) and are recorded above as WARNING-level follow-ups — neither affects the substantive security posture or the phase goal.

**Overall determination: Phase 1's goal — "a single init turns an empty folder into a valid, git-tracked experiment workspace with a live-validated Kaggle connection and a locked-down network egress allowlist" — is achieved.** Status: `passed`, 5/5.

---

_Verified: 2026-07-10T06:49:57Z_
_Verifier: Claude (gsd-verifier)_
