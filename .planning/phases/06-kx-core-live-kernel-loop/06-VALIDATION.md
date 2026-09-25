---
phase: 6
slug: kx-core-live-kernel-loop
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-25
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 (dev group, locked) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths `tests`, `addopts = -m 'not live'`, marker `live`) |
| **Quick run command** | `uv run pytest -q -x tests/kx` |
| **Full suite command** | `uv run pytest -q` (+ optional `uv run --group template-test pytest -q tests/template`) |
| **Live command** | `uv run pytest -m live -q tests/live` (real Kaggle; CPU kernels only; never submits) |
| **Estimated runtime** | ~15 seconds offline; live checks ~30–90 s per CPU kernel run |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q -x tests/kx`
- **After every plan wave:** Run `uv run pytest -q` (whole offline suite; v1 tests included until 06-06 retires them)
- **Before `/gsd:verify-work`:** Full offline suite green **plus** the in-phase live checks (06-01 init, 06-02 sync, 06-04 Titanic cycle, 06-05 failure paths + `next_action`-only transcript) recorded in VERIFICATION
- **Max feedback latency:** 15 seconds (offline)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-* | 01 | 1 | CORE-01 | — | Exactly one JSON envelope on stdout; stray prints / child stdout never leak | unit + subprocess | `uv run pytest -q tests/kx/test_cli_contract.py` | ❌ W0 | ⬜ pending |
| 06-01-* | 01 | 1 | CORE-02 | T-06 credential | Credential masked; fabricated token never in stdout/stderr; missing creds → `needs_user`, no prompt | unit | `uv run pytest -q tests/kx/test_init.py tests/kx/test_credentials.py tests/kx/test_adapter_guard.py` | ❌ W0 | ⬜ pending |
| 06-01-* | 01 | 1 | CORE-06 | — | `uv sync --project` from empty dir yields working `kx`; `kaggle==2.2.3` pinned | smoke | `uv run pytest -q tests/kx/test_packaging.py` | ❌ W0 | ⬜ pending |
| 06-01-* | 01 | 1 | CORE-02 | T-06 credential | Real credential validates live | LIVE | `uv run pytest -m live tests/live/test_live_init.py` | ❌ W0 | ⬜ pending |
| 06-02-* | 02 | 2 | PROF-01 | — | Profile built only from allow-listed structured fields; no prose | unit | `uv run pytest -q tests/kx/test_profile.py` | ❌ W0 | ⬜ pending |
| 06-02-* | 02 | 2 | PROF-01 | — | `kx sync titanic` live | LIVE | `uv run pytest -m live tests/live/test_live_sync.py` | ❌ W0 | ⬜ pending |
| 06-03-* | 03 | 2 | CORE-03 | — | Invalid `experiment.json` refused before `adapter.push` | unit | `uv run pytest -q tests/kx/test_experiment_spec.py tests/kx/test_run_refuses_invalid.py` | ❌ W0 | ⬜ pending |
| 06-03-* | 03 | 2 | TMPL-01 | — | Rendered template parses; no kx imports; `repr()`-injection safe; env keys only | unit | `uv run pytest -q tests/kx/test_template_render.py` | ❌ W0 | ⬜ pending |
| 06-03-* | 03 | 2 | ENS-01 | — | `kx-preds/1` validator rejects bad headers/counts/folds/NaN/dup ids/path escape | unit | `uv run pytest -q tests/kx/test_preds.py` | ❌ W0 | ⬜ pending |
| 06-04-* | 04 | 3 | RUN-01 | T-06 egress / path traversal | `enable_internet:false` explicit + read back; safe-path pull; bounded poll; version read back never guessed | unit (FakeAdapter) | `uv run pytest -q tests/kx/test_kernel.py tests/kx/test_pull_safe.py tests/kx/test_poll.py` | ❌ W0 | ⬜ pending |
| 06-04-* | 04 | 3 | CORE-04 | — | Fail-closed recorder ladder; ledger byte-stable | unit | `uv run pytest -q tests/kx/test_record.py tests/kx/test_ledger.py` | ❌ W0 | ⬜ pending |
| 06-04-* | 04 | 3 | RUN-01 / TMPL-01 / ENS-01 | — | Titanic cycle live: SUCCESS, machine-checked CV, `kx-preds/1` outputs | LIVE | `uv run pytest -m live tests/live/test_live_titanic_cycle.py` | ❌ W0 | ⬜ pending |
| 06-05-* | 05 | 4 | CORE-04 | — | Strategy facts, digest incl. FAILED rows | unit | `uv run pytest -q tests/kx/test_strategy.py tests/kx/test_lb_gap.py tests/kx/test_submissions_log.py` | ❌ W0 | ⬜ pending |
| 06-05-* | 05 | 4 | CORE-04 | — | Throwing kernel / invalid `result.json` → FAILED, null score | LIVE | `uv run pytest -m live tests/live/test_live_failures.py` | ❌ W0 | ⬜ pending |
| 06-05-* | 05 | 4 | CORE-01 | — | AI completes loop from `next_action` alone | LIVE (manual transcript) | executor follows envelopes `kx init` → `kx strategy` | n/a | ⬜ pending |
| 06-06-* | 06 | 4 | CORE-07 | — | No superseded tokens in `src/`, `SKILL.md`, templates; egress doc says "unverified" | static (grep/AST) | `uv run pytest -q tests/kx/test_core07_removals.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Task IDs are finalized by the planner; rows map requirement → plan → command.*

---

## Wave 0 Requirements

- [ ] `tests/kx/conftest.py` — `FakeAdapter` (records calls; scripted responses; can raise and print to stdout), `tmp_ws` fixture, fabricated-token env fixture
- [ ] `tests/kx/fixtures/` — stripped spike-001 raw JSON (titanic, equity), sample `kernel_run.json`, sample pulled `output/` sets (valid, lying mean, bad preds), a script-kernel benign log (captured from the first live run)
- [ ] `tests/live/` — live tests marked `live`, each creating a tmp workspace outside the repo
- [ ] Framework: none to install (pytest locked). Optional `template-test` dependency group (human-verify gate).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| AI completes the full loop driven only by `next_action` | CORE-01 | Measures agent behaviour, not code | From an empty `/tmp/kx-live/<name>` dir, follow each envelope's `next_action` from `kx init` through `kx strategy`; paste transcript into VERIFICATION |
| Live credential never appears in the transcript | CORE-02 | Real secret; cannot be fixture-asserted | Run `kx init` with the real `~/.kaggle/access_token`; grep the captured output for the token prefix; expect no match |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
