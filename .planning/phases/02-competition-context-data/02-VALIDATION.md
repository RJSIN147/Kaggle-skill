---
phase: 2
slug: competition-context-data
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-10
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `02-RESEARCH.md` §Validation Architecture; plan IDs reconciled against the
> checker-approved `02-01..02-05-PLAN.md` (VERIFICATION PASSED, revision iteration 2).

**`nyquist_compliant: true`** — every task in every plan carries an `<automated>` verify, no task
run uses watch-mode, sampling continuity holds (no 3 consecutive tasks without automated verify),
and no Wave-0 `MISSING` reference is left dangling.

**`wave_0_complete: false`** — the Wave 0 test files below do not exist yet; `/gsd:execute-phase 2`
creates them. Flip this to `true` once they are on disk and green.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing `tests/`, `conftest.py` from Phase 1) |
| **Config file** | none dedicated; `conftest.py` provides `run_script`, `tmp_workspace`, `seeded_workspace`, `git_repo`, `clean_kaggle_env` fixtures and the `-m live` marker |
| **Quick run command** | `uv run pytest tests/ -x -q` (excludes `-m live` by default) |
| **Full suite command** | `uv run pytest tests/` |
| **Live suite (opt-in)** | `uv run pytest -m live` |
| **Estimated runtime** | ~5–15 seconds (mock-backed unit suite); live suite bounded by network |

**Convention (inherited from Phase 1):** skill scripts are exercised as **subprocesses** via the
`run_script` fixture; unit tests are mock/fixture-backed; real Kaggle calls are gated behind
`@pytest.mark.live` (see `tests/test_credentials_live.py`).

⚠ **Fixture correctness is load-bearing.** `conftest.py`'s `seeded_workspace` must pre-reserve
`cv.scheme`, `competition.type`, and `submission.{daily_limit,limit_provenance}` as `null` —
matching what `init_workspace.py` actually scaffolds. Plan 02-02 extends it. Without this, tests
for the config writes pass against an absent key while production silently no-ops against a
reserved `null`. That masking is precisely the blocker caught in revision 2.

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/ -x -q`
- **After every plan wave:** `uv run pytest tests/`
- **Before `/gsd:verify-work`:** full suite green; `-m live` suite run once against a real
  competition slug (or explicitly skipped with a recorded reason)
- **Max feedback latency:** 15 seconds

---

## Per-Criterion Verification Map

| Criterion | Plan | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-----------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| Egress — `api.kaggle.com` on allowlist, no wildcard broadening (**blocking prerequisite**) | 02-01 | COMP-02 | T-02-EGRESS-01 | Narrow allowlist | unit | `uv run pytest tests/test_egress_allowlist.py -x` | ❌ W0 | ⬜ pending |
| Gateway — `run_kaggle()` generalizes `run_kaggle_list()`; timeout→124; never echoes captured output | 02-01 | COMP-01, COMP-02 | T-02-LEAK-01 | Captured CLI output never surfaced raw | unit | `uv run pytest tests/test_gateway.py -x` | ❌ W0 | ⬜ pending |
| C3 unclassified 403 fails closed, names **both** gates, never guesses (D-12) | 02-01 | COMP-02 | T-02-GUESS-01 | Never infers a gate cause from a generic message | unit | `uv run pytest tests/test_gateway.py -x` | ❌ W0 | ⬜ pending |
| **C2 fence** — no interior `<untrusted-content` survives `escape_markers` across case/tag/partial variants | 02-02 | COMP-02 | T-02-TAMPER-01 | Fence cannot be broken from inside | unit | `uv run pytest tests/test_untrusted.py::test_fence_cannot_be_broken -x` | ❌ W0 | ⬜ pending |
| **C2 no-derived-exec** — taint sentinel in no recorded argv; `argv[0]` ∈ allowlist (**both** sentinel + argv monkeypatch) | 02-02 | COMP-02 | T-02-INJECT-01 | Competition text never reaches a subprocess | unit | `uv run pytest tests/test_untrusted.py::test_no_competition_text_reaches_subprocess -x` | ❌ W0 | ⬜ pending |
| C1 limit regex — titanic rules fixture → `10`, provenance `extracted`; decoy "select up to **5** final submissions" must NOT match | 02-02 | COMP-01 | T-02-INTEGRITY-01 | A fabricated limit can never masquerade as extracted | unit | `uv run pytest tests/test_limit_regex.py -x` | ❌ W0 | ⬜ pending |
| C1 capture — `competition.md` metric/rules/limit sections populated; `competition.type` enum written by tooling | 02-02 | COMP-01 | T-02-TYPE-01 | AI passes a `choices=`-validated flag; tooling writes | unit | `uv run pytest tests/test_capture.py -x` | ❌ W0 | ⬜ pending |
| **Config-write regression** — starting from a config where the key exists as `null`, `set_config_field` lands a **non-null** value (`write_control_json` cannot) | 02-02, 02-04 | COMP-01 | T-02-WRITE-01 | D-05/D-13/D-14 writes actually persist | unit | `uv run pytest tests/test_capture.py tests/test_cv_evidence.py -x` | ❌ W0 | ⬜ pending |
| Section safe-merge — `competition_doc.replace_section` replaces only a `_TODO (Phase 2)_` body; a curated section survives a re-run; siblings untouched (D-04) | 02-02 | COMP-01 | — | Idempotent at section granularity | unit | `uv run pytest tests/test_capture.py -x` | ❌ W0 | ⬜ pending |
| C3 gate exit — gated fixture → exit `77` + exact rules URL, **no poll loop** (mock call-count == 1; `time.sleep` monkeypatched, asserted not-called) | 02-03 | COMP-02 | T-02-DOS-01 | Never busy-loops an authenticated endpoint | unit | `uv run pytest tests/test_gate.py -x` | ❌ W0 | ⬜ pending |
| C3 re-probe verifies — `userHasEntered` flipped True → exit 0, proceeds | 02-03 | COMP-02 | — | Re-invocation *is* the verification | unit | `uv run pytest tests/test_gate.py -x` | ❌ W0 | ⬜ pending |
| **C4 zip-slip** — abs / `..` / symlink / nested members each raise `UnsafeArchiveMember`; sibling temp dir stays empty; benign control extracts | 02-03 | COMP-03 | T-02-PATH-01 | No file escapes `data/` | unit | `uv run pytest tests/test_extract.py -x` | ❌ W0 | ⬜ pending |
| C1 CV scheme — evidence → scheme decision table; enum written by tooling; **name + rationale** land in `competition.md` `## Cross-validation scheme` | 02-04 | COMP-01 | T-02-INTEGRITY-02 | AI reasons, tooling writes; two-part deliverable (D-05) | unit | `uv run pytest tests/test_cv_evidence.py -x` | ❌ W0 | ⬜ pending |
| C1 AV degrade — ML env absent → exit 0, `AV: SKIPPED (ML env absent; run uv sync)` recorded | 02-04 | COMP-01 | — | Flag-don't-abort (Phase 1 D-07) | unit | `uv run pytest tests/test_cv_evidence.py -x` | ❌ W0 | ⬜ pending |
| D-09 independence — `analyze_data.py` with no prior capture still writes `cv.scheme` + `cv-evidence.json` and **flags** the missing capture | 02-04 | COMP-01 | — | Entry points are independently re-runnable | unit | `uv run pytest tests/test_cv_evidence.py -x` | ❌ W0 | ⬜ pending |
| `set_execution_target` regression — SETUP-02 argparse surface, exit codes, stdout unchanged after the `set_config_field` refactor | 02-02 | — | — | Phase 1 behavior preserved | unit | `uv run pytest tests/test_config.py -x` | ✅ | ⬜ pending |
| Live CLI shapes — `pages`/`files`/`download`/403 match recorded signatures; no token-shaped string leaks | 02-05 | COMP-01, COMP-02 | T-02-LEAK-02 | Recorded signatures stay true | integration | `uv run pytest -m live tests/test_competition_live.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Created during execution, before the implementation each one guards.

- [ ] `tests/test_egress_allowlist.py` — `api.kaggle.com` present, no wildcard (analog: `tests/test_settings.py`)
- [ ] `tests/test_gateway.py` — `run_kaggle` timeout/no-echo; `classify_gate` fail-closed on unclassified 403
- [ ] `tests/test_untrusted.py` — `test_fence_cannot_be_broken`, `test_no_competition_text_reaches_subprocess` (**C2 deliverables**)
- [ ] `tests/test_limit_regex.py` — limit extraction + provenance tagging + the decoy-line assertion
- [ ] `tests/test_capture.py` — `competition.md` sections, `competition.type` write, `replace_section` idempotence, config-write regression
- [ ] `tests/test_gate.py` — exit-77, no-busy-loop, re-probe (**C3**)
- [ ] `tests/test_extract.py` — malicious-archive fixture + `test_no_file_escapes` (**C4**)
- [ ] `tests/test_cv_evidence.py` — evidence→scheme table, AV degrade, D-09 independence, config-write regression
- [ ] `tests/test_competition_live.py` — `-m live` CLI-shape assertions (extends `test_credentials_live.py`)
- [ ] `tests/conftest.py` — **extend** `seeded_workspace` to pre-reserve `competition.type` + `submission.{daily_limit,limit_provenance}` as `null` (additive; Phase 1 tests unaffected)
- [ ] `tests/cv_fixtures.py` — one builder generating grouped / temporal / imbalanced `train.csv`/`test.csv` pairs on demand
- [ ] `tests/fixtures/pages_all.json` — captured titanic `competitions pages` payload

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Accept competition rules in browser | COMP-02 | Kaggle's rules gate is UI-only — there is no API to accept it. Modeled as `checkpoint:human-action` in 02-05 (the one checkpoint type that still stops under auto-mode). | Claude runs `download_data.py`, hits exit 77, surfaces `https://www.kaggle.com/competitions/<slug>/rules`. Operator accepts in browser. Claude re-invokes — the re-invocation's preflight probe IS the verification (D-10). Nothing polls. |
| Confirm exact phone-settings URL | COMP-02 | Assumption A3 (`/settings/phone`) unverified; requires a browser | 02-05 Task 3. Confirm the live URL (fall back to `/settings` if it 404s); Claude records it in `references/kaggle-cli-behavior.md` with provenance. |
| Phone-verification 403 signature | COMP-02 | Cannot be triggered from an already phone-verified account; no fixture exists | Documented `pytest.skip("cannot trigger phone-gate from a verified account")` placeholder. D-12 fails closed regardless of signature, so behavior does not depend on the answer. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] Both C2 named deliverable tests appear as explicit acceptance criteria
- [x] Config-write regression test asserts a non-null value from a reserved-`null` starting state
- [x] `nyquist_compliant: true` set in frontmatter
- [ ] `wave_0_complete` — flip to `true` once the Wave 0 files exist and are green (during `/gsd:execute-phase 2`)

**Approval:** approved 2026-07-10 (plan-checker: VERIFICATION PASSED, revision iteration 2)
