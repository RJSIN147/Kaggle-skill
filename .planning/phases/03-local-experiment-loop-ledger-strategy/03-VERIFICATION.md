---
phase: 03-local-experiment-loop-ledger-strategy
verified: 2026-07-11T15:30:00Z
status: gaps_found
score: 3/5 roadmap success criteria verified
overrides_applied: 0
gaps:
  - truth: "Every experiment lands in a git-backed ledger (meta.json canonical + derived ledger.jsonl) that fully rebuilds from the per-experiment folders. (Roadmap Success Criterion 4 / MEM-01)"
    status: failed
    reason: >
      record_experiment.py's ledger append/dedupe block is gated behind `if status == "SUCCESS":`
      (record_experiment.py lines ~352-382). A FAILED experiment gets a fully-formed meta.json
      (idea/hypothesis/provenance all present) but is NEVER appended to control/ledger.jsonl
      during the standard scaffold -> run -> record -> regen loop that SKILL.md sequences.
      rebuild_ledger.py, by contrast, derives a row for EVERY meta.json that passes
      validate_meta regardless of status (experiment_meta.to_ledger_row's own docstring says
      "A FAILED meta with a null cv_mean still produces a valid row"), so the incremental
      ledger and a full rebuild of the SAME folder set produce DIFFERENT ledger.jsonl content.
      SKILL.md documents rebuild_ledger.py only as an on-drift repair tool ("If the ledger ever
      drifts, rebuild_ledger.py rebuilds it..."), not a step in the sequenced loop, so under
      normal use the divergence is never corrected. Empirically reproduced end-to-end (see
      Behavioral Spot-Checks): after recording a FAILED experiment, `control/ledger.jsonl` is
      empty; running `rebuild_ledger.py` immediately afterward, with no other change, adds a
      row for that same FAILED experiment — proving "ledger.jsonl fully rebuilds from the
      per-experiment folders" does not hold for the ledger produced by the ordinary loop.
    artifacts:
      - path: "scripts/record_experiment.py"
        issue: "Lines ~349-382: ledger row write/dedupe/atomic-replace logic only runs `if status == \"SUCCESS\":`; FAILED experiments never reach control/ledger.jsonl."
    missing:
      - "record_experiment.py must write/update a ledger.jsonl row for FAILED experiments too (experiment_meta.to_ledger_row already supports a null cv_mean row), or must invoke the same full-derivation rebuild_ledger.py uses on every record so the incremental and rebuilt ledgers can never diverge."
  - truth: "The AI reasons over history so it does not re-propose an already-tried idea. (Roadmap Success Criterion 5 / MEM-02)"
    status: failed
    reason: >
      This is the direct downstream consequence of the ledger gap above, not a separate defect
      in regen_strategy.py. regen_strategy.py's tried-list digest — the ONLY mechanism SKILL.md
      instructs the AI to consult before scaffolding a new idea ("read control/ledger.jsonl
      ... and the tried-list digest in strategy.md") — is derived exclusively from
      control/ledger.jsonl rows (_tried_list_body in regen_strategy.py). Because FAILED
      experiments never reach ledger.jsonl under normal operation, a previously-tried-and-FAILED
      idea is invisible to the never-repeat check — precisely the case MEM-02 exists to prevent
      (an AI is far more likely to accidentally re-propose an idea that already FAILED than one
      that already succeeded, since a success ends the search). regen_strategy.py's own renderer
      is not at fault: it correctly renders FAILED rows in the tried-list when they are present
      in the ledger (proven by tests/test_regen_strategy.py::test_failed_rows_never_win_current_best,
      which seeds a FAILED row directly and confirms it is excluded only from "current best", not
      from the tried list). Empirically reproduced end-to-end: after scaffolding + recording a
      FAILED "baseline LGBM" idea (with hypothesis "GBDT beats constant baseline"), regenerating
      strategy.md renders "## Tried-list digest\n\n_No experiments recorded yet._" — the idea is
      completely absent from the AI's history-reasoning surface.
    artifacts:
      - path: "scripts/record_experiment.py"
        issue: "Same root cause as the ledger gap above."
      - path: "scripts/regen_strategy.py"
        issue: "_tried_list_body (correct in isolation) inherits the blind spot because it only ever sees rows record_experiment.py chose to append."
    missing:
      - "Same fix as the ledger gap: once FAILED experiments land in control/ledger.jsonl, the tried-list digest and the never-repeat check will automatically cover full experiment history."
human_verification: []
---

# Phase 3: Local Experiment Loop, Ledger & Strategy — Verification Report

**Phase Goal:** The full idea-to-run-to-verdict-to-ledger-to-strategy cycle works end-to-end on local compute alone — machine-verified scores, never a fabricated number, never a Kaggle submission spent. This is the core-value milestone.
**Verified:** 2026-07-11T15:30:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | AI authors a fresh experiment.py per experiment from the scaffold using a backend-agnostic data-path resolver + result contract, runs it locally to produce a CV score + artifacts; fold-internal preprocessing enforced | ✓ VERIFIED | `scripts/scaffold_experiment.py` mints `exp-NNN`, renders `experiment.py.tmpl` (`resolve_data_dir`, `run_cv`) with a resolved `registry_entry` literal — no skill import (kernel-portable). `run_cv` does `pp.fit_transform(Xtr, ytr)` on the TRAIN fold only, `pp.transform(Xva)` on VAL (experiment.py.tmpl:127-130) — leakage-safe by construction. Empirically confirmed a scaffold+SUCCESS-record cycle end-to-end (see spot-checks). `tests/test_resolve_data_dir.py`, `tests/test_run_cv.py` (skips cleanly without sklearn), `tests/test_scaffold_experiment.py` all pass. |
| 2 | An experiment is captured as idea + hypothesis + machine-captured result + a written verdict in an immutable per-experiment folder | ✓ VERIFIED | `scaffold_experiment.py` writes a `meta.json` stub with idea/hypothesis; `record_experiment.py` carries idea/hypothesis/created/exp_id forward on BOTH SUCCESS and FAILED paths (empirically confirmed for both). `VERDICT.md` is created via `create_if_absent` (never clobbers AI-authored prose on re-record). `tests/test_record_experiment.py` covers both paths. |
| 3 | Numeric fields are written only by tooling from a machine-checked result.json — a deliberately-throwing notebook is recorded as a FAILURE, not a success — and every ledger row carries provenance (run id, artifact hash, git commit, seed) | ✓ VERIFIED | `record_experiment._validate_result` implements the full 7-step fail-closed ladder (schema/types → finite → anti-lie `statistics.mean` recompute → metric-match incl. the WR-03 fix → range gate). Empirically confirmed: a throwing run (`--run-exit-code 1`, no result.json) → `status="FAILED"`, `failure_reason="missing_result"`, zero success rows. Every row that DOES land in `ledger.jsonl` carries `git_commit`+`seed` sourced from `meta["provenance"]` (`experiment_meta.to_ledger_row`), and `validate_meta` requires all four provenance keys before any row is derived. `run_local.py` captures only `proc.returncode`, never stdout, confirmed by source read and `tests/test_run_local.py`. |
| 4 | Every experiment lands in a git-backed ledger (meta.json canonical + derived ledger.jsonl) that fully rebuilds from the per-experiment folders | ✗ FAILED | See gaps. `record_experiment.py` only appends to `ledger.jsonl` on SUCCESS; FAILED experiments get a `meta.json` but never a ledger row in the standard loop, so a rebuild of the same folders produces DIFFERENT content than the incrementally-built ledger — empirically reproduced. |
| 5 | The strategy doc (current best, hypothesis queue, next action) is regenerated from the ledger each cycle — never hand-edited — and the AI reasons over history so it does not re-propose an already-tried idea | ✗ FAILED (partially) | The mechanical half is VERIFIED: `regen_strategy.py` fully overwrites `strategy.md` atomically each cycle (tooling FACTS + AI `--reasoning-file` REASONING, verbatim splice); a hand edit is clobbered on the next regen (`tests/test_regen_strategy.py`, empirically confirmed). The reasoning-surface half FAILS: the tried-list digest — the sole never-repeat mechanism — is blind to FAILED experiments (same root cause as truth 4), so the AI can silently re-propose an idea that already failed. |

**Score:** 3/5 roadmap success criteria verified (2 FAILED, sharing one root cause).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| EXP-01 | 03-03 | Experiment = idea + hypothesis + generated script + machine-captured result + verdict | ✓ SATISFIED | `scaffold_experiment.py` mints the folder; `record_experiment.py` carries idea/hypothesis forward on both paths; `VERDICT.md` stub created. |
| EXP-02 | 03-03 | AI authors a fresh notebook/script per experiment from a template scaffold, backend-agnostic data-path + result contract | ✓ SATISFIED | `experiment.py.tmpl` ships `resolve_data_dir()` + `run_cv()`; the rendered `experiment.py` imports no skill code (kernel-portable). |
| EXP-03 | 03-04 | User can run an experiment locally, producing a CV score and artifacts | ✓ SATISFIED | `run_local.py` shells `uv run --no-sync`, exit-code-only capture; `run_cv` emits `result.json` + `artifacts/oof.npy`. |
| EXP-04 | 03-01, 03-04 | Numeric results written by tooling from a machine-checked result.json, never hand-written by the AI; every ledger row carries provenance | ✓ SATISFIED | `record_experiment.py`'s fail-closed ladder + anti-lie recompute is genuinely strong (confirmed by code read + tests + manual reproduction); every row that lands in the ledger does carry full provenance. (Note: this requirement is about the INTEGRITY of rows that exist, not about completeness of which experiments get a row — that gap is tracked under MEM-01.) |
| MEM-01 | 03-02, 03-04 | Every experiment is logged to a structured, git-backed ledger (meta.json canonical + derived ledger.jsonl index) | ✗ BLOCKED | See gaps — FAILED experiments never reach `ledger.jsonl` in the standard loop. `meta.json` (canonical) IS written for every experiment; the derived index is incomplete. |
| MEM-02 | 03-05 | Experiment history lets the AI reason over what's been tried so it never re-proposes an already-tried idea | ✗ BLOCKED | See gaps — the tried-list digest the never-repeat check relies on is blind to FAILED ideas. |
| MEM-03 | 03-05 | A living strategy doc (current best, hypothesis queue, next action) is regenerated from the ledger each cycle, never hand-edited | ✓ SATISFIED | The overwrite/atomicity/never-hand-edited mechanic itself is correct and tested; its content is only as complete as the ledger it reads (tracked under MEM-01's gap, not a defect of `regen_strategy.py` itself). |

No orphaned requirements — all 7 IDs assigned to Phase 3 in REQUIREMENTS.md are claimed by a plan's frontmatter.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `scripts/metric_registry.py` | stdlib metric source of truth (REGISTRY + SUPPORTED) | ✓ VERIFIED | 15-metric REGISTRY incl. `custom` escape hatch; stdlib-only (`from math import inf`); no sklearn/pandas/numpy import. |
| `scripts/set_metric.py` | D-08 setter, direction looked up not free-typed | ✓ VERIFIED | Reserved exit 78 (`LIMIT_NEEDS_USER`) for uncaptured metric; `custom` requires explicit `--greater-is-better`; empirically confirmed writing `config.json.metric`. |
| `scripts/templates/config.json.tmpl` | reserved-null `"metric"` key | ✓ VERIFIED | Present. |
| `scripts/templates/pyproject.toml.tmpl` | ML floors (lightgbm/xgboost/catboost/numpy) | ✓ VERIFIED | All four floors present, no newest-major pins. |
| `scripts/experiment_meta.py` | to_ledger_row + validate_meta, single-source schema | ✓ VERIFIED | Pure stdlib; `to_ledger_row` sources `git_commit`/`seed` from `meta["provenance"]`; docstring explicitly documents FAILED-row support. |
| `scripts/rebuild_ledger.py` | glob meta.json -> sorted -> atomic rebuild | ✓ VERIFIED | Atomic (`tempfile`+`os.replace`); corrupt/invalid metas skip-and-warn; empirically confirmed it derives rows for BOTH SUCCESS and FAILED metas — this is the artifact that exposes the record_experiment.py gap. |
| `scripts/templates/meta.json.tmpl`, `VERDICT.md.tmpl` | canonical meta skeleton + verdict prose skeleton | ✓ VERIFIED | Both present, render cleanly, meta.json.tmpl carries the full provenance shape. |
| `scripts/templates/experiment.py.tmpl` | resolve_data_dir + run_cv harness + LightGBM starter + result.json emit | ✓ VERIFIED | Verbatim leakage-safe fold loop; CR-01-fixed literal rendering (`$slug_literal` etc., no raw string interpolation). |
| `scripts/scaffold_experiment.py` | mint exp-NNN, render template, meta stub, advance cursor | ✓ VERIFIED | Empirically confirmed idempotent minting, cursor advance, charset gates (slug/cv_scheme) block malicious values before rendering. |
| `scripts/run_local.py` | uv run --no-sync, exit-code capture, env-absent degrade | ✓ VERIFIED | `--no-sync` present, no `pip install`; stdout never parsed for a score. |
| `scripts/record_experiment.py` | fail-closed validation ladder -> meta.json + ledger row + provenance | ⚠️ PARTIAL | Validation ladder, anti-lie recompute, and WR-03 range-gate fix are all correct. Ledger-row persistence is INCOMPLETE — SUCCESS-only (see gaps). |
| `scripts/regen_strategy.py` | facts-from-ledger + reasoning splice -> atomic overwrite | ✓ VERIFIED (mechanically) | Atomic full overwrite confirmed (hand-edit clobbered); FACTS/REASONING split correct. Its OUTPUT is incomplete only because its ledger input is incomplete (see gaps). |
| `SKILL.md` | Local experiment loop section + Scripts rows + never-repeat prompt | ✓ VERIFIED | All five loop entry points documented in sequence; never-repeat instruction appears before the scaffold step; within the ~520-line progressive-disclosure budget. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `set_metric.py` | `metric_registry.py` | `from metric_registry import REGISTRY, SUPPORTED` | ✓ WIRED | Confirmed by import + empirical run. |
| `set_metric.py` | `control/config.json` | `set_config_field` | ✓ WIRED | Empirically confirmed metric written. |
| `rebuild_ledger.py` | `experiment_meta.py` | `to_ledger_row`/`validate_meta` | ✓ WIRED | Confirmed by import + empirical rebuild producing correct rows for both statuses. |
| `rebuild_ledger.py` | `control/ledger.jsonl` | atomic tempfile + `os.replace` | ✓ WIRED | Confirmed — no `.tmp` residue, byte-identical delete-then-rebuild (test + manual). |
| `scaffold_experiment.py` | `control/state.json` | read-increment-write `next_exp_id` | ✓ WIRED | Empirically confirmed cursor advance 1→2. |
| `scaffold_experiment.py` | `metric_registry.py` | resolved `registry_entry` literal render | ✓ WIRED | Confirmed rendered `experiment.py` contains the correct `sklearn_callable` for the configured metric and imports no skill code. |
| `experiment.py.tmpl` (`run_cv`) | `experiments/exp-NNN/result.json` | `write_text(json.dumps(result))` | ✓ WIRED | Confirmed via code read + template contract; `run_cv` unit-tested (skips without sklearn — by design, per phase note). |
| `record_experiment.py` | scaffold `meta.json` stub | stub carry-forward | ✓ WIRED | Empirically confirmed idea/hypothesis/created/exp_id preserved on both SUCCESS and FAILED. |
| `record_experiment.py` | `experiments/exp-NNN/result.json` | fail-closed validate + recompute | ✓ WIRED | Empirically confirmed: throwing run → FAILED; valid result → SUCCESS with correct numbers. |
| `record_experiment.py` | `control/ledger.jsonl` | append `to_ledger_row` (SUCCESS only) | ⚠️ PARTIAL | Wired for SUCCESS; NOT wired for FAILED — this is the gap. |
| `record_experiment.py` | git provenance | `hashlib.sha256` + `git rev-parse HEAD` + explicit-path stage | ✓ WIRED | Confirmed `git_commit`, `artifact_hash`, `git_dirty` all populated correctly; no `git add -A`. |
| `regen_strategy.py` | `control/ledger.jsonl` | read rows, compute current-best by direction | ✓ WIRED | Confirmed reading + rendering correct given ledger content (content itself is what's incomplete). |
| `regen_strategy.py` | `strategy.md` | atomic tempfile + `os.replace` full overwrite | ✓ WIRED | Confirmed — hand-edited `strategy.md` fully replaced on next regen. |
| `SKILL.md` | all five loop scripts | documented sequencing + never-repeat prompt | ✓ WIRED | Confirmed in SKILL.md prose; script rows present in the Scripts table. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `control/ledger.jsonl` (via `record_experiment.py`, standard loop) | ledger rows | `to_ledger_row(meta)` on SUCCESS only | Partial — real data for SUCCESS rows, but a whole status class (FAILED) never flows through at all | ⚠️ HOLLOW for FAILED experiments |
| `control/ledger.jsonl` (via `rebuild_ledger.py`) | ledger rows | `to_ledger_row(meta)` for every validated meta.json | Yes, all statuses | ✓ FLOWING |
| `strategy.md` tried-list digest | `rows` from `control/ledger.jsonl` | `regen_strategy._read_ledger` | Real data, but sourced from the incomplete standard-loop ledger | ⚠️ HOLLOW (inherits upstream gap) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full offline test suite | `uv run pytest -q -m "not live"` | `182 passed, 1 skipped, 8 deselected` | ✓ PASS (matches SUMMARY claim) |
| CR-01 fix: malicious slug blocked before rendering | `scaffold_experiment.py --idea ... --hypothesis ...` with `competition_slug` containing `"; import os; os.system(...)` | `cannot scaffold: competition_slug ... is not a valid Kaggle slug` (exit 1) | ✓ PASS |
| End-to-end: set_metric → scaffold → record FAILED (throwing run) | see transcript below | `meta.json` status=FAILED, idea/hypothesis preserved, `control/ledger.jsonl` stays empty | ✓ PASS (confirms criterion 3) / reveals gap for criterion 4/5 |
| End-to-end: rebuild_ledger immediately after the FAILED record | `rebuild_ledger.py --workspace .` | ledger.jsonl gains a FAILED row for the same experiment with NO other change | ✗ Reveals the gap — proves incremental ≠ full rebuild |
| End-to-end: scaffold → record SUCCESS (valid result.json) | see transcript below | `meta.json` status=SUCCESS, ledger.jsonl gains the correct SUCCESS row | ✓ PASS |
| End-to-end: regen_strategy after only the FAILED experiment is recorded | `regen_strategy.py --reasoning-file ...` | Tried-list digest renders `_No experiments recorded yet._` despite a real recorded FAILED idea existing | ✗ Reveals the gap — proves MEM-02 broken in the standard loop |
| WR-03 fix correctness (human-eyeball request from 03-REVIEW-FIX.md) | code trace + `test_custom_metric_cannot_bypass_bounded_range_gate` | `allow_custom = metric_name == "custom"`; a result self-reporting `metric="custom"` is rejected (`schema_invalid`) unless config itself declared `custom` | ✓ CONFIRMED CORRECT — no further concern |

### Anti-Patterns Found

None blocking. `SKILL.md:206` and `scripts/templates/strategy.md.tmpl:13` contain the substring `_TODO`/`TODO`, but both are intentional placeholder prose (the strategy stub's first-idea placeholder, and a reference to a *different*, pre-existing `_TODO` stub concept from Phase 2's competition.md) — not unresolved debt markers in this phase's own code. No `FIXME`/`XXX`/`HACK`/`PLACEHOLDER` found in any file this phase modified.

IN-01 (`--exp-dir` not constrained to the workspace — path traversal) and IN-02 (recorded `artifacts`/`oof_path` trusted verbatim) remain unfixed per `03-REVIEW-FIX.md`'s explicit scope decision (Critical + Warning only). Both are low-risk in this loop (the path is SKILL/loop-supplied, not externally attacker-controlled) and do not block phase goal achievement — noted for awareness only, not gaps.

### Human Verification Required

None. All truths are mechanically verifiable and were verified (or falsified) by direct code reading, unit-test execution, and live end-to-end script runs in a scratch workspace.

### Gaps Summary

The phase delivers a genuinely strong anti-lie integrity spine: the fail-closed validation ladder, the anti-lie mean-recompute, the WR-03 range-gate fix, the CR-01 injection fix, and the atomic-write discipline across `rebuild_ledger.py`/`regen_strategy.py`/the ledger dedupe are all correct and hold up under adversarial testing (confirmed both by the offline suite and by live reproduction in a scratch workspace).

However, one confirmed, reproducible defect breaks two of the five roadmap success criteria and two of the seven required requirement IDs (MEM-01, MEM-02): **`record_experiment.py` only appends a ledger row when an experiment SUCCEEDS.** A FAILED experiment is correctly recorded in its own canonical `meta.json` (idea, hypothesis, provenance all intact — EXP-01/EXP-04 hold), but it never reaches `control/ledger.jsonl` during the standard `scaffold -> run -> record -> regen` loop that `SKILL.md` sequences. Since `regen_strategy.py`'s tried-list digest — the sole mechanism the AI is instructed to consult before proposing a new idea — reads exclusively from `ledger.jsonl`, every FAILED idea is invisible to the never-repeat check. This is precisely the failure mode MEM-02 exists to prevent: an AI is more likely to accidentally re-propose an idea that already failed (the search isn't over) than one that already succeeded (the search is over). The gap was empirically reproduced end-to-end in a scratch workspace: after recording a FAILED "baseline LGBM" idea, `strategy.md`'s tried-list digest renders `_No experiments recorded yet._`, and running `rebuild_ledger.py` (documented in `SKILL.md` only as an on-drift repair tool, not a sequenced step) immediately surfaces the missing row — proving the incremental ledger and a full rebuild of the identical folder set diverge, which directly contradicts roadmap Success Criterion 4's "fully rebuilds from the per-experiment folders."

The fix is narrowly scoped and consistent with code already in the repo: `experiment_meta.to_ledger_row` already documents and supports a FAILED row with a null `cv_mean`, and `rebuild_ledger.py` already derives such rows correctly. `record_experiment.py` needs to either (a) also write/update a ledger row on the FAILED path, or (b) call the same full-derivation logic `rebuild_ledger.py` uses on every record so the incremental and rebuilt ledgers can never diverge.

---

_Verified: 2026-07-11T15:30:00Z_
_Verifier: Claude (gsd-verifier)_
