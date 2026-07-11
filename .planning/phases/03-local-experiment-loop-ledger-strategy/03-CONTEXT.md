# Phase 3: Local Experiment Loop, Ledger & Strategy - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning

<domain>
## Phase Boundary

The full **idea → run → verdict → ledger → strategy** cycle works end-to-end on **local
compute alone**, CV-only — machine-verified scores, never a fabricated number, never a Kaggle
submission spent. This is the core-value milestone.

**In scope:** EXP-01, EXP-02, EXP-03, EXP-04, MEM-01, MEM-02, MEM-03 — experiment
representation (idea + hypothesis + generated code + machine result + written verdict), the
notebook scaffold with a backend-agnostic data-path resolver + result contract, local CV
execution with fold-internal preprocessing, tooling-written numbers with provenance, the
git-backed ledger (`meta.json` canonical + derived `ledger.jsonl`), never-repeat reasoning,
and ledger-regenerated strategy.

**Explicitly NOT in this phase (boundary guards):**
- **Kernel push/poll/pull is Phase 4 (EXP-05).** Phase 3 creates the machine-checked result
  contract; Phase 4 **extends it (traceback scan), never re-derives it.** The
  `resolve_data_dir()` helper and the result.json contract are authored here so the *same*
  code runs on a kernel later — but no kernel code is written in Phase 3.
- **Submission, budget gating, CV→LB gap tracking are Phase 5 (SCORE-*).** Phase 3 produces
  the CV numbers Phase 5 trends; it never submits.
- **Semantic idea dedup is v2 (ANLY-01).** v1 never-repeat is **prompt-driven** only.
- **Hyperparameter sweeps are out of scope** — an experiment is one idea + one verdict (v1).
- Comparison/summary views over the ledger (ANLY-02) and evidence-ranked queue synthesis
  (ANLY-03) are v2. Phase 3's tried-list is a flat digest, not a ranked analysis.

</domain>

<decisions>
## Implementation Decisions

### Experiment artifact & cycle cadence (EXP-01, EXP-02)

- **D-01: The AI authors a plain `experiment.py`, run locally via `uv run`; converted to
  `.ipynb` with jupytext only at Phase-4 kernel-push time.** Diffable `.py` under git is the
  local source of truth; jupytext is already installed. NOT a locally-executed `.ipynb` (no
  papermill/Jupyter execution stack in the local path), NOT dual `.py`+`.ipynb` maintenance.
  Aligns with CLAUDE.md §"Stack Patterns by Variant" (plain `.py` runs, no Jupyter dependency
  required) and §Supporting Libraries (jupytext for lossless `.py`⇄`.ipynb` at push time).

- **D-02: One cycle = separate, idempotent entry points the SKILL sequences** —
  `scaffold_experiment → run → record → regen_strategy` — mirroring Phase 2's D-09 (three
  idempotent entry points, no orchestrator wrapper). Each step is independently re-runnable
  after a failure without redoing the others (e.g. a failed run doesn't re-scaffold; a fixed
  notebook re-runs without re-recording the prior attempt). NOT a single monolithic
  `run_experiment` orchestrator. Follows the established Phase-2 script-sequencing convention
  and the scripts-stdlib-only / self-locating / `--workspace` contract.

- **D-03: Backend-agnostic data path via a `resolve_data_dir()` helper in the scaffold.**
  The helper prefers `/kaggle/input/<slug>/` if it exists, else the workspace `data/`
  (overridable via `--data-dir`). Backend detection is **code, not config** — the *same*
  `experiment.py` runs locally and on a kernel untouched. This is the EXP-02 "backend-agnostic
  data-path resolver" and the seam Phase 4 reuses (never re-derives). NOT a runner-set
  `KAGGLE_DATA_DIR` env var (would make a bare kernel run depend on the runner replicating it).

### Result contract & failure semantics (EXP-03, EXP-04)

- **D-04: `result.json` carries per-fold scores + mean + std + metric name + n_folds** — not a
  single mean scalar. Preserves CV variance (a stable 0.82±0.005 vs a fragile 0.82±0.08) and
  gives Phase 5's CV→LB gap tracking real material. The ledger row records at least the mean
  (the decision metric) plus the variance.

- **D-05: The notebook WRITES `result.json`; a separate recorder script VALIDATES then
  PERSISTS.** `experiment.py` writes `experiments/exp-NNN/result.json` at a known path; the
  recorder validates its schema and writes the numbers into `meta.json` / `ledger.jsonl`. Clean
  separation — the AI's code *emits*, tooling *verifies-then-persists*. This is the mechanical
  realization of EXP-04 "numeric fields written only by tooling, never hand-written by the AI."
  NOT stdout-scraping for a score line (fragile; no schema to validate; stray prints break it).

- **D-06: FAIL-CLOSED run classification — a run is FAILED if ANY of:** process exits nonzero,
  OR `result.json` is missing, OR `result.json` fails schema validation, OR the score is
  non-finite / outside the metric's valid range. Any single condition trips it. A
  deliberately-throwing notebook — or one that swallows an exception and writes a garbage/half
  score — is recorded as a **failure with a verdict**, never as success (criterion 3). Mirrors
  Phase 2's fail-closed gateway posture. NOT exit-code-only (that's the exact silent-failure
  hole the criterion targets). Phase 4 extends this with a run-log traceback scan; it does not
  weaken it.

### CV harness — enforced leakage-safety + machine metric (criterion 1, EXP-03, EXP-04)

- **D-07: The scaffold ships a `run_cv(...)` harness the AI plugs into.** The harness owns the
  fold loop and applies the AI's `preprocess_fn` **inside each fold** (fit on the train fold,
  transform the val fold), computes the metric, and emits `result.json`. The AI still writes the
  model, features, and preprocessing freely — but anything routed through the harness is
  leakage-safe **by construction**. This reconciles the locked PROJECT decision "AI owns the
  code each cycle / maximum flexibility" with criterion 1's "fold-internal preprocessing
  enforced": the harness is the easy, correct default, not a straitjacket. NOT a
  convention/example-only loop (leakage guarded only by trust — criterion 1 arguably rules that
  out), NOT a mandatory no-escape harness (fights flexibility when a bespoke split is needed).
  ⚠ **Planner tension to hold:** the harness must be flexible enough (custom splitter, custom
  metric callable, group/time-aware splits) that the AI rarely needs to bypass it — otherwise
  D-07 collapses toward "convention only" in practice.

- **D-08: Phase 3 ADDS a tooling-written machine `metric` field to `config.json`** (name +
  direction, e.g. `{"name": "roc_auc", "greater_is_better": true}`), derived from what Phase 2
  captured. The harness reads it to compute the right metric; the D-06 validity-range check and
  the D-11 current-best selection also read it — **one machine source of truth.**
  🔗 **Cross-phase dependency the researcher MUST resolve:** Phase 2's `capture_competition.py`
  wrote the metric into `competition.md` **prose only** — `config.json` currently has
  `cv.scheme`, `submission`, `competition.type` but **no `metric` field**. Phase 3 must
  populate `config.json.metric` mechanically. Decide whether that means (a) a Phase-3 tooling
  step that derives it (with an AI-decides-tooling-persists flow like D-05's `cv.scheme`, since
  metric→sklearn-scorer mapping + direction may be ambiguous), or (b) extending capture. Either
  way the field is **enum/tooling-written, never AI-free-typed**, and must map to a concrete
  scorer + direction the harness can call. Handle the metric-not-captured / unmappable case
  honestly (block, don't guess).

- **D-09: Fixed default seed (e.g. 42) with a per-experiment override.** The default seed drives
  the splitter and the model and is recorded in every experiment's provenance; an experiment may
  deliberately override it (e.g. to probe seed stability) and the override is captured too. So
  two runs of "the same" idea are directly comparable by default. Seed is one of the EXP-04
  provenance fields (alongside run id, artifact hash, git commit). NOT a fresh random seed each
  run.

### Ledger, provenance & experiment folder (MEM-01, EXP-04)

- **D-10: `meta.json` per experiment is canonical; `ledger.jsonl` is a DERIVED index** that
  fully rebuilds from the per-experiment folders (a `rebuild_ledger.py`). Ledger rows carry the
  score/verdict/artifact links; every row carries provenance — **run id, artifact hash, git
  commit, seed** (EXP-04). This matches the roadmap 03-01 suggested plan and D-12 (Phase 1)
  "track code + ledger + docs." `state.json.next_exp_id` (already scaffolded, starts at 1) is
  the id cursor; ids are zero-padded `exp-NNN` (D-11, Phase 1).

### Strategy regeneration & never-repeat (MEM-02, MEM-03)

- **D-11: strategy.md = tooling-rendered FACTS + AI-authored REASONING (hybrid).** Tooling
  renders the mechanical sections from the ledger — **current-best** (the best CV mean by the
  metric's direction from D-08) and the full **tried-list** (idea + score + verdict link). The
  AI authors the reasoning sections — **hypothesis queue** and **next action** — fresh each
  cycle. Facts cannot drift or be fabricated; reasoning stays smart. NOT fully tooling-generated
  (loses the AI judgment that IS the living strategy), NOT fully AI-authored (the current-best
  number would be AI-typed — the exact fabrication risk tooling-writes-numbers prevents).

- **D-12: strategy.md is FULLY OVERWRITTEN each cycle** — deliberately UNLIKE `competition.md`'s
  section-safe-merge. Regeneration replaces the file wholesale (mechanical sections from the
  ledger, reasoning re-authored by the AI as part of the cycle), with a header stating
  "generated each cycle — manual edits are overwritten." MEM-03 wants regeneration, not
  preservation; a stale hand-edit must never survive and drift from the ledger. The regen step
  writes the doc atomically from (tooling facts) + (the AI's freshly-supplied reasoning block).

- **D-13: Never-repeat is prompt-driven over the ledger + tried-list digest (v1).** The AI reads
  the derived `ledger.jsonl` (idea / hypothesis / verdict / score per row) and the
  tooling-rendered tried-list in strategy.md, and is prompted to check any proposed idea against
  that history **before** authoring `experiment.py`. Cheap, and the digest is already produced
  by strategy regen (D-11). NOT re-reading every `VERDICT.md` each cycle (cost grows with every
  experiment; duplicates the ledger row). Semantic/embedding dedup is explicitly deferred to v2
  (ANLY-01) — add only once real duplicate near-misses are observed.

### Claude's Discretion

- **result.json full schema** beyond the D-04 required fields (params/hyperparams block, OOF
  predictions path, artifact manifest, timing) — planner's call; keep it validatable.
- **Experiment-folder contents & immutability enforcement** — the folder holds at least
  `experiment.py`, `result.json`, `meta.json`, `VERDICT.md`, and an `artifacts/` dir
  (criterion 2 "immutable per-experiment folder"). Whether immutability is enforced (e.g.
  read-only after record) or by convention (never rewritten) is the planner's call.
- **VERDICT.md authorship** — the written worked/didn't/why is AI prose (criterion 2); the
  numeric fields it references come from tooling (D-05). Exact template is planner discretion.
- **`run_cv(...)` signature** — how the AI supplies model factory / feature fn / preprocess fn,
  and how a custom splitter or custom metric callable is passed (must satisfy the D-07 tension).
- **Default ML dependency floors added to the workspace `pyproject.toml`** (lightgbm / xgboost /
  catboost per CLAUDE.md) — declared here per D-14/D-06; pick **floors** compatible with the
  Kaggle `kaggle/python` image, NOT newest majors (pandas 3.0 / numpy 2.5.1 are the parity
  traps CLAUDE.md flags). Runtime `pip install` is forbidden — declare, validate presence,
  instruct `uv sync` if absent (degrade-don't-abort, per D-06/D-07 Phase-2 posture).
- **rebuild_ledger.py rebuild semantics** — full rebuild vs incremental append, and how a
  corrupt/partial `meta.json` is handled during rebuild.
- **How the AI's reasoning block reaches the D-12 regen step** (passed as an arg / a temp file /
  a fenced section the tooling reads) — planner's call; must keep the mechanical sections
  tooling-owned.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project intent, scope, and success criteria
- `.planning/ROADMAP.md` §"Phase 3: Local Experiment Loop, Ledger & Strategy" — the fixed phase
  goal, 5 success criteria, and the 4 suggested plans (03-01 ledger schema + provenance;
  03-02 notebook template + path resolver + CV harness + result contract; 03-03 local runner +
  recorder + silent-failure detection; 03-04 orchestrator lifecycle + strategy regen +
  never-repeat).
- `.planning/REQUIREMENTS.md` §Experiment (EXP-01..04) + §Memory (MEM-01..03) — authoritative
  requirement text. Note EXP-05 (kernel) is Phase 4 and SCORE-* is Phase 5 — out of this phase.
- `.planning/PROJECT.md` §"Core Value", §Constraints, §"Key Decisions" — the locked decisions
  this phase must honor: "AI authors a fresh notebook per experiment from a scaffold (maximum
  flexibility; the AI owns the code each cycle)", "Versioning = structured ledger + git",
  "Experiment = idea + hypothesis + result + written verdict", "CV-first scoring", context
  split (static comp file / history / living strategy).

### Prior-phase decisions this phase builds on (READ — the contracts are already locked)
- `.planning/phases/01-workspace-credentials-egress-guardrails/01-CONTEXT.md` — D-10 workspace
  layout (`control/`, `experiments/exp-NNN/`, docs at root), D-11 zero-padded `exp-NNN` ids,
  D-12/D-13 git tracks code+ledger+docs / ignores data+artifacts (`.gitignore` already
  anticipates `experiments/*/` artifacts), D-14 minimal `pyproject.toml` stub (ML stack declared
  HERE in Phase 3).
- `.planning/phases/02-competition-context-data/02-CONTEXT.md` — D-05 "tooling recommends → AI
  reasons → tooling writes" (the pattern D-08's metric field and the whole result contract
  mirror), D-06 "declare ML floor now, degrade gracefully / never runtime pip install",
  the `config.json` shape (`cv.scheme` written, **`metric` NOT yet present** — the D-08 gap).

### Technology stack, skill authoring, and generated-code stack (MANDATORY)
- `CLAUDE.md` — the full prescriptive stack. Specifically for Phase 3:
  - §"Supporting Libraries — Generated-Notebook ML Stack" — sklearn CV splitters
    (`KFold`/`StratifiedKFold`/`GroupKFold`/`TimeSeriesSplit`), LightGBM as default first model,
    xgboost/catboost second, jupytext for `.py`⇄`.ipynb` at push time.
  - §"Experiment Ledger / Tracking — favor plain files" — append-only `ledger.jsonl` (one
    experiment per line), per-experiment `VERDICT.md` markdown, `config.json` for state.
  - §"Stack Patterns by Variant" — local path: data via `kaggle competitions download`, run
    `experiment.py` via `uv run`, CV via `sklearn.model_selection`, emit `result.json`
    (CV score + params) + artifacts, append to `ledger.jsonl`; scripts self-locate
    (`Path(__file__)`), take `--workspace`, stdlib-only.
  - §"Version Compatibility" + §"What NOT to Use" — Kaggle-image parity floors (NOT newest
    majors), no runtime `pip install`, no fabricated/AI-hand-written numbers.

### Existing skill code the new scripts sit beside (reuse the conventions)
- `SKILL.md` — the entry-point sequencing + gate-protocol conventions the new
  scaffold/run/record/regen steps must extend; the "Scripts (progressive disclosure)" table
  gets new rows.
- `scripts/kaggle_gateway.py` — the fail-closed / exit-code / no-echo pattern to imitate for
  new tooling error handling.
- `scripts/templates/config.json.tmpl`, `state.json.tmpl`, `strategy.md.tmpl` — the files
  Phase 3 extends (`config.json` gains `metric`; `strategy.md` becomes regenerated per D-11/D-12;
  `state.json.next_exp_id` is the id cursor).

### External structure-only exemplar (NOT a dependency — do not import or couple to it)
- `~/.claude/plugins/cache/shepsci/kaggle-skill/2.3.0/` — study for structure only; PROJECT.md
  forbids depending on it. Reimplement independently.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`scripts/kaggle_gateway.py`** — the fail-closed, exit-code-only, no-echo, timeout-bounded
  pattern to reuse for the new runner/recorder tooling error handling.
- **`scripts/init_workspace.py`** (safe-merge scaffolder) — the self-locating, `--workspace`,
  stdlib-only, section-safe-merge template-writing pattern to mirror for `scaffold_experiment`.
- **`scripts/analyze_data.py` + `cv_evidence.py`** — the "tooling emits evidence → AI decides
  → tooling persists (enum-validated)" flow (D-05) that D-08's metric field and the result
  contract directly mirror; also the "declare ML floor, degrade to SKIPPED if env absent" posture.
- **`control/config.json` / `state.json` / `strategy.md` templates** — already scaffolded;
  Phase 3 extends them (metric field, regenerated strategy, next_exp_id cursor) rather than
  inventing new state files.
- **`.gitignore`** — already anticipates `experiments/*/` artifact patterns (D-13, Phase 1), so
  the ledger/experiment-folder tracking split is pre-wired; verify it covers the new artifact
  paths.

### Established Patterns
- **Scripts are stdlib-only, self-locating (`Path(__file__)`), take `--workspace`, exit-code
  driven** — but the *generated* `experiment.py` and the `run_cv` harness run under the
  workspace `uv run` ML env (D-06 precedent: plumbing stdlib, ML step under uv). Keep the split.
- **Non-interactive scripts + SKILL holds any human loop** (Phase 2 D-10 gate protocol) — the
  run/record steps stay argparse-in / exit-code-out; the SKILL sequences them.
- **CLAUDE.md is the pattern authority** for stack/versions/security; treat as the conventions doc.

### Integration Points
- `control/config.json` — gains the machine `metric` field (D-08); `cv.scheme` (Phase 2) feeds
  the harness's splitter selection.
- `control/state.json.next_exp_id` — the experiment-id cursor the scaffold step increments.
- `control/ledger.jsonl` + per-experiment `meta.json` — the MEM-01 canonical/derived pair.
- `strategy.md` — flips from a static stub to a per-cycle regenerated doc (D-11/D-12).
- `competition.md` §"Cross-validation scheme" / §"Evaluation metric" — the human-readable
  sources the D-08 machine metric field is reconciled against.

</code_context>

<specifics>
## Specific Ideas

- The `run_cv(...)` harness applying the AI's `preprocess_fn` **inside** each fold is the
  concrete mechanism the user chose for criterion 1 — leakage-safe by construction, not by
  convention. The planner should design its signature so a custom splitter and a custom metric
  callable are first-class (so the AI almost never needs to bypass it — the D-07 tension).
- `result.json` should be honest about variance: **per-fold array + mean + std**, not a lone
  scalar — the user explicitly wanted the fold-level detail preserved for Phase 5.
- The machine `metric` field is `{name, greater_is_better}`-shaped and must resolve to a
  concrete scorer + direction; the metric→scorer mapping is the researcher's key open item
  (see D-08 cross-phase dependency).
- strategy.md's regenerated header must say plainly it is overwritten each cycle (D-12).

</specifics>

<deferred>
## Deferred Ideas

- **Semantic / embedding-based idea dedup** — raised implicitly by the never-repeat discussion;
  explicitly v2 (ANLY-01). v1 stays prompt-driven (D-13). Add once real duplicate near-misses
  are observed.
- **Comparison / summary / best-so-far-delta views over the ledger** — v2 (ANLY-02). Phase 3's
  tried-list is a flat digest, not a ranked/trend analysis.
- **Evidence-ranked hypothesis-queue synthesis** (order the queue from observed ledger movement)
  — v2 (ANLY-03). In v1 the AI orders the queue by judgment (D-11), not from measured deltas.
- **Hyperparameter sweeps as an experiment type** — out of scope (v1 = one idea + one verdict);
  EXT-02 in v2.
- **Kernel execution of the same experiment** — Phase 4 (EXP-05); the result contract and
  `resolve_data_dir()` are built here to be *extended* there, but no kernel code in Phase 3.

</deferred>

---

*Phase: 3-Local Experiment Loop, Ledger & Strategy*
*Context gathered: 2026-07-11*
