# Architecture Research

**Domain:** AI-driven Kaggle competition experimentation framework, delivered as a Claude Code skill
**Researched:** 2026-07-09
**Confidence:** HIGH on Kaggle mechanics (verified vs official Kaggle CLI docs + `shepsci/kaggle-skill` reference package audited 2026-05); MEDIUM-HIGH on the workspace/ledger design (opinionated synthesis, not yet validated by a shipped loop)

## Standard Architecture

The system has **two distinct layers that must never be conflated**:

- **Layer A — the SKILL PACKAGE** is code + docs the skill author ships and versions. It is installed read-only (into the plugin/skills cache) and is *stateless with respect to any competition*. It contains the orchestration brain (`SKILL.md`), deterministic helper scripts, reference docs, egress config, and the templates used to scaffold a workspace.
- **Layer B — the WORKSPACE** is user data + generated artifacts the skill *operates on*. It is created in the user's empty folder, has its own git repo, and holds all mutable state: config, the three context files, the ledger, and one directory per experiment.

The skill takes the workspace path as its operating context (CWD). One installed skill drives many independent workspaces (one per competition).

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  LAYER A — SKILL PACKAGE (installed, read-only, competition-agnostic)  │
├──────────────────────────────────────────────────────────────────────┤
│  .claude-plugin/plugin.json      .claude/settings.json (egress + hook) │
│  skills/kaggle-lab/                                                    │
│    SKILL.md .............. router / orchestration brain (frontmatter)  │
│    scripts/ ............. deterministic tooling (the "components")     │
│       ├ init_workspace.py      ├ kaggle_gateway.py  (CLI wrapper)      │
│       ├ ledger.py              ├ run_local.py                         │
│       ├ run_kernel.py          ├ submit.py                            │
│       └ rebuild_ledger.py      └ capture_context.py                   │
│    references/ .......... on-demand docs (CLI cheatsheet, CV playbook, │
│       │                    kernel-metadata schema, ledger spec)        │
│    templates/ ........... workspace scaffold sources (notebook.ipynb,  │
│                            competition.md, strategy.md, config.json,   │
│                            meta.schema.json, .gitignore, README)       │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │  operates on (path arg / CWD)
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  LAYER B — WORKSPACE (user's folder, own git repo, all mutable state)  │
├──────────────────────────────────────────────────────────────────────┤
│  .kaggle-lab/  config.json · ledger.jsonl · state.json  ← control plane │
│  context/      competition.md (static) · strategy.md (living)          │
│  experiments/  exp-NNNN-slug/ { experiment.md, meta.json, notebook,    │
│                 kernel-metadata.json?, artifacts/ }                    │
│  data/         <comp-slug>/  (gitignored, local runs only)             │
│  submissions/  submissions.jsonl                                       │
│  .gitignore · README.md                                                │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │  Kaggle CLI (single egress choke point)
                                 ▼
        ┌──────────────────────────────────────────────────┐
        │  Kaggle.com — competition data · KKB kernels (GPU) │
        │  · leaderboard · submissions                       │
        └──────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Layer | Responsibility | Typical Implementation |
|-----------|-------|----------------|------------------------|
| **SKILL.md router** | A | Map user intent ("run next experiment", "switch to kernel", "submit best") to scripts/orchestration; hold the workflow narrative | Markdown skill with frontmatter (`allowed-tools: Bash Read Write WebFetch`) |
| **Workspace Scaffolder** | A→B | Turn an empty folder into a valid workspace: dirs, `config.json`, empty context files from templates, `git init`, `.gitignore` | `init_workspace.py` copying `templates/` |
| **Kaggle Gateway** | A | Sole wrapper over the Kaggle CLI: auth check, data download, kernel push/status/output/pull, competition submit/leaderboard. All egress funnels here | `kaggle_gateway.py` shelling to `kaggle` CLI |
| **Context Manager** | A on B | Read/write the three context files; keep them small and well-formed for AI consumption | `capture_context.py` + conventions in SKILL.md |
| **Ledger** | A on B | Append/update/query per-experiment records; keep `ledger.jsonl` as a derived index over `meta.json` files | `ledger.py`, `rebuild_ledger.py` |
| **Notebook Authoring / Template** | A→B | Scaffold a fresh notebook per experiment with a backend-agnostic data-path cell, CV harness, and artifact-writing contract | `templates/notebook.ipynb`; AI fills the idea-specific cells |
| **Execution Runner (adapter)** | A on B | Common contract with two impls: `LocalRunner`, `KernelRunner`. Dispatch → monitor → retrieve artifacts into `experiments/…/artifacts/` | `run_local.py`, `run_kernel.py` |
| **Experiment Orchestrator** | A on B | Drive the lifecycle state machine; write `state.json` for resumability; sequence context/ledger/git updates | logic in SKILL.md + a thin `cycle.py` |

## Recommended Project Structure

### Layer A — skill package (what the author versions)

```
kaggle-lab/                        # the plugin repo
├── .claude-plugin/plugin.json     # plugin manifest, points at skills/
├── .claude/settings.json          # egress allowlist + SessionStart credential hook
├── skills/kaggle-lab/
│   ├── SKILL.md                   # router + workflow; frontmatter declares allowed-tools
│   ├── scripts/                   # deterministic, testable tooling
│   ├── references/                # docs the AI Reads on demand (keep out of context until needed)
│   └── templates/                 # sources copied into a new workspace
├── tests/                         # unit tests on ledger/runner/gateway; a live e2e smoke
├── README.md · LICENSE · PRIVACY.md
```

### Layer B — scaffolded workspace (what the user versions)

```
<workspace>/                       # empty folder → git repo
├── .kaggle-lab/                   # framework control plane (small, always git-tracked)
│   ├── config.json                # execution target, comp slug, username, CV scheme, paths
│   ├── ledger.jsonl               # append/update index — one compact line per experiment
│   └── state.json                 # in-flight run cursor for resumability
├── context/
│   ├── competition.md             # STATIC facts (schema, metric, limits, rules) — rarely edited
│   └── strategy.md                # LIVING plan (current best, hypothesis queue, next action)
├── experiments/
│   └── exp-0007-lgbm-target-encoding/
│       ├── experiment.md          # prose card: hypothesis + written verdict (human source of truth)
│       ├── meta.json              # canonical structured record for this experiment
│       ├── notebook.ipynb         # AI-authored, backend-agnostic
│       ├── kernel-metadata.json   # present only if run on a kernel
│       └── artifacts/
│           ├── cv_scores.json     # per-fold + mean/std (tiny, git-tracked)
│           ├── oof.parquet        # out-of-fold preds (large → gitignored by default)
│           ├── submission.csv     # generated predictions (git-tracked; small)
│           └── run.log            # stdout/stderr or pulled kernel log
├── data/<comp-slug>/              # downloaded competition data — GITIGNORED, local runs only
├── submissions/submissions.jsonl  # every submit: exp id, file hash, LB score, timestamp
├── .gitignore                     # data/, *.parquet, credentials
└── README.md                      # generated usage notes
```

### Structure Rationale

- **`.kaggle-lab/` as a control plane:** small, always-tracked files (config + index + cursor) separated from bulky per-experiment content. This is the first thing the AI and any resume logic read.
- **Three context files with different volatility (the core design decision):** `competition.md` = write-once facts; `ledger.jsonl` = append-only history; `strategy.md` = rewritten each cycle. Splitting by change-frequency keeps AI context small — a new cycle reads facts + plan + the *tail* of the ledger, never the whole experiment corpus.
- **One directory per experiment, immutable after close:** each idea gets a fresh folder and a fresh notebook. Nothing is edited in place across experiments, so git history reads as a clean sequence of attempts and the AI never confuses "what I tried" with "what I'm trying."
- **`meta.json` is canonical, `ledger.jsonl` is derived:** avoids the classic duplication trap (see anti-patterns).

## Architectural Patterns

### Pattern 1: Execution backend as a swappable adapter

**What:** `LocalRunner` and `KernelRunner` implement one contract — *given an experiment dir + competition slug, produce `artifacts/` (cv_scores.json, submission.csv, run.log) and a terminal status.* The orchestrator, ledger, verdict, and submission steps are backend-agnostic. Divergence is confined to a single band of the lifecycle (`authored → running → results_captured`).

**When to use:** Always. It is what makes "execution target set at init, changeable anytime, globally or per-experiment" a one-line config/override rather than two parallel workflows.

**Trade-offs:** The notebook template must honor a backend-neutral data-path convention (Pattern 2), which is a small tax on the template. Payoff: everything downstream of the run is written once.

### Pattern 2: Backend-agnostic data-path resolution in the notebook

**What:** Every authored notebook begins with a fixed resolver cell so the *same* notebook runs locally or on a kernel unchanged:

```python
import os
INPUT_DIR = "/kaggle/input/<comp-slug>" if os.path.isdir("/kaggle/input") else os.environ["KLAB_DATA_DIR"]
```

Local runs export `KLAB_DATA_DIR=../../data/<comp-slug>`; kernels expose `/kaggle/input/<comp-slug>` automatically because the slug is listed in `competition_sources`. Artifacts are always written to a `./` working dir that both backends map back into `experiments/…/artifacts/`.

**When to use:** Every experiment. It is the linchpin of the write-once-run-either-backend property.

**Trade-offs:** Assumes the competition attaches cleanly under `/kaggle/input/<slug>`; multi-source or externally-hosted data needs an explicit override in `config.json`.

### Pattern 3: Ledger as a derived index; git as the content store

**What:** git holds full history + diffs of notebooks, `experiment.md`, `meta.json`, and context files. `ledger.jsonl` is a *projection* — the handful of fields the AI needs to reason across all experiments at once — and is fully regenerable from the `meta.json` files via `rebuild_ledger.py`. Each ledger line carries the `git_commit` sha that produced it, linking index → exact tree state.

**When to use:** Always. The ledger is the "small context" surface; git is the audit trail.

**Trade-offs:** Two representations of overlapping fields. Mitigated by the hard rule *write `meta.json` first, then (re)derive the ledger line* — never hand-edit the ledger.

### Pattern 4: Run cursor for idempotent, resumable cycles

**What:** `state.json` records the single in-flight experiment and its lifecycle phase, backend, kernel slug, and dispatch time. Transitions persist `state.json` *before* the side-effect where feasible; on resume the orchestrator reads it and continues any non-terminal experiment. Kernel runs survive context resets because the kernel keeps executing on Kaggle — resume just re-polls `kaggle kernels status`.

**When to use:** Every cycle, but load-bearing for kernel runs (minutes to hours, async).

**Trade-offs:** One-experiment-at-a-time cursor keeps v1 simple; parallel experiments would need a cursor list.

## Data Flow

### Cycle flow (the experiment lifecycle state machine)

```
                         ┌──────────────────────────── strategy.md read (plan) ┐
[new cycle] ─ read: competition.md (facts) + strategy.md + tail(ledger.jsonl) ──┘
     ↓
(1) proposed          → write experiment.md stub + meta.json{status:proposed}; append ledger line
     ↓
(2) authored          → AI writes notebook.ipynb from template; pick target (config default | per-exp override)
     ↓
(3) running  ── LOCAL ─────────────────────────────┐   ── KERNEL ─────────────────────────────┐
     │   ensure data: kaggle competitions download   │  emit kernel-metadata.json               │
     │   run notebook (nbconvert/papermill/py)        │  kaggle kernels push -p <exp dir>        │
     │   artifacts land directly in artifacts/        │  poll: kaggle kernels status (loop)      │
     │                                                │  kaggle kernels output/pull → artifacts/ │
     └───────────────────────────┬────────────────────┴──────────────┬───────────────────────────┘
                                  ▼                                    ▼
(4) results_captured  → parse cv_scores.json → meta.json.cv (mean/std/folds)
     ↓
[optional, GATED] submitted → kaggle competitions submit -c SLUG -f artifacts/submission.csv
     │                         → record LB in submissions.jsonl + meta.json.lb; track CV→LB gap
     ↓
(5) verdict_written   → AI writes verdict (worked|didn't|inconclusive + why) to experiment.md + meta.json
     ↓
(6) ledger_updated    → rebuild/update ledger line from meta.json; git commit (checkpoint)
     ↓
(7) strategy_updated  → patch strategy.md (current best? re-rank hypothesis queue; set next action); git commit
```

**Local vs kernel divergence (confined to steps 3–4):**

| Concern | Local (default) | Kaggle Kernel (GPU) |
|---------|-----------------|---------------------|
| Data provisioning | `kaggle competitions download -c SLUG -p data/SLUG` once (delivered as zip; unzip locally) | Attach on Kaggle via `competition_sources:["SLUG"]` in `kernel-metadata.json`; **no local download** |
| Notebook data path | `KLAB_DATA_DIR` → `data/SLUG` | `/kaggle/input/SLUG` (auto) |
| Dispatch | run notebook/script in-process | `kaggle kernels push -p <exp dir>` |
| Compute | local CPU/GPU, synchronous | KKB free GPU/TPU (`enable_gpu`, `--accelerator`), **asynchronous** |
| Progress | exit code | poll `kaggle kernels status` until `complete`/`error` |
| Artifact retrieval | already on disk | `kaggle kernels output OWNER/SLUG -p artifacts/` (+ `kernels pull -m` for executed nb + log) |
| Resumability | not resumable — restart on interrupt | resilient — kernel runs server-side; resume = re-poll |
| Failure modes | env/dep errors | quota exhaustion, kernel timeout, queue wait, no-internet-by-default |

**Submission is backend-independent.** Whichever backend produced `artifacts/submission.csv` (kernel output is pulled back to the same path), submission always routes through the CLI: `kaggle competitions submit -c SLUG -f artifacts/submission.csv -m "<exp-id>: <hypothesis>"`, then LB is read via `kaggle competitions submissions`/`leaderboard`. This decouples "where it ran" from "how it's scored on the LB."

### Git ↔ ledger interaction (avoiding duplication)

```
meta.json (canonical, per experiment) ──derive──▶ ledger.jsonl line (compact projection)
        │                                                   │
        └── git tracks full content + diffs                 └── carries git_commit sha back to the tree
rebuild_ledger.py: ledger.jsonl := f(all meta.json)   # idempotent source-of-truth rebuild
```

- **git tracks:** notebooks, `experiment.md`, `meta.json`, context files, `config.json`, small artifacts (`cv_scores.json`, `submission.csv`). **Does not track:** `data/` (gitignored), large binaries (`*.parquet` gitignored by default; git-lfs optional).
- **ledger indexes:** id, one-line hypothesis, target, cv (mean/std), lb, verdict, status, parent (lineage), created, commit. It is the AI's cross-experiment reasoning surface so it never re-proposes a tried idea *without reading every folder*.
- **No hand-maintained duplication:** write `meta.json`, then derive the ledger line. If they ever diverge, `rebuild_ledger.py` regenerates the ledger from the folders.

### Concrete schemas

`meta.json` (canonical per experiment):
```json
{
  "id": "exp-0007", "slug": "lgbm-target-encoding",
  "status": "closed",           // proposed|authored|running|results_captured|verdict_written|closed|failed
  "hypothesis": "Target-encoding high-cardinality categoricals beats one-hot on CV.",
  "parent": "exp-0004",         // lineage
  "execution_target": "local",  // local|kernel  (per-experiment override of config default)
  "notebook": "notebook.ipynb",
  "cv": { "metric": "auc", "mean": 0.9123, "std": 0.0031,
          "folds": [0.910,0.914,0.913,0.909,0.916], "scheme": "5-fold stratified, seed 42" },
  "lb": { "score": 0.9098, "submitted_at": "2026-07-09T13:22:00Z" },   // null unless submitted
  "verdict": "worked",          // worked|didnt|inconclusive
  "verdict_note": "CV +0.004 vs one-hot; CV→LB gap small (0.0025).",
  "artifacts": { "cv": "artifacts/cv_scores.json", "oof": "artifacts/oof.parquet",
                 "submission": "artifacts/submission.csv", "log": "artifacts/run.log" },
  "kernel": { "slug": "myuser/kaggle-lab-titanic-exp0007" },   // null for local
  "created_at": "2026-07-09T12:00:00Z", "updated_at": "2026-07-09T13:30:00Z",
  "git_commit": "a1b2c3d"
}
```

`ledger.jsonl` line (projection — one per experiment, kept compact for context):
```json
{"id":"exp-0007","hyp":"TE high-card cats beats one-hot","tgt":"local","cv":0.9123,"cv_std":0.0031,"lb":0.9098,"verdict":"worked","status":"closed","parent":"exp-0004","created":"2026-07-09","commit":"a1b2c3d"}
```

`config.json` (workspace defaults; per-experiment `meta.json` overrides):
```json
{
  "competition": "titanic", "kaggle_username": "myuser",
  "execution_target": "local",
  "metric": "auc", "metric_direction": "maximize",
  "cv": { "scheme": "stratified_kfold", "folds": 5, "seed": 42 },
  "data_dir": "data/titanic",
  "kernel": { "accelerator": "NvidiaTeslaT4", "enable_gpu": true, "enable_internet": false },
  "submission": { "daily_limit": 5 }
}
```

`state.json` (resumability cursor):
```json
{ "active_experiment": "exp-0008", "phase": "running:kernel",
  "kernel_slug": "myuser/kaggle-lab-titanic-exp0008",
  "dispatched_at": "2026-07-09T13:00:00Z", "last_poll": "2026-07-09T13:05:00Z" }
```

### Context-management data flow (keeping AI context small)

1. **Start of cycle:** read `competition.md` (bounded facts) + `strategy.md` (bounded plan) + `tail(ledger.jsonl)` (recent history). Open individual `experiment.md`/`meta.json` only when a specific prior experiment is relevant.
2. **End of cycle:** append/update one ledger line; patch `strategy.md` (never append unboundedly — rewrite the queue, keep "what's working/not" distilled).

## Scaling Considerations

"Scale" here is **experiment count and data size**, not users.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1–30 experiments | Everything as designed; read full ledger freely. Monolithic scripts are fine. |
| 30–200 experiments | Read only `tail(ledger.jsonl)` + `strategy.md` by default; strategy doc must aggressively distill (drop dead branches). Consider a `ledger.py query` summarizer (top-K by CV, by lineage). |
| 200+ experiments / large data | Ledger stays flat (jsonl scales fine); risk is *context*, not storage. Add ledger compaction/rollups per theme. Large `data/` and `oof.parquet` never enter git; prefer kernel runs to avoid repeated local downloads. |

### Scaling Priorities

1. **First bottleneck — AI context, not compute.** The ledger + strategy doc must summarize, not accumulate. Bound what a cycle reads.
2. **Second bottleneck — submission budget.** CV-first discipline + a submissions dedup/rationing check protect the daily limit long before compute matters.
3. **Third — local data footprint.** Repeated multi-GB downloads; mitigate by caching `data/` and defaulting heavy competitions to kernels.

## Anti-Patterns

### Anti-Pattern 1: Storing workspace state inside the skill package
**What people do:** Write ledger/config/artifacts into the installed skill directory.
**Why it's wrong:** Breaks multi-competition use, is wiped on skill upgrade, and mixes read-only code with mutable data.
**Do this instead:** Skill scripts take the workspace path (CWD); all state lives in Layer B under the user's own git repo.

### Anti-Pattern 2: Hand-maintaining both `meta.json` and the ledger
**What people do:** Update the ledger line and the experiment record independently.
**Why it's wrong:** Guaranteed drift; the AI reasons over a stale index.
**Do this instead:** `meta.json` is canonical; the ledger is derived and rebuildable (`rebuild_ledger.py`).

### Anti-Pattern 3: Hardcoding data paths in notebooks
**What people do:** Bake `/kaggle/input/...` or a local path into the authored notebook.
**Why it's wrong:** The notebook then runs on only one backend, defeating "changeable anytime."
**Do this instead:** The Pattern 2 resolver cell; backend chosen at dispatch, not authoring.

### Anti-Pattern 4: Treating LB as the primary signal
**What people do:** Submit every experiment and rank by leaderboard score.
**Why it's wrong:** Burns the daily budget and overfits the public LB (CV→LB gap ignored).
**Do this instead:** CV-first — CV mean/std is the decision signal; submit only to calibrate the gap; record every submit.

### Anti-Pattern 5: Editing one notebook in place across experiments
**What people do:** Mutate a single notebook and re-run.
**Why it's wrong:** Destroys the "what have I tried" history the whole framework exists to preserve.
**Do this instead:** Fresh immutable folder + fresh notebook per experiment; lineage via `parent`.

### Anti-Pattern 6: Unbounded strategy/ledger growth
**What people do:** Append forever to `strategy.md` and read the whole ledger every cycle.
**Why it's wrong:** Blows the AI context window — the exact failure the three-file split is meant to prevent.
**Do this instead:** Rewrite `strategy.md` each cycle (distill, don't append); read the ledger tail + targeted queries.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Kaggle CLI/API | All calls through the single **Kaggle Gateway** module | Rules must be accepted once via the Kaggle **UI** before any submit — there is no CLI "join". `competitions download` delivers a **zip** (no `--unzip` in CLI ≥1.8). |
| Kaggle Kernels (KKB) | `kernels push` → `status` poll → `output`/`pull`; config via `kernel-metadata.json` | Kernel slug derived deterministically from experiment id so re-push **updates** (idempotent) rather than duplicating. `enable_internet` defaults off; pip installs on kernels need it on. |
| git | User's workspace repo; one commit per lifecycle checkpoint | Content store + audit trail; `.gitignore` excludes `data/`, large artifacts, credentials. |
| Credentials (`~/.kaggle/`) | SessionStart hook + a credential-check script; egress allowlisted in `settings.json` | Never echo/log/commit token values. Egress scoped to `*.kaggle.com`, `storage.googleapis.com`, PyPI. |

**Edge case to flag for the roadmap:** *Code Competitions* accept **only notebook submissions** (the kernel is re-run against hidden test data), not CSV-via-CLI. v1's CLI-CSV submit path targets standard competitions; detect code-competitions at context capture and either warn or route submission through the kernel. Note this in PITFALLS.

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Orchestrator ↔ Runner | Adapter contract (dir + slug in → artifacts + status out) | The only place local/kernel differ; keep it thin. |
| Ledger ↔ meta.json | One-way derive (`meta.json` → ledger line) | Never the reverse; rebuild is idempotent. |
| Context Manager ↔ AI | The three files are the shared memory | Volatility-partitioned to bound context. |
| Runner ↔ Kaggle Gateway | Kernel runner calls Gateway; local runner does not touch the network except for the one-time data download | Single egress choke point. |

## Suggested Build Order (dependency-respecting)

Aligned to the PROJECT core value: *one clean end-to-end local cycle first.*

1. **Skill skeleton + egress + credential check** — `plugin.json`, `settings.json` (Kaggle/PyPI allowlist + credential hook), SKILL.md stub, Kaggle Gateway auth slice. *Unblocks everything.*
2. **Workspace Scaffolder + config schema + context templates** — empty folder → valid workspace, `git init`. *(Requirement: initialize workspace.)*
3. **Kaggle Gateway: data download + context capture** — populate `competition.md` (metric, schema, limits, rules) from the competition overview; download data for local runs. *Depends on 1–2.*
4. **Ledger + per-experiment record schema** — `meta.json` + `ledger.jsonl` + `rebuild_ledger.py`. *Depends on 2.*
5. **Notebook template + Local Runner + CV harness** — backend-agnostic notebook, `run_local.py`, CV-scores artifact contract. *Depends on 2–4.*
6. **Experiment Orchestrator (local end-to-end)** — wire proposed→authored→running(local)→results→verdict→ledger→strategy, with `state.json`. **← MVP / core-value milestone.** *Depends on 3–5.*
7. **Kernel Runner** — `kernel-metadata.json` generation (`competition_sources`, GPU), push/poll/fetch, `/kaggle/input` path. *Depends on 6 + Gateway; adds the GPU path without touching downstream steps.*
8. **Submission flow** — CLI submit, `submissions.jsonl`, LB capture, CV→LB gap into strategy, dedup/rationing against the daily limit. *Depends on 6 (backend-independent).*
9. **Resumability hardening** — `state.json` cursor semantics, kernel re-poll on resume, submission dedup by file hash, `rebuild_ledger` recovery. *Depends on 6–8.*

Dependency shape: **1 → 2 → {3,4} → 5 → 6** is the critical path to the first working cycle; **7, 8, 9** layer on independently because the adapter and derived-ledger patterns keep everything after the run backend-agnostic.

## Sources

- `shepsci/kaggle-skill` v2.3.0 reference package (SKILL.md, `.claude/settings.json`, `plugin.json`, kllm scripts `cli_execute.sh`/`poll_kernel.sh`/`cli_competition.sh`, `references/cli-reference.md`) — HIGH confidence, audited 2026-05. Package structure, egress config, kernel/competition CLI mechanics, `kernel-metadata.json` schema.
- [Kaggle CLI docs — kernels & kernel metadata](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md) and [Kernel Commands (DeepWiki)](https://deepwiki.com/Kaggle/kaggle-api/4.3-kernel-commands) — HIGH confidence. `competition_sources` attaches competition data server-side; push/status/output flow.
- [Kaggle Competition Documentation](https://www.kaggle.com/docs/competitions) and [Code Competitions — Errors & Debugging](https://www.kaggle.com/code-competition-debugging) — MEDIUM-HIGH. Code-competition notebook-submission constraint; daily submission limits (error submissions count).
- `.planning/PROJECT.md` — project constraints, key decisions, out-of-scope boundaries.

---
*Architecture research for: AI-driven Kaggle competition experimentation framework (Claude Code skill)*
*Researched: 2026-07-09*
