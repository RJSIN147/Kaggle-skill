---
phase: 03-local-experiment-loop-ledger-strategy
verified: 2026-07-11T17:00:00Z
status: passed
score: 5/5 roadmap success criteria verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/5
  gaps_closed:
    - "Every experiment lands in a git-backed ledger (meta.json canonical + derived ledger.jsonl) that fully rebuilds from the per-experiment folders. (Roadmap Success Criterion 4 / MEM-01)"
    - "The AI reasons over history so it does not re-propose an already-tried idea. (Roadmap Success Criterion 5 / MEM-02)"
  gaps_remaining: []
  regressions: []
human_verification: []
---

# Phase 3: Local Experiment Loop, Ledger & Strategy — Verification Report

**Phase Goal:** The full idea-to-run-to-verdict-to-ledger-to-strategy cycle works end-to-end on local compute alone — machine-verified scores, never a fabricated number, never a Kaggle submission spent. This is the core-value milestone.
**Verified:** 2026-07-11T17:00:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure (commits `72e6583`, `dc5483f`)

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | AI authors a fresh experiment.py per experiment from the scaffold using a backend-agnostic data-path resolver + result contract, runs it locally to produce a CV score + artifacts; fold-internal preprocessing enforced | ✓ VERIFIED | Unchanged since prior verification. `scaffold_experiment.py` mints `exp-NNN`, renders `experiment.py.tmpl` (`resolve_data_dir`, `run_cv`) with a resolved `registry_entry` literal — no skill import (kernel-portable). `run_cv` fits preprocessing on the TRAIN fold only. Re-confirmed CR-01 (injection-safe slug gate) live in this session: a malicious `competition_slug` (`"titanic; import os; os.system(...)"`) is rejected before any rendering, no `os.system` executed. |
| 2 | An experiment is captured as idea + hypothesis + machine-captured result + a written verdict in an immutable per-experiment folder | ✓ VERIFIED | Re-confirmed live: `scaffold_experiment.py` writes a `meta.json` stub with idea/hypothesis; `record_experiment.py` carries idea/hypothesis/created/exp_id forward on BOTH the SUCCESS and FAILED path (both reproduced this session). `VERDICT.md` created via `create_if_absent`. |
| 3 | Numeric fields are written only by tooling from a machine-checked result.json — a deliberately-throwing notebook is recorded as a FAILURE, not a success — and every ledger row carries provenance (run id, artifact hash, git commit, seed) | ✓ VERIFIED | `_validate_result`'s fail-closed ladder and anti-lie recompute are unchanged by the fix commit (verified via diff: only `rebuild_ledger.py`/`record_experiment.py`'s ledger-persistence block and tests changed — `_validate_result` byte-identical). Live-reproduced this session: an exp with no `result.json` and `--run-exit-code 1` records `status=FAILED`, `failure_reason=missing_result`. Both the SUCCESS row and the new FAILED row in the ledger carry non-empty `git_commit` and a numeric `seed`. |
| 4 | Every experiment lands in a git-backed ledger (meta.json canonical + derived ledger.jsonl) that fully rebuilds from the per-experiment folders | ✓ VERIFIED (gap closed) | Live-reproduced end-to-end in an independent scratch workspace: recorded one SUCCESS (exp-001) and one FAILED (exp-002, `--run-exit-code 1`) experiment through the normal `record_experiment.py` loop. `control/ledger.jsonl` ends with 2 rows — the FAILED row present with `cv_mean: null`, `cv_std: null`, real `git_commit`/`seed`/`idea`. Copied the incremental ledger bytes, deleted the file, ran `rebuild_ledger.py --workspace .` fresh, and diffed: **byte-identical** (`diff` reported no difference). Re-recording the FAILED experiment a second time left the ledger at exactly 2 rows (idempotent) with no `.tmp` residue in `control/`. |
| 5 | The strategy doc (current best, hypothesis queue, next action) is regenerated from the ledger each cycle — never hand-edited — and the AI reasons over history so it does not re-propose an already-tried idea | ✓ VERIFIED (gap closed) | Live-reproduced: after recording the SUCCESS + FAILED mix above, ran `regen_strategy.py --reasoning-file ...`. The rendered `strategy.md`'s "Tried-list digest" now lists BOTH rows: `- exp-001 | ... | SUCCESS | 0.81±0.008 | [verdict](...)` and `- exp-002 | XGBoost on target-encoded cats | FAILED | — | [verdict](...)` — the previously-invisible FAILED idea is now visible to the never-repeat check. "Current best" correctly still picks only the SUCCESS row (FAILED rows are excluded from current-best, per unchanged `_current_best_body` logic and `test_failed_rows_never_win_current_best`). `regen_strategy.py` itself was not touched by the fix commit (confirmed via `git show --stat 72e6583`) — the atomic full-overwrite/never-hand-edited mechanic verified previously is unaffected. |

**Score:** 5/5 roadmap success criteria verified (2 gaps closed, 0 regressions).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| EXP-01 | 03-03 | Experiment = idea + hypothesis + generated script + machine-captured result + verdict | ✓ SATISFIED | Unchanged; re-confirmed live this session (stub carry-forward on both SUCCESS/FAILED paths). |
| EXP-02 | 03-03 | AI authors a fresh notebook/script per experiment from a template scaffold, backend-agnostic data-path + result contract | ✓ SATISFIED | Unchanged; `experiment.py.tmpl` untouched by the fix commit. |
| EXP-03 | 03-04 | User can run an experiment locally, producing a CV score and artifacts | ✓ SATISFIED | Unchanged; `run_local.py` untouched by the fix commit. |
| EXP-04 | 03-01, 03-04 | Numeric results written by tooling from a machine-checked result.json, never hand-written by the AI; every ledger row carries provenance | ✓ SATISFIED | `_validate_result` byte-identical to prior verification (confirmed via diff). Every ledger row observed this session (SUCCESS and FAILED alike) carries `git_commit` + `seed`. |
| MEM-01 | 03-02, 03-04 | Every experiment is logged to a structured, git-backed ledger (meta.json canonical + derived ledger.jsonl index) | ✓ SATISFIED (was BLOCKED) | Gap closed: FAILED experiments now reach `control/ledger.jsonl` (null-score row) on the standard loop; incremental ledger proven byte-identical to a fresh `rebuild_ledger.py` rebuild of the same folders in this session's live reproduction. |
| MEM-02 | 03-05 | Experiment history lets the AI reason over what's been tried so it never re-proposes an already-tried idea | ✓ SATISFIED (was BLOCKED) | Gap closed: the tried-list digest now renders the FAILED idea alongside the SUCCESS idea, confirmed live. |
| MEM-03 | 03-05 | A living strategy doc (current best, hypothesis queue, next action) is regenerated from the ledger each cycle, never hand-edited | ✓ SATISFIED | Unchanged; `regen_strategy.py` not modified by the fix commit; atomic full-overwrite mechanic previously verified and unaffected. |

All 7 requirement IDs assigned to Phase 3 in REQUIREMENTS.md (EXP-01, EXP-02, EXP-03, EXP-04, MEM-01, MEM-02, MEM-03) are now SATISFIED. No orphaned requirements.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `scripts/record_experiment.py` | fail-closed validation ladder -> meta.json + ledger row + provenance, on BOTH SUCCESS and FAILED paths | ✓ VERIFIED | Ledger persistence now unconditional: after writing `meta.json`, calls `rebuild_ledger.rebuild_ledger_file(ws)` regardless of status. Diff of commit `72e6583` shows the prior `if status == "SUCCESS":`-gated append block fully replaced. `_validate_result` (the anti-lie ladder) untouched. |
| `scripts/rebuild_ledger.py` | glob meta.json -> sorted -> atomic rebuild, now exposing a reusable `rebuild_ledger_file(ws)` | ✓ VERIFIED | `rebuild_ledger_file(ws)` extracted as the single full-derivation + atomic-write function; `main()` now delegates to it. Confirmed importable from `record_experiment.py` (`from rebuild_ledger import rebuild_ledger_file`) and confirmed it drives both the on-demand CLI and the incremental recorder in this session's live run. |
| `scripts/experiment_meta.py` | to_ledger_row + validate_meta, single-source schema | ✓ VERIFIED | Unchanged; `to_ledger_row` already supported a null-`cv_mean` FAILED row (docstring: "A FAILED meta with a null cv_mean still produces a valid row") — now this path is actually reached in the standard loop. |
| `scripts/regen_strategy.py` | facts-from-ledger + reasoning splice -> atomic overwrite | ✓ VERIFIED | Untouched by the fix commit; its output is now complete because its ledger input is complete (confirmed live — FAILED row renders in the tried-list). |
| `tests/test_record_experiment.py` | regression coverage for the fix | ✓ VERIFIED | 3 new tests present and passing: `test_failed_experiment_appends_single_null_score_row`, `test_re_recording_failed_is_idempotent_single_ledger_row`, `test_incremental_ledger_equals_full_rebuild_for_mixed_statuses`. Independently reproduced all three assertions live in a fresh scratch workspace (not just trusting `pytest` green). |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `record_experiment.py` | `control/ledger.jsonl` | `rebuild_ledger_file(ws)` call on BOTH SUCCESS and FAILED paths | ✓ WIRED | Was PARTIAL (SUCCESS-only) in the prior verification; now unconditional. Live-confirmed: FAILED row present with null score, correct provenance. |
| `record_experiment.py` | `rebuild_ledger.py` | `from rebuild_ledger import rebuild_ledger_file` | ✓ WIRED | Import confirmed present; no `os`/`to_ledger_row` dead imports left in `record_experiment.py` (removed per the fix). |
| `regen_strategy.py` | `control/ledger.jsonl` | read rows, compute current-best + tried-list | ✓ WIRED | Now reads a COMPLETE ledger; tried-list digest live-confirmed to include the FAILED row while current-best correctly excludes it. |
| All Phase-3 links verified prior (set_metric↔registry, scaffold↔state.json, scaffold↔metric_registry, experiment.py.tmpl↔result.json, record_experiment↔meta stub, record_experiment↔git provenance, regen_strategy↔strategy.md, SKILL.md↔loop scripts) | — | — | ✓ WIRED (no regression) | None of these files were touched by the fix commit (`git show --stat 72e6583` lists only `scripts/rebuild_ledger.py`, `scripts/record_experiment.py`, `tests/test_record_experiment.py`); spot-checked CR-01 (injection-blocked slug) live this session, still holds. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `control/ledger.jsonl` (via `record_experiment.py`, standard loop) | ledger rows | `rebuild_ledger_file(ws)` → `to_ledger_row(meta)` for every valid `meta.json`, SUCCESS and FAILED alike | Yes — real data for both statuses; FAILED rows carry an honest null, never a fabricated number | ✓ FLOWING (was HOLLOW for FAILED experiments) |
| `control/ledger.jsonl` (via `rebuild_ledger.py`) | ledger rows | `to_ledger_row(meta)` for every validated meta.json | Yes, all statuses | ✓ FLOWING (unchanged) |
| `strategy.md` tried-list digest | `rows` from `control/ledger.jsonl` | `regen_strategy._read_ledger` | Yes — now sourced from the complete standard-loop ledger | ✓ FLOWING (was HOLLOW, inherited upstream gap) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full offline test suite | `uv run pytest -q -m "not live"` | `185 passed, 1 skipped, 8 deselected` (matches SUMMARY claim; skip is `test_run_cv`, expected — no sklearn in dev env) | ✓ PASS |
| Independent live repro: record FAILED experiment through the normal loop | `python3 scripts/record_experiment.py --workspace <scratch> --exp-dir experiments/exp-002 --run-exit-code 1` | ledger gains exactly 1 row, `status=FAILED`, `cv_mean=null`, `cv_std=null`, real `git_commit`/`seed`/`idea` | ✓ PASS |
| Independent live repro: incremental ledger == full rebuild for SUCCESS+FAILED mix | recorded exp-001 (SUCCESS) + exp-002 (FAILED), copied ledger bytes, deleted file, ran `rebuild_ledger.py --workspace .`, diffed | `diff` reported zero differences — byte-identical | ✓ PASS |
| Independent live repro: re-recording the same FAILED experiment is idempotent | ran `record_experiment.py` on exp-002 a second time | ledger stayed at 2 rows total (no duplicate), no `.tmp` residue in `control/` | ✓ PASS |
| Independent live repro: tried-list digest surfaces the FAILED idea | `regen_strategy.py --reasoning-file ...` after the SUCCESS+FAILED mix | `strategy.md`'s "Tried-list digest" lists both `exp-001 | ... | SUCCESS | 0.81±0.008 | ...` and `exp-002 | XGBoost on target-encoded cats | FAILED | — | ...`; "Current best" correctly shows only exp-001 | ✓ PASS |
| Regression: CR-01 injection-blocked slug | `scaffold_experiment.py` with `competition_slug` containing `"; import os; os.system('touch /tmp/pwned')"` | `cannot scaffold: competition_slug ... is not a valid Kaggle slug` (exit 1); `/tmp/pwned` never created | ✓ PASS (no regression) |
| Regression: no debt markers in modified files | `grep -n -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER"` on `record_experiment.py`, `rebuild_ledger.py`, `tests/test_record_experiment.py` | none found | ✓ PASS |

### Anti-Patterns Found

None blocking. No new debt markers (`TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`) introduced by the fix commit.

IN-01 (`--exp-dir` not constrained to the workspace — path traversal) and IN-02 (recorded `artifacts`/`oof_path` trusted verbatim) remain unfixed, exactly as scoped in `03-REVIEW-FIX.md` (Critical + Warning only; both were explicitly deferred as low-risk INFO items). Re-confirmed both are still present in the current `record_experiment.py` (`exp_dir = (ws / exp_rel).resolve()` has no containment check against `ws`; `meta["artifacts"] = valid_result.get("artifacts", [])` copies the result-reported paths verbatim). Both remain low-risk in this loop (the path is SKILL/loop-supplied, not externally attacker-controlled) and do not block phase goal achievement — noted for awareness only, not gaps.

### Human Verification Required

None. All truths are mechanically verifiable and were re-verified by direct code diffing, unit-test execution, and an independent live end-to-end reproduction in a scratch workspace (separate from the executor's own test fixtures).

### Gaps Summary

Both gaps from the prior verification are closed. The root-cause fix — `record_experiment.py` now delegates to `rebuild_ledger.rebuild_ledger_file(ws)` (a shared full-derivation + atomic-write path) on both the SUCCESS and FAILED branches, instead of only appending on SUCCESS — makes the incremental ledger a pure function of the `experiments/*/meta.json` folders by construction. This was independently reproduced end-to-end in a fresh scratch workspace (separate from the phase's own test suite): a FAILED experiment now appends a single null-score row with honest provenance; a full `rebuild_ledger.py` rebuild of the same folders after a SUCCESS+FAILED mix is byte-identical to the incrementally-built ledger; re-recording a FAILED experiment is idempotent; and `regen_strategy.py`'s tried-list digest — the sole never-repeat mechanism — now surfaces the FAILED idea while still correctly excluding it from "current best."

No regressions were found in previously-verified behavior: the anti-lie `_validate_result` ladder (fail-closed schema/type/finite/anti-lie-recompute/metric-match/range-gate chain), the CR-01 injection-safe slug gate, the WR-03 bounded-range custom-metric fix, and atomic-write discipline are all unchanged by the fix commit (confirmed via `git show --stat 72e6583`, which touches only `scripts/rebuild_ledger.py`, `scripts/record_experiment.py`, and `tests/test_record_experiment.py`) and were spot-checked live. `regen_strategy.py` itself was not modified — its previously-verified atomic full-overwrite/never-hand-edited mechanic is unaffected. All 7 requirement IDs assigned to Phase 3 (EXP-01..04, MEM-01..03) are now SATISFIED. IN-01 and IN-02 remain intentionally unfixed, low-risk INFO items per the phase's explicit scope decision — recorded here for awareness, not blocking.

All 5 roadmap success criteria now hold. The phase goal — a full idea-to-run-to-verdict-to-ledger-to-strategy cycle that works end-to-end on local compute alone, with machine-verified scores, never a fabricated number, never a Kaggle submission spent — is achieved.

---

_Verified: 2026-07-11T17:00:00Z_
_Verifier: Claude (gsd-verifier)_
