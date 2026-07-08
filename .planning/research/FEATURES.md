# Feature Research

**Domain:** AI-driven Kaggle *competition* experimentation framework, delivered as a standalone Claude Code skill (local-first execution + push-to-Kaggle-Kernel, CV-first scoring, ledger + git versioning)
**Researched:** 2026-07-09
**Confidence:** HIGH for the ops surface and shepsci comparison (read the source directly); MEDIUM-HIGH for competition workflow discipline and adjacent-tool feature sets (web-verified + well-established domain practice)

## Orientation: three reference points

Everything below is triangulated against three adjacent tool classes, because "table stakes" only means something relative to what exists:

1. **shepsci/kaggle-skill (v2.3.0)** — a broad Kaggle *operations* toolkit (registration, competition landscape reports, kagglehub/CLI/MCP download+submit+publish, hackathon writeup retrieval, benchmark tasks, badge collection across 5 phases, ~66 MCP tools). It is an **ops surface**, not an experiment loop. We reimplement only the ~5 CLI operations the loop actually needs (auth-check, competition download, kernel push/poll/output, submit, submissions/leaderboard read) and deliberately leave the rest as anti-features.
2. **Generic ML experiment trackers** — MLflow, Weights & Biases, DVC. These are **metric loggers with dashboards + model/data versioning**. They record runs; they do not *reason*, do not propose ideas, do not write verdicts, do not avoid repetition, and know nothing about a Kaggle submission budget. Our ledger is lighter but carries a **reasoning layer** they lack.
3. **Autonomous ML agents** — AIDE (tree search over code solutions), AutoKaggle (multi-agent), MLE-STAR, benchmarked by MLE-bench. These are **fully autonomous, unsupervised optimizers**. Our loop is deliberately the opposite: **human-steerable, documented-reasoning, one-idea-at-a-time**. That distinction is the core of the differentiator and anti-feature sections.

The Core Value from PROJECT.md — *"one clean end-to-end experiment cycle: empty folder → idea run → result + reasoning in the ledger → strategy updated"* — is the yardstick. A feature is table stakes only if that cycle is broken or unusable without it.

## Feature Landscape

### Table Stakes (the loop is unusable without these)

These map 1:1 to the PROJECT.md Active requirements. Each is decomposed with complexity and its hard prerequisites.

| # | Feature | Why Expected (loop-critical role) | Complexity | Notes / implementation |
|---|---------|-----------------------------------|------------|------------------------|
| T1 | **Workspace init / scaffolding** | Turns an empty folder into the workspace; nothing else can be written without the directory layout + config + context-file stubs + `git init` | LOW–MEDIUM | Create `data/`, `experiments/`, `notebooks/`, context files, a workspace config (execution target, competition slug, submission limit), and initialize git. No external deps. Pure filesystem + template rendering. |
| T2 | **Kaggle auth setup + validation** | Every Kaggle operation (download, kernel, submit) fails without valid credentials | LOW | Reimplement shepsci's credential check: detect `~/.kaggle/kaggle.json` / `KAGGLE_API_TOKEN`, `chmod 600`, run a cheap authenticated call (`kaggle competitions list`) to validate. Do **not** rebuild account creation — assume the user has a Kaggle account (see anti-features). |
| T3 | **Static competition-context file** | The AI needs eval metric, data schema, rules, and the submission limit to author correct notebooks and score correctly | MEDIUM | Populate at init from `kaggle competitions files` + competition page content, then let the human/AI fill gaps (exact metric semantics, submission/day limit, forbidden data). Store as a rarely-changing markdown/frontmatter file. This is the AI's "constitution" for the comp. |
| T4 | **Competition data download (local path)** | Local-first is the default execution target; no local run without data | LOW | `kaggle competitions download -c <slug> -p data/` + unzip (note: CLI ≥1.8 dropped `--unzip` for competitions — handle extraction ourselves with zip-slip protection). Gated behind rules acceptance (UI one-time step; surface the URL, cannot be automated). |
| T5 | **Execution-target config (local vs Kaggle Kernel), set at init, overridable globally or per-experiment** | The whole product promises "local by default, push to Kernel for GPU"; the switch must be first-class | MEDIUM | Workspace-level default in config, per-experiment override recorded in the ledger row. Drives which code path (T7 vs T8) an experiment takes and where data lives (local disk vs `competition_sources` attachment). |
| T6 | **Experiment representation + fresh-notebook scaffold** (idea + hypothesis → generated notebook/script → result → verdict) | This is the atomic unit the entire framework reasons over; the AI authors a fresh notebook each cycle from a template | MEDIUM | Define the experiment schema (id, idea, hypothesis, target, exec-target, notebook path, CV score, LB score, verdict, artifacts, git SHA, timestamp). Ship a notebook/script scaffold that bakes in the CV harness convention and reads the static context file. The AI owns the body; the scaffold enforces structure so results are comparable. |
| T7 | **Run an experiment locally → CV score + artifacts** | The default, fast iteration path; produces the primary signal (CV) | MEDIUM–HIGH | Execute the generated notebook/script locally, enforce a k-fold CV convention, capture the CV score in a machine-readable form (e.g., a metrics JSON the scaffold writes), and persist artifacts (OOF preds, model, submission CSV). The hard part is a **reliable score-capture contract** so every experiment reports comparably. |
| T8 | **Push notebook to Kaggle Kernel, run on GPU, pull results** | The GPU / heavy-compute path and the route for official runs | HIGH | Generate `kernel-metadata.json` (id, code_file, `enable_gpu`, `enable_internet`, `competition_sources`), `kaggle kernels push`, **poll `kaggle kernels status`** (30s loop, parse complete/error), then `kaggle kernels output` + `kernels pull --metadata`. Reconcile pulled artifacts into the same score-capture contract as T7. Most failure-prone surface: metadata correctness, data attachment, long polling, quota limits. |
| T9 | **Submit predictions + record LB score** | The only way to get the real leaderboard signal; must be logged | MEDIUM | `kaggle competitions submit -c <slug> -f <csv> -m <msg>`, then poll `kaggle competitions submissions` (submission scoring is async) to read back the public LB score and write it onto the experiment's ledger row. Always routes through the CLI regardless of where code ran. |
| T10 | **Structured experiment ledger, git-backed** | The queryable memory of every experiment; the substrate for history-reasoning, strategy, and summaries | MEDIUM | Append-per-experiment structured store (JSONL or a table of frontmatter files) holding metadata + CV + LB + artifact links + verdict + git SHA. Commit each experiment so code history is diffable underneath. Schema stability matters — downstream features (D-series) read this. |
| T11 | **Living strategy doc, AI-updated each cycle** | Human + AI's shared plan: current best, hypothesis queue, what to try next | LOW–MEDIUM | A markdown doc the AI rewrites at cycle close from the ledger state. Low mechanical complexity; value comes from the update *prompt discipline*, not the file format. |
| T12 | **Experiment-history reasoning (never re-propose a tried idea)** | Prevents the AI from wasting cycles/budget repeating itself — a real failure mode of naive LLM loops | MEDIUM | Before proposing, the AI reads the ledger's idea/hypothesis/verdict history and checks the new idea against it. v1 can be prompt-driven (feed history, instruct "do not repeat"); the ledger's structure is what makes this tractable. |

### Differentiators (why the AI-driven loop beats manual notebooks and beats generic trackers)

Generic trackers (MLflow/W&B/DVC) log numbers. Autonomous agents (AIDE/AutoKaggle) optimize blindly. The wedge here is **documented, competition-aware reasoning that a human stays in the loop of**. These features are where that value lives.

| # | Feature | Value Proposition | Complexity | Notes |
|---|---------|-------------------|------------|-------|
| D1 | **Idea → verdict reasoning capture** ("worked / didn't / why", written) | This is the product's soul. MLflow/W&B record `metric=0.87`; they never record *why you tried it or what you concluded*. The written verdict is what makes the history worth reasoning over and turns a run log into institutional memory. | MEDIUM | Enforce a verdict field per experiment (not optional). The verdict cites the CV/LB delta and states a conclusion + implication for next moves. This is mostly a **schema constraint + prompt contract**, cheap to build, high in value. Depends on T6/T10. |
| D2 | **Never-repeat memory / idea dedup** | Turns T12 from "don't repeat" into "actively surface what's already been tried and how it went." Prevents budget-burning loops that plague naive agent scaffolds. | MEDIUM | v1: history-in-context + explicit dedup instruction. v1.x: lightweight semantic similarity over past idea/hypothesis text to flag near-duplicates before a run. Depends on T10/T12. |
| D3 | **CV→LB gap tracking** | The single most important discipline in solo Kaggle: *trust your CV, don't overfit the public LB*. Recording both signals and the gap per submission catches leakage, metric misalignment, and public-LB overfitting early. **No generic tracker has any notion of this** — it is competition-native. | MEDIUM | Store CV and LB on the same row, compute the gap, trend it across experiments, and flag anomalies (gap widening → suspect leakage or shakeup risk). Depends on T7+T9 both feeding T10. |
| D4 | **Submission-budget awareness** | Kaggle rations submissions per day. The biggest lever is *number of high-quality experiments*, not probing the LB. Gating submissions on CV improvement and tracking daily budget used/remaining conserves the scarce resource and encodes the CV-first doctrine. | MEDIUM | Track submissions used vs the daily limit (from T3), warn/refuse when a submission wouldn't beat current best CV, and record budget state per day. Depends on T3 (limit), T9 (submit events), T10 (history). |
| D5 | **Comparison / summary views over the ledger** | "Best-so-far, what moved the needle, deltas between experiments" — the analysis a human would otherwise reconstruct by hand from scattered notebooks. Turns the ledger into insight. | MEDIUM | AI-generated (and/or scripted) leaderboard-of-experiments, ranked by CV, with LB gaps and verdict digests. Read-only over T10; safe to build last. |
| D6 | **Strategy synthesis from history** (hypothesis queue prioritization) | Elevates T11 from "a doc the AI edits" to "a prioritized next-move plan derived from what the ledger proves." | MEDIUM | The AI ranks the open hypothesis queue using observed CV movement and verdicts. Depends on T10/T11 + D1 verdicts. |

**Design note:** D1–D6 are individually low-to-medium in *mechanical* complexity — most are prompt contracts and read-side views over a well-designed ledger (T10). The engineering risk is almost entirely in getting **T10's schema and T7/T8's score-capture contract right**. Invest there; the differentiators then come cheaply on top. This is the opposite of the ops toolkit (shepsci), where the value is in the breadth of operations, not the reasoning.

### Anti-Features (deliberately NOT built for v1)

Each is something an adjacent tool ships and that a stakeholder might reflexively request. Documented here with the reason, so scope doesn't creep back in.

| Feature | Where it comes from / why requested | Why NOT in v1 | What to do instead |
|---------|-------------------------------------|---------------|--------------------|
| **Badge collection** (5-phase, ~38 badges) | shepsci `badge-collector` | Zero relationship to winning a competition; pure gamification of the platform. | Omit entirely. Not even v2. |
| **Forum / writeup discovery + retrieval** | shepsci `hackathon/` + comp-report scraping | Genuinely useful competition *knowledge*, but it is a research/discovery surface, not the experiment loop. Adds MCP/scraping + untrusted-content handling complexity. | Defer to **v2**: writeup retrieval could feed the static competition-context file (PROJECT.md flags this). Keep the context file's schema open to it. |
| **Competition landscape reports** (list/scan across categories) | shepsci `comp-report` | Discovery ("what should I enter?") is a pre-loop concern; v1 assumes the competition is already chosen (its slug is set at init). | Omit for v1. User picks the comp; we operate inside it. |
| **Benchmark task creation / episode & simulation logs** | shepsci `hackathon/benchmark-endpoints`, `episode-endpoints` | Niche Kaggle-MCP surfaces irrelevant to standard supervised competitions. | Omit entirely. |
| **Model publishing / dataset publishing** (`models create`, `dataset_upload`) | shepsci `kagglehub_publish`, kllm `cli_publish` | Solo competitor doesn't publish models/datasets to compete. Submission ≠ publishing. | Omit for v1. Only exception: if a large model must be uploaded as a private dataset to attach to a Kernel — treat as an internal detail of T8, not a user-facing publish feature. |
| **Account creation / registration walkthrough** | shepsci `registration` | Full account-creation flow is one-time and off-path. | Reduce to T2 (credential *validation* only); assume account exists. |
| **Automated hyperparameter sweeps as a first-class feature** | Every tracker (W&B Sweeps, Optuna integrations) | PROJECT.md decision: an experiment is **one idea + one verdict** in v1. Sweeps explode the ledger cardinality and dilute the documented-reasoning unit. | An experiment *may* internally tune, but v1 records it as a single idea/verdict. Layer sweeps on later as a distinct experiment type (v1.x+). |
| **Fully autonomous, unsupervised tree-search / multi-agent optimizer** | AIDE (500-node tree search), AutoKaggle (multi-agent), MLE-STAR | Directly opposed to the product thesis. These optimize blindly for 24h and burn compute/submissions with no human-legible reasoning trail. Our value is *documented, human-steerable* reasoning. | Human-in-the-loop, one deliberate idea at a time, each with a written verdict. |
| **Multi-agent / cross-runtime portability** (opencode, Gemini CLI, etc.) | shepsci markets 35+ agents | PROJECT.md constraint: Claude Code first. Chasing portability before the loop works is premature. | Keep the workspace format (files, ledger, scaffold) runtime-neutral so a later port is cheap, but do **not** build/test other runtimes in v1. |
| **General (non-competition) ML R&D workflows** | MLflow/W&B are domain-agnostic | Competition-optimized v1 (CV-first, submission budget, LB gap) is a *tighter, more valuable* loop than a generic tracker. Generalizing dilutes it. | Stay competition-scoped. The CV→LB/submission-budget features only make sense in a competition. |
| **Hosted web UI / dashboards / team collaboration / shared server** | MLflow tracking server, W&B cloud, DVC Studio | v1 is solo + local-first; **git is the sync/collab substrate** and markdown/CLI is the interface. A dashboard is a large build for a single-user tool. | Ledger + markdown + AI-generated summary views (D5) in the terminal. Git handles history and any future sharing. |
| **Remote model registry / model serving / deployment** | MLflow registry, W&B artifacts | Competitions end at a submission CSV; there is nothing to deploy or serve. | Artifacts live in the workspace + git; the "registry" is the ledger. |

## Feature Dependencies

```
T1 Workspace init / scaffold  (root — nothing precedes it)
 ├── T2 Auth setup + validation
 │      └── T3 Static competition-context file
 │             ├── T4 Local data download
 │             └── (submission limit) ──feeds──> D4 Submission-budget awareness
 ├── T5 Execution-target config
 └── T6 Experiment representation + notebook scaffold
        │   (reads T3 for metric/schema; needs T4 data for local path)
        ├── T7 Run locally → CV score + artifacts        (needs T4, T5, T6)
        ├── T8 Kernel push/poll/pull → CV + artifacts     (needs T2, T5, T6)
        │
        └──> T10 Experiment ledger (git-backed)           (needs T1 git, T6 schema)
               ├── writes from T7 / T8 (CV) and T9 (LB)
               ├──> T11 Living strategy doc               (reads T10)
               ├──> T12 History reasoning / never-repeat   (reads T10)
               │       └──enhanced-by──> D2 Idea dedup / semantic memory
               ├──> D1 Idea→verdict capture (schema constraint on T6/T10)
               ├──> D3 CV→LB gap tracking   (needs T7/T8 + T9 on same row)
               ├──> D5 Comparison / summary views
               └──> D6 Strategy synthesis    (T11 + D1 verdicts)

T9 Submit + record LB   (needs T2 + an experiment that produced a submission CSV via T7 or T8)
        └──feeds──> D3 (LB half of the gap), D4 (budget consumption)
```

### Dependency Notes

- **Everything requires T1 then T2.** Init lays down the folder + git + config; auth validation must pass before any Kaggle call. These two are the unavoidable first phase.
- **T3 is the linchpin of correctness.** The static context file (eval metric, data schema, submission limit) is read by T6 (to author correct notebooks and score correctly) and supplies the daily limit that D4 rations against. Get it wrong and every downstream experiment is subtly wrong.
- **T6 before any run.** The experiment schema + notebook scaffold defines the score-capture contract that T7 and T8 must both satisfy; build it before either execution path.
- **T7 and T8 are parallel implementations of the same contract.** Local (T7) is the default and simpler; Kernel (T8) is the harder, GPU path. They must write CV scores identically so the ledger and D3/D5 don't care which produced a row. **Build T7 first** (validates the whole loop cheaply, no Kaggle compute quota spent), then T8.
- **T10 is the hub.** The ledger is read by T11, T12, D1, D3, D5, D6 and written by T7/T8/T9. Its schema is the highest-leverage design decision in the project — stabilize it early. Nearly every differentiator is a thin read-side or schema-constraint layer over T10.
- **D3 needs both signals on one row.** CV→LB gap tracking is inert until T7/T8 (CV) *and* T9 (LB) both land on the same experiment. It therefore arrives naturally only after the first submission path works.
- **D1 (verdict) is a schema constraint, not a separate build.** Bake the mandatory verdict field into T6/T10 from day one — retrofitting it later means backfilling history.
- **D4 conflicts with LB-probing habits.** It deliberately *refuses* low-value submissions; that is the point (CV-first discipline). It depends on T3's limit + T9's events.

## MVP Definition

### Launch With (v1) — the one clean end-to-end cycle

The MVP is exactly the Core Value: empty folder → idea run → result + reasoning in ledger → strategy updated. Ruthlessly, that is:

- [ ] **T1 Workspace init/scaffold** — nothing exists without it
- [ ] **T2 Auth validation** — no Kaggle op works without it
- [ ] **T3 Static competition-context file** — the AI can't author correct code without metric/schema
- [ ] **T4 Local data download** — the default (local) path needs data
- [ ] **T5 Execution-target config** — the promised local/Kernel switch
- [ ] **T6 Experiment representation + notebook scaffold** — the atomic unit + the score-capture contract
- [ ] **T7 Run locally → CV score + artifacts** — proves the loop with zero Kaggle compute spent
- [ ] **T10 Ledger (git-backed)** — the memory substrate everything reads
- [ ] **T11 Living strategy doc** — closes the cycle ("what to try next")
- [ ] **T12 History reasoning (never-repeat)** — minimum viable "AI-driven," not just "AI-logged"
- [ ] **D1 Idea→verdict capture** — the schema constraint that makes it a *reasoning* loop, not a run log (cheap; ship in v1)

This is a **fully local, CV-only** end-to-end loop. It is demonstrable and valuable without ever touching Kaggle compute or spending a submission — which is exactly why it de-risks the project.

### Add Immediately After the Local Loop Proves Out (v1, second slice)

Kaggle-compute + real leaderboard signal. These complete the "compete for real" story:

- [ ] **T8 Kernel push/poll/pull** — GPU path (trigger: local loop is stable and a comp needs GPU)
- [ ] **T9 Submit + record LB** — real leaderboard signal
- [ ] **D3 CV→LB gap tracking** — activates the moment T9 lands (trust-your-CV discipline)
- [ ] **D4 Submission-budget awareness** — activates with T9 (conserve the daily ration)

### Add After Validation (v1.x)

- [ ] **D2 Semantic idea dedup** — trigger: prompt-only never-repeat (T12) proves insufficient and duplicates slip through
- [ ] **D5 Comparison/summary views** — trigger: the ledger has enough experiments that manual scanning hurts
- [ ] **D6 Strategy synthesis / prioritized hypothesis queue** — trigger: the hypothesis queue outgrows a hand-maintained list
- [ ] **Hyperparameter-sweep experiment type** — trigger: single-idea experiments feel too coarse

### Future Consideration (v2+)

- [ ] **Writeup/knowledge retrieval feeding the context file** — the one anti-feature with a real v2 path (PROJECT.md flags it)
- [ ] **Multi-agent / cross-runtime portability** — only after the Claude Code loop is validated
- [ ] Everything else in the anti-feature table stays out.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| T1 Workspace init/scaffold | HIGH | LOW | P1 |
| T2 Auth validation | HIGH | LOW | P1 |
| T3 Static competition-context file | HIGH | MEDIUM | P1 |
| T4 Local data download | HIGH | LOW | P1 |
| T5 Execution-target config | MEDIUM | MEDIUM | P1 |
| T6 Experiment repr + notebook scaffold | HIGH | MEDIUM | P1 |
| T7 Run locally → CV | HIGH | MEDIUM–HIGH | P1 |
| T10 Ledger (git-backed) | HIGH | MEDIUM | P1 |
| T11 Living strategy doc | MEDIUM | LOW | P1 |
| T12 History reasoning (never-repeat) | HIGH | MEDIUM | P1 |
| D1 Idea→verdict capture | HIGH | LOW (schema) | P1 |
| T8 Kernel push/poll/pull | HIGH | HIGH | P2 |
| T9 Submit + record LB | HIGH | MEDIUM | P2 |
| D3 CV→LB gap tracking | HIGH | MEDIUM | P2 |
| D4 Submission-budget awareness | HIGH | MEDIUM | P2 |
| D2 Semantic idea dedup | MEDIUM | MEDIUM | P3 |
| D5 Comparison/summary views | MEDIUM | MEDIUM | P3 |
| D6 Strategy synthesis | MEDIUM | MEDIUM | P3 |

**Priority key:** P1 = must-have for the local end-to-end loop (v1 first slice); P2 = must-have for real competing (v1 second slice); P3 = post-validation enhancement.

## Competitor / Adjacent-Tool Feature Analysis

| Capability | shepsci/kaggle-skill | MLflow / W&B / DVC | Autonomous agents (AIDE/AutoKaggle) | **Our approach** |
|-----------|----------------------|--------------------|-------------------------------------|------------------|
| Kaggle auth | Full registration + validation | N/A | Assumes configured | Validation only (T2); assume account exists |
| Competition data download | Yes (CLI/kagglehub/MCP) | N/A | Yes | Reimplement the CLI slice we need (T4) |
| Kernel execution (GPU) | Yes (push/poll/output) | N/A | Runs locally in sandbox | Reimplement push/poll/pull (T8) |
| Submit + LB read | Yes (submit/submissions/leaderboard) | N/A | Yes (unsupervised) | T9, human-gated by D4 budget |
| Experiment logging | No (ops only, no loop) | Yes (metrics/params/artifacts) | Internal tree/nodes | Structured ledger + git (T10) |
| **Written reasoning / verdicts** | No | No | No (opaque optimization) | **Yes — mandatory verdict (D1)** |
| **Never-repeat memory** | No | No | Partial (tree dedup, not human-legible) | **Yes, history-reasoned (T12/D2)** |
| **CV→LB gap discipline** | No | No | Optimizes LB directly (overfit risk) | **Yes, first-class (D3)** |
| **Submission-budget rationing** | No | No | Often burns budget | **Yes, CV-gated (D4)** |
| Human-in-the-loop | Ops on request | Logging only | No (autonomous) | **Yes — one deliberate idea/cycle** |
| Badges / writeups / benchmarks / publishing | Yes (broad) | No | No | **No (anti-features)** |
| Hosted UI / team | No | Yes (server/cloud) | No | **No — local-first, git + markdown** |

**Takeaway:** shepsci owns *breadth of Kaggle operations*; the trackers own *metric logging + dashboards*; the autonomous agents own *unsupervised optimization*. **No one owns the documented, competition-aware, human-steerable reasoning loop** — that is the open lane this framework fills, and D1–D4 are the features that occupy it.

## Sources

- shepsci/kaggle-skill v2.3.0 (read directly): `skills/kaggle/SKILL.md`, `README.md`, `modules/kllm/scripts/{cli_execute.sh, poll_kernel.sh, cli_competition.sh}`, `modules/kllm/references/cli-reference.md`, `modules/badge-collector/` — **HIGH confidence** (primary source, on disk)
- [The Kaggle Grandmasters Playbook (NVIDIA)](https://developer.nvidia.com/blog/the-kaggle-grandmasters-playbook-7-battle-tested-modeling-techniques-for-tabular-data/) — CV-first discipline, "more high-quality experiments" as the lever
- [What the Kaggle MAP Competition Taught Me About Trusting My CV (Medium)](https://medium.com/@aniruddhapal/what-the-kaggle-map-competition-taught-me-about-trusting-my-cv-f5996a89d771) — trust-your-CV, public-vs-private LB overfitting
- [Kaggle Handbook: Fundamentals to Survive a Shake-up (Medium)](https://medium.com/global-maksimum-data-information-technologies/kaggle-handbook-fundamentals-to-survive-a-kaggle-shake-up-3dec0c085bc8) — CV→LB gap, shakeup risk, leakage in preprocessing
- [A Comprehensive Comparison of ML Experiment Tracking Tools (Towards Data Science)](https://towardsdatascience.com/a-comprehensive-comparison-of-ml-experiment-tracking-tools-9f0192543feb/) and [MLflow vs W&B vs DVC (TechPlained)](https://www.techplained.com/mlflow-vs-wandb-vs-dvc) — tracker feature surfaces (metric logging, registry, data versioning; no reasoning/verdict layer)
- [AutoKaggle (arXiv)](https://arxiv.org/html/2410.20424v3), [AIDE (aide.ml)](https://www.aide.ml/), [MLE-bench (arXiv)](https://arxiv.org/pdf/2410.07095) — autonomous-agent landscape; establishes the human-in-the-loop / documented-reasoning contrast and the "don't build a blind optimizer" anti-feature

---
*Feature research for: AI-driven Kaggle competition experimentation framework (Claude Code skill)*
*Researched: 2026-07-09*
