# Phase 3: Local Experiment Loop, Ledger & Strategy - Research

**Researched:** 2026-07-11
**Domain:** Local CV experiment execution, leakage-safe cross-validation harness, machine-verified result contract, git-backed ledger/provenance, ledger-regenerated strategy — all inside a stdlib Claude Code skill
**Confidence:** HIGH (design + sklearn facts verified); MEDIUM on exact Kaggle-image ML pins (flagged as implementation-time verification)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** AI authors a plain `experiment.py`, run locally via `uv run`; converted to `.ipynb` with jupytext only at Phase-4 kernel-push time. Diffable `.py` under git is the local source of truth. NOT a locally-executed `.ipynb`, NOT dual `.py`+`.ipynb`.
- **D-02:** One cycle = separate, idempotent entry points the SKILL sequences — `scaffold_experiment → run → record → regen_strategy`. Each independently re-runnable after failure. NOT a monolithic orchestrator.
- **D-03:** Backend-agnostic data path via a `resolve_data_dir()` helper *in the scaffold*. Prefers `/kaggle/input/<slug>/` if it exists, else workspace `data/` (overridable via `--data-dir`). Backend detection is **code, not config** — same `experiment.py` runs locally and on a kernel untouched. NOT a runner-set env var.
- **D-04:** `result.json` carries per-fold scores + mean + std + metric name + n_folds — not a single mean scalar.
- **D-05:** The notebook WRITES `result.json`; a separate recorder script VALIDATES then PERSISTS into `meta.json` / `ledger.jsonl`. The AI's code *emits*, tooling *verifies-then-persists*. NOT stdout-scraping.
- **D-06:** FAIL-CLOSED run classification — a run is FAILED if ANY of: nonzero exit, OR `result.json` missing, OR schema-invalid, OR score non-finite / outside the metric's valid range. Recorded as a **failure with a verdict**, never success. NOT exit-code-only. Phase 4 *extends* (traceback scan), never weakens.
- **D-07:** The scaffold ships a `run_cv(...)` harness the AI plugs into; harness owns the fold loop and applies the AI's `preprocess_fn` **inside each fold** (fit on train fold, transform val fold), computes the metric, emits `result.json`. AI still writes model/features/preprocessing freely. NOT convention-only, NOT a no-escape harness. ⚠ Planner tension: the harness MUST be flexible enough (custom splitter, custom metric callable, group/time-aware splits) that the AI rarely needs to bypass it.
- **D-08:** Phase 3 ADDS a tooling-written machine `metric` field to `config.json` (`{"name": ..., "greater_is_better": ...}`), derived from what Phase 2 captured. One machine source of truth read by the harness (metric), D-06 (validity range), and D-11 (current-best). Field is **enum/tooling-written, never AI-free-typed**, must map to a concrete scorer + direction. Handle metric-not-captured / unmappable honestly (block, don't guess).
- **D-09:** Fixed default seed (e.g. 42) with a per-experiment override; seed drives splitter + model and is recorded in every experiment's provenance. NOT a fresh random seed each run.
- **D-10:** `meta.json` per experiment is canonical; `ledger.jsonl` is a DERIVED index that fully rebuilds from per-experiment folders (a `rebuild_ledger.py`). Every row carries provenance — run id, artifact hash, git commit, seed. `state.json.next_exp_id` (starts at 1) is the id cursor; ids are zero-padded `exp-NNN`.
- **D-11:** strategy.md = tooling-rendered FACTS (current-best by metric direction + full tried-list) + AI-authored REASONING (hypothesis queue + next action). NOT fully tooling-generated, NOT fully AI-authored.
- **D-12:** strategy.md is FULLY OVERWRITTEN each cycle (unlike competition.md's section-safe-merge), with a header stating "generated each cycle — manual edits are overwritten." Written atomically from (tooling facts) + (AI's freshly-supplied reasoning block).
- **D-13:** Never-repeat is prompt-driven over the ledger + tried-list digest (v1). AI checks any proposed idea against history BEFORE authoring `experiment.py`. NOT re-reading every VERDICT.md. Semantic dedup deferred to v2.

### Claude's Discretion

- `result.json` full schema beyond D-04 required fields (params/hyperparams, OOF path, artifact manifest, timing) — keep it validatable.
- Experiment-folder contents & immutability enforcement (holds at least `experiment.py`, `result.json`, `meta.json`, `VERDICT.md`, `artifacts/`) — enforced (read-only) or by convention — planner's call.
- VERDICT.md authorship — AI prose; numeric fields it references come from tooling. Template is planner discretion.
- `run_cv(...)` signature — how the AI supplies model factory / feature fn / preprocess fn, custom splitter, custom metric callable (must satisfy the D-07 tension).
- Default ML dependency floors added to the workspace `pyproject.toml` (lightgbm / xgboost / catboost) — floors compatible with the Kaggle image, NOT newest majors. Runtime `pip install` forbidden — declare, validate presence, instruct `uv sync` if absent.
- `rebuild_ledger.py` rebuild semantics — full rebuild vs incremental; corrupt/partial `meta.json` handling.
- How the AI's reasoning block reaches the D-12 regen step (arg / temp file / fenced section) — must keep mechanical sections tooling-owned.

### Deferred Ideas (OUT OF SCOPE)

- Semantic / embedding-based idea dedup (v2, ANLY-01). v1 stays prompt-driven (D-13).
- Comparison / summary / best-so-far-delta views over the ledger (v2, ANLY-02). Phase 3's tried-list is a flat digest.
- Evidence-ranked hypothesis-queue synthesis (v2, ANLY-03). v1 AI orders the queue by judgment.
- Hyperparameter sweeps as an experiment type (v1 = one idea + one verdict; EXT-02 v2).
- Kernel execution of the same experiment (Phase 4, EXP-05). Result contract + `resolve_data_dir()` built here to be *extended* there, no kernel code in Phase 3.
- Submission / budget / CV→LB gap (Phase 5, SCORE-*). Phase 3 produces the CV numbers Phase 5 trends; it never submits.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXP-01 | Experiment = idea + hypothesis + generated script + machine result + written verdict | Experiment-folder layout (§Architecture Patterns), `meta.json` schema (§Ledger), VERDICT.md convention |
| EXP-02 | AI authors a fresh script from a template scaffold; backend-agnostic data-path + result contract so the same code runs local or kernel | `experiment.py` scaffold with `resolve_data_dir()` (Pattern 2) + `run_cv()` harness (Pattern 3) + `result.json` contract (§result.json schema) |
| EXP-03 | Run locally → CV score + artifacts | `run_local.py` runner under `uv run` (Pattern 4), leakage-safe fold loop (§run_cv design) |
| EXP-04 | Numeric results tooling-written from a machine-checked `result.json`, never hand-written; provenance (run id, artifact hash, git commit, seed) on every row | Recorder emit/verify/persist split (Pattern 5), provenance capture from stdlib (§Provenance) |
| MEM-01 | Every experiment logged to a git-backed ledger (`meta.json` canonical + derived `ledger.jsonl`) | `meta.json`/`ledger.jsonl`/`rebuild_ledger.py` design (§Ledger) |
| MEM-02 | History lets the AI never re-propose a tried idea | Prompt-driven never-repeat over `ledger.jsonl` + tried-list digest (§Never-repeat) |
| MEM-03 | Living strategy doc regenerated from the ledger each cycle, never hand-edited | `regen_strategy.py` full-overwrite + hybrid facts/reasoning (§Strategy regeneration) |
</phase_requirements>

## Summary

Phase 3 is the core-value milestone: the full `scaffold → run → record → regen` loop on local, CV-only compute. The overriding integrity constraint is that **no number the AI types ever becomes a recorded score** — the AI writes code that *emits* `result.json`; stdlib tooling *validates then persists*. Every design choice here follows Phase 2's proven `tooling-recommends → AI-reasons → tooling-writes` pattern (D-05) and its `stdlib plumbing / one ML step behind uv run` split (D-06).

The single most important open item — the **metric→scorer mapping (D-08)** — resolves cleanly with a **stdlib-only `metric_registry.py`** that maps a small enum of known Kaggle metric names to `{greater_is_better, prediction_type, valid_range, sklearn_callable_name}`. The registry is importable by the stdlib recorder (for direction + range validation) *and* referenced by the ML-env harness (which resolves the callable name to a real sklearn function). `config.json.metric` is written by a Phase-3 tooling setter mirroring `analyze_data.py --cv-scheme` exactly: the AI reads the captured metric prose, decides the enum, and passes an argparse-`choices`-validated flag; tooling writes `{name, greater_is_better}`. Metrics that do not map (mAP@K, Dice/IoU, bespoke competition metrics) resolve to `name: "custom"` with an explicit direction, and the experiment supplies its own metric callable through `run_cv(metric=...)` — the same escape hatch that resolves the D-07 flexibility tension. An uncaptured metric **blocks** (reserved exit code) rather than guessing.

The `run_cv(...)` harness makes leakage-safety structural by owning `fit_transform` on the train fold and `transform` on the val fold itself — the AI supplies an *unfitted* transformer, never a fitted one — while custom splitters and custom metric callables are first-class so the AI almost never bypasses it. `meta.json` (canonical, tracked) + a derived `ledger.jsonl` (rebuilt by `rebuild_ledger.py` from the per-experiment folders) carry provenance computed entirely from stdlib (`hashlib.sha256`, `git rev-parse HEAD`, `uuid4`, the recorded seed). Strategy regeneration overwrites `strategy.md` wholesale each cycle from tooling-rendered facts plus an AI reasoning block delivered via a `--reasoning-file`.

**Primary recommendation:** Build six new stdlib entry points beside the Phase-2 scripts — `set_metric.py` (D-08 setter), `scaffold_experiment.py`, `run_local.py`, `record_experiment.py`, `rebuild_ledger.py`, `regen_strategy.py` — plus two importable stdlib modules (`metric_registry.py`, `experiment_meta.py`) and one ML-env template (`templates/experiment.py.tmpl` shipping `resolve_data_dir()` + `run_cv()`). Reuse `set_config_field`, `replace_section`-style helpers, the gateway/exit-code posture, and the explicit-path git staging already established.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Metric name → scorer + direction resolution | Skill plumbing (stdlib `metric_registry.py`) | ML env (harness resolves callable) | Direction + valid-range are stdlib metadata the recorder needs without importing sklearn (D-06 split) |
| `config.json.metric` write | Skill plumbing (setter via `set_config_field`) | AI (decides enum) | Mirrors D-05 `cv.scheme`: AI reasons, tooling writes enum-validated value |
| Fresh experiment authoring | AI | Skill plumbing (scaffold writes template) | PROJECT decision: AI owns the code each cycle |
| Cross-validation fold loop + leakage-safety | ML env (`run_cv()` in the scaffold) | AI (supplies model/features/preprocess) | Harness enforces fit-on-train/transform-val by construction (criterion 1) |
| Data path resolution | ML env (`resolve_data_dir()` in experiment.py) | — | Backend detection is code, runs identically local + kernel (D-03) |
| Score capture + validation | Skill plumbing (recorder, stdlib) | — | EXP-04: numeric fields tooling-written only; never trust emitted mean |
| Provenance (hash/commit/seed/run-id) | Skill plumbing (stdlib `hashlib`/`subprocess`/`uuid`) | — | Must not depend on the ML env; deterministic + auditable |
| Ledger canonical store + derived index | Skill plumbing (`meta.json` + `rebuild_ledger.py`) | git | MEM-01: rebuildable from folders; git is the durable layer |
| Strategy facts rendering | Skill plumbing (`regen_strategy.py`) | AI (reasoning block) | D-11 hybrid: facts can't drift, reasoning stays smart |
| Never-repeat check | AI (prompt-driven) | Skill plumbing (renders tried-list digest) | D-13: cheap v1; digest is a by-product of regen |

## Standard Stack

### Core (skill plumbing — stdlib only, NO new deps)

| Module | Version | Purpose | Why Standard |
|--------|---------|---------|--------------|
| Python stdlib `json`, `csv`, `argparse`, `pathlib`, `subprocess`, `hashlib`, `uuid`, `statistics`, `math`, `os`, `tempfile` | 3.11+ | All new plumbing scripts (scaffold/run/record/rebuild/regen/set-metric) + `metric_registry.py` + `experiment_meta.py` | CLAUDE.md §Stack Patterns mandates stdlib-only self-locating scripts; matches every existing `scripts/*.py` [VERIFIED: codebase grep — every script imports only stdlib except the `uv run` shell-out] |

`statistics.mean` / `statistics.pstdev` cover CV mean/std; `math.isfinite` covers the D-06 non-finite gate; `hashlib.sha256` covers artifact hashing; `uuid.uuid4().hex` covers run-id. All confirmed present [VERIFIED: `python3 -c` run this session].

### Supporting (generated-experiment ML stack — declared in workspace `pyproject.toml`, run under `uv run`)

| Library | Recommended floor | Purpose | When to Use |
|---------|-------------------|---------|-------------|
| scikit-learn | `>=1.5` (latest 1.9.0) | CV splitters (`KFold`/`StratifiedKFold`/`GroupKFold`/`TimeSeriesSplit`), metric functions, preprocessing base classes | The CV backbone the `run_cv` harness is built on [CITED: CLAUDE.md §Supporting Libraries; scikit-learn.org/stable] |
| pandas | `>=2.2` (latest 3.0.3) | Tabular I/O + frames in `experiment.py` | Default data wrangling; floor avoids the pandas-3.0 parity trap [CITED: CLAUDE.md §Version Compatibility] |
| numpy | `>=1.26` (transitive) | Arrays, OOF vectors | Universal; floor keeps Python-3.11 compatibility (numpy 2.5.1 needs 3.12) [CITED: CLAUDE.md] |
| lightgbm | `>=4.5` (latest 4.6.0) | **Default first model** for tabular | Fast, strong, low-tuning baseline the scaffold suggests [CITED: CLAUDE.md] |
| xgboost | `>=2.1` (latest 3.3.0) | Second GBDT | Ensembling / when LightGBM underperforms; 2.1 floor keeps 3.11 wheels [CITED: CLAUDE.md] |
| catboost | `>=1.2` (latest 1.2.10) | GBDT for high-cardinality categoricals | Best out-of-box on categorical data [CITED: CLAUDE.md] |
| jupytext | `>=1.16` (1.19.4 present) | `.py`⇄`.ipynb` at Phase-4 push time — **NOT used in Phase 3 execution** | Present locally [VERIFIED: `jupytext 1.19.4` this session]; keep out of the local run path (D-01) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib recorder validating `result.json` | Scrape a score line from stdout | Fragile, no schema, stray prints break it — explicitly rejected by D-05 |
| `metric_registry.py` (stdlib metadata) | `sklearn.metrics.get_scorer(name)` directly in the recorder | Would force sklearn into stdlib plumbing (breaks D-06 split); `get_scorer` also returns *negated* error scorers, hiding the raw human-readable number |
| Unfitted-transformer contract in `run_cv` | `preprocess_fn(X_train, X_val)` free function | Free function *can* peek at `X_val`; transformer `fit_transform`/`transform` split is leakage-safe **by construction** (criterion 1) |
| Dedicated `set_metric.py` entry point | Fold metric setting into `scaffold_experiment.py` | Metric is competition-level (set once), not per-experiment; a setter mirrors `capture_competition.py --set-competition-type`. (Discretionary — either is defensible.) |
| `root_mean_squared_error` (sklearn ≥1.4) | `sqrt(mean_squared_error(...))` | Both fine; the direct fn is cleaner and covered by the `>=1.5` floor [VERIFIED: scikit-learn.org — added 1.4] |

**Installation (workspace `pyproject.toml` — extends the existing D-14 stub, does NOT touch the skill repo pyproject):**
```toml
# Added in Phase 3 (extends the existing pandas>=2.2 / scikit-learn>=1.5 floors):
dependencies = [
    "pandas>=2.2",
    "scikit-learn>=1.5",
    "numpy>=1.26",
    "lightgbm>=4.5",
    "xgboost>=2.1",
    "catboost>=1.2",
]
```
Operator runs `uv sync` in the workspace. Runtime `pip install` is forbidden (CLAUDE.md §What NOT to Use) — the runner **validates presence and degrades** (see Pitfall 5), never installs.

**Version verification:** PyPI live-version confirmation via `pip index versions` was blocked in this sandbox (no `pip` on PATH; network scoped). Versions above are `[CITED: CLAUDE.md §Version Compatibility, verified against PyPI 2026-07-09]` — two days stale. `root_mean_squared_error`/`root_mean_squared_log_error` (sklearn 1.4+), `cohen_kappa_score(weights="quadratic")`, and `get_scorer_names` were re-confirmed live this session [VERIFIED: scikit-learn.org/stable]. **Planner:** the first Wave-0 task that touches the workspace env should re-run `uv run python -c "import sklearn,lightgbm,xgboost,catboost,pandas,numpy; print(...versions...)"` to pin the actual synced versions.

## Package Legitimacy Audit

> These packages populate the **workspace** `pyproject.toml` (installed by the operator via `uv sync`), not the skill repo. slopcheck could not run (no `pip`/`slopcheck` on PATH in this sandbox). All are household-name ML packages previously verified against PyPI in CLAUDE.md; none are hallucination candidates. Per protocol, absent a live slopcheck run they are treated as `[CITED]` from CLAUDE.md's prior verification, and the planner should still gate the first `uv sync` behind the existing degrade-gracefully posture (already the D-06 stance — no extra checkpoint needed).

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| scikit-learn | PyPI | 15+ yrs | >70M/mo | github.com/scikit-learn/scikit-learn | unavailable | Approved (CITED) |
| pandas | PyPI | 15+ yrs | >250M/mo | github.com/pandas-dev/pandas | unavailable | Approved (CITED) |
| numpy | PyPI | 15+ yrs | >300M/mo | github.com/numpy/numpy | unavailable | Approved (CITED) |
| lightgbm | PyPI | 8+ yrs | >6M/mo | github.com/microsoft/LightGBM | unavailable | Approved (CITED) |
| xgboost | PyPI | 9+ yrs | >20M/mo | github.com/dmlc/xgboost | unavailable | Approved (CITED) |
| catboost | PyPI | 7+ yrs | >2M/mo | github.com/catboost/catboost | unavailable | Approved (CITED) |
| jupytext | PyPI | 6+ yrs | >2M/mo | github.com/mwouts/jupytext | unavailable | Approved (present locally 1.19.4) |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                       control/config.json (cv.scheme ✓ Phase2 | metric ✗→set here D-08)
                                    │
  competition.md ── Evaluation ─────┤ AI reads prose, decides enum
   metric prose  ── metric (fenced) │
                                    ▼
                          [set_metric.py]  ── writes {name,greater_is_better} ── config.json.metric
                                    │ (enum-validated; blocks if uncaptured/unmappable)
                                    ▼
  state.json.next_exp_id ──► [scaffold_experiment.py] ──► experiments/exp-NNN/experiment.py
        (id cursor, ++)            │ renders template:        (AI then EDITS: model,
                                   │  resolve_data_dir()       features, preprocess,
                                   │  run_cv() harness         hypothesis)
                                   ▼
   /kaggle/input/<slug>/ ?  ──►  [run_local.py]  ── uv run python experiment.py --exp-dir ...
        else data/  (D-03)         │  (captures exit code; NEVER trusts stdout for a score)
                                   ▼
             experiment.py ── run_cv() ──► fold loop:
                fit_transform(X_train) / transform(X_val)  ← leakage-safe by construction
                model_factory().fit → predict/predict_proba → metric()
                                   │
                                   ▼ WRITES (D-05: notebook emits)
                        experiments/exp-NNN/result.json  (per-fold[] + mean + std + n_folds + metric)
                                   │
                                   ▼
                        [record_experiment.py]  ── VALIDATE (D-06 fail-closed) then PERSIST (D-05)
                          │ schema? finite? in metric range? mean==mean(folds)?
                          │ + provenance: sha256(experiment.py), git rev-parse HEAD, seed, uuid4
                          ├──► experiments/exp-NNN/meta.json   (canonical, tracked)
                          ├──► experiments/exp-NNN/VERDICT.md  (stub; AI writes worked/didn't/why)
                          └──► control/ledger.jsonl            (append derived row)
                                   │
   [rebuild_ledger.py] ◄──────────┘ (full rebuild from all meta.json — MEM-01)
                                   │
                                   ▼
             ledger.jsonl ──► [regen_strategy.py] + AI --reasoning-file
                          │ FACTS: current-best (by direction) + tried-list digest (D-11)
                          │ REASONING: hypothesis queue + next action (AI, fresh)
                          ▼ atomic full overwrite (D-12)
                        strategy.md  ("generated each cycle — manual edits overwritten")
                          │
                          ▼ tried-list digest + ledger.jsonl feed the AI's
                        never-repeat prompt-check BEFORE the next scaffold (D-13)
```

### Recommended Project Structure (additions only)

```
scripts/
├── metric_registry.py        # NEW stdlib: name → {greater_is_better, prediction_type, valid_range, sklearn_callable_name}
├── experiment_meta.py        # NEW stdlib: meta.json <-> ledger.jsonl row schema + (de)serialize + validate
├── set_metric.py             # NEW: D-08 setter — AI decides enum, tooling writes config.metric
├── scaffold_experiment.py    # NEW: mint exp-NNN (state.next_exp_id++), write experiment.py from template + meta stub
├── run_local.py              # NEW: uv run python experiment.py; capture exit code; env-presence check
├── record_experiment.py      # NEW: validate result.json (fail-closed) → meta.json + VERDICT stub + ledger row + provenance
├── rebuild_ledger.py         # NEW: full rebuild ledger.jsonl from experiments/*/meta.json
├── regen_strategy.py         # NEW: facts from ledger + AI reasoning block → strategy.md (atomic overwrite)
└── templates/
    ├── experiment.py.tmpl    # NEW: ships resolve_data_dir() + run_cv() + a LightGBM starter the AI edits
    ├── meta.json.tmpl        # NEW (optional): canonical meta skeleton
    └── VERDICT.md.tmpl       # NEW: worked/didn't/why prose skeleton (numbers referenced, not typed)
experiments/exp-NNN/          # per-experiment folder (criterion 2 immutable-after-record)
    experiment.py  result.json  meta.json  VERDICT.md  artifacts/
```

### Pattern 1: Metric registry (stdlib metadata; the D-06 split applied to metrics)

**What:** A stdlib dict keyed by config metric name. Holds everything the *recorder* needs (direction, valid range) without importing sklearn, plus the *callable name string* the *harness* resolves inside the ML env.
**When to use:** Read by `set_metric.py` (validate the enum + look up direction), `record_experiment.py` (range + direction check), and the scaffold's `run_cv` (resolve the actual sklearn function).

```python
# metric_registry.py — stdlib ONLY (imported by the recorder). No sklearn import here.
# The harness (ML env) maps sklearn_callable -> the real function; this module only
# names it, so importing this in stdlib plumbing never pulls scikit-learn (D-06).
from math import inf

# prediction_type ∈ {"label", "proba", "raw"} tells run_cv whether to call
#   model.predict (label/raw) or model.predict_proba (proba).
REGISTRY = {
    "roc_auc":       {"greater_is_better": True,  "prediction_type": "proba", "range": (0.0, 1.0),  "sklearn_callable": "roc_auc_score"},
    "logloss":       {"greater_is_better": False, "prediction_type": "proba", "range": (0.0, inf),  "sklearn_callable": "log_loss"},
    "accuracy":      {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "accuracy_score"},
    "f1":            {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "f1_score"},
    "f1_macro":      {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "f1_score"},   # average="macro" in harness
    "precision":     {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "precision_score"},
    "recall":        {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "recall_score"},
    "rmse":          {"greater_is_better": False, "prediction_type": "raw",   "range": (0.0, inf),  "sklearn_callable": "root_mean_squared_error"},
    "mae":           {"greater_is_better": False, "prediction_type": "raw",   "range": (0.0, inf),  "sklearn_callable": "mean_absolute_error"},
    "rmsle":         {"greater_is_better": False, "prediction_type": "raw",   "range": (0.0, inf),  "sklearn_callable": "root_mean_squared_log_error"},
    "mape":          {"greater_is_better": False, "prediction_type": "raw",   "range": (0.0, inf),  "sklearn_callable": "mean_absolute_percentage_error"},
    "r2":            {"greater_is_better": True,  "prediction_type": "raw",   "range": (-inf, 1.0), "sklearn_callable": "r2_score"},
    "qwk":           {"greater_is_better": True,  "prediction_type": "label", "range": (-1.0, 1.0), "sklearn_callable": "cohen_kappa_score"},  # weights="quadratic" in harness
    "mcc":           {"greater_is_better": True,  "prediction_type": "label", "range": (-1.0, 1.0), "sklearn_callable": "matthews_corrcoef"},
    # Escape hatch — NOT auto-mappable to a stock sklearn scorer. name="custom" means the
    # experiment.py supplies its own metric callable via run_cv(metric=...). Direction and
    # range MUST be given explicitly to set_metric.py (they cannot be looked up).
    "custom":        {"greater_is_better": None,  "prediction_type": None,    "range": (-inf, inf), "sklearn_callable": None},
}
SUPPORTED = tuple(REGISTRY)  # argparse choices for set_metric.py
```

**Metric → sklearn mapping table (the D-08 deliverable):**

| Kaggle metric name | config `name` | sklearn callable | `greater_is_better` | prediction_type | valid range | maps cleanly? |
|--------------------|---------------|------------------|---------------------|-----------------|-------------|----------------|
| AUC / ROC AUC | `roc_auc` | `roc_auc_score` | true | proba (pos class) | [0,1] | ✅ (binary; multiclass needs `multi_class=` — flag) |
| LogLoss / cross-entropy | `logloss` | `log_loss` | false | proba (full matrix) | [0,∞) | ✅ |
| Accuracy | `accuracy` | `accuracy_score` | true | label | [0,1] | ✅ |
| F1 | `f1` / `f1_macro` | `f1_score` | true | label | [0,1] | ✅ (multiclass → `average=`) |
| Precision / Recall | `precision`/`recall` | `precision_score`/`recall_score` | true | label | [0,1] | ✅ |
| RMSE | `rmse` | `root_mean_squared_error` | false | raw | [0,∞) | ✅ (sklearn ≥1.4) |
| MAE | `mae` | `mean_absolute_error` | false | raw | [0,∞) | ✅ |
| RMSLE | `rmsle` | `root_mean_squared_log_error` | false | raw (nonneg preds) | [0,∞) | ✅ (sklearn ≥1.4) |
| MAPE | `mape` | `mean_absolute_percentage_error` | false | raw | [0,∞) | ✅ |
| R² | `r2` | `r2_score` | true | raw | (-∞,1] | ✅ |
| Quadratic Weighted Kappa | `qwk` | `cohen_kappa_score(weights="quadratic")` | true | label (int) | [-1,1] | ⚠ not a `get_scorer` name — needs the `weights=` kwarg [VERIFIED: scikit-learn.org] |
| Matthews CorrCoef | `mcc` | `matthews_corrcoef` | true | label | [-1,1] | ✅ |
| MAP@K / mean average precision @ K | `custom` | — (AI-supplied) | true | ranking | [0,1] | ❌ **not in sklearn** → custom callable |
| Dice / IoU / segmentation, pinball, bespoke weighted metrics | `custom` | — (AI-supplied) | explicit | varies | explicit | ❌ → custom callable |

**Do NOT** map competition-specific metrics onto a "close enough" sklearn scorer — a wrong scorer silently corrupts every CV number and the CV→LB gap Phase 5 trends. Unmappable ⇒ `custom` + explicit direction, or block.

### Pattern 2: `resolve_data_dir()` — backend-agnostic path (D-03, the Phase-4 seam)

**What:** A helper *inside* `experiment.py` (so a bare kernel run needs no runner). Prefers the Kaggle mount, else the workspace `data/`, overridable.
**When to use:** Every experiment. Same code local + kernel, untouched — this is the seam Phase 4 reuses and never re-derives.

```python
# Source: pattern derived from CLAUDE.md §Stack Patterns + D-03. Lives in experiment.py.
import os
from pathlib import Path

def resolve_data_dir(slug: str, override: str | None = None) -> Path:
    """Prefer the Kaggle mount, else the local workspace data/. Detection is CODE, not config."""
    if override:
        return Path(override)
    kaggle = Path(f"/kaggle/input/{slug}")
    if kaggle.is_dir():
        return kaggle                      # on a Kaggle Kernel — same script, untouched
    return Path(__file__).resolve().parents[2] / "data"   # workspace data/ (exp dir is experiments/exp-NNN/)
```

### Pattern 3: `run_cv(...)` — leakage-safe-by-construction harness (D-07, criterion 1)

**What:** The scaffold owns the fold loop; the AI supplies an unfitted model factory, an unfitted preprocessor (fit/transform interface), and optionally a feature fn, a custom splitter, and a custom metric callable. Leakage-safety is structural: the *harness* calls `fit_transform` on the train fold and `transform` on the val fold — the AI never hands over a fitted object.
**When to use:** Default path for every experiment. Custom splitter + custom metric are first-class so the AI rarely bypasses it (resolves the ⚠ D-07 tension).

```python
# Source: sklearn.model_selection + D-04/D-06/D-07. Ships in experiment.py.tmpl, runs under uv run.
import json, time
import numpy as np
from statistics import mean, pstdev
from sklearn.model_selection import KFold, StratifiedKFold, GroupKFold, TimeSeriesSplit
from sklearn import metrics as skm

_SPLITTERS = {"KFold": KFold, "StratifiedKFold": StratifiedKFold,
              "GroupKFold": GroupKFold, "TimeSeriesSplit": TimeSeriesSplit}

def _make_splitter(scheme, n_splits, seed):
    cls = _SPLITTERS[scheme]
    if cls in (KFold, StratifiedKFold):
        return cls(n_splits=n_splits, shuffle=True, random_state=seed)
    return cls(n_splits=n_splits)          # GroupKFold/TimeSeriesSplit take no random_state

def _resolve_metric(metric, registry_entry):
    if callable(metric):                   # custom metric callable — first-class escape hatch
        return metric, registry_entry["prediction_type"]
    fn = getattr(skm, registry_entry["sklearn_callable"])
    ptype = registry_entry["prediction_type"]
    # thin wrappers for the kwarg-needing metrics:
    if metric == "qwk":     return (lambda yt, yp: fn(yt, yp, weights="quadratic")), ptype
    if metric == "f1_macro":return (lambda yt, yp: fn(yt, yp, average="macro")), ptype
    return fn, ptype

def run_cv(*, X, y, model_factory, preprocess_factory=None, feature_fn=None,
           metric, registry_entry, cv_scheme, n_splits=5, seed=42, groups=None,
           splitter=None, exp_dir=".", prediction_type=None):
    """Leakage-safe fold loop. Writes result.json. Returns the result dict.

    model_factory():      -> a FRESH, UNFITTED estimator per fold.
    preprocess_factory(): -> a FRESH, UNFITTED transformer (fit/transform) per fold; the
                             HARNESS does fit_transform(train)/transform(val) — the AI never
                             fits it, so train->val leakage is impossible by construction.
    feature_fn(df)->X:    optional; default assumes X is already the feature matrix.
    metric:               a registry name (str) OR a callable(y_true, y_pred)->float.
    splitter:             optional pre-built splitter to fully bypass scheme selection.
    """
    metric_fn, ptype = _resolve_metric(metric, registry_entry)
    ptype = prediction_type or ptype
    if feature_fn is not None:
        X = feature_fn(X)
    split = splitter or _make_splitter(cv_scheme, n_splits, seed)
    Xv = np.asarray(X); yv = np.asarray(y)
    fold_scores, oof = [], np.full(len(yv), np.nan, dtype=float)
    t0 = time.time()
    split_args = (Xv, yv, groups) if cv_scheme == "GroupKFold" else (Xv, yv)
    for tr, va in split.split(*split_args):
        Xtr, Xva, ytr = Xv[tr], Xv[va], yv[tr]
        if preprocess_factory is not None:
            pp = preprocess_factory()
            Xtr = pp.fit_transform(Xtr, ytr)   # FIT on train fold only
            Xva = pp.transform(Xva)            # TRANSFORM val fold — no leakage
        model = model_factory()
        model.fit(Xtr, ytr)
        if ptype == "proba":
            proba = model.predict_proba(Xva)
            pred = proba[:, 1] if proba.shape[1] == 2 else proba
        else:
            pred = model.predict(Xva)
        fold_scores.append(float(metric_fn(yv[va], pred)))
        if ptype != "proba" or (hasattr(pred, "ndim") and pred.ndim == 1):
            oof[va] = np.asarray(pred).reshape(-1)[: len(va)]
    result = {
        "schema_version": 1,
        "metric": metric if isinstance(metric, str) else "custom",
        "greater_is_better": registry_entry["greater_is_better"],
        "cv_scheme": cv_scheme, "n_folds": len(fold_scores),
        "fold_scores": [round(s, 8) for s in fold_scores],
        "cv_mean": float(mean(fold_scores)),
        "cv_std": float(pstdev(fold_scores)) if len(fold_scores) > 1 else 0.0,
        "seed": seed, "prediction_type": ptype,
        "timing_sec": round(time.time() - t0, 3),
        "written_by": "run_cv", "artifacts": [],
    }
    from pathlib import Path
    np.save(Path(exp_dir) / "artifacts" / "oof.npy", oof)
    (Path(exp_dir) / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
```

**Anti-leakage note:** the harness must NOT accept a pre-fitted transformer or a `preprocess_fn(X_train, X_val)` that sees both frames simultaneously — that is the leakage hole criterion 1 targets. The `preprocess_factory() -> unfitted transformer` contract is the load-bearing design choice; document it loudly in the template.

### Pattern 4: `run_local.py` — the runner (EXP-03)

**What:** Shells `uv run --no-sync python experiment.py --exp-dir experiments/exp-NNN --slug <slug>` inside the workspace, captures the exit code (never trusts stdout for a score), times out, and hands off to the recorder. Mirrors `analyze_data.run_adversarial_validation`'s `uv run --no-sync` posture exactly.
**When to use:** Local execution (the default target). `--no-sync` means a missing ML env → clean non-zero (D-06 FAILED), never a silent network install.

### Pattern 5: recorder emit/verify/persist split (D-05, EXP-04) — see §result.json + §Ledger below.

### Anti-Patterns to Avoid

- **Trusting the emitted `cv_mean`.** The recorder MUST recompute `mean(fold_scores)` and compare — a notebook that swallows an exception and writes a plausible mean is exactly the D-06 silent failure. Recompute, don't trust.
- **Importing sklearn into any `scripts/*.py` plumbing.** Breaks the D-06 stdlib/ML split and the stdlib-only script contract. Only `experiment.py` (under `uv run`) imports the ML stack.
- **`git add -A` when staging provenance.** The codebase already forbids this (leak-guard trips on `control/raw/last-error.txt`); stage `meta.json` + `experiment.py` by explicit path.
- **A no-escape harness.** If a custom metric or bespoke split isn't first-class, the AI writes its own loop and criterion 1's "enforced" collapses to "convention." Custom splitter + custom metric callable are non-negotiable (D-07 tension).
- **Auto-mapping a competition metric to a near sklearn scorer.** Silently wrong numbers. Use `custom` or block.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-validation splitting | A hand-rolled fold indexer | `sklearn.model_selection.{KFold,StratifiedKFold,GroupKFold,TimeSeriesSplit}` | Stratification, grouping, and temporal ordering have subtle edge cases (empty strata, group spillover) sklearn handles [CITED: CLAUDE.md] |
| Metric computation | Manual RMSE/AUC/logloss math | `sklearn.metrics.*` | AUC tie-handling, logloss clipping, RMSLE nonneg guards are easy to get wrong |
| Metric name → direction/range | Ad-hoc `if name==...` scattered across scripts | One `metric_registry.py` | Single source of truth read by setter + recorder + harness (D-08) |
| Fold-internal preprocessing | Fitting a scaler/encoder on the full frame then splitting | Harness `fit_transform(train)/transform(val)` | Fit-on-all-then-split is *the* canonical CV leakage bug (criterion 1) |
| Artifact hashing | Custom checksum | `hashlib.sha256` | Standard, collision-resistant, stdlib |
| Commit capture | Parsing `git log` text | `git rev-parse HEAD` + `git status --porcelain` for dirty flag | Exact, machine-stable |
| Atomic file write (strategy.md) | Write-in-place | `tempfile` + `os.replace` | Crash-safe overwrite (D-12) |
| CV mean/std | Manual sum loops | `statistics.mean` / `statistics.pstdev` | Stdlib, correct, present [VERIFIED this session] |

**Key insight:** In CV tooling, the dangerous bugs are silent — a leaky preprocessor or a wrong metric produces a *plausible* number that only reveals itself as a CV→LB divergence weeks later. The value of this phase is that tooling makes those bugs *loud* (structural leakage-safety + machine range/finite checks), so hand-rolling any of the above defeats the phase's entire purpose.

## result.json schema (D-04 required + discretionary)

**Required (D-04):** `metric`, `n_folds`, `fold_scores` (array), `cv_mean`, `cv_std`.
**Recommended full schema (Claude's discretion, kept validatable):**

```json
{
  "schema_version": 1,
  "metric": "roc_auc",
  "greater_is_better": true,
  "cv_scheme": "StratifiedKFold",
  "n_folds": 5,
  "fold_scores": [0.8201, 0.8134, 0.8290, 0.8055, 0.8188],
  "cv_mean": 0.81736,
  "cv_std": 0.00794,
  "seed": 42,
  "prediction_type": "proba",
  "params": {"model": "LGBMClassifier", "n_estimators": 500, "learning_rate": 0.05},
  "oof_path": "artifacts/oof.npy",
  "artifacts": ["artifacts/oof.npy"],
  "timing_sec": 12.4,
  "written_by": "run_cv"
}
```

**Recorder validation (`record_experiment.py`, fail-closed — D-05/D-06), in order:**
1. File exists and parses as JSON → else FAILED(`missing_result` / `schema_invalid`).
2. Required keys present with correct types; `len(fold_scores) == n_folds`; `n_folds >= 2` → else FAILED(`schema_invalid`).
3. Every fold score, `cv_mean`, `cv_std` pass `math.isfinite` → else FAILED(`non_finite`).
4. `abs(cv_mean - statistics.mean(fold_scores)) < 1e-6` (the anti-lie recompute) → else FAILED(`schema_invalid`).
5. `metric` matches `config.json.metric.name` (or is `custom`) → else FAILED(`schema_invalid`).
6. `range_lo <= cv_mean <= range_hi` from `metric_registry` (and each fold score) → else FAILED(`out_of_range`).
7. All pass → SUCCESS; persist score into `meta.json` + append ledger row.

Any FAILED still writes `meta.json` with `status="FAILED"`, `failure_reason=<enum>`, and a VERDICT.md stub prompting the AI to write *why* it failed — a failure is recorded **with a verdict**, never dropped or upgraded to success (criterion 3).

## Ledger, provenance & rebuild (MEM-01, EXP-04, D-10)

**`meta.json` (canonical, tracked per D-13 `.gitignore` exceptions):**
```json
{
  "schema_version": 1,
  "exp_id": "exp-001",
  "created": "2026-07-11T14:22:07Z",
  "idea": "LightGBM baseline on raw features",
  "hypothesis": "GBDT with StratifiedKFold beats a constant-rate baseline",
  "status": "SUCCESS",
  "failure_reason": null,
  "metric": "roc_auc",
  "greater_is_better": true,
  "cv_scheme": "StratifiedKFold",
  "n_folds": 5,
  "fold_scores": [0.8201, 0.8134, 0.8290, 0.8055, 0.8188],
  "cv_mean": 0.81736,
  "cv_std": 0.00794,
  "provenance": {
    "run_id": "a1b2c3d4e5f6...",
    "artifact_hash": "sha256:9f86d0818...",
    "git_commit": "12fcc16",
    "git_dirty": false,
    "seed": 42
  },
  "result_path": "experiments/exp-001/result.json",
  "verdict_path": "experiments/exp-001/VERDICT.md",
  "artifacts": ["artifacts/oof.npy"]
}
```

**`ledger.jsonl` derived row (one line, subset for AI reasoning + D-13 digest):**
```json
{"exp_id":"exp-001","status":"SUCCESS","idea":"LightGBM baseline on raw features","metric":"roc_auc","greater_is_better":true,"cv_mean":0.81736,"cv_std":0.00794,"git_commit":"12fcc16","seed":42,"created":"2026-07-11T14:22:07Z","verdict_path":"experiments/exp-001/VERDICT.md"}
```

**Provenance from stdlib (all confirmed this session):**
```python
import hashlib, subprocess, uuid
run_id = uuid.uuid4().hex
artifact_hash = "sha256:" + hashlib.sha256((exp_dir / "experiment.py").read_bytes()).hexdigest()
commit = subprocess.run(["git","rev-parse","--short","HEAD"], cwd=ws, capture_output=True, text=True).stdout.strip()
dirty  = bool(subprocess.run(["git","status","--porcelain","--", str(exp_dir)], cwd=ws, capture_output=True, text=True).stdout.strip())
```
- **`artifact_hash`** = sha256 of `experiment.py` (the reproducibility anchor — what code produced the number). Optionally extend to a Merkle-style hash over sorted `artifacts/` file hashes.
- **`git_commit`**: to make the commit meaningful, the recorder should `git add -- experiments/exp-NNN/experiment.py experiments/exp-NNN/meta.json` and (optionally) commit before/at record time, then capture HEAD; record `git_dirty=true` if the tree still has uncommitted changes under the exp dir so provenance never silently claims a clean commit it didn't have.
- **`seed`**: copied from `result.json` (which copied it from the run) — the D-09 default 42 or the per-experiment override.

**`rebuild_ledger.py` semantics (recommend FULL rebuild):**
- Glob `experiments/exp-*/meta.json`, sort by `exp_id`, derive each row via `experiment_meta.to_ledger_row`, write `ledger.jsonl` atomically (`tempfile`+`os.replace`).
- **Corrupt/partial `meta.json`:** do NOT fabricate. On a `JSONDecodeError` or a meta missing required keys → emit a `stderr` warning naming the folder and **skip** it (or write a minimal `{"exp_id":..,"status":"UNKNOWN","note":"unreadable meta.json"}` sentinel row — planner's call; skipping keeps the ledger clean, the sentinel keeps the count honest). Rebuild is idempotent and never partial-writes the live file (atomic replace).
- Full rebuild is preferred over incremental append because it makes `ledger.jsonl` a pure function of the folders (MEM-01 "fully rebuilds"), so a hand-corrupted ledger self-heals.

## Strategy regeneration & never-repeat (MEM-02/03, D-11/D-12/D-13)

**`regen_strategy.py` (full overwrite, atomic):**
- **FACTS (tooling-rendered from `ledger.jsonl`):**
  - **Current best:** among `status=="SUCCESS"` rows, `max(cv_mean)` if `greater_is_better` else `min(cv_mean)`; render exp id, `cv_mean ± cv_std`, idea, verdict link. Empty ledger → "None yet."
  - **Tried-list digest:** every row → `exp-NNN | idea | status | cv_mean±std | verdict link`. This digest doubles as the D-13 never-repeat surface.
- **REASONING (AI-authored, fresh each cycle):** hypothesis queue + next action. Delivered to the tool via `--reasoning-file <path>` (a markdown fragment the AI writes); tooling splices it into the reasoning sections. (Alternatives: `--reasoning "..."` arg, or a fenced `<!-- reasoning -->` block the tool reads — `--reasoning-file` keeps mechanical sections tooling-owned and avoids shell-quoting a multi-paragraph block.)
- **Overwrite (D-12):** render the full doc (header + facts + reasoning) to `strategy.md.tmp`, `os.replace` onto `strategy.md`. Header verbatim: *"Generated each cycle from control/ledger.jsonl — manual edits are overwritten."*

**Never-repeat (D-13, prompt-driven):** before `scaffold_experiment.py` writes a new `experiment.py`, the SKILL instructs the AI to read `control/ledger.jsonl` (idea/hypothesis/verdict/score per row) and the tried-list digest in `strategy.md`, and to confirm the proposed idea is not a duplicate of a tried one. No new tooling — the digest is a by-product of regen; the check lives in the SKILL prose (mirrors the existing gate-protocol convention where the SKILL holds the human/AI loop and scripts stay non-interactive).

## Runtime State Inventory

> This is a greenfield feature phase (new scripts + new per-experiment folders), NOT a rename/refactor. No pre-existing runtime state is being renamed. The only *mutable* state touched:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `control/state.json.next_exp_id` (starts at 1) — incremented by `scaffold_experiment.py`; `control/ledger.jsonl` (currently empty string) — appended by recorder, rebuilt by `rebuild_ledger.py` | Code: read-increment-write the cursor via a `set_config_field`-style setter on state.json; append/rebuild ledger |
| Live service config | None — Phase 3 is fully local, no external services touched (no Kaggle calls) | None — verified: no `kaggle_gateway` import needed in any Phase-3 script |
| OS-registered state | None | None — verified: no schedulers/daemons |
| Secrets/env vars | None new. `resolve_data_dir()` reads no secrets; runner inherits the existing egress sandbox | None |
| Build artifacts | Workspace `pyproject.toml` gains lightgbm/xgboost/catboost/numpy floors → operator must re-run `uv sync` to materialize the env before the first run | Instruct `uv sync`; runner degrades to a clear error if env absent (Pitfall 5) |

**Nothing found** in Live-service / OS-registered / Secrets categories — verified by grepping Phase-3 scope against the existing script imports (no gateway, no credential, no network path in the loop).

## Common Pitfalls

### Pitfall 1: Fit-on-all-then-split preprocessing leakage
**What goes wrong:** A scaler/encoder/target-encoder fit on the full training frame before CV leaks val-fold statistics into training → optimistic CV, CV→LB divergence.
**Why it happens:** It's the intuitive order (preprocess, then split) and it "works."
**How to avoid:** The `run_cv` harness fits the transformer on the train fold and transforms the val fold *itself*; the AI supplies an *unfitted* `preprocess_factory()`. Never accept a fitted transformer or a two-frame `preprocess_fn`.
**Warning signs:** CV noticeably better than a public-kernel baseline; `cv_std` implausibly tiny.

### Pitfall 2: Trusting the emitted mean (the silent-failure hole)
**What goes wrong:** A notebook catches an exception and writes a hard-coded or half-computed `cv_mean`; exit code is 0; it's recorded as success.
**Why it happens:** Exit-code-only classification (explicitly rejected by D-06).
**How to avoid:** Recorder recomputes `mean(fold_scores)` and cross-checks; validates finite + in-range; a mismatch or out-of-range trips FAILED regardless of exit code.
**Warning signs:** `cv_mean` doesn't equal `mean(fold_scores)`; a score outside the metric's range (e.g. AUC = 1.7).

### Pitfall 3: Wrong prediction type for the metric
**What goes wrong:** Passing hard labels to `roc_auc_score`/`log_loss` (which need probabilities) or probabilities to `accuracy_score` → wrong or crashing scores.
**Why it happens:** The metric's required input isn't tracked.
**How to avoid:** `prediction_type` in `metric_registry` drives whether the harness calls `predict` vs `predict_proba`. For proba binary, pass the positive-class column.
**Warning signs:** `log_loss` errors on integer labels; AUC exactly 0.5 with a real model.

### Pitfall 4: Multiclass ROC AUC / averaging kwargs
**What goes wrong:** `roc_auc_score` on multiclass without `multi_class="ovr"/"ovo"` raises; `f1_score` on multiclass without `average=` raises or averages wrongly.
**Why it happens:** The registry's default entries are binary-shaped.
**How to avoid:** Provide `f1_macro` and document that multiclass AUC needs the AI to pass a custom metric callable (`lambda yt, yp: roc_auc_score(yt, yp, multi_class="ovr")`) — a first-class `run_cv(metric=...)` case. Flag this in the scaffold comments.
**Warning signs:** ValueError mentioning `multi_class` or `average`.

### Pitfall 5: Runtime pip install temptation when the ML env is absent
**What goes wrong:** A script tries to `pip install lightgbm` on ImportError → silent env mutation, security/repro smell, forbidden by CLAUDE.md.
**Why it happens:** "Just make it work."
**How to avoid:** `run_local.py` uses `uv run --no-sync`; on non-zero import failure it prints "workspace ML env not synced — run `uv sync`" and records nothing (or a SKIPPED-style clear message), exactly like `analyze_data`'s AV degrade. Declare deps, validate presence, instruct — never install.
**Warning signs:** A network fetch during a "local" run.

### Pitfall 6: Kaggle-image version parity (pandas 3.0 / numpy 2.5)
**What goes wrong:** Code written against pandas 3.0 (Copy-on-Write default, PyArrow strings) or numpy 2.x runs locally but breaks on the older `kaggle/python` image in Phase 4, poisoning CV→LB parity.
**Why it happens:** Newest-major locally ≠ Kaggle's pins.
**How to avoid:** Declare *floors* (`pandas>=2.2`, `numpy>=1.26`), not newest majors; keep generated code on stable APIs. Confirm the current `kaggle/python` pins at Phase-4 implementation time.
**Warning signs:** `.tolist()`/dtype/string-dtype behavior differing between local and kernel.

### Pitfall 7: TimeSeriesSplit fold sizes / GroupKFold group arg
**What goes wrong:** `TimeSeriesSplit` yields expanding-window folds (not k equal folds) and no `random_state`; `GroupKFold.split` needs `groups=`. Treating them like `KFold` gives wrong or crashing splits.
**How to avoid:** `_make_splitter` handles the no-`random_state` case; the harness passes `groups` only for `GroupKFold`. Data must be time-sorted before `TimeSeriesSplit`.

## Code Examples

### `set_metric.py` — the D-08 setter (mirrors `analyze_data.py --cv-scheme`)
```python
# Source: pattern mirrored from analyze_data.py / capture_competition.py setter modes.
# AI reads competition.md "Evaluation metric" prose, decides the enum, passes --metric;
# tooling writes config.json.metric. Direction is looked up from the registry for known
# names (cannot be mistyped); "custom" REQUIRES an explicit --direction.
import argparse, json, sys
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path: sys.path.insert(0, str(SCRIPT_DIR))
from init_workspace import set_config_field                    # reuse the setter
from metric_registry import REGISTRY, SUPPORTED

METRIC_NOT_CAPTURED = 78  # reuse the LIMIT_NEEDS_USER-style "ask the user / block" convention

def main(argv=None):
    ap = argparse.ArgumentParser(prog="set_metric.py")
    ap.add_argument("--workspace", type=Path, default=Path.cwd())
    ap.add_argument("--metric", choices=SUPPORTED, required=True,
                    help="The AI's decision from the captured Evaluation-metric prose. Enum-validated.")
    ap.add_argument("--direction", choices=("greater_is_better","lower_is_better"), default=None,
                    help="REQUIRED only when --metric custom; ignored otherwise (looked up).")
    a = ap.parse_args(argv)
    cfg_path = a.workspace / "control" / "config.json"
    entry = REGISTRY[a.metric]
    if a.metric == "custom":
        if a.direction is None:
            print("set_metric: --direction is required for a custom metric (block, don't guess).", file=sys.stderr)
            return 2
        gib = a.direction == "greater_is_better"
    else:
        gib = entry["greater_is_better"]
    rc = set_config_field(cfg_path, ("metric",), {"name": a.metric, "greater_is_better": gib})
    if rc == 0:
        print(f"metric set to {a.metric} (greater_is_better={gib}).")
    return rc
```
**Block-don't-guess:** the SKILL runs `set_metric.py` only after confirming `competition.md` "Evaluation metric" is captured (not the `_TODO` stub). If uncaptured, block and instruct running `capture_competition.py` first — never default a metric.

### `config.json` after Phase 3 (the new `metric` field)
```json
{
  "workspace_version": 1,
  "competition_slug": "titanic",
  "execution_target": "local",
  "cv": { "scheme": "StratifiedKFold" },
  "metric": { "name": "roc_auc", "greater_is_better": true },
  "submission": { "daily_limit": 10, "limit_provenance": "extracted" },
  "competition": { "type": "csv" },
  "created": "..."
}
```
Add `"metric": {"name": null, "greater_is_better": null}` to `config.json.tmpl` so the reserved-null key exists (only `set_config_field` can fill it — the same reserved-null pattern as `cv.scheme`, per `write_control_json` merge-add-missing semantics).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `sqrt(mean_squared_error(...))` for RMSE | `root_mean_squared_error` direct fn | sklearn 1.4 (2024) | Cleaner registry entry; covered by `>=1.5` floor [VERIFIED: scikit-learn.org] |
| `sklearn.metrics.SCORERS` dict | `get_scorer_names()` / `get_scorer()` | sklearn 1.3 | Use `get_scorer_names` if you ever validate against sklearn's own list [VERIFIED: scikit-learn.org] |
| pandas default copy semantics | Copy-on-Write default (pandas 3.0) | pandas 3.0 (2025) | Parity trap — declare `>=2.2` floor, don't rely on 3.0-only behavior [CITED: CLAUDE.md] |
| RMSLE via `sqrt(mean_squared_log_error)` | `root_mean_squared_log_error` | sklearn 1.4 | Direct fn; nonneg-input guard built in |

**Deprecated/outdated:** none blocking. jupytext stays reserved for Phase 4 (do not add to the local run path — D-01).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Kaggle `kaggle/python` image is compatible with the recommended floors (pandas≥2.2, numpy≥1.26, sklearn≥1.5, lightgbm≥4.5) | Standard Stack / Pitfall 6 | Low for Phase 3 (local-only); matters at Phase 4 — re-verify the live image pins then |
| A2 | Live PyPI versions match CLAUDE.md's 2026-07-09 snapshot (2 days stale; `pip` unavailable in sandbox) | Standard Stack | Low — all are stable majors; Wave-0 env task will pin actuals |
| A3 | The default 5-fold `n_splits` is acceptable when not overridden | run_cv | Low — overridable per experiment; StratifiedKFold needs each class to have ≥ n_splits members (tiny minority classes may force fewer folds) |
| A4 | `custom` metric direction is always knowable by the AI from competition prose | set_metric / registry | Medium — if the AI mis-judges direction, current-best selection inverts; mitigated by explicit `--direction` + human confirmation |
| A5 | slopcheck would rate all 6 ML packages `[OK]` (could not run this session) | Package Legitimacy Audit | Negligible — all are top-download packages with known repos |

## Open Questions

1. **Where does `set_metric.py` live — standalone vs folded into scaffold?**
   - Known: metric is competition-level (set once), read by the harness before any run.
   - Unclear: standalone entry point vs a precondition step of `scaffold_experiment.py`.
   - Recommendation: standalone setter (mirrors `--set-competition-type`); run once during setup. Planner may fold it in if it prefers fewer entry points.

2. **Should the recorder auto-commit `experiment.py` + `meta.json` for a clean `git_commit` provenance, or record HEAD + a `git_dirty` flag?**
   - Known: provenance needs a commit; an uncommitted tree makes `git rev-parse HEAD` point at the *previous* state.
   - Recommendation: record HEAD + `git_dirty` honestly; offer an optional `--commit` flag that stages the exp folder by explicit path and commits before capturing HEAD. Don't force a commit (the user may want to review first).

3. **OOF for multiclass/proba metrics** — the sketch stores a 1-D OOF; multiclass proba OOF is 2-D.
   - Recommendation: store OOF as-is (`np.save` handles 2-D); make `oof` optional and skip cleanly when shape is ambiguous. Low priority for v1 tabular default.

4. **`immutability` enforcement of the experiment folder (criterion 2, Claude's discretion)** — read-only chmod after record vs convention-only.
   - Recommendation: convention-only for v1 (never rewritten; a re-run scaffolds a new `exp-NNN`). Read-only chmod fights re-running a fixed notebook (D-02 idempotency) — avoid.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | All scripts | ✓ | 3.13.13 | — |
| uv | `run_local.py` (`uv run`) | ✓ | 0.11.14 | — (runner errors clearly if absent, like analyze_data) |
| git | provenance (commit/dirty) | ✓ | present (`git rev-parse` works) | record `git_commit=null` + a warning if no repo |
| jupytext | Phase 4 only (NOT this phase) | ✓ | 1.19.4 | — |
| scikit-learn / pandas / numpy / lightgbm / xgboost / catboost | `experiment.py` under `uv run` | ✗ (workspace env not synced here) | — | **Operator runs `uv sync`**; runner degrades with a clear "run uv sync" message (D-06 posture), never installs |
| slopcheck / pip | package audit | ✗ | — | Used CLAUDE.md's prior PyPI verification (CITED) |

**Missing dependencies with no fallback:** none block Phase-3 *plumbing* (all stdlib + git + uv present).
**Missing dependencies with fallback:** the ML stack is absent in *this* checkout — expected; it lives in the scaffolded **workspace** env the operator syncs. The runner must detect absence and instruct `uv sync` (do not build kernel/network install paths).

## Validation Architecture

> Nyquist validation is enabled (`workflow.nyquist_validation: true`). Tests exercise scripts as **subprocesses** via the existing `run_script` fixture (conftest.py) — the documented `python3 scripts/<name>.py --workspace <dir>` contract — never importing at module top level.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest ≥8.0 (dev group) [VERIFIED: repo pyproject.toml] |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]`; `addopts = -m 'not live'`; `live` marker excluded by default |
| Quick run command | `uv run pytest tests/test_<new>.py -x -q` |
| Full suite command | `uv run pytest` (mock suite, offline, `-m 'not live'`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-08 | metric enum → `{name,greater_is_better}` written; `custom` needs `--direction`; uncaptured blocks | unit | `uv run pytest tests/test_set_metric.py -x` | ❌ Wave 0 |
| D-08 | registry direction/range/prediction_type correct for each known metric | unit | `uv run pytest tests/test_metric_registry.py -x` | ❌ Wave 0 |
| EXP-02, criterion 1 | `run_cv` fits transformer on train fold, transforms val fold (leakage-safe); custom splitter + custom metric first-class; emits valid `result.json` | unit (tiny synthetic CSV, real sklearn) | `uv run pytest tests/test_run_cv.py -x` | ❌ Wave 0 (needs ML env → mark `live`-like or gate on import) |
| EXP-02, D-03 | `resolve_data_dir` prefers `/kaggle/input/<slug>` else `data/`; `--data-dir` override | unit | `uv run pytest tests/test_resolve_data_dir.py -x` | ❌ Wave 0 |
| EXP-03, D-06 | `run_local` returns nonzero on missing env / throwing script; captures exit code | unit | `uv run pytest tests/test_run_local.py -x` | ❌ Wave 0 |
| EXP-04, D-05/D-06 | recorder FAILS on missing/schema-invalid/non-finite/out-of-range/mean-mismatch; SUCCESS persists; provenance fields present | unit | `uv run pytest tests/test_record_experiment.py -x` | ❌ Wave 0 |
| MEM-01, D-10 | `rebuild_ledger` reconstructs `ledger.jsonl` from `meta.json` folders; skips corrupt meta with warning; atomic | unit | `uv run pytest tests/test_rebuild_ledger.py -x` | ❌ Wave 0 |
| MEM-03, D-11/D-12 | `regen_strategy` renders current-best by direction + tried-list; splices AI reasoning; full overwrite; header present | unit | `uv run pytest tests/test_regen_strategy.py -x` | ❌ Wave 0 |
| EXP-01, D-02, D-10 | `scaffold_experiment` mints `exp-NNN`, increments `state.next_exp_id`, writes `experiment.py` from template + meta stub; idempotent | unit | `uv run pytest tests/test_scaffold_experiment.py -x` | ❌ Wave 0 |

**Key observable behaviors the plans must assert against:**
- A deliberately-throwing `experiment.py` ⇒ recorder writes `meta.json status=FAILED` + VERDICT stub, appends NO success ledger row (criterion 3 — the headline test).
- A notebook that writes `cv_mean` ≠ `mean(fold_scores)` ⇒ FAILED(`schema_invalid`) (anti-lie recompute).
- An AUC of 1.7 (out of `[0,1]`) ⇒ FAILED(`out_of_range`).
- Fitting a scaler on the full frame vs via the harness ⇒ the harness path yields the leakage-safe (typically lower) CV — assert the harness calls `fit_transform` only on train indices (spy/mock transformer counting rows seen at fit).
- `ledger.jsonl` deleted then `rebuild_ledger` ⇒ byte-identical reconstruction from `meta.json`.

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_<script>.py -x -q`
- **Per wave merge:** `uv run pytest` (full mock suite)
- **Phase gate:** full mock suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_metric_registry.py` — REQ D-08 (registry correctness)
- [ ] `tests/test_set_metric.py` — REQ D-08 (setter + block-don't-guess + custom direction)
- [ ] `tests/test_run_cv.py` — REQ EXP-02/criterion 1 (leakage-safety, result.json) — needs a synthetic frame fixture + real sklearn; gate on `pytest.importorskip("sklearn")` or a new `ml` marker
- [ ] `tests/test_resolve_data_dir.py` — REQ D-03
- [ ] `tests/test_run_local.py` — REQ EXP-03/D-06 (exit-code capture, env-absent message)
- [ ] `tests/test_record_experiment.py` — REQ EXP-04/D-05/D-06 (all five FAILED reasons + SUCCESS + provenance)
- [ ] `tests/test_rebuild_ledger.py` — REQ MEM-01/D-10 (rebuild + corrupt-skip + atomic)
- [ ] `tests/test_regen_strategy.py` — REQ MEM-03/D-11/D-12 (facts + reasoning + overwrite)
- [ ] `tests/test_scaffold_experiment.py` — REQ EXP-01/D-02 (id cursor + idempotency)
- [ ] Shared fixture: a tiny deterministic `train.csv`/`test.csv` + a seeded workspace with `config.metric` (extend `conftest.py` / reuse `cv_fixtures.py`)
- [ ] Decide the `run_cv` test strategy: a new `ml`/`live` marker (excluded from the default offline mock run, like the existing `live` marker) so the default suite stays green without the ML env, OR `importorskip`

## Project Constraints (from CLAUDE.md)

- **Runtime:** Claude Code first; avoid hard deps blocking opencode portability. Scripts self-locate (`Path(__file__)`), take `--workspace`, are stdlib-only, non-interactive (argparse in / exit-code out). New scripts MUST follow this.
- **Dependencies:** No dependency on external skills. Study shepsci/kaggle-skill for structure only; do not import.
- **No runtime `pip install`** — declare deps, validate presence, instruct `uv sync`. The one ML step runs under `uv run --no-sync`.
- **No fabricated/AI-hand-written numbers** — tooling writes numbers from a machine-checked `result.json` (EXP-04). Enum/tooling-written config fields via `set_config_field`; the AI never free-types a value.
- **Kaggle-image parity** — declare floors, not newest majors (pandas≥2.2, numpy≥1.26, sklearn≥1.5).
- **Security:** never echo/log/commit credentials; stage provenance by explicit path (never `git add -A` — the leak guard trips on `control/raw/last-error.txt`). Phase 3 makes no network calls.
- **`enable_internet` / kernels:** out of scope this phase (Phase 4).
- **SKILL.md ≤ ~500 lines, progressive disclosure:** add new rows to the Scripts table + a "Local experiment loop" section; keep heavy detail in `references/`.

## Sources

### Primary (HIGH confidence)
- Codebase (read this session): `scripts/{cv_evidence,analyze_data,init_workspace,capture_competition,competition_doc,kaggle_gateway}.py`, `scripts/templates/{config.json,state.json,strategy.md,pyproject.toml,gitignore,competition.md}.tmpl`, `SKILL.md`, `tests/conftest.py`, `tests/test_config.py`, repo `pyproject.toml`, `.planning/config.json` — established conventions, D-05 flow, reserved-null/`set_config_field` write path, `uv run --no-sync` posture, explicit-path git staging, exit-code gate protocol.
- scikit-learn official docs (WebSearch verified this session): `root_mean_squared_error`/`root_mean_squared_log_error` added 1.4; `cohen_kappa_score(weights="quadratic")`; `get_scorer_names`; latest 1.9.0 — https://scikit-learn.org/stable/modules/model_evaluation.html
- Live tool checks this session: `python3` stdlib presence (`hashlib`,`uuid`,`statistics`,`math`), `git rev-parse HEAD`, `math.isfinite(nan/inf)`, `jupytext 1.19.4`, `uv 0.11.14`, `python 3.13.13`.

### Secondary (MEDIUM confidence)
- `CLAUDE.md` §Supporting Libraries / §Version Compatibility / §What NOT to Use / §Stack Patterns — ML stack versions (PyPI-verified 2026-07-09), floors-not-majors guidance, no-runtime-install posture.
- `.planning/{ROADMAP,REQUIREMENTS,PROJECT}.md` + phase 01/02 CONTEXT.md — locked decisions and success criteria.

### Tertiary (LOW confidence — flagged for validation)
- Kaggle `kaggle/python` image live pins (WebSearch surfaced Kaggle/docker-python but exact 2026 pins not parsed) — A1, re-verify at Phase-4 implementation: https://github.com/Kaggle/docker-python/releases
- Live PyPI versions (pip unavailable in sandbox) — A2, Wave-0 env task pins actuals.

## Metadata

**Confidence breakdown:**
- Standard stack (skill plumbing / stdlib): HIGH — mirrors existing verified scripts.
- Metric registry + `run_cv` design: HIGH — sklearn API facts re-verified live; leakage-safe-by-construction is a well-established pattern.
- Ledger / provenance / strategy design: HIGH — pure stdlib, confirmed primitives.
- ML stack versions: MEDIUM — CITED from CLAUDE.md (2 days stale); Kaggle-image parity MEDIUM (Phase-4 concern).
- Package legitimacy: MEDIUM — slopcheck unavailable; canonical packages CITED.

**Research date:** 2026-07-11
**Valid until:** ~2026-08-10 for the design (stable); re-verify ML versions + Kaggle-image pins at Phase-4 start (fast-moving).
