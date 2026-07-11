---
phase: 03-local-experiment-loop-ledger-strategy
fixed_at: 2026-07-11T00:00:00Z
verification_path: .planning/phases/03-local-experiment-loop-ledger-strategy/03-VERIFICATION.md
gaps_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
requirements: [MEM-01, MEM-02]
key-files:
  modified:
    - scripts/record_experiment.py
    - scripts/rebuild_ledger.py
    - tests/test_record_experiment.py
---

# Phase 03: Verification Gap Fix Report

**Fixed at:** 2026-07-11
**Source verification:** .planning/phases/03-local-experiment-loop-ledger-strategy/03-VERIFICATION.md
**Gaps in scope:** 1 (one root cause breaking Roadmap Criteria 4 & 5 / MEM-01 & MEM-02)
**Fixed:** 1 · **Skipped:** 0

**One-liner:** FAILED experiments now land in `control/ledger.jsonl` (null-cv_mean rows, never a
fabricated score) by having `record_experiment.py` delegate to the same full-derivation path
`rebuild_ledger.py` uses — so the incremental ledger is byte-identical to a full rebuild by
construction, and the never-repeat tried-list finally sees tried-and-failed ideas.

Verified with `uv run pytest -q -m "not live"`: **185 passed, 1 skipped, 8 deselected** (was
182 passed pre-fix; +3 new regression tests). The single skip is `test_run_cv` (skips cleanly
when sklearn is absent) — expected by design.

## Fixed Gap

### MEM-01 / MEM-02: FAILED experiments never reached the ledger in the standard loop

**Roadmap Criteria:** 4 (git-backed ledger that fully rebuilds from the per-experiment folders)
and 5 (AI reasons over history so it never re-proposes an already-tried idea).

**Files modified:** `scripts/record_experiment.py`, `scripts/rebuild_ledger.py`,
`tests/test_record_experiment.py`
**Commit:** `72e6583`

**Root cause:** `record_experiment.py` gated its ledger row write/dedupe/atomic-replace block
behind `if status == "SUCCESS":`. A FAILED experiment produced a complete canonical `meta.json`
(idea/hypothesis/provenance intact) but was never appended to `control/ledger.jsonl` during the
normal `scaffold -> run -> record -> regen` loop. Because `rebuild_ledger.py` derives a row for
*every* valid `meta.json` regardless of status (`experiment_meta.to_ledger_row` already supports a
null-`cv_mean` FAILED row), the incremental ledger and a full rebuild of the *same* folders
diverged (breaks Criterion 4). And since `regen_strategy.py`'s never-repeat tried-list digest reads
only `ledger.jsonl`, every tried-and-FAILED idea was invisible to the AI (breaks Criterion 5 /
MEM-02 — the exact failure mode it exists to prevent).

**Applied fix (delegate-to-rebuild, the invariant-by-construction option the verifier offered):**
- Extracted `rebuild_ledger.rebuild_ledger_file(ws)` — the single full-derivation + atomic
  (`tempfile` + `os.replace`) write path — now shared by `rebuild_ledger.main()` and the recorder.
- `record_experiment.py` calls `rebuild_ledger_file(ws)` after writing `meta.json`, on the SUCCESS
  and FAILED path alike. The ledger is thus a pure function of the meta folders on every record, so
  the incrementally-maintained `ledger.jsonl` is byte-identical to a full `rebuild_ledger.py` run —
  the two can never diverge. Dedupe-by-`exp_id` (WR-01) is now inherent (one folder → one row, so
  re-recording SUCCESS *or* FAILED yields exactly one row) and the write stays atomic.
- A FAILED row carries a null `cv_mean`/`cv_std` and empty fold fields — a recorded fact derived
  straight from the meta, **never** a fabricated number. The anti-lie fail-closed SUCCESS
  validation ladder (`_validate_result`, the `statistics.mean` recompute, the WR-03 range gate) is
  **untouched**.
- Removed the now-dead `os` and `to_ledger_row` imports from `record_experiment.py`; scripts stay
  stdlib-only (no ML imports).

**Regression tests added / updated:**
- (a) `test_failed_experiment_appends_single_null_score_row` — a FAILED experiment appends exactly
  one ledger row with `cv_mean is None` and honest provenance (idea/git_commit/seed present).
- (b) `test_re_recording_failed_is_idempotent_single_ledger_row` — re-recording that FAILED
  experiment stays at exactly one row.
- (c) `test_incremental_ledger_equals_full_rebuild_for_mixed_statuses` — after recording a
  SUCCESS + FAILED mix through the loop, `ledger.jsonl` is **byte-identical** to a fresh
  `rebuild_ledger.py` of the same folders.
- (d) the null-score guarantee is asserted across every FAILED-path test (the five prior tests that
  expected an *empty* ledger were updated to expect one FAILED/null-`cv_mean` row instead).

## Deviations from Plan

None beyond the sanctioned design choice. The verifier offered two fix options — (a) also write a
row on the FAILED path, or (b) delegate to the same full-derivation `rebuild_ledger.py` uses.
Option (b) was chosen because it makes "incremental ledger == full rebuild" true *by construction*
(not by coincidental append ordering), which is the canonical invariant the gap demanded. The prior
per-record incremental-append behavior of preserving an unparseable pre-existing ledger line
verbatim is necessarily superseded — that behavior is mathematically incompatible with the
"ledger is a pure function of the meta folders" invariant, and rebuild's own skip-and-warn posture
is the intended self-healing behavior.

## Self-Check: PASSED

- `scripts/record_experiment.py`, `scripts/rebuild_ledger.py`, `tests/test_record_experiment.py` —
  all present and modified (commit `72e6583`).
- Commit `72e6583` exists on the worktree branch.
- Full non-live suite green: 185 passed, 1 skipped (expected), 8 deselected.
