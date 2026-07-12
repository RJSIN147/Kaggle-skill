---
phase: 05-submission-leaderboard-tracking
plan: 04
subsystem: submission-gate
tags: [wave-3, gate, fail-closed, d-05, d-06, d-08, validation, free-entry-point, stdlib]

requires:
  - scripts/submissions_log.py (charged_today, remaining_slots, COUNT_UNAVAILABLE, read_rows)
  - scripts/kaggle_gateway.py (run_kaggle, classify_gate, dump_last_error, _parse_json_array, 65/69/75/77)
  - scripts/metric_registry.py (prediction_type — the D-09 label-trap discriminator)
  - scripts/scaffold_experiment.py (_find_sample_submission — the R4 ladder rungs 1-2)
  - tests/test_gate_policy.py, tests/test_check_submission.py (the 05-01 RED contract)
provides:
  - scripts/submission_gate.py (NOISE_K_DEFAULT, RECOMMENDATIONS, ASSUMED_PROVENANCE,
    is_meaningful, decide — pure, I/O-free D-05/D-06/D-08 policy)
  - scripts/check_submission.py (VALIDATION_REASONS, Reference, validate_submission,
    label_trap_warning, fetch_submissions, best_submitted_cv, main — the FREE entry point;
    exits 0/65/69/75/77)
affects:
  - 05-05 (submit.py re-runs this gate's decision behind --confirm; the same
    module-level run_kaggle monkeypatch seam applies)
  - 05-07 (SKILL.md branches on the EXACT exit codes 0/65/69/75/77)

tech-stack:
  added: []
  patterns:
    - "pure policy module (zero I/O) + thin I/O entry point — the decision matrix is testable with no filesystem and no network"
    - "run_kaggle bound at MODULE level (the poll_kernel posture) so the suite substitutes the gateway and asserts argv without executing"
    - "math.isclose guard on a STRICT float inequality evaluated at its exact boundary"
    - "closed reason enum (VALIDATION_REASONS) paralleling record_experiment.FAILURE_REASONS"

key-files:
  created:
    - scripts/submission_gate.py
    - scripts/check_submission.py
  modified: []

decisions:
  - "check_submission implements its OWN fetch_submissions rather than calling submissions_log.fetch_submissions — the latter resolves run_kaggle from ITS module globals, which monkeypatching check_submission.run_kaggle cannot reach. The parse/count/budget logic is still imported, never re-derived."
  - "is_meaningful guards the strict inequality with math.isclose: 0.81-0.80 == 0.010000000000000009 > 0.01 would score an exactly-at-bound gain as meaningful from IEEE-754 error alone"
  - "a numeric 0.0 cv_std collapses the noise bound to zero (permissive); an ABSENT (None) cv_std fails CLOSED — unknowable noise is not a zero bound"
  - "the D-09 label-trap check consults metric_registry.prediction_type, so a roc_auc competition whose reference file shows 0/1 is NOT falsely warned about legitimate probabilities"
  - "the label trap forces requires_confirmation (exit 75) rather than exit 65 — the file is structurally valid and a hard refusal would false-positive on real proba competitions"
  - "remaining <= 0 and remaining is None both set requires_confirmation False — there is no slot to consciously confirm"

metrics:
  duration: ~25min
  tasks: 2
  files-created: 2
  files-modified: 0
  completed: 2026-07-12
---

# Phase 5 Plan 04: The FREE Submission Gate Summary

Built the gate that answers "should I submit this?" **completely** — type refusal, file
validation, Kaggle-authoritative budget, CV-vs-fold-noise decision, rendered material —
**without ever spending a slot**, with the D-05/D-06/D-08 policy isolated in a pure,
I/O-free module so the decision matrix is exhaustively testable.

## What Was Built

**Task 1 — `scripts/submission_gate.py` (`ba9acb5`).** The policy, and nothing but the
policy: no filesystem, no network, no clock, no `main()`, no side effects on import. Every
function is pure, so `test_gate_policy.py` is a plain decision matrix.

`NOISE_K_DEFAULT = 1.0`, and the docstring states *why* rather than asserting it: `cv_std`
from `run_cv` is the **population** std of the fold scores, not the standard error of the
mean (~2.2x smaller at 5 folds), so requiring a gain to exceed one full fold-std is roughly
a 2-sigma test in SEM terms — deliberately **conservative**. The asymmetry is the whole
argument: a false SUBMIT wastes a scarce, irreversible slot; a false BLOCK costs **one
keystroke**, because D-05 guarantees the human can override with the numbers in front of
them. The two error costs are nowhere near symmetric, so the bar leans toward the cheap
mistake.

`decide()` applies four rules in order: an unknowable budget (`remaining is None`) blocks
and never guesses a count; an exhausted budget blocks regardless of how good the CV is (a
gain cannot buy a slot that does not exist); an `assumed_default` limit warns on **every**
decision and gates the **last** assumed slot behind explicit confirmation even when the CV
says SUBMIT; and finally the D-06 noise test decides, blocking-by-default *with*
`requires_confirmation` when the gain is within noise.

**Task 2 — `scripts/check_submission.py` (`fbd68fe`).** The FREE entry point — stdlib-only
(the plumbing tier is pandas-free, so CSVs go through the `csv` module), self-locating,
`--workspace`-driven, argparse-in/exit-code-out, never interactive.

The ladder, each rung failing closed with a distinct code: **D-01** refuses any
`competition.type != "csv"` with exit 69 *before any Kaggle call at all* — it costs nothing
to know the CSV path cannot serve a code competition, so nothing is spent finding out.
**D-02** runs four `csv`-module checks against the competition's own reference file (exact
**ordered** header, exact row count, **order-independent** id-set equality, and no
blank/NaN/NA/null/inf in any prediction column), each failure exiting 65 with a message
naming the *exact* mismatch — `row count 2 != expected 3`, `3 id(s) ... are MISSING (first:
894)` — because a validator that only says "invalid" teaches nothing and invites a blind
override, which spends the very slot the check exists to protect. **D-04** derives the
budget from Kaggle's authoritative submissions list and blocks rather than guess when it is
unfetchable or unparseable. **D-05/D-06** delegate to the pure policy, then the material is
rendered with real numbers and the override command printed.

## Key Decisions

**The reference-file ladder reuses Phase 2's signal instead of guessing a filename — and
prints its pick.** Titanic's reference file is `gender_submission.csv`, *not* the
conventional name a guessing resolver would reach for. `test_sample_resolution_ladder`
plants a decoy `sample_submission.csv` with a wrong header right next to the real file: a
guessing resolver picks the decoy and reports a bogus header mismatch. The manifest signal
wins, then a case-insensitive glob, then `test.csv`'s id column, then failure — and the
chosen file is **printed**, because Phase 2's own comment flags the heuristic as weak and a
silently-wrong reference would validate garbage clean and spend a real slot on it
(T-05-04-03).

**The D-09 label trap is caught for real, and the discriminator matters.** A LABEL metric
needs `0`/`1`, but a `run_cv` that *means* its fold predictions emits `0.4`/`0.6` — right
shape, right ids, no blanks, so all four structural checks pass it happily and a real slot
burns on numbers Kaggle cannot use. The check consults `metric_registry.prediction_type`
from the tooling-written config rather than guessing from the data: a **roc_auc**
competition whose reference file happens to show `0`/`1` legitimately *wants* continuous
probabilities and must not be warned about. It forces `requires_confirmation` (exit 75)
rather than exit 65 — the file *is* structurally valid, and a hard refusal would
false-positive on genuine probability competitions.

**A `0.0` cv_std is permissive; an absent one fails closed.** The plan's task text grouped
"missing/None/0" as a zero noise bound while also demanding a fail-closed guard on
non-numeric input — a latent contradiction, since `None` *is* non-numeric. Resolved on the
fail-closed side: a numeric `0.0` genuinely means no fold-noise to clear (any strict gain
passes, and `test_noise_gate_matrix` pins that), but an **absent** std is *unknowable*
noise, and claiming a gain exceeds a bound we could not compute would be fabricated
confidence.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] IEEE-754 error at the exact noise bound made a strictly-forbidden gain "meaningful"**
- **Found during:** Task 1 (`test_noise_gate_matrix` line 60 failed on first run)
- **Issue:** D-06 requires `margin > k * cv_std` to be **strictly** greater, so a gain of
  exactly one fold-std must NOT pass. But in IEEE-754, `0.81 - 0.80 == 0.010000000000000009`,
  which *is* `> 0.01`. The exactly-at-bound case — the one the policy explicitly rules out —
  passed purely from representation error, and would have spent an irreversible slot on a
  difference the gate is designed to reject.
- **Fix:** Guarded the strict inequality with `math.isclose(margin, bound, rel_tol=1e-9,
  abs_tol=1e-12)`; a margin within tolerance of the bound is treated as *on* it. The
  tolerance sits far below any CV gain that could matter and far above double-rounding noise.
- **Files modified:** `scripts/submission_gate.py`
- **Commit:** `ba9acb5`

**2. [Rule 3 - Blocking] `submissions_log.fetch_submissions` is unreachable through the test's monkeypatch seam**
- **Found during:** Task 2
- **Issue:** The plan says to call `submissions_log.fetch_submissions(slug)`. But that
  function resolves `run_kaggle` from **`submissions_log`'s** module globals, while every
  test does `monkeypatch.setattr(check_submission, "run_kaggle", fake)`. The patch would not
  reach it: the real gateway would spawn a real `kaggle` CLI call during the unit suite —
  defeating the argv assertions that are the entire mechanical proof of `test_never_submits`,
  and breaking `test_validation_happy_path` (a failed live call → `rows=None` → BLOCK → 75
  instead of 0).
- **Fix:** `check_submission` implements its own thin `fetch_submissions(ws, slug)` that
  calls the **module-level** `run_kaggle` — exactly the seam `poll_kernel.py` already uses.
  All the substance (`charged_today`, `remaining_slots`, `COUNT_UNAVAILABLE`, `read_rows`,
  the status/score/date parses) is still **imported** from `submissions_log`, never
  re-derived; only the ~10-line gateway call is local. It additionally routes 127/124/403
  through the established `download_data` posture (missing CLI / timeout / `classify_gate`
  → 77), which the shared helper does not do.
- **Files modified:** `scripts/check_submission.py`
- **Commit:** `fbd68fe`

**3. [Rule 1 - Bug] The word "nominating" in the D-01 refusal message tripped the D-12 guard**
- **Found during:** Task 2 verification
- **Issue:** The plan's own acceptance criterion requires `grep -rin "final.selection\|nominat"`
  to return nothing (proving D-12 final-selection advisory is not built). My D-01 message
  described a code competition as "pushing a KERNEL and **nominating** a kernel VERSION",
  which matches `nominat` and failed the mechanical guard for a purely cosmetic reason.
- **Fix:** Rephrased to "pointing Kaggle at a kernel VERSION". The guard is honest again and
  the message is unchanged in meaning.
- **Files modified:** `scripts/check_submission.py`
- **Commit:** `fbd68fe`

### Scope Note (not a deviation — a cross-plan dependency)

The plan's `<verification>` block lists `tests/test_no_credential_leak.py` as green. Its 4
failures are **exclusively** `submit.py` / `fetch_lb.py` reported as `NOT IMPLEMENTED` —
both are **05-05's** files, which this parallel worktree must not create. 05-01's summary
assigns that suite to 05-05 (*"05-05 → test_submit.py, test_fetch_lb.py,
test_no_credential_leak.py"*). Both of *this* plan's scripts are in the suite's
`PHASE5_SCRIPTS` list and produce **zero** offenders in the leak scan. The suite goes green
when 05-05 merges.

## Verification

| Check | Result |
|-------|--------|
| `uv run pytest tests/test_gate_policy.py -q` | **7 passed** (was 7 RED) |
| `uv run pytest tests/test_check_submission.py -q` | **14 passed** (was 14 RED) |
| Full suite | **236 passed, 23 failed, 1 skipped** (was 215 / 44) |
| Net change | **+21 passed, −21 failed** — exactly this plan's RED nodes, **zero regressions** |
| Remaining failures | `test_submit` (9), `test_no_credential_leak` (4), `test_fetch_lb` (4) → **05-05**; `test_regen_strategy` (3), `test_lb_gap` (3) → **05-06**. None in this plan's scope. |
| `uvx ruff check scripts/` | **All checks passed** |
| Purity of `submission_gate.py` (`def main\|open(\|Path(\|run_kaggle\|subprocess`) | **empty** — no I/O of any kind |
| `import pandas\|import numpy` in both scripts | **empty** (stdlib `csv` only) |
| `input(` in both scripts | **empty** (never interactive) |
| `subprocess` in both scripts | **empty** (every Kaggle call via the gateway) |
| `final.selection\|nominat` in both scripts | **empty** (D-12 is not built) |
| `competitions submit` argv in both scripts | **empty** — the gate is FREE |
| Guessed reference filename (non-glob/comment lines) | **empty** — the manifest signal is reused |

`test_never_submits` is the load-bearing one: it drives **all four** code paths (clear /
validation-failed / unsupported-type / no-sample) and asserts from the captured argv that
`"submit"` never appears and that the only Kaggle call ever issued is
`("competitions", "submissions", ...)` — the read-only authoritative count.

## Known Stubs

None. Every function declared by this plan is fully implemented and exercised by a passing
test.

## Threat Flags

None — no new surface beyond the plan's register. All seven `mitigate` dispositions are
discharged:

- **T-05-04-01** (spending a slot) — no `submit` argv is constructed anywhere in either
  module; pinned mechanically by `test_never_submits` across every code path.
- **T-05-04-02** (garbage submission) — the four `csv` checks + the D-09 integer-column
  trap; exit 65 with the exact mismatch named.
- **T-05-04-03** (wrong reference file) — the chosen file is **printed**; the ladder falls
  back glob → `test.csv` → fail closed; the manifest signal is taken as a **basename only**
  (`Path(named).name`), so a `../../` value cannot escape `data/`.
- **T-05-04-04** (wrong competition type) — D-01 exits 69 *before* any gateway call
  (`calls == []` asserted).
- **T-05-04-05** (silent miscount) — the count comes from Kaggle's authoritative list on the
  UTC day boundary via `charged_today`; the `-1` sentinel → `remaining_slots` → `None` →
  `decide` **blocks**. Never guessed, and never mistaken for "plenty left".
- **T-05-04-06** (token echo) — the raw CLI buffer is matched, never printed; a 403 goes
  through `classify_gate` (77) and the buffer is quarantined via `dump_last_error`.
- **T-05-04-07** (path traversal) — `--exp-dir` is resolved then containment-checked against
  `ws/experiments/`; `--exp-id` must match `^exp-\d{3}$`.

Zero dependencies installed (T-05-04-SC `accept` holds).

## For the Next Plan

- **05-05** (`submit.py`): bind `run_kaggle` at **module level** and call it directly — the
  monkeypatch seam every test relies on (see Deviation 2). Re-use `submission_gate.decide`
  behind `--confirm` rather than re-deriving the policy; treat `remaining_slots() → None` as
  **BLOCK**, never as "plenty left".
- **05-07** (SKILL.md): the exit contract is live and exhaustively tested — `0` clear,
  `65` validation failed, `69` type unsupported, `75` gate blocked (**not an error** — the
  human may confirm and run `submit.py`), `77` UI gate, plus `124`/`127` passed through from
  the gateway.
- The override command `check_submission.py` prints is
  `python3 scripts/submit.py --workspace <ws> --exp-id <id> --confirm [--reason "..."]` —
  05-05's flag surface must match it (`--reason` OPTIONAL, D-07).

## Self-Check: PASSED

`scripts/submission_gate.py` and `scripts/check_submission.py` both exist on disk with the
claimed content; both commits (`ba9acb5`, `fbd68fe`) are present in git history.
