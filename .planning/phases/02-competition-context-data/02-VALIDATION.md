---
phase: 2
slug: competition-context-data
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-10
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `02-RESEARCH.md` §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing `tests/`, `conftest.py` from Phase 1) |
| **Config file** | none dedicated; `conftest.py` provides `run_script`, `tmp_workspace`, `seeded_workspace`, `git_repo` fixtures and the `-m live` marker |
| **Quick run command** | `uv run pytest tests/ -x -q` (excludes `-m live` by default) |
| **Full suite command** | `uv run pytest tests/` |
| **Live suite (opt-in)** | `uv run pytest -m live` |
| **Estimated runtime** | ~5–15 seconds (mock-backed unit suite); live suite bounded by network |

**Convention (inherited from Phase 1):** skill scripts are exercised as **subprocesses** via the
`run_script` fixture; unit tests are mock/fixture-backed; real Kaggle calls are gated behind
`@pytest.mark.live` (see `tests/test_credentials_live.py`).

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/`
- **Before `/gsd:verify-work`:** Full suite must be green; `-m live` suite run once against a real
  competition slug (or explicitly skipped with recorded reason)
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

> Task IDs are assigned by the planner. This map is keyed on **success criterion** until plans
> exist, then extended with `{phase}-{plan}-{task}` IDs during execution.

| Criterion | Plan (expected) | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-----------|-----------------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| C1 capture → `competition.md` sections + tooling-written config fields | 02-02 | COMP-01 | — | Enum-validated `cv.scheme`, `competition.type`; `daily_limit` int | unit | `uv run pytest tests/test_capture.py tests/test_cv_evidence.py -x` | ❌ W0 | ⬜ pending |
| C1 limit regex → titanic rules fixture yields `10`, provenance `extracted`; the "select up to 5 final submissions" line is NOT matched | 02-02 | COMP-01 | T-INTEGRITY-01 | Fabricated limit can never masquerade as extracted | unit | `uv run pytest tests/test_limit_regex.py -x` | ❌ W0 | ⬜ pending |
| **C2 fence** — no interior `<untrusted-content` survives `escape_markers` across case/tag/partial variants | 02-02 | COMP-02 | T-TAMPER-01 | Fence cannot be broken from inside | unit | `uv run pytest tests/test_untrusted.py::test_fence_cannot_be_broken -x` | ❌ W0 | ⬜ pending |
| **C2 no-derived-exec** — taint sentinel appears in no recorded argv; `argv[0]` ∈ allowlist | 02-02 | COMP-02 | T-INJECT-01 | Competition text never reaches a subprocess | unit | `uv run pytest tests/test_untrusted.py::test_no_competition_text_reaches_subprocess -x` | ❌ W0 | ⬜ pending |
| C3 gate exit — gated fixture → exit `77` + exact rules URL, **no poll loop** (mock call-count == 1; `time.sleep` never called) | 02-01 | COMP-02 | T-DOS-01 | Never busy-loops an authenticated endpoint | unit | `uv run pytest tests/test_gate.py -x` | ❌ W0 | ⬜ pending |
| C3 re-probe verifies — `userHasEntered` flipped True → exit 0, proceeds | 02-01 | COMP-02 | — | Re-invocation *is* the verification | unit | `uv run pytest tests/test_gate.py -x` | ❌ W0 | ⬜ pending |
| C3 unclassified 403 fails closed, names both gates | 02-01 | COMP-02 | T-GUESS-01 | Never guesses a gate cause | unit | `uv run pytest tests/test_gate.py -x` | ❌ W0 | ⬜ pending |
| **C4 zip-slip** — abs / `..` / symlink / nested members each raise `UnsafeArchiveMember`; sibling temp dir stays empty; benign control extracts | 02-03 | COMP-03 | T-PATH-01 | No file escapes `data/` | unit | `uv run pytest tests/test_extract.py -x` | ❌ W0 | ⬜ pending |
| Egress — `api.kaggle.com` present in allowlist template | 02-01 | COMP-02 | T-EGRESS-01 | Narrow allowlist; no wildcard | unit | `uv run pytest tests/test_egress_allowlist.py -x` | ❌ W0 | ⬜ pending |
| Live CLI shapes — `pages`/`files`/`download`/403 match recorded signatures | 02-01 | COMP-01/02 | — | Recorded signatures stay true | integration | `uv run pytest -m live tests/test_competition_live.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_untrusted.py` — `test_fence_cannot_be_broken`, `test_no_competition_text_reaches_subprocess` (C2 deliverables, COMP-02)
- [ ] `tests/test_extract.py` — malicious-archive fixture + `test_no_file_escapes` (C4, COMP-03)
- [ ] `tests/test_gate.py` — mock-gateway exit-code, no-busy-loop, re-probe, fail-closed (C3, COMP-02)
- [ ] `tests/test_capture.py` — `competition.md` section population (C1, COMP-01)
- [ ] `tests/test_cv_evidence.py` — evidence → CV scheme decision table (C1, COMP-01)
- [ ] `tests/test_limit_regex.py` — limit extraction + provenance tagging (C1, COMP-01)
- [ ] `tests/test_egress_allowlist.py` — `api.kaggle.com` present, no wildcard broadening
- [ ] `tests/test_competition_live.py` — `-m live` CLI-shape assertions (extends `test_credentials_live.py`)
- [ ] **Fixtures:** captured `pages_all.json` (titanic); malicious + benign in-memory zip builder;
      tiny `train.csv`/`test.csv` variants (grouped / temporal / imbalanced)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Phone-verification 403 signature | COMP-02 | Cannot be triggered from an already phone-verified account; no fixture exists | Leave a documented `pytest.skip("cannot trigger phone-gate from a verified account")` placeholder. Design fails closed (D-12) regardless of signature. |
| Rules acceptance in browser | COMP-02 | Kaggle's rules gate is UI-only by design — there is no API to accept | Operator opens `https://www.kaggle.com/competitions/<slug>/rules`, accepts, re-invokes `download_data.py`. The re-invocation's preflight probe IS the automated verification. |
| Exact phone-settings URL | COMP-02 | Assumption A3 (`/settings/phone`) unverified | Confirm the live URL at implementation; record in `references/kaggle-cli-behavior.md` with provenance. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] Both C2 named deliverable tests exist and are green
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
