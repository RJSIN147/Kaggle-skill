---
phase: 05-submission-leaderboard-tracking
verified: 2026-07-12T00:00:00Z
status: human_needed
score: 7/7 must-haves verified
overrides_applied: 0
human_verification:
  - test: "A1 — verify submissions.date is UTC at the first real Kaggle submission"
    expected: "The Kaggle-returned `date` matches the noted UTC wall clock at submit time; if it differs by a local UTC offset, A1 is REFUTED and the day-boundary logic in charged_today/parse_utc must be corrected."
    why_human: "Cannot be proven without spending a real, irreversible daily submission slot with live Kaggle credentials — explicitly deferred per 05-HUMAN-UAT.md, no credentials/scored workspace exist on this machine."
resolved_after_verification:
  - item: "WR-02 — submit.py did not mechanically re-check the daily budget or the CV-improvement gate before spending a slot"
    decision: "Option (b) — harden. Chosen by the developer on 2026-07-12."
    outcome: >-
      RESOLVED. scripts/submit.py now calls _gate() before the TOCTOU re-hash and before any
      gateway call. Gate logic is IMPORTED, not re-derived (submission_gate.decide,
      submission_gate.NOISE_K_DEFAULT, submissions_log.remaining_slots/charged_today/
      COUNT_UNAVAILABLE), and the budget read goes through the injectable
      fetch_lb.read_submissions(..., runner=run_kaggle) — never the namespace-trap
      submissions_log.fetch_submissions(). Test-first: 7 tests confirmed RED against the
      pre-fix submit.py, GREEN after. Suite 277 -> 287 passed. Commits 6633682 (tests, RED)
      -> 62e86b4 (fix, GREEN).
    confirm_semantics: >-
      --confirm OVERRIDES (requires_confirmation=True): a within-noise CV gain, and the last
      ASSUMED slot — judgment calls about real, readable numbers, and the documented exit-75
      loop. --confirm does NOT override (requires_confirmation=False): an EXHAUSTED budget, an
      UNKNOWABLE budget, and an experiment with NO READABLE CV — there is nothing coherent to
      confirm. This line was already drawn by submission_gate.decide's requires_confirmation
      flag; submit.py now honors it instead of ignoring it. No new policy was invented.
    note: >-
      REVIEW.md's prose had claimed an exhausted budget IS overridable by design. That read came
      from SKILL.md prose; submission_gate.decide rule 2 says the opposite in code (BLOCK
      regardless of how spectacular the CV signal is). The prose was corrected to match the
      module — the code is the gate. SKILL.md's exit-75 entry now carries an explicit table of
      what --confirm does and does not override.
---

# Phase 5: Submission & Leaderboard Tracking Verification Report

**Phase Goal:** Submit under CV-first discipline with budget gating and CV-to-LB gap tracking
**Verified:** 2026-07-12
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `submit.py` spends a slot only under the full safety contract: PENDING row written BEFORE the poll, `rc==0` treated as advisory (fail-open literal matching), success confirmed by READ-BACK, double-spend refused (incl. `--reconcile`-back-filled rows with `file_sha256=None`, CR-01), CSV validated against the sample before submitting (CR-02), `--confirm` required | ✓ VERIFIED | Read `scripts/submit.py:212-242` (D-02 validation call), `:245-302` (`_refuse_double_spend`, blocks on hash match OR hash-absent), `:342-349` (`--confirm` gate), `:433-451` (PENDING row appended before poll). Independently ran `tests/test_submit.py::test_refuses_double_spend_after_reconcile`, `test_refuses_an_unvalidated_submission_csv`, `test_a_valid_csv_still_submits` — all pass. Commits `23c437a` (CR-01), `a5b87eb` (CR-02) confirmed present in the working tree. |
| 2 | CV remains the SOLE decision metric; the CV→LB gap is observed and trended (`scripts/lb_gap.py` + `regen_strategy._lb_gap_body` + `strategy.md.tmpl`'s `## CV-to-LB gap` section); no code path lets a leaderboard score influence experiment selection | ✓ VERIFIED | `scripts/check_submission.py::best_submitted_cv` (the sole comparison-set builder for `is_meaningful`/`decide`) is keyed exclusively on ledger `cv_mean`, filtered by submission *status* — never by `public_score`. Grepped every use of `public_score`/`lb_score` in `submission_gate.py`, `check_submission.py`, `regen_strategy.py`: the only two sites are `check_submission._divergence_line` (a printed trend line) and `lb_gap.py` (the derived, read-only alarm) — neither feeds `is_meaningful`/`decide`/`best_submitted_cv`. `lb_gap.rank_inversions` fires on rank inversion (scale-free, direction-aware) and `alarm_body` renders 3 honest states, including the `<2 scored` case. Independently ran `tests/test_lb_gap.py`, `tests/test_regen_strategy.py` — 17/17 pass. |
| 3 | Budget accounting fails closed: `submissions_log.charged_today()` returns `-1` (`COUNT_UNAVAILABLE`) on ANY unparseable status or date; `remaining_slots()` returns `None` on an unusable count; every consumer treats `None` as BLOCK, never "plenty left" | ✓ VERIFIED | `scripts/submissions_log.py:284-329` (`charged_today` returns `COUNT_UNAVAILABLE` immediately on an unparseable status or date, never `continue`s past it), `:332-341` (`remaining_slots` returns `None` whenever `charged==COUNT_UNAVAILABLE`). Sole consumer `submission_gate.decide` (`scripts/submission_gate.py:225-238`) treats `remaining is None` as `BLOCKED`/`requires_confirmation=False` — never permissive. `check_submission.py:715` renders `"UNKNOWN (fail closed)"` when `remaining is None`. Independently confirmed with the reviewer's own repro pattern: `charged_today -> -1 -> remaining_slots -> None -> decide -> BLOCKED`. |
| 4 | `check_submission.py`, the free entry point, spends NO slot on any code path (clear / blocked / validation-failed / unsupported) | ✓ VERIFIED | `tests/test_check_submission.py::test_never_submits` asserts, across all 4 scenarios, that every captured argv is `("competitions", "submissions", ...)` and never carries `"submit"`. Ran it independently — passes. Grepped `scripts/*.py` for the literal `"competitions", "submit"` construction: it exists in exactly one file, `scripts/submit.py:330`. |
| 5 | No test or dev path can reach a real `kaggle competitions submit` | ✓ VERIFIED | `tests/test_submit.py::test_no_live_test_ever_submits` mechanically greps every `tests/test_*live*.py` for a submit invocation and fails the suite if found; ran it — passes. `tests/test_submission_live.py` (the only live-marked submission test) issues exactly one read-only `competitions submissions` call and is docstring-pinned as READ-ONLY. Live tests are excluded from the default run (`pyproject.toml: addopts = "-m 'not live'"`). Note: the guard is a substring match on 3 literal spellings (WR-07, open warning) — evadable by reformatting, not a hard compiler-level guarantee, but it is real and currently effective. |
| 6 | `submission.csv` — previously nonexistent anywhere in the codebase (D-09 gap) — now exists, is emitted by the extended `run_cv` harness, respects the anti-leakage fold-preprocessor contract for test rows, uses type-aware (not `np.mean`) aggregation for label metrics, and degrades gracefully to no-file for pure-diagnostic experiments | ✓ VERIFIED | `scripts/templates/experiment.py.tmpl:143-261` implements `run_cv(..., submission_agg=)`, writing `submission.csv` flat at the experiment root only when test preds exist. **Independently installed numpy+scikit-learn into an isolated `uv venv` (they are deliberately absent from this repo's own dev deps — see `pyproject.toml`) and RAN the previously-`importorskip`-skipped `tests/test_run_cv.py` for real**: `test_submission_optional`, `test_label_aggregation_is_not_mean`, `test_test_preds_use_fold_preprocessor`, `test_preprocess_fits_on_train_fold_only`, `test_named_metric_roc_auc_writes_recorder_acceptable_result`, `test_custom_splitter_and_callable_metric` — all 6 passed. Full suite with ML deps present: 283 passed (277 default + 6 previously skipped), 0 failed. |
| 7 | `SKILL.md` sequences `check_submission -> [the human decides] -> submit -> fetch_lb`; the human confirmation loop lives in `SKILL.md`, never in an `input()` inside a script; the gate protocol branches on the exact exit codes 65/69/75 alongside 77/78 | ✓ VERIFIED | `SKILL.md:184-208` (exit-code gate entries for 65/69/75), `:375-413` (the numbered check→decide→submit→fetch sequence). Grepped `scripts/submit.py`, `check_submission.py`, `fetch_lb.py`, `submission_gate.py`, `submissions_log.py`, `lb_gap.py`, `regen_strategy.py` for `input(` — zero matches. |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `scripts/submit.py` | The ONE slot-spending entry point | ✓ VERIFIED | 539 lines; CR-01/CR-02 fixes present and test-covered |
| `scripts/check_submission.py` | The FREE pre-submit gate | ✓ VERIFIED | 760 lines; CR-03 fix present and test-covered; `test_never_submits` passes |
| `scripts/submission_gate.py` | Pure D-05/D-06/D-08 policy | ✓ VERIFIED | 355 lines; CR-03 candidate-CV-first ordering confirmed in `is_meaningful`/`decide` |
| `scripts/submissions_log.py` | The ONE `submissions.jsonl` schema module | ✓ VERIFIED | 499 lines; fail-closed `charged_today`/`remaining_slots` confirmed |
| `scripts/fetch_lb.py` | The D-03 detach fallback + `--reconcile` | ✓ VERIFIED | Bounded `poll_lb`, `LB_BUDGET_S=600`, `_resume`, `--reconcile` all present |
| `scripts/lb_gap.py` | Pure derived CV↔LB view + rank-inversion alarm | ✓ VERIFIED | 221 lines; `join_cv_lb`, `rank_inversions`, `alarm_body` all present and tested |
| `scripts/templates/experiment.py.tmpl` | `run_cv` extended to emit `submission.csv` | ✓ VERIFIED | Confirmed functionally via a real (ML-deps-installed) test run, not just static read |
| `SKILL.md` | The gate protocol + check→decide→submit→fetch sequence | ✓ VERIFIED | Exit 65/69/75/77/78 entries + numbered sequence present |
| `references/kaggle-cli-behavior.md` | Submit/submissions fixture entries incl. fail-open literals | ✓ VERIFIED (with a known, intentional PLACEHOLDER for A1) | `Could not find competition` / `Could not submit to competition` literals present; A1 entry explicitly marked `<!-- PLACEHOLDER -->`, not falsely claimed verified |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `submit.py` | `control/submissions.jsonl` | `append_row(PENDING)` before the poll loop | ✓ WIRED | `scripts/submit.py:437-451`, before `poll_lb` at `:469` |
| `submit.py` | `submissions_log.py` | `find_by_exp_id` over `read_submissions` (the read-back proof) | ✓ WIRED | `scripts/submit.py:413-418` |
| `fetch_lb.py` | `submissions_log.py` | `upsert_row` transitions PENDING → SCORED/FAILED | ✓ WIRED | Confirmed via `record_outcome`/`upsert_row` imports, exercised by `tests/test_fetch_lb.py` |
| `lb_gap.py` | `control/ledger.jsonl` + `control/submissions.jsonl` | join on `exp_id`, `meta.json` never opened | ✓ WIRED | `scripts/regen_strategy.py:287,291` reads both files from disk; `_lb_gap_body` calls `lb_gap.join_cv_lb` |
| `check_submission.py` | `submissions_log.py` | `charged_today`/`remaining_slots` import for the Kaggle-authoritative budget | ✓ WIRED | `scripts/check_submission.py:78-81` imports; `:662-669` calls |
| `submit.py` | `check_submission.py` | D-02 validation reuse (`_resolve_reference`, `validate_submission`) | ✓ WIRED | `scripts/submit.py:87` imports; `:212-240` calls before the TOCTOU re-hash |
| `submit.py` | `submissions_log.py` / `submission_gate.py` | budget + CV-improvement re-check before spending | ✗ NOT WIRED | `submit.py` imports neither `submission_gate` nor `charged_today`/`remaining_slots` — see WR-02 below and the human-verification item |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `strategy.md` `## CV-to-LB gap` | `sub_rows`, `rows` (ledger) | `submissions_log.read_rows(ws)` + `_read_ledger(ws/control/ledger.jsonl)` — real disk reads in `regen_strategy.main` | Yes | ✓ FLOWING |
| `check_submission.py` decision material | `charged`, `remaining`, `best_cv` | Live `run_kaggle("competitions","submissions",...)` call + `ledger.jsonl` read | Yes | ✓ FLOWING |
| `submission.csv` | fold test predictions | `run_cv`'s fold loop, fitted per-fold preprocessor | Yes (verified by executing the real, non-mocked test with numpy/sklearn installed) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full mock suite (no ML deps) | `uv run pytest -q` | `277 passed, 1 skipped, 12 deselected` | ✓ PASS |
| `ruff` lint | `uvx ruff check scripts/` | `All checks passed!` | ✓ PASS |
| CR-01 regression (reconcile then double-spend) | `uv run pytest tests/test_submit.py::test_refuses_double_spend_after_reconcile` | pass | ✓ PASS |
| CR-02 regression (unvalidated CSV) | `uv run pytest tests/test_submit.py -k "unvalidated_submission_csv or valid_csv_still_submits"` | pass | ✓ PASS |
| CR-03 regression (unreadable candidate CV) | `uv run pytest tests/test_gate_policy.py -k unreadable_candidate_cv tests/test_check_submission.py::test_missing_cv_is_never_clear` | pass | ✓ PASS |
| `submission.csv` emission (real numpy/sklearn, isolated venv) | `uv venv` + `uv pip install numpy scikit-learn` + `pytest tests/test_run_cv.py` | `6 passed` (previously `1 skipped` in the default env) | ✓ PASS |
| Full suite with ML deps present | same venv, `pytest -q` | `283 passed, 12 deselected` | ✓ PASS |
| No `input()` in any submission script | `grep -n "input(" scripts/{submit,check_submission,fetch_lb,submission_gate,submissions_log,lb_gap,regen_strategy}.py` | no matches | ✓ PASS |
| No debt markers (TBD/FIXME/XXX) in phase-touched files | `grep -n -E "TBD\|FIXME\|XXX"` over all 16 phase-modified files | no matches | ✓ PASS |

### Probe Execution

Step 7c: SKIPPED — no `scripts/*/tests/probe-*.sh` convention exists in this repo, and no plan/summary declares probe-based verification. The equivalent mechanism here is the pytest suite (exercised above) plus the code-review CRITICAL-fix-and-regression-test cycle documented in `05-REVIEW.md`.

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| SCORE-01 | 05-01, 05-02, 05-03, 05-05, 05-07 | User can submit predictions via the Kaggle CLI and record the resulting LB score | ✓ SATISFIED (mechanism) / requires A1 human-verify at first real use | `submit.py` + `fetch_lb.py` fully implement the slot-spend/read-back/detach/record flow; no live submission has been made yet (deliberately deferred — see human_verification) |
| SCORE-02 | 05-01, 05-03, 05-06, 05-07 | CV is the decision metric everywhere; the framework computes and trends the CV→LB gap with a divergence alarm | ✓ SATISFIED | `lb_gap.py` + `regen_strategy._lb_gap_body` + `strategy.md.tmpl`; no LB score reaches `is_meaningful`/`decide`/`best_submitted_cv` |
| SCORE-03 | 05-01, 05-03, 05-04, 05-05, 05-07 | Submissions are rationed against the daily limit; the framework gates submissions on CV improvement and tracks remaining budget | ✓ SATISFIED (as an advisory gate, per D-05's explicit design) / see WR-02 | `submission_gate.py` + `check_submission.py` implement the full D-05/D-06/D-08 policy and fail-closed budget accounting; `submit.py` itself does NOT independently re-check budget or CV-improvement before spending — enforcement is via the documented `SKILL.md` workflow rather than a second mechanical check inside the spend path |

No orphaned requirement IDs: SCORE-01/02/03 are each claimed by at least one plan's frontmatter and match `.planning/REQUIREMENTS.md`'s v1 list exactly. Note: `.planning/REQUIREMENTS.md` still shows all three as `[ ]` / "Pending" in its tracking table — this is a bookkeeping artifact (the file has not been updated post-phase), not a code gap; flagging for the developer to update at milestone-audit time.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `scripts/submit.py` | (whole file) | No independent budget/CV-improvement re-check before spending (WR-02) | ⚠️ Warning | The irreversible action's own script trusts the caller to have run `check_submission.py` first; `SKILL.md` documents this as "always run this first" but nothing mechanical enforces it, unlike CR-02's precedent for CSV validation |
| `scripts/submissions_log.py` | 347-372 | `fetch_submissions()` has zero production callers and mis-binds `run_kaggle` from its own module globals (WR-01) | ⚠️ Warning | Dead code / footgun if ever wired up naively; tracked in `05-HUMAN-UAT.md` as open debt |
| `tests/test_submit.py` | 816-821 | Source guard is a 3-literal substring match, not a normalized/regex match (WR-07) | ⚠️ Warning | Currently effective; evadable by reformatting (e.g. `run_kaggle(*SUBMIT_ARGV)`) |
| `scripts/lb_gap.py` | 203-220 | `alarm_body` de-dupes pairs by `exp_id` (last-write-wins), can misname the LB score on a re-submitted experiment (WR-08) | ⚠️ Warning | Cosmetic — the inversion itself is still detected correctly; only the rendered numbers can be stale |
| `scripts/check_submission.py` | 445-455, 553, 722 | WR-03 (403 misclassification), WR-10 (`--exp-dir experiments` containment edge case), WR-11 (`-1` sentinel printed raw) | ⚠️ Warning (x3) | All low-severity, already documented in `05-REVIEW.md`, none reach the irreversible surface |
| `scripts/submissions_log.py` | 242-273 | `validate_row` has zero callers and disagrees with rows `fetch_lb` legitimately writes (WR-04) | ⚠️ Warning | Dead validator, not wired up; would reject legitimate reconciled rows if it were |
| `scripts/submit.py` | 431 | Kaggle-returned `ref` is trusted without a type check (WR-05) | ⚠️ Warning | Could corrupt `upsert_row` on a malformed Kaggle response; not observed live |
| `scripts/submissions_log.py` | 310-329 | `charged_today` fails closed permanently on ANY historical row with a bad status, not just today's (WR-06) | ⚠️ Warning | Matches the LITERAL must-have as specified ("fails closed on any unparseable status/date"); the over-broad *scope* of the fail-close is a separate, already-documented refinement opportunity |

No BLOCKER anti-patterns and no unresolved debt markers (TBD/FIXME/XXX) found in any of the 16 phase-touched files.

### Human Verification Required

### 1. A1 — verify `submissions.date` is UTC

**Test:** At the first real, live Kaggle submission (with real credentials and a scored workspace): note the UTC wall clock (`date -u`) immediately before running `submit.py --confirm`, then compare it to the `date` value Kaggle returns on read-back.
**Expected:** The returned `date` matches the noted UTC wall clock → A1 CONFIRMED. If it differs by a local UTC offset → A1 REFUTED, and `submissions_log.parse_utc`/`charged_today`'s day-boundary handling must be corrected.
**Why human:** Cannot be proven without spending a real, irreversible daily submission slot. No Kaggle credentials or scored workspace exist on this machine. Already tracked with a full, correct procedure in `05-HUMAN-UAT.md` and a `<!-- PLACEHOLDER -->` in `references/kaggle-cli-behavior.md` (not falsely claimed verified anywhere in the codebase).

### 2. Decide whether `submit.py` should mechanically re-check the budget and CV-improvement gate

**Test:** Review `scripts/submit.py` (confirmed: it never imports `submission_gate` or `submissions_log.charged_today`/`remaining_slots`) against `05-REVIEW.md`'s WR-02 finding, and decide whether the current advisory-only design (enforced solely by `SKILL.md`'s documented `check → decide → submit` sequence) is the intended final state, or whether it should be hardened to independently gate the spend path — the way CR-02 hardened CSV validation to not depend on the caller having run `check_submission.py` first.
**Expected:** Either an explicit acceptance (e.g., a verification override recorded in this file) stating the advisory-only design is intentional per D-05, or a follow-up plan to add the re-check to `submit.py`.
**Why human:** This is a product/architecture judgment call about how far mechanical enforcement should extend on the irreversible surface, not a mechanical pass/fail the verifier can resolve. The phase's own code review already surfaced it and classified it as a non-blocking warning; re-litigating that classification without developer input would be presumptuous.

### Gaps Summary

No FAILED must-haves were found. Every truth explicitly named in this verification's scope — the fail-open/read-back/PENDING-before-poll/double-spend/CSV-validation/`--confirm` contract in `submit.py`; the fail-closed budget-accounting chain in `submissions_log.py`; CV-as-sole-decision-metric in `submission_gate.py`/`check_submission.py`; the CV→LB gap trend and rank-inversion alarm in `lb_gap.py`; the D-09 `submission.csv` emission gap being closed in `run_cv`; the `check_submission.py` free-gate's zero-slot-spend guarantee; and the `SKILL.md` wiring of the human loop — was independently verified against the actual code and, where feasible, against real (not mocked) test execution, including installing the ML stack into an isolated venv specifically to exercise the previously-skipped `run_cv` submission-emission tests.

The code review (`05-REVIEW.md`) found 3 CRITICALs on the irreversible submission path (CR-01 double-spend-via-reconcile, CR-02 missing CSV validation in `submit.py`, CR-03 CV-less first submission clearing the gate); all 3 were independently confirmed fixed in this verification, each backed by a passing regression test that was also independently re-run here. 11 warnings remain open by design and are re-surfaced above rather than silently dropped.

Two items require a human decision before the phase can be called fully closed:
1. **A1** (the UTC assumption underlying day-boundary budget accounting) — deliberately deferred, cannot be proven without spending a real slot, already tracked with a correct procedure.
2. **WR-02** (`submit.py` has no independent budget/CV-gate re-check) — a real, material asymmetry with the CR-02 precedent that the developer should consciously accept or schedule a fix for, since it is closer to the phase's core "budget gating" promise than the other 10 warnings.

Given these, `status: human_needed` rather than `passed` — not because a truth failed, but because the phase's own governance already flagged two items that require a human decision, and this verifier does not have standing to make either call unilaterally.

---

_Verified: 2026-07-12_
_Verifier: Claude (gsd-verifier)_
