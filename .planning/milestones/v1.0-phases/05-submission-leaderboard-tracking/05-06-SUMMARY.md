---
phase: 05-submission-leaderboard-tracking
plan: 06
subsystem: strategy
tags: [score-02, cv-lb-gap, rank-inversion, divergence-alarm, derived-view, facts-renderer]

requires:
  - scripts/submissions_log.py (read_rows — the ONE submissions.jsonl schema, 05-03)
  - scripts/regen_strategy.py (the Phase 3 D-11/D-12 regen contract, extended not forked)
  - scripts/experiment_meta.py (LEDGER_ROW_KEYS — the join keys, already on the ledger row)
  - tests/test_lb_gap.py + tests/test_regen_strategy.py (the 05-01 RED nodes)
provides:
  - scripts/lb_gap.py (join_cv_lb, rank_inversions, alarm_state, alarm_body, to_pairs)
  - scripts/regen_strategy.py::_lb_gap_body (the third tooling-rendered facts section)
  - scripts/templates/strategy.md.tmpl (## CV-to-LB gap)
affects:
  - 05-05 (fetch_lb writes the SCORED rows this view reads)
  - 05-07 (SKILL.md wiring — the regen step now surfaces the gap + alarm)

tech-stack:
  added: []
  patterns:
    - "pure-function module (already-loaded row lists in, data out) — no filesystem, no network, no main()"
    - "DERIVED view over two JSONL files joined on exp_id — never a denormalized copy"
    - "facts/reasoning split: tooling renders numbers, the AI's fragment is spliced verbatim"
    - "scale-free alarm (rank inversion) instead of a tuned absolute threshold"

key-files:
  created:
    - scripts/lb_gap.py
  modified:
    - scripts/regen_strategy.py
    - scripts/templates/strategy.md.tmpl

decisions:
  - "rank_inversions returns (better_cv_id, better_lb_id, cv_delta, lb_delta) and checks BOTH orientations of each unordered pair, so the alarm names which experiment CV favoured and which one the leaderboard favoured"
  - "alarm_body is emitted UNCONDITIONALLY — including on a workspace with zero submissions — so the honest '(have 0)' line is always present and an empty gap section can never read as an all-clear"
  - "the PENDING/FAILED counts are rendered as bare counts, never as experiment ids: an unscored row must not appear in the facts block at all, or it would look like it carries a number"
  - "regen_strategy inserts SCRIPT_DIR on sys.path (the submissions_log posture) so its two new sibling imports resolve regardless of how the script is invoked"

metrics:
  duration: ~25min
  tasks: 2
  files-created: 1
  files-modified: 2
  completed: 2026-07-12
---

# Phase 5 Plan 06: CV→LB Gap & Rank-Inversion Alarm Summary

SCORE-02 is real: the framework now trends the CV→LB gap per submission from a derived
join of `submissions.jsonl` × `ledger.jsonl`, and raises a scale-free, direction-aware
rank-inversion alarm when CV ordering stops predicting leaderboard ordering — while CV
remains the decision metric everywhere.

## What Was Built

**Task 1 — `scripts/lb_gap.py` (`1801c1b`).** A pure, stdlib-only, import-side-effect-free
module with no `main()` and no I/O of any kind. Every function takes already-loaded row
lists, which is precisely what lets the whole contract be tested without a filesystem and
without touching Kaggle.

- `join_cv_lb(sub_rows, ledger_rows)` — the DERIVED D-11 view. Indexes the ledger by
  `exp_id` (SUCCESS rows with a numeric `cv_mean` only), then emits one row per SCORED
  submission carrying a non-None `public_score`, with `gap = lb_score - cv_mean`, sorted by
  `scored_at` ascending. That ordering *is* the trend. PENDING rows, FAILED rows, rows whose
  `public_score` is None (Kaggle's `""`), rows with a null `exp_id` (an out-of-band
  `fetch_lb --reconcile` back-fill) and rows absent from the ledger are all **excluded, never
  coerced**. Many submissions per experiment fall out for free — each scored submission is
  its own row, which a single per-experiment field could never represent.
- `rank_inversions(pairs, greater_is_better)` — the D-10 alarm. For every unordered pair it
  checks both orientations: an inversion exists when CV says B beats A while the leaderboard
  says A beats B. Returns `(better_cv_id, better_lb_id, cv_delta, lb_delta)` so the renderer
  can *name the numbers* rather than assert a conclusion.
- `alarm_state` / `alarm_body` — the honesty layer, plus the renderer `regen_strategy`
  splices (the signature 05-01 pinned).

**Task 2 — the extended regen contract (`afe2c5f`).** `_lb_gap_body(sub_rows, ledger_rows,
greater_is_better)` is a *third* facts renderer spliced into `_render` alongside
`_current_best_body` and `_tried_list_body`, under a new `## CV-to-LB gap` heading. The
Phase 3 D-11/D-12 contract was **extended, not forked**: the header, current-best, tried-list,
the verbatim `--reasoning-file` splice and the full atomic overwrite are all untouched.
`scripts/templates/strategy.md.tmpl` gains the matching section so a freshly-scaffolded
strategy has the same shape the regenerator produces.

Live render of a genuine inversion:

```
| exp | cv_mean | lb_score | gap (lb − cv) |
| --- | --- | --- | --- |
| exp-001 | 0.81 | 0.77 | -0.04 |
| exp-002 | 0.84 | 0.75 | -0.09 |

_1 submission(s) PENDING (not yet scored) — run `fetch_lb.py` to score them._

**Divergence alarm: RANK INVERSION across 2 scored submissions.** CV ordering has stopped
predicting leaderboard ordering, so CV is no longer a trustworthy decision metric...

- **exp-002** has the better CV (0.84 vs 0.81, Δcv 0.03) but the WORSE leaderboard score
  (0.75 vs 0.77, Δlb 0.02) — **exp-001** wins on the leaderboard.
```

## Key Decisions

**The alarm is emitted unconditionally — even with zero submissions.** The natural
implementation would render `None yet.` for an empty gap section and stop there. That reads
as an all-clear to a human, which is exactly the T-05-06-03 spoof the plan warns about. So
`alarm_body` always runs, and a workspace that has never submitted gets the explicit
`Divergence alarm: needs >=2 scored submissions (have 0).` line alongside `None yet.` Slightly
redundant prose, but there is no reading of it under which a user believes CV and LB have been
compared and found to agree. `test_lb_block_absent_when_no_submissions` pins this.

**PENDING/FAILED submissions are counted, never named.** `_lb_gap_body` renders
`1 submission(s) PENDING` rather than listing exp-003. An unscored experiment id appearing
anywhere inside a *facts* block invites the reader to assume a number exists for it. The
regen test asserts, specifically, that `exp-003` and `exp-004` appear nowhere before the
`## Reasoning` heading.

**Both orientations of each pair are checked.** `rank_inversions` does not assume the input is
sorted by CV. It tests `better(b_cv, a_cv) and better(a_lb, b_lb)` *and* its mirror, so the
returned tuple always correctly identifies which experiment CV favoured versus which one the
leaderboard favoured — which is what makes the rendered sentence trustworthy rather than a
coin-flip that happens to be right half the time.

**SCORE-02 discipline held.** No code path added here lets an LB score influence a selection.
`lb_gap` computes and reports; `_lb_gap_body` observes and warns. D-12 (a final-selection /
nomination advisory) was deliberately **not** built — `grep -rin "final.selection\|nominat"
scripts/` returns nothing across the entire scripts tree.

## Deviations from Plan

None — the plan executed exactly as written. Two elaborations the plan's own text demanded:
`to_pairs()` (a trivial shape adapter between `join_cv_lb`'s dicts and the alarm's tuples,
which the plan implies but does not name), and the `sys.path` insert in `regen_strategy.py`
mirroring the `submissions_log.py` posture so the two new sibling imports resolve under any
invocation.

## Verification

| Check | Result |
|-------|--------|
| `uv run pytest tests/test_lb_gap.py -q` | **3 passed** (test_gap_trend, test_rank_inversion_alarm, test_alarm_needs_two_points) |
| `uv run pytest tests/test_regen_strategy.py -q` | **14 passed** — the 3 new Phase-5 nodes AND all 11 pre-existing regen nodes |
| `uv run pytest -q` (full suite) | 221 passed, 38 failed, 1 skipped |
| The 38 failures | **all** in `test_check_submission` / `test_submit` / `test_gate_policy` / `test_fetch_lb` / `test_no_credential_leak` — `ModuleNotFoundError` for modules owned by the concurrent 05-04 and 05-05 agents. **Zero Phase 1–4 regressions; zero failures in my scope.** |
| `ruff check scripts/` | All checks passed |
| `grep -n "def main\|open(\|Path(\|run_kaggle\|subprocess" scripts/lb_gap.py` | **empty** — the module is pure |
| `grep -n "meta.json" scripts/lb_gap.py scripts/regen_strategy.py` | **empty** — D-11 immutability preserved |
| `grep -rin "final.selection\|nominat" scripts/` | **empty** — D-12 is not built |
| Live render (inversion + PENDING workspace) | table, pending count and alarm render correctly; no `.tmp` residue |

## Known Stubs

None. `fetch_lb.py` (referenced by the PENDING note's remediation text) is 05-05's deliverable
and lands in the same wave; the reference is a documented instruction to the user, not a code
dependency — `lb_gap` and `regen_strategy` import nothing from it.

## Threat Flags

None. This plan adds no network, filesystem-write or auth surface: `lb_gap.py` performs no I/O
at all, and `regen_strategy.py` gains only one additional *read* (via the existing fail-clear
`submissions_log.read_rows`). Zero dependencies installed. All five `mitigate` dispositions in
the plan's register are discharged: T-05-06-01 by the tooling-rendered facts block
(`test_lb_block_rendered`), T-05-06-02 by admitting only SCORED rows with a non-None
`public_score`, T-05-06-03 by the unconditional honesty line, T-05-06-04 by the derived join
(the experiment folder is never reopened), T-05-06-05 by `read_rows`' skip-and-warn on a
corrupt line and `[]` on a missing file.

## Self-Check: PASSED

- `scripts/lb_gap.py` — FOUND
- `scripts/regen_strategy.py` — FOUND (modified)
- `scripts/templates/strategy.md.tmpl` — FOUND (modified)
- Commit `1801c1b` (Task 1) — FOUND in git history
- Commit `afe2c5f` (Task 2) — FOUND in git history
