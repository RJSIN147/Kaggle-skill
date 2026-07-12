---
phase: 5
slug: submission-leaderboard-tracking
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-12
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `05-RESEARCH.md` § Validation Architecture. The planner fills the
> Per-Task Verification Map once plan/task IDs exist.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest ≥8.0 (already configured — no Wave 0 install needed) |
| **Config file** | `pyproject.toml` → `[tool.pytest.ini_options]` (`testpaths = ["tests"]`, `addopts = "-m 'not live'"`, `live` marker registered) |
| **Quick run command** | `uv run pytest tests/test_submit.py tests/test_check_submission.py tests/test_budget.py -x -q` |
| **Full suite command** | `uv run pytest` (live suite excluded by default) |
| **Live suite (opt-in)** | `uv run pytest -m live` — **READ-ONLY Kaggle calls only** |
| **Estimated runtime** | ~15 seconds (mock suite; no CLI process is ever spawned) |

---

## ⭐ Phase-Defining Constraint: never spend a submission slot to test the submit path

A real submission is **irreversible** and consumes a scarce daily slot. Four enforcement layers,
all reusing conventions that already exist in this repo:

1. **Mock-backed unit tests (primary).** `monkeypatch.setattr(module, "run_kaggle", fake)` — the
   established pattern from `tests/test_gateway.py::_fake_run_kaggle`. Tests assert on the **argv**
   the fake receives, proving the exact command shape without executing it.
2. **Live-captured fixtures.** `tests/fixtures/submissions/*.json` transcribed from the real CLI
   output pinned in `05-RESEARCH.md` §R2 — not hand-invented (Phase 2 learned that lesson and
   recorded it in `references/kaggle-cli-behavior.md`).
3. **Source-guard test (the irreversibility guarantee).** Mirrors
   `test_poll_kernel.py::test_source_routes_through_gateway`: no `@pytest.mark.live` test may
   contain `competitions submit`. Makes the constraint **enforced, not remembered**.
4. **`--dry-run` on `submit.py`.** Prints the exact argv it *would* pass to the gateway and exits 0
   without calling it.

**Live tests may call ONLY `competitions submissions` (read-only)** — one CLI-drift canary asserting
the 7 JSON keys and the `SubmissionStatus.` prefix still hold. It spends nothing.

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/test_submit.py tests/test_check_submission.py tests/test_budget.py -x -q`
- **After every plan wave:** `uv run pytest` (full mock suite)
- **Before `/gsd:verify-work`:** full suite green **and** `uv run ruff check scripts/`
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

> **Planner: complete this table.** Task IDs are assigned during planning; the Requirement →
> Behavior → Command rows below are pre-derived from research and are authoritative — map each
> to the task that delivers it.

| Task ID | Plan | Wave | Requirement | Behavior (must be TRUE) | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-------------------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | SCORE-01 | `submit.py` builds exact argv; never `-k`/`-v`/`--sandbox` | unit (mock gw) | `uv run pytest tests/test_submit.py::test_argv_shape -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-01 | **rc==0 + `Could not find competition` ⇒ FAILURE** (fail-open guard) | unit | `uv run pytest tests/test_submit.py::test_fail_open_404_is_not_success -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-01 | **rc==0 + `Could not submit to competition` ⇒ FAILURE** | unit | `uv run pytest tests/test_submit.py::test_fail_open_upload_is_not_success -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-01 | rc==0 + read-back finds no matching row ⇒ fail closed | unit | `uv run pytest tests/test_submit.py::test_unconfirmed_submission_fails_closed -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-01 | Read-back correlates on `description` prefix + `date >= started`, recovers Kaggle `ref` | unit | `uv run pytest tests/test_submit.py::test_correlates_by_exp_id -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-01 | `"SubmissionStatus.COMPLETE"` → SCORED; bare `COMPLETE` parses; garbage → `None` (never a false terminal) | unit | `uv run pytest tests/test_submissions_log.py::test_parse_status -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-01 | `publicScore` `""` → `None` (**never `0.0`**); `"0.77511"` → `0.77511` | unit | `uv run pytest tests/test_submissions_log.py::test_parse_score -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-01 | LB poll: bounded budget, jitter ≤ cap, **DETACH on expiry** (row stays PENDING; slot not lost) | unit (injected clock) | `uv run pytest tests/test_fetch_lb.py::test_detach_preserves_pending -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-01 | `fetch_lb.py` re-runnable: PENDING → SCORED, idempotent on second run | unit | `uv run pytest tests/test_fetch_lb.py::test_idempotent_resume -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-01 | `submit.py` refuses duplicate (same `exp_id` + `file_sha256`) without `--resubmit` | unit | `uv run pytest tests/test_submit.py::test_refuses_double_spend -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-01 | `competition.type ∈ {code, unknown}` ⇒ refusal exit code, **gateway never called** | unit | `uv run pytest tests/test_check_submission.py::test_refuses_non_csv_type -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-01 (D-09) | `run_cv` with test data emits `submission.csv`; **without it, still records a valid CV result** | unit | `uv run pytest tests/test_run_cv.py::test_submission_optional -x` | ⚠ extend | ⬜ pending |
| TBD | TBD | TBD | SCORE-01 (D-09) | **`label` metrics VOTE, never mean** (a 5-fold 0/1 aggregate contains only 0/1) | unit | `uv run pytest tests/test_run_cv.py::test_label_aggregation_is_not_mean -x` | ⚠ extend | ⬜ pending |
| TBD | TBD | TBD | SCORE-01 (D-09) | `proba`/`raw` metrics mean across folds; test preds use each fold's own fitted preprocessor (no leakage) | unit | `uv run pytest tests/test_run_cv.py::test_test_preds_use_fold_preprocessor -x` | ⚠ extend | ⬜ pending |
| TBD | TBD | TBD | SCORE-02 | CV→LB gap computed per SCORED submission; unscored rows excluded | unit | `uv run pytest tests/test_lb_gap.py::test_gap_trend -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-02 | **Rank-inversion alarm fires** on (CV better, LB worse); direction-aware for both `greater_is_better` values | unit | `uv run pytest tests/test_lb_gap.py::test_rank_inversion_alarm -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-02 | Alarm is **honest with <2 scored** submissions (states it; never fabricates a signal) | unit | `uv run pytest tests/test_lb_gap.py::test_alarm_needs_two_points -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-02 | `regen_strategy.py` renders the LB block from tooling facts; AI reasoning still spliced; full overwrite preserved | unit | `uv run pytest tests/test_regen_strategy.py::test_lb_block_rendered -x` | ⚠ extend | ⬜ pending |
| TBD | TBD | TBD | SCORE-02 | LB score is **never** written into `meta.json` (D-11 immutability) | unit | `uv run pytest tests/test_submit.py::test_meta_json_untouched -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-03 | Budget counts **today's** rows, **excludes ERROR** (D-13), **includes PENDING** | unit | `uv run pytest tests/test_budget.py::test_charged_today -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-03 | **UTC boundary**: identical count under `TZ=Pacific/Kiritimati` (+14) and `TZ=Pacific/Midway` (−11) | unit (TZ-parametrized) | `uv run pytest tests/test_budget.py::test_utc_day_boundary -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-03 | Unfetchable/unparseable count ⇒ **fail closed** (block; never guess) | unit | `uv run pytest tests/test_budget.py::test_fails_closed_when_count_unavailable -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-03 | D-06 gate: gain ≤ `k·cv_std` ⇒ **BLOCKED**; gain > `k·cv_std` ⇒ clear; **first-ever submission ⇒ clear** | unit | `uv run pytest tests/test_gate_policy.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-03 | D-08: `limit_provenance == "assumed_default"` ⇒ warn **every time**; **last** assumed slot ⇒ blocked pending confirmation | unit | `uv run pytest tests/test_gate_policy.py::test_assumed_limit_last_slot -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCORE-03 | `check_submission.py` **never calls `competitions submit`** (it is free) | unit (argv assertion) | `uv run pytest tests/test_check_submission.py::test_never_submits -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-02 | Validation catches header mismatch, row-count mismatch, id-set mismatch, blank/NaN prediction — each with a precise message | unit | `uv run pytest tests/test_check_submission.py::test_validation_matrix -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-02 | Sample resolved via `submission_csv_in_manifest` (**`gender_submission.csv`**), then glob, then `test.csv` fallback | unit | `uv run pytest tests/test_check_submission.py::test_sample_resolution_ladder -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SECURITY | Raw CLI buffer **never echoed**; token-shaped string in submit output is quarantined, not printed | unit | `uv run pytest tests/test_no_credential_leak.py -x` | ⚠ extend | ⬜ pending |
| TBD | TBD | TBD | SAFETY | **No `live`-marked test invokes `competitions submit`** | source guard | `uv run pytest tests/test_submit.py::test_no_live_test_ever_submits -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DRIFT | Live canary: `submissions --format json` still yields 7 keys + `SubmissionStatus.` prefix | live (read-only) | `uv run pytest -m live tests/test_submission_live.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_submissions_log.py` — status/score parse, row schema, atomic append (SCORE-01/02)
- [ ] `tests/test_check_submission.py` — validation matrix, sample resolution, never-submits, type refusal (SCORE-01/03, D-02)
- [ ] `tests/test_submit.py` — argv shape, **fail-open guards**, read-back correlation, double-spend refusal, `meta.json` immutability, live-submit source guard (SCORE-01)
- [ ] `tests/test_fetch_lb.py` — detach/resume, idempotence, PENDING→SCORED (SCORE-01)
- [ ] `tests/test_budget.py` — charged-today, ERROR-excluded, **UTC boundary (TZ-parametrized)**, fail-closed (SCORE-03)
- [ ] `tests/test_gate_policy.py` — D-05/D-06/D-08 gate matrix (SCORE-03)
- [ ] `tests/test_lb_gap.py` — gap trend + rank-inversion alarm + <2-point honesty (SCORE-02)
- [ ] `tests/test_submission_live.py` — read-only CLI-drift canary (`-m live`)
- [ ] `tests/fixtures/submissions/*.json` + `submit_*.txt` — **live-captured** shapes from RESEARCH §R1/§R2
- [ ] Extend `tests/test_run_cv.py` — D-09 optional emission, label-vs-mean aggregation, fold-preprocessor reuse
- [ ] Extend `tests/test_regen_strategy.py` — the LB/gap facts block
- [ ] Framework install: **none needed** — pytest ≥8.0 with the `live` marker is already configured

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| **The first real end-to-end submission** | SCORE-01 | Irreversible — spends a real slot. Cannot be automated by definition. | Human-supervised: run `check_submission.py` → `submit.py` on a real competition once. Capture the success-path output into `references/kaggle-cli-behavior.md`. |
| **Is `submissions.date` UTC?** (RESEARCH open question A1) | SCORE-03 | The CLI returns a **naive** ISO timestamp with no tz suffix. Unprovable without a real submission at a known wall-clock time. | At the first real submit (above), record local time + the returned `date`. If they differ by the local UTC offset, `date` is UTC — confirm the budget's day-boundary assumption. **Gate the budget model behind this check.** |

---

## Validation Sign-Off

- [ ] All tasks have an `<automated>` verify command or a Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all ❌ MISSING test files above
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] **No automated test can ever invoke `competitions submit`** (source guard green)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
