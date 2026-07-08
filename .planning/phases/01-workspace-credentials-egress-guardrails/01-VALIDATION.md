---
phase: 1
slug: workspace-credentials-egress-guardrails
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-09
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `01-RESEARCH.md` §"Validation Architecture". Task IDs are wired to
> plans by the planner; rows below are keyed to requirements + concrete test files.

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

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | 01-02 | 1 | SETUP-01 | — | Empty dir → full layout (control/, docs, .gitignore, git repo) | unit (tmp_path) | `uv run pytest tests/test_init_workspace.py::test_full_layout -x` | ❌ W0 | ⬜ pending |
| TBD | 01-02 | 1 | SETUP-01 | — | Safe-merge: re-run never overwrites (D-02 idempotency) | unit | `uv run pytest tests/test_init_workspace.py::test_safe_merge_idempotent -x` | ❌ W0 | ⬜ pending |
| TBD | 01-02 | 1 | SETUP-01 | — | `git init` → repo on `main` + initial commit | unit | `uv run pytest tests/test_init_workspace.py::test_git_init -x` | ❌ W0 | ⬜ pending |
| TBD | 01-02 | 1 | SETUP-02 | — | `config.json` execution_target=local default; setter changes it; enum-validated | unit | `uv run pytest tests/test_config.py::test_execution_target -x` | ❌ W0 | ⬜ pending |
| TBD | 01-01 | 1 | SETUP-03 | — | Credential source detection + precedence (env > kaggle.json); token-type detection | unit (monkeypatch) | `uv run pytest tests/test_credentials.py::test_precedence -x` | ❌ W0 | ⬜ pending |
| TBD | 01-01 | 1 | SETUP-03 | — | command-not-found → UNVALIDATED + install remediation (D-07) | unit (mock `which`) | `uv run pytest tests/test_credentials.py::test_kaggle_missing -x` | ❌ W0 | ⬜ pending |
| TBD | 01-01 | 1 | SETUP-03 | — | Live validation against real Kaggle (pass/fail) | integration / manual | `uv run pytest tests/test_credentials_live.py -m live` | ❌ W0 | ⬜ pending |
| TBD | 01-01 | 1 | SETUP-04 | T-cred-perms | chmod 600 self-heal on group/world-readable kaggle.json (consent) | unit (tmp mode) | `uv run pytest tests/test_credentials.py::test_chmod_600 -x` | ❌ W0 | ⬜ pending |
| TBD | 01-01 | 1 | SETUP-04 | T-cred-echo | No script echoes a credential value (regex over *.py/*.sh) | security unit | `uv run pytest tests/test_no_credential_leak.py -x` | ❌ W0 | ⬜ pending |
| TBD | 01-02 | 1 | SETUP-04 | T-cred-commit | `.gitignore` covers .env/kaggle.json/access_token | unit | `uv run pytest tests/test_gitignore.py::test_secrets_ignored -x` | ❌ W0 | ⬜ pending |
| TBD | 01-01 | 1 | SETUP-04 | T-cred-commit | Pre-commit scanner blocks a staged fake token; passes clean content | unit (subprocess git repo in tmp) | `uv run pytest tests/test_leak_scan.py -x` | ❌ W0 | ⬜ pending |
| TBD | 01-01 | 1 | SETUP-04 | T-egress | `settings.json` valid JSON; `sandbox.network.allowedDomains` ⊇ required hosts | unit | `uv run pytest tests/test_settings.py::test_egress_allowlist -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky. Task IDs assigned by the planner; wire each PLAN task's `<automated>` verify to the matching command above.*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — tmp-workspace fixture; monkeypatched HOME/env fixtures
- [ ] `tests/test_init_workspace.py` — SETUP-01/02 layout + idempotency + git
- [ ] `tests/test_config.py` — SETUP-02 execution_target schema
- [ ] `tests/test_credentials.py` — SETUP-03 precedence, chmod, command-not-found
- [ ] `tests/test_credentials_live.py` — `-m live` integration (real token)
- [ ] `tests/test_no_credential_leak.py` — SETUP-04 no-echo scan (port exemplar's pattern, reimplemented)
- [ ] `tests/test_gitignore.py` — SETUP-04 secrets ignored
- [ ] `tests/test_settings.py` — SETUP-04 egress allowlist shape
- [ ] `tests/test_leak_scan.py` — SETUP-04 pre-commit scanner blocks/passes
- [ ] Framework install: `uv pip install pytest` + `[tool.pytest.ini_options]` with a `live` marker

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live Kaggle credential validation passes end-to-end | SETUP-03 | Needs a real Kaggle API token; cannot run in CI without a secret | Set real `KAGGLE_USERNAME`/`KAGGLE_KEY`, run `uv run pytest tests/test_credentials_live.py -m live`; expect pass. |
| Off-allowlist fetch is actually refused by the sandbox | SETUP-04 | Requires the live Claude Code sandbox (bubblewrap+socat) active on the host; socat is currently MISSING | With sandbox active, attempt an off-allowlist host fetch from a subprocess; expect refusal/prompt, not silent success. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
