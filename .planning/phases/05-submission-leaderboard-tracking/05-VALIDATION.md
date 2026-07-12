---
phase: 5
slug: submission-leaderboard-tracking
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-12
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `05-RESEARCH.md` § Validation Architecture. The Per-Task Verification Map is
> filled in below (planning complete, 2026-07-12).

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

## Wave / Plan Layout (assigned during planning)

| Wave | Plans | What it delivers |
|------|-------|------------------|
| 1 | 05-01 | Nyquist Wave 0: live-captured fixtures + every RED test module (no Phase-5 script exists yet) |
| 2 | 05-02, 05-03 | D-09 harness (`submission.csv` production) ‖ foundation (exit codes + `submissions_log.py` + `noise_k`) |
| 3 | 05-04, 05-05, 05-06 | the FREE gate ‖ submit + fetch_lb ‖ CV→LB gap + divergence alarm |
| 4 | 05-07 | SKILL.md gate protocol + `references/kaggle-cli-behavior.md` + the A1 live checkpoint |

**Task ID convention:** `{plan}-T{n}` — e.g. `05-05-T2` = plan 05-05, task 2.
Wave-0 RED authorship for every row below happens in **05-01** (T2 for the data/decision tier,
T3 for the entry points and the extended modules). The `Task ID` column names the task that turns
the row **GREEN**.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Behavior (must be TRUE) | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-------------------------|-----------|-------------------|-------------|--------|
| 05-05-T2 | 05-05 | 3 | SCORE-01 | `submit.py` builds exact argv; never `-k`/`-v`/`--sandbox` | unit (mock gw) | `uv run pytest tests/test_submit.py::test_argv_shape -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-05-T2 | 05-05 | 3 | SCORE-01 | **rc==0 + `Could not find competition` ⇒ FAILURE** (fail-open guard) | unit | `uv run pytest tests/test_submit.py::test_fail_open_404_is_not_success -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-05-T2 | 05-05 | 3 | SCORE-01 | **rc==0 + `Could not submit to competition` ⇒ FAILURE** | unit | `uv run pytest tests/test_submit.py::test_fail_open_upload_is_not_success -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-05-T2 | 05-05 | 3 | SCORE-01 | rc==0 + read-back finds no matching row ⇒ fail closed | unit | `uv run pytest tests/test_submit.py::test_unconfirmed_submission_fails_closed -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-05-T2 | 05-05 | 3 | SCORE-01 | Read-back correlates on `description` prefix + `date >= started`, recovers Kaggle `ref` | unit | `uv run pytest tests/test_submit.py::test_correlates_by_exp_id -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-05-T2 | 05-05 | 3 | SCORE-01 | PENDING row (exp_id + ref + hash) is written **BEFORE** the poll — a crash never orphans a spent slot | unit | `uv run pytest tests/test_submit.py::test_pending_row_written_before_poll -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-05-T2 | 05-05 | 3 | SCORE-01 | `--dry-run` prints the argv and **never calls the gateway** | unit (argv assertion) | `uv run pytest tests/test_submit.py::test_dry_run_never_calls_gateway -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-03-T2 | 05-03 | 2 | SCORE-01 | `"SubmissionStatus.COMPLETE"` → SCORED; bare `COMPLETE` parses; garbage → `None` (never a false terminal) | unit | `uv run pytest tests/test_submissions_log.py::test_parse_status -x` | ❌ W0 (05-01-T2) | ⬜ pending |
| 05-03-T2 | 05-03 | 2 | SCORE-01 | `publicScore` `""` → `None` (**never `0.0`**); `"0.77511"` → `0.77511` | unit | `uv run pytest tests/test_submissions_log.py::test_parse_score -x` | ❌ W0 (05-01-T2) | ⬜ pending |
| 05-03-T2 | 05-03 | 2 | SCORE-01 | `submissions.jsonl` row schema is a fixed-order 14-key tuple; atomic rewrite is byte-stable | unit | `uv run pytest tests/test_submissions_log.py::test_row_schema tests/test_submissions_log.py::test_atomic_rewrite -x` | ❌ W0 (05-01-T2) | ⬜ pending |
| 05-05-T3 | 05-05 | 3 | SCORE-01 | LB poll: bounded budget, jitter ≤ cap, **DETACH on expiry** (row stays PENDING; slot not lost) | unit (injected clock) | `uv run pytest tests/test_fetch_lb.py::test_detach_preserves_pending -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-05-T3 | 05-05 | 3 | SCORE-01 | `fetch_lb.py` re-runnable: PENDING → SCORED, idempotent on second run | unit | `uv run pytest tests/test_fetch_lb.py::test_idempotent_resume -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-05-T3 | 05-05 | 3 | SCORE-01 | Kaggle `ERROR` ⇒ row becomes FAILED with `error_description: null` (reason not fabricated); D-13 recorded-not-counted | unit | `uv run pytest tests/test_fetch_lb.py::test_error_row_becomes_failed -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-05-T3 | 05-05 | 3 | SCORE-01 | `--reconcile` back-fills out-of-band submissions; no `exp-NNN` prefix ⇒ `exp_id: null` | unit | `uv run pytest tests/test_fetch_lb.py::test_reconcile_backfills_out_of_band -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-05-T2 | 05-05 | 3 | SCORE-01 | `submit.py` refuses duplicate (same `exp_id` + `file_sha256`) without `--resubmit` | unit | `uv run pytest tests/test_submit.py::test_refuses_double_spend -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-04-T2 | 05-04 | 3 | SCORE-01 | `competition.type ∈ {code, unknown}` ⇒ exit 69, **gateway never called** | unit | `uv run pytest tests/test_check_submission.py::test_refuses_non_csv_type -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-02-T1 | 05-02 | 2 | SCORE-01 (D-09) | `run_cv` with test data emits `submission.csv`; **without it, still records a valid CV result** | unit | `uv run pytest tests/test_run_cv.py::test_submission_optional -x` | ⚠ extend (05-01-T3) | ⬜ pending |
| 05-02-T1 | 05-02 | 2 | SCORE-01 (D-09) | **`label` metrics VOTE, never mean** (a 5-fold 0/1 aggregate contains only 0/1) | unit | `uv run pytest tests/test_run_cv.py::test_label_aggregation_is_not_mean -x` | ⚠ extend (05-01-T3) | ⬜ pending |
| 05-02-T1 | 05-02 | 2 | SCORE-01 (D-09) | `proba`/`raw` metrics mean across folds; test preds use each fold's own fitted preprocessor (no leakage) | unit | `uv run pytest tests/test_run_cv.py::test_test_preds_use_fold_preprocessor -x` | ⚠ extend (05-01-T3) | ⬜ pending |
| 05-02-T2 | 05-02 | 2 | SCORE-01 (D-09) | Scaffolder renders the sample header (`gender_submission.csv` ⇒ `PassengerId`/`Survived`); no header ⇒ `None` ⇒ emission skipped gracefully | unit | `uv run pytest tests/test_scaffold_experiment.py -x` | ⚠ extend | ⬜ pending |
| 05-06-T1 | 05-06 | 3 | SCORE-02 | CV→LB gap computed per SCORED submission; unscored rows excluded | unit | `uv run pytest tests/test_lb_gap.py::test_gap_trend -x` | ❌ W0 (05-01-T2) | ⬜ pending |
| 05-06-T1 | 05-06 | 3 | SCORE-02 | **Rank-inversion alarm fires** on (CV better, LB worse); direction-aware for both `greater_is_better` values | unit | `uv run pytest tests/test_lb_gap.py::test_rank_inversion_alarm -x` | ❌ W0 (05-01-T2) | ⬜ pending |
| 05-06-T1 | 05-06 | 3 | SCORE-02 | Alarm is **honest with <2 scored** submissions (states it; never fabricates a signal) | unit | `uv run pytest tests/test_lb_gap.py::test_alarm_needs_two_points -x` | ❌ W0 (05-01-T2) | ⬜ pending |
| 05-06-T2 | 05-06 | 3 | SCORE-02 | `regen_strategy.py` renders the LB block from tooling facts; AI reasoning still spliced; full overwrite preserved | unit | `uv run pytest tests/test_regen_strategy.py::test_lb_block_rendered -x` | ⚠ extend (05-01-T3) | ⬜ pending |
| 05-05-T2 | 05-05 | 3 | SCORE-02 | LB score is **never** written into `meta.json` (D-11 immutability) | unit | `uv run pytest tests/test_submit.py::test_meta_json_untouched -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-03-T2 | 05-03 | 2 | SCORE-03 | Budget counts **today's** rows, **excludes ERROR** (D-13), **includes PENDING** | unit | `uv run pytest tests/test_budget.py::test_charged_today -x` | ❌ W0 (05-01-T2) | ⬜ pending |
| 05-03-T2 | 05-03 | 2 | SCORE-03 | **UTC boundary**: identical count under `TZ=Pacific/Kiritimati` (+14) and `TZ=Pacific/Midway` (−11) | unit (TZ-parametrized) | `uv run pytest tests/test_budget.py::test_utc_day_boundary -x` | ❌ W0 (05-01-T2) | ⬜ pending |
| 05-03-T2 | 05-03 | 2 | SCORE-03 | Unfetchable/unparseable count ⇒ **fail closed** (block; never guess) | unit | `uv run pytest tests/test_budget.py::test_fails_closed_when_count_unavailable -x` | ❌ W0 (05-01-T2) | ⬜ pending |
| 05-03-T1 | 05-03 | 2 | SCORE-03 | Exit codes 65 / 69 / 75 exist, are sysexits-aligned, and collide with nothing (77/78/124/126/127/128+) | unit | `uv run pytest tests/test_gateway.py -x` | ⚠ extend | ⬜ pending |
| 05-04-T1 | 05-04 | 3 | SCORE-03 | D-06 gate: gain ≤ `k·cv_std` ⇒ **BLOCKED**; gain > `k·cv_std` ⇒ clear; **first-ever submission ⇒ clear** | unit | `uv run pytest tests/test_gate_policy.py -x` | ❌ W0 (05-01-T2) | ⬜ pending |
| 05-04-T1 | 05-04 | 3 | SCORE-03 | D-08: `limit_provenance == "assumed_default"` ⇒ warn **every time**; **last** assumed slot ⇒ blocked pending confirmation | unit | `uv run pytest tests/test_gate_policy.py::test_assumed_limit_last_slot -x` | ❌ W0 (05-01-T2) | ⬜ pending |
| 05-04-T2 | 05-04 | 3 | SCORE-03 | `check_submission.py` **never calls `competitions submit`** (it is free) | unit (argv assertion) | `uv run pytest tests/test_check_submission.py::test_never_submits -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-04-T2 | 05-04 | 3 | D-02 | Validation catches header mismatch, row-count mismatch, id-set mismatch, blank/NaN prediction — each with a precise message; exit 65 | unit | `uv run pytest tests/test_check_submission.py::test_validation_matrix -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-04-T2 | 05-04 | 3 | D-02 | Sample resolved via `submission_csv_in_manifest` (**`gender_submission.csv`**), then glob, then `test.csv` fallback | unit | `uv run pytest tests/test_check_submission.py::test_sample_resolution_ladder -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-05-T2 | 05-05 | 3 | SECURITY | Raw CLI buffer **never echoed**; token-shaped string in submit output is quarantined, not printed | unit | `uv run pytest tests/test_no_credential_leak.py -x` | ⚠ extend (05-01-T3) | ⬜ pending |
| 05-01-T3 | 05-01 | 1 | SAFETY | **No `live`-marked test invokes `competitions submit`** | source guard | `uv run pytest tests/test_submit.py::test_no_live_test_ever_submits -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-07-T3 | 05-07 | 4 | DRIFT | Live canary: `submissions --format json` still yields 7 keys + `SubmissionStatus.` prefix | live (read-only) | `uv run pytest -m live tests/test_submission_live.py -x` | ❌ W0 (05-01-T3) | ⬜ pending |
| 05-07-T1 | 05-07 | 4 | SCORE-03 (D-05/D-07) | SKILL.md gate protocol branches on 65 / 69 / 75; the human decides on exit 75; `--reason` is OPTIONAL; D-12 is nowhere | doc assertion | `grep -q "check_submission.py" SKILL.md && grep -q "75" SKILL.md && ! grep -qi "nominat\|final selection" SKILL.md` | ⚠ extend | ⬜ pending |
| 05-07-T2 | 05-07 | 4 | SCORE-01 | `references/kaggle-cli-behavior.md` records the fail-open literals, the 7-field allow-list, the `SubmissionStatus.` prefix, and the no-quota-command finding | doc assertion | `grep -q "Could not find competition" references/kaggle-cli-behavior.md && grep -q "Could not submit to competition" references/kaggle-cli-behavior.md && grep -q "SubmissionStatus." references/kaggle-cli-behavior.md` | ⚠ extend | ⬜ pending |
| 05-07-T2 | 05-07 | 4 | SCORE-01 | `experiments/*/submission.csv` stays **ignored by decision** (provenance = `file_sha256`); `control/submissions.jsonl` stays tracked | doc/config assertion | `grep -q "experiments/\*/\*.csv" scripts/templates/gitignore.tmpl && ! grep -q "!experiments/\*/submission.csv" scripts/templates/gitignore.tmpl && uv run pytest tests/test_gitignore.py -x -q` | ⚠ extend | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All authored in **05-01** (wave 1) — no Phase-5 script exists at that point, so every module below
is imported **inside** the test body and collection never crashes.

- [ ] `tests/test_submissions_log.py` — status/score parse, row schema, atomic rewrite (SCORE-01/02) — *05-01-T2*
- [ ] `tests/test_budget.py` — charged-today, ERROR-excluded, **UTC boundary (TZ-parametrized)**, fail-closed (SCORE-03) — *05-01-T2*
- [ ] `tests/test_gate_policy.py` — D-05/D-06/D-08 gate matrix (SCORE-03) — *05-01-T2*
- [ ] `tests/test_lb_gap.py` — gap trend + rank-inversion alarm + <2-point honesty (SCORE-02) — *05-01-T2*
- [ ] `tests/test_check_submission.py` — validation matrix, sample resolution, never-submits, type refusal (SCORE-01/03, D-02) — *05-01-T3*
- [ ] `tests/test_submit.py` — argv shape, **fail-open guards**, read-back correlation, write-ordering, double-spend refusal, `meta.json` immutability, `--dry-run`, live-submit source guard (SCORE-01) — *05-01-T3*
- [ ] `tests/test_fetch_lb.py` — detach/resume, idempotence, PENDING→SCORED, ERROR→FAILED, `--reconcile` (SCORE-01) — *05-01-T3*
- [ ] `tests/test_submission_live.py` — read-only CLI-drift canary (`-m live`) — *05-01-T3*
- [ ] `tests/fixtures/submissions/*.json` + `submit_404.txt` / `submit_upload_failed.txt` — **live-captured** shapes from RESEARCH §R1/§R2 — *05-01-T1*
- [ ] Extend `tests/test_run_cv.py` — D-09 optional emission, label-vs-mean aggregation, fold-preprocessor reuse — *05-01-T3*
- [ ] Extend `tests/test_regen_strategy.py` — the LB/gap facts block — *05-01-T3*
- [ ] Extend `tests/test_no_credential_leak.py` — the four new scripts — *05-01-T3*
- [ ] Framework install: **none needed** — pytest ≥8.0 with the `live` marker is already configured

---

## Manual-Only Verifications

| Behavior | Requirement | Task | Why Manual | Test Instructions |
|----------|-------------|------|------------|-------------------|
| **The first real end-to-end submission** | SCORE-01 | **05-07-T3** (`checkpoint:human-verify`, blocking) | Irreversible — spends a real slot. Cannot be automated by definition. | Human-supervised: `check_submission.py` → `submit.py --confirm` on a real competition once. Confirm success came from the READ-BACK, not from rc==0. Capture the success-path output into `references/kaggle-cli-behavior.md`. |
| **Is `submissions.date` UTC?** (RESEARCH open question A1) | SCORE-03 | **05-07-T3** (same checkpoint) | The CLI returns a **naive** ISO timestamp with no tz suffix. Unprovable without a real submission at a known wall-clock time. | At the first real submit, record `date -u` before submitting and compare it to the returned `date`. Match ⇒ **A1 CONFIRMED**; differs by the local UTC offset ⇒ **REFUTED** and the budget day-boundary is a BLOCKER. Record the verdict in `references/kaggle-cli-behavior.md`. |

---

## Validation Sign-Off

- [x] All tasks have an `<automated>` verify command or a Wave 0 dependency
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all ❌ MISSING test files above (authored in 05-01)
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] **No automated test can ever invoke `competitions submit`** (source guard: `05-01-T3` → `tests/test_submit.py::test_no_live_test_ever_submits`)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned 2026-07-12 — Per-Task Verification Map complete, no TBDs remaining.
</content>
