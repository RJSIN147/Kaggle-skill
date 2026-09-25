---
phase: 1
slug: workspace-credentials-egress-guardrails
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-09
revised: 2026-07-09
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `01-RESEARCH.md` §"Validation Architecture". Task IDs are wired to
> plans by the planner; rows below are keyed to requirements + concrete test files.
> Revised 2026-07-09 to add the cross-AI-review pins (D-01 slug gate, D-02 deep-merge/malformed,
> D-09 settings merge + settings fail-clear, D-03/D-06 consent, git-staging scope, leak-scanner content-scan).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest ≥8.0 (NOT installed — Wave 0 installs) |
| **Config file** | none yet — Wave 0 adds `[tool.pytest.ini_options]` (with a `live` marker) to the skill's `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds (unit + security; excludes `-m live`) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q` (all unit/security; excludes `-m live`)
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full unit+security suite must be green; the live credential test (`-m live`) run once manually with a real token.
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

Base contract (unchanged):

| Plan (GREEN) | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-02 | 2 | SETUP-01 | — | Empty dir → full layout (control/, docs, .gitignore, git repo) | unit (tmp_path) | `uv run pytest tests/test_init_workspace.py::test_full_layout -x` | ❌ W0 | ⬜ pending |
| 01-02 | 2 | SETUP-01 | — | Safe-merge: re-run never overwrites (D-02 idempotency) | unit | `uv run pytest tests/test_init_workspace.py::test_safe_merge_idempotent -x` | ❌ W0 | ⬜ pending |
| 01-03 | 3 | SETUP-01 | — | `git init` → repo on `main` + initial commit | unit | `uv run pytest tests/test_init_workspace.py::test_git_init -x` | ❌ W0 | ⬜ pending |
| 01-02 | 2 | SETUP-02 | — | `config.json` execution_target=local default; setter changes it; enum-validated | unit | `uv run pytest tests/test_config.py::test_execution_target -x` | ❌ W0 | ⬜ pending |
| 01-04 | 3 | SETUP-03 | — | Credential source detection + precedence (env > kaggle.json); token-type detection | unit (monkeypatch) | `uv run pytest tests/test_credentials.py::test_precedence -x` | ❌ W0 | ⬜ pending |
| 01-04 | 3 | SETUP-03 | — | command-not-found → UNVALIDATED + install remediation (D-07) | unit (mock `which`) | `uv run pytest tests/test_credentials.py::test_kaggle_missing -x` | ❌ W0 | ⬜ pending |
| 01-04 | 3 | SETUP-03 | — | Live validation against real Kaggle (pass/fail) | integration / manual | `uv run pytest tests/test_credentials_live.py -m live` | ❌ W0 | ⬜ pending |
| 01-04 | 3 | SETUP-04 | T-cred-perms | chmod 600 self-heal on group/world-readable kaggle.json (consent) | unit (tmp mode) | `uv run pytest tests/test_credentials.py::test_chmod_600 -x` | ❌ W0 | ⬜ pending |
| 01-04 | 3 | SETUP-04 | T-cred-echo | No script echoes a credential value (regex over *.py/*.sh) | security unit | `uv run pytest tests/test_no_credential_leak.py -x` | ❌ W0 | ⬜ pending |
| 01-03 | 3 | SETUP-04 | T-cred-commit | `.gitignore` covers .env/kaggle.json/access_token | unit | `uv run pytest tests/test_gitignore.py::test_secrets_ignored -x` | ❌ W0 | ⬜ pending |
| 01-03 | 3 | SETUP-04 | T-cred-commit | Pre-commit scanner blocks a staged fake token; passes clean content | unit (subprocess git repo in tmp) | `uv run pytest tests/test_leak_scan.py -x` | ❌ W0 | ⬜ pending |
| 01-03 | 3 | SETUP-04 | T-egress | `settings.json` valid JSON; `sandbox.network.allowedDomains` ⊇ required hosts | unit | `uv run pytest tests/test_settings.py::test_egress_allowlist -x` | ❌ W0 | ⬜ pending |

Review-driven pins (NEW — all authored RED in 01-01 Wave 0, turned GREEN in the plan noted):

| Plan (GREEN) | Wave | Requirement | Locked Decision | Secure Behavior | Automated Command | File Exists | Status |
|------|------|-------------|-----------------|-----------------|-------------------|-------------|--------|
| 01-02 | 2 | SETUP-01 | D-01 | Fresh workspace without `--slug` creates nothing, exits non-zero (mechanical guided-then-scaffold gate) | `uv run pytest tests/test_init_workspace.py::test_refuses_creation_without_slug -x` | ❌ W0 | ⬜ pending |
| 01-02 | 2 | SETUP-01 | D-02 | Deep-merge preserves a nested user edit (`cv.scheme`) while adding missing keys | `uv run pytest tests/test_init_workspace.py::test_safe_merge_deep_preserves_nested -x` | ❌ W0 | ⬜ pending |
| 01-02 | 2 | SETUP-01 | D-02 | Malformed control JSON is not overwritten; fail-clear (non-zero exit, bytes intact) | `uv run pytest tests/test_init_workspace.py::test_safe_merge_malformed_json_fails_clearly -x` | ❌ W0 | ⬜ pending |
| 01-02 | 2 | SETUP-02 | D-02 | Only `--set-execution-target` overwrites; a plain re-run never resets a manual change | `uv run pytest tests/test_config.py::test_no_overwrite_outside_setter -x` | ❌ W0 | ⬜ pending |
| 01-03 | 3 | SETUP-04 | D-09 | Existing `.claude/settings.json` is deep-merged (user key preserved, hosts unioned), not skipped | `uv run pytest tests/test_settings.py::test_egress_allowlist_merges_existing -x` | ❌ W0 | ⬜ pending |
| 01-03 | 3 | SETUP-04 | D-02/D-09 | Malformed pre-existing `.claude/settings.json` is not overwritten; fail-clear (non-zero exit, bytes intact) — same guarantee config.json gets | `uv run pytest tests/test_settings.py::test_egress_allowlist_malformed_fails_clearly -x` | ❌ W0 | ⬜ pending |
| 01-03 | 3 | SETUP-01/04 | D-02 | Scaffold commit stages only scaffold-owned paths; a stray user file is not swept in | `uv run pytest tests/test_init_workspace.py::test_scaffold_commit_excludes_stray_files -x` | ❌ W0 | ⬜ pending |
| 01-03 | 3 | SETUP-04 | D-15 | Broadened dotenv patterns (export/quoted/spaced/lowercase) are blocked | `uv run pytest tests/test_leak_scan.py::test_blocks_export_quoted_dotenv -x` | ❌ W0 | ⬜ pending |
| 01-03 | 3 | SETUP-04 | D-15 | Bare 32-hex NOT in a `"key":` JSON field does not false-positive | `uv run pytest tests/test_leak_scan.py::test_ignores_unrelated_32hex_json -x` | ❌ W0 | ⬜ pending |
| 01-04 | 3 | SETUP-04 | D-03/D-06a | chmod-600 self-heal applies only with consent (`--yes`); reported otherwise | `uv run pytest tests/test_credentials.py::test_chmod_600_requires_consent -x` | ❌ W0 | ⬜ pending |
| 01-04 | 3 | SETUP-04 | D-03/D-06b | `.env` population from kaggle.json applies only with consent; offered otherwise | `uv run pytest tests/test_credentials.py::test_env_population_requires_consent -x` | ❌ W0 | ⬜ pending |
| 01-04 | 3 | SETUP-04 | D-04/V7 | Captured subprocess stderr is never surfaced raw; a token-shaped string is masked/omitted | `uv run pytest tests/test_credentials.py::test_subprocess_output_no_secret -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky. Task IDs assigned by the planner; wire each PLAN task's `<automated>` verify to the matching command above.*

---

## Wave 0 Requirements

Nine files total in `tests/` (`conftest.py` + 8 `test_*.py`). New review-driven pins are added as FUNCTIONS inside the existing 8 files — no new files — so the file count stays 8 `test_*.py`.

- [ ] `tests/conftest.py` — tmp-workspace fixture; monkeypatched HOME/env fixtures; throwaway-git-repo helper for leak-scan/commit-scope tests
- [ ] `tests/test_init_workspace.py` — SETUP-01/02 layout + idempotency + git; **+ test_refuses_creation_without_slug, test_safe_merge_deep_preserves_nested, test_safe_merge_malformed_json_fails_clearly, test_scaffold_commit_excludes_stray_files**
- [ ] `tests/test_config.py` — SETUP-02 execution_target schema; **+ test_no_overwrite_outside_setter**
- [ ] `tests/test_credentials.py` — SETUP-03 precedence, chmod, command-not-found; **+ test_chmod_600_requires_consent, test_env_population_requires_consent, test_subprocess_output_no_secret**
- [ ] `tests/test_credentials_live.py` — `-m live` integration (real token)
- [ ] `tests/test_no_credential_leak.py` — SETUP-04 no-echo scan (port exemplar's pattern, reimplemented)
- [ ] `tests/test_gitignore.py` — SETUP-04 secrets ignored
- [ ] `tests/test_settings.py` — SETUP-04 egress allowlist shape; **+ test_egress_allowlist_merges_existing** (D-09 merge)**, + test_egress_allowlist_malformed_fails_clearly** (D-02/D-09 fail-clear)
- [ ] `tests/test_leak_scan.py` — SETUP-04 pre-commit scanner blocks/passes; **+ test_blocks_export_quoted_dotenv, test_ignores_unrelated_32hex_json**
- [ ] Framework install: `uv pip install pytest` + `[tool.pytest.ini_options]` with a `live` marker

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live Kaggle credential validation passes end-to-end | SETUP-03 | Needs a real Kaggle API token; cannot run in CI without a secret | Set real `KAGGLE_USERNAME`/`KAGGLE_KEY`, run `uv run pytest tests/test_credentials_live.py -m live`; expect pass. |
| Off-allowlist fetch is actually refused by the sandbox (host-enforcement half of criterion 5) | SETUP-04 | Requires the live Claude Code sandbox (bubblewrap+socat) active on the host; socat is currently MISSING | With sandbox active + socat installed, attempt an off-allowlist host fetch from a subprocess; expect refusal/prompt, not silent success. Generated-settings correctness is covered by the automated `test_settings.py` tests; this manual step covers enforcement. |
| Consent-gated D-06b/c normalize branches | SETUP-04 | Interactive consent flow (`--yes`) with real/placeholder kaggle.json | Per 01-04 Task 3 steps 6-7: without consent the `.env`-populate fix is offered not applied; with `--yes` it applies; no secret printed. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
