# Requirements: Kaggle Experimentation Framework

**Defined:** 2026-07-09
**Core Value:** One clean end-to-end experiment cycle — from an empty folder to an idea run, its result and reasoning logged to the ledger, and the strategy doc updated.

## v1 Requirements

Requirements for the initial release. Each maps to a roadmap phase.

### Setup

- [ ] **SETUP-01**: User can initialize an experiment workspace in an empty folder (directory layout, config, git init, context-file stubs)
- [ ] **SETUP-02**: User can choose a default execution target (local or Kaggle Kernel) at init, and change it anytime — globally or per-experiment
- [ ] **SETUP-03**: User can connect their Kaggle account via the Kaggle CLI, and the framework validates the credential with a live call
- [ ] **SETUP-04**: Credentials are stored securely and never echoed; network egress is scoped to Kaggle and standard package sources

### Competition

- [ ] **COMP-01**: User can capture static competition context (eval metric, data schema, rules, daily submission limit, correct CV scheme) into a dedicated `competition.md` file at setup
- [ ] **COMP-02**: The framework preflights UI-only Kaggle gates (rules acceptance, phone verification) and gives clear one-time browser instructions on a 403 before the loop's first download/submit
- [ ] **COMP-03**: User can download competition data locally with safe (zip-slip-protected) extraction

### Experiment

- [ ] **EXP-01**: An experiment is represented as an idea + hypothesis, its generated notebook/script, its machine-captured result, and a written verdict (worked / didn't / why)
- [ ] **EXP-02**: The AI authors a fresh notebook/script per experiment from a template scaffold, using a backend-agnostic data-path + result contract so the same code runs locally or on a Kernel
- [ ] **EXP-03**: User can run an experiment locally, producing a cross-validation score and artifacts
- [ ] **EXP-04**: Numeric results are written by tooling (from a machine-checked `result.json`), never hand-written by the AI; every ledger row carries provenance (run id, artifact hash, git commit, seed)
- [ ] **EXP-05**: User can push a notebook to a Kaggle Kernel, run it on Kaggle compute (GPU), poll to completion, and pull results/artifacts back — with silent-failure (traceback-in-log) detection

### Memory

- [ ] **MEM-01**: Every experiment is logged to a structured, git-backed ledger (`meta.json` canonical per experiment + derived `ledger.jsonl` index with score, verdict, artifact links)
- [ ] **MEM-02**: Experiment history lets the AI reason over what's been tried so it never re-proposes an already-tried idea
- [ ] **MEM-03**: A living strategy doc (current best, hypothesis queue, what to try next) is regenerated from the ledger each cycle — never hand-edited

### Scoring

- [ ] **SCORE-01**: User can submit predictions to the competition via the Kaggle CLI and record the resulting LB score
- [ ] **SCORE-02**: CV is the decision metric everywhere; the framework computes and trends the CV→LB gap with a divergence alarm
- [ ] **SCORE-03**: Submissions are rationed against the daily limit; the framework gates submissions on CV improvement and tracks remaining budget

## v2 Requirements

Deferred to a future release. Tracked but not in the current roadmap.

### Analysis & Loop Hardening

- **ANLY-01**: Semantic idea dedup (embedding/fingerprint), beyond v1's prompt-driven never-repeat — add once real duplicate near-misses are observed
- **ANLY-02**: Comparison/summary views over the ledger (best-so-far, deltas, trends)
- **ANLY-03**: Evidence-ranked strategy synthesis that orders the hypothesis queue from observed ledger movement

### Extended Inputs

- **EXT-01**: Writeup/forum-knowledge retrieval feeding the competition-context file
- **EXT-02**: Hyperparameter sweeps as a first-class experiment type
- **EXT-03**: Multi-agent / cross-runtime portability (opencode and other agents)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Dependency on shepsci/kaggle-skill | Building fully standalone; reimplement only the ~6 Kaggle ops the loop needs |
| Badges, forum/writeup discovery, competition-landscape reports | Broad Kaggle-ops surface, not core to the experiment loop |
| Model / dataset publishing | Not part of the competition experiment loop |
| Hosted dashboards / team collaboration | Single-practitioner, file-based, AI-readable tool by design |
| Fully autonomous unsupervised optimization | Human-in-the-loop reasoning is the point; opaque budget-burning agents are the anti-pattern |
| General (non-competition) ML R&D workflows | Competition-optimized for v1 |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SETUP-01 | TBD | Pending |
| SETUP-02 | TBD | Pending |
| SETUP-03 | TBD | Pending |
| SETUP-04 | TBD | Pending |
| COMP-01 | TBD | Pending |
| COMP-02 | TBD | Pending |
| COMP-03 | TBD | Pending |
| EXP-01 | TBD | Pending |
| EXP-02 | TBD | Pending |
| EXP-03 | TBD | Pending |
| EXP-04 | TBD | Pending |
| EXP-05 | TBD | Pending |
| MEM-01 | TBD | Pending |
| MEM-02 | TBD | Pending |
| MEM-03 | TBD | Pending |
| SCORE-01 | TBD | Pending |
| SCORE-02 | TBD | Pending |
| SCORE-03 | TBD | Pending |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 0 (pending roadmap)
- Unmapped: 18 ⚠️

---
*Requirements defined: 2026-07-09*
*Last updated: 2026-07-09 after initial definition*
