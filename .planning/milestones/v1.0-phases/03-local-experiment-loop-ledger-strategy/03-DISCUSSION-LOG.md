# Phase 3: Local Experiment Loop, Ledger & Strategy - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-11
**Phase:** 3-Local Experiment Loop, Ledger & Strategy
**Areas discussed:** Experiment artifact & cycle invocation, Result contract & failure semantics, CV harness — enforced vs convention, Strategy regen & never-repeat

---

## Experiment artifact & cycle invocation (EXP-01/02)

### Artifact format

| Option | Description | Selected |
|--------|-------------|----------|
| .py + jupytext to .ipynb | Plain `experiment.py` run via `uv run`; converted to `.ipynb` at kernel-push time. CLAUDE.md-recommended; jupytext installed. | ✓ |
| .ipynb via papermill | Real `.ipynb` executed locally with papermill; adds Jupyter stack, noisier git. | |
| Maintain both | Paired `.py`+`.ipynb` kept in sync; more moving parts. | |

**User's choice:** .py + jupytext to .ipynb

### Cycle cadence

| Option | Description | Selected |
|--------|-------------|----------|
| Separate entry points | scaffold → run → record → regen_strategy, independent re-runnable scripts (mirrors Phase 2 D-09). | ✓ |
| One run_experiment orchestrator | Single command does it all; mid-cycle failure re-runs everything. | |
| You decide | Planner's call. | |

**User's choice:** Separate entry points

### Data-path resolver

| Option | Description | Selected |
|--------|-------------|----------|
| resolve_data_dir() helper | Prefer `/kaggle/input/<slug>/` else workspace `data/`; detection is code, not config. | ✓ |
| Runner sets env var | Runner exports `KAGGLE_DATA_DIR`; notebook reads it. | |
| You decide | Planner's call. | |

**User's choice:** resolve_data_dir() helper

**Notes:** The resolver + result contract are authored in Phase 3 specifically so the same code runs on a Phase-4 kernel untouched (extend, never re-derive).

---

## Result contract & failure semantics (EXP-03/04)

### CV score representation

| Option | Description | Selected |
|--------|-------------|----------|
| Per-fold + mean + std | Full per-fold array, mean, std, metric name, n_folds; preserves variance for Phase 5. | ✓ |
| Mean scalar only | Single mean; hides fold variance. | |
| You decide | Planner's call. | |

**User's choice:** Per-fold + mean + std

### Failure classification

| Option | Description | Selected |
|--------|-------------|----------|
| Strict: any of several | FAILED on nonzero exit OR missing result.json OR schema-invalid OR non-finite/out-of-range score. Fail-closed. | ✓ |
| Exit code only | FAILED only on nonzero exit; swallowed exceptions log as success. | |
| You decide | Planner's call. | |

**User's choice:** Strict: any of several

### Result contract handoff

| Option | Description | Selected |
|--------|-------------|----------|
| Notebook writes, recorder validates | Notebook writes result.json; recorder validates schema then persists numbers. | ✓ |
| Runner scrapes stdout | Runner parses a printed score line; fragile, no schema. | |
| You decide | Planner's call. | |

**User's choice:** Notebook writes, recorder validates

---

## CV harness — enforced vs convention (criterion 1)

### Leakage-safety guarantee

| Option | Description | Selected |
|--------|-------------|----------|
| Provided harness, AI plugs in | `run_cv(...)` owns the fold loop, applies AI's preprocess_fn inside each fold; AI supplies model/features. Leakage-safe by construction, flexibility preserved. | ✓ |
| Convention + example only | Example loop the AI edits; leakage guarded only by trust. | |
| Harness mandatory, no escape | AI can't write a custom CV loop; tightest, fights flexibility. | |

**User's choice:** Provided harness, AI plugs in

### Metric source

| Option | Description | Selected |
|--------|-------------|----------|
| Add machine metric field | Phase 3 adds tooling-written `metric` (name + direction) to config.json; harness + validity-check + current-best all read it. | ✓ |
| AI passes metric each run | AI reads competition.md prose and passes metric each cycle; drift risk. | |
| You decide | Planner's call. | |

**User's choice:** Add machine metric field

### Seed / determinism

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed default, per-exp override | Fixed seed (e.g. 42) recorded in provenance; deliberate per-experiment override captured. | ✓ |
| Random seed per run | Fresh random seed each run; runs not directly comparable. | |
| You decide | Planner's call. | |

**User's choice:** Fixed default, per-exp override

**Notes:** The metric field is a real cross-phase gap — Phase 2 wrote the metric only into `competition.md` prose; `config.json` has no `metric` field yet. Flagged in CONTEXT.md D-08 as the researcher's key open item (metric→scorer mapping + direction; AI-decides-tooling-persists to avoid free-typing).

---

## Strategy regen & never-repeat (MEM-02/03)

### Machine-rendered vs AI-authored split

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: tooling facts + AI reasoning | Tooling renders current-best + tried-list from ledger; AI authors hypothesis queue + next action. | ✓ |
| Fully tooling-generated | Whole doc rendered from ledger; loses AI judgment. | |
| Fully AI-authored | AI writes whole doc; current-best number AI-typed (fabrication risk). | |

**User's choice:** Hybrid: tooling facts + AI reasoning

### Enforcing never-hand-edited

| Option | Description | Selected |
|--------|-------------|----------|
| Full overwrite each cycle | Regeneration replaces strategy.md wholesale; header warns edits are overwritten. Unlike competition.md safe-merge. | ✓ |
| Section-safe-merge | Preserve hand-edited sections; contradicts "never hand-edited". | |
| You decide | Planner's call. | |

**User's choice:** Full overwrite each cycle

### Never-repeat read path

| Option | Description | Selected |
|--------|-------------|----------|
| Ledger + tried-list digest | AI reads ledger.jsonl + rendered tried-list, prompted to check proposed idea before authoring. | ✓ |
| Re-read all VERDICT.md | AI opens every VERDICT.md each cycle; cost grows, duplicates ledger. | |
| You decide | Planner's call. | |

**User's choice:** Ledger + tried-list digest

---

## Claude's Discretion

- Full `result.json` schema beyond the required fields (params, OOF path, artifact manifest, timing).
- Experiment-folder contents & immutability enforcement (read-only vs convention).
- `VERDICT.md` template and authorship (AI prose; numbers from tooling).
- `run_cv(...)` signature (custom splitter / custom metric callable as first-class — the D-07 tension).
- Default ML dependency floors for the workspace `pyproject.toml` (Kaggle-image parity floors, no runtime pip install).
- `rebuild_ledger.py` rebuild semantics (full vs incremental; corrupt meta.json handling).
- How the AI's reasoning block reaches the strategy regen step.

## Deferred Ideas

- Semantic / embedding idea dedup — v2 (ANLY-01); v1 stays prompt-driven.
- Comparison / summary / best-so-far-delta views over the ledger — v2 (ANLY-02).
- Evidence-ranked hypothesis-queue synthesis — v2 (ANLY-03).
- Hyperparameter sweeps as an experiment type — out of scope v1; EXT-02 in v2.
- Kernel execution of the same experiment — Phase 4 (EXP-05).
