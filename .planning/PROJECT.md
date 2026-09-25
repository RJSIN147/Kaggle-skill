# Kaggle Experimentation Framework

## What This Is

A standalone Claude Code skill that turns an empty folder into an AI-driven Kaggle
**competition** experimentation workspace, for any competition type: tabular, vision, NLP,
time-series, code-only, API-served, simulation or writeup. It connects to the user's Kaggle
account through the `kaggle` CLI and Python API. It profiles the competition from structured
API facts, and drives a well-documented experiment loop:
- the AI proposes an idea
- runs it on a Kaggle kernel by default (locally as an option for small data)
- captures the result and a written verdict
- versions it in a ledger backed by git
- updates a living strategy
- prepares the competition's own kind of submission for the human to run

Built first for a single practitioner competing on Kaggle through Claude Code.

## Core Value

One clean end-to-end experiment cycle must work reliably — from an empty folder to an idea run,
its result and reasoning logged to the ledger, and the strategy doc updated. Everything else in
the framework exists to serve that loop.

## Current Milestone: v2.0 Kaggle-general

**Goal:** kaggle-exp works across Kaggle competition types. It runs on a Kaggle kernel by default, and a
competition profile built from the API drives it. A phase counts as done only when it has run live on a real
competition.

**Target features:**
- **`kx` core:**
  - One CLI whose every command prints JSON with a `next_action`, replacing the 28 scripts and the exit-code
    protocol.
  - A Kaggle adapter built on `kaggle.api`/`kagglesdk`.
  - An `experiment.json` spec.
  - `SKILL.md` of about 150 lines, with per-type `references/types/*.md`.
  - Reuses v1's ledger, record, gateway and kernel modules.
- **Competition profiles (`kx sync`):**
  - SDK-derived submission mode (`csv_upload | code_kernel (+api_served) | agent | writeup | artifact_upload |
    unknown`), modality, data size and limits, confirmed by the AI.
  - Type-specific experiment templates.
- **Kaggle-first compute:**
  - Script kernels by default.
  - Sources, accelerator and runtime limit set per experiment.
  - A train → inference kernel pipeline with manifests.
  - Local runs on a subsample.
  - Recording the kernel image's versions.
- **Submission modes (`kx submit` / `kx lb`):**
  - `csv_upload`, `code_kernel` (incl. API-served) and `agent` (simulation track), plus writeup guidance.
  - The human runs every submit; kx confirms it by read-back.
- **Tools for winning:**
  - `kx research`: discussions, public notebooks and host metric kernels.
  - `kx ensemble`: blending saved OOF predictions.
  - `kx select`: picking the two final submissions.

**Groundwork:** the Phase 0 spikes all passed (`.planning/spikes/`, and the `spike-findings-kaggle-skill` skill).

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Initialize an experiment workspace in an empty folder (layout, config, repo init, context stubs) — v1.0 (Phase 1, SETUP-01)
- ✓ Choose a default execution target (local vs Kaggle Kernel), overridable globally or per experiment — v1.0 (Phase 1, SETUP-02)
- ✓ Connect to the user's Kaggle account, with a live credential check that never echoes the secret — v1.0 (Phase 1, SETUP-03/04; the egress half was only partially demonstrated)
- ✓ Capture static competition context into a dedicated file at setup — v1.0 (Phase 2, COMP-01). v1 scraped type and limits from rules prose; v2 replaces this with API profiles.
- ✓ Preflight UI-only Kaggle gates, and download data with zip-slip-safe extraction — v1.0 (Phase 2, COMP-02/03)
- ✓ An experiment is an idea, a hypothesis, a generated script, a machine-captured result and a written verdict — v1.0 (Phase 3, EXP-01)
- ✓ The AI writes a fresh script for each experiment from a kernel-portable scaffold — v1.0 (Phase 3, EXP-02)
- ✓ Run an experiment locally, producing a CV score and artifacts — v1.0 (Phase 3, EXP-03)
- ✓ Only tooling writes numeric results, from a machine-checked `result.json`, with provenance — v1.0 (Phase 3, EXP-04)
- ✓ A version-controlled ledger (`meta.json` canonical, derived `ledger.jsonl`), a never-repeat history and a regenerated strategy doc — v1.0 (Phase 3, MEM-01/02/03)
- ✓ Push an experiment to a Kaggle Kernel, poll it, pull its artifacts and detect silent failures — v1.0 (Phase 4, EXP-05; live-verified 2026-09-25 after quick task 260925-66x)
- ✓ Submit via the Kaggle CLI and record the LB score, confirmed by read-back — v1.0 (Phase 5, SCORE-01; the only live submits so far used the raw CLI, not `submit.py`)
- ✓ CV-first decisions, a CV→LB gap trend with a divergence alarm, and submissions rationed against the daily limit — v1.0 (Phase 5, SCORE-02/03; `submissions.date` confirmed UTC live)

### Active

<!-- Current scope. Building toward these. All are hypotheses until shipped and validated. -->

- [ ] One `kx` CLI with JSON `next_action` output replaces the v1 scripts and exit-code protocol, reusing the kept v1 modules
- [ ] Competition profile from SDK structured fields (six submission modes, modality, data size, limits), confirmed by the AI
- [ ] Type-specific experiment templates selected by the profile
- [ ] Script kernels as the default runtime, with per-experiment sources, accelerator and runtime limit; local runs as an option
- [ ] Train → inference kernel pipelines with recorded upstream manifests
- [ ] Submission modes: `csv_upload`, `code_kernel` (incl. API-served), `agent`; writeup guidance only. Every submit is human-run and confirmed by read-back
- [ ] Research ingestion (discussions, public notebooks, host metric kernels for exact-metric CV)
- [ ] OOF ensembling and final-submission selection

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Dependency on shepsci/kaggle-skill — built fully standalone; reimplement only the Kaggle operations actually needed.
- Badges, benchmarks, model/dataset publishing — Kaggle-ops features that don't help win a competition. (v1 also excluded forum and notebook research; that moves into scope for v2, because spike 005 showed it is the highest-signal input.)
- Proven multi-agent portability (opencode, other agents) — Claude Code first; keep the structure portable and port later.
- General (non-competition) ML R&D workflows — the framework is competition-focused.
- Automated hyperparameter sweeps as a first-class feature — an experiment is a single idea plus a verdict; sweeps can be layered on later.
- Autonomous submitting — the human runs every submission. Claude Code auto-mode also treats a submit as a real-world transaction and blocks it.

## Context

- **Current state (v1.0 shipped 2026-09-25):**
  - 29 stdlib-only helper scripts (~9.4k LOC Python), 42 test modules (~9.6k LOC, 341 passing) and a 488-line SKILL.md.
  - The loop runs end to end, both locally and on a Kaggle kernel (live parity CV of 0.8305 on Titanic).
  - v1 is shaped around tabular data and CSV submissions:
    - It regex-scraped competition type and limits from rules prose, and labelled Titanic a code competition.
    - Its kernel path converts `.py` to a notebook, which caused 4 live bugs (fixed in quick task 260925-66x).
    - It has no path for code-only, API-served, simulation or writeup competitions.
- **v2 groundwork:** the Phase 0 spikes (2026-09-25, `.planning/spikes/`, packaged as the `spike-findings-kaggle-skill`
  skill) live-validated:
  - competition profiles derived from the Kaggle API
  - script kernels and `kernel_sources` chaining
  - submitting a script kernel version to code competitions, both tabular and `kaggle_evaluation` API-served
  - a ConnectX agent loop
  - reading discussions, public notebooks and host metric kernels for research
- **Reference point:** `shepsci/kaggle-skill` is installed in this environment (the `kaggle-skill:kaggle` plugin) and is a broad Kaggle *operations* toolkit (setup, downloads, notebooks, submissions, writeups, benchmarks, badges). This project targets a different layer — the *experimentation loop* — and is deliberately built standalone rather than on top of it.
- **Kaggle integration** relies on the Kaggle CLI/API and a user API token (`~/.kaggle/kaggle.json`). Kernel execution requires kernel metadata, competition-dataset attachment, and completion polling to pull outputs.
- **Data flow follows the execution target:** local runs download competition data locally; Kaggle-Kernel runs attach data on Kaggle. Submissions always route through the Kaggle CLI regardless of where code ran.
- **Delivery form:** the framework ships as a skill (SKILL.md + supporting scripts and reference docs) that scaffolds and then operates on the user's workspace folder.
- **Guiding principle:** AI-driven workflow — results and reasoning must be documented well enough that the AI (and the user) can pick smart next moves and avoid repetition.

## Constraints

- **Runtime**: Claude Code first — avoid hard dependencies that would block porting to opencode/other agents later.
- **Dependencies**: The `kaggle` package only (CLI + its bundled `kagglesdk`), with no dependency on external skills. The skill has its own locked uv environment; "stdlib-only" was dropped at v2.
- **Compute**: A Kaggle kernel is the default runtime (script kernels). Local execution is an option for small or tabular data. Live checks use CPU kernels where possible, because the GPU quota is shared with the user's other work.
- **Live verification**: "Done" for any phase means a live run on a real competition. Fixtures only guard against regressions. Live checks never submit to a competition the user is actively competing in.
- **Submissions**: The human runs every `kaggle competitions submit`. kx prepares and validates, hands over the exact command, then confirms by read-back.
- **Kaggle limits**: Respect competition submission limits and kernel quotas; CV-first discipline conserves submission budget.
- **Security**: Requires a Kaggle API token; network egress scoped to Kaggle and standard package sources.

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Build fully standalone (no shepsci/kaggle-skill dependency) | Full control; avoid coupling to another skill's surface and lifecycle | ✓ Good |
| Competition-focused | The tightest, most valuable loop; general R&D would dilute it | ✓ Good |
| Local-first default, Kaggle Kernels for GPU/submissions; target set at init, changeable anytime | Fast local iteration, free GPU when needed | ⚠️ Revisit — v2 makes the kernel the default runtime, because most prize competitions are code-only or too large to run locally. Local stays an option. |
| Experiment = idea + hypothesis + result + written verdict | The unit the AI reasons over | ✓ Good |
| Versioning = structured ledger + git | Queryable for the AI, diffable underneath | ✓ Good |
| Context split: static competition file / experiment history / living strategy doc | Separates rarely-changing facts from evolving state | ✓ Good — in v2 the static file comes from an API profile instead of scraped prose |
| AI writes a fresh notebook per experiment from a scaffold | The AI owns the code each cycle | ✓ Good — but as a plain script: v2 pushes script kernels (spike 003 gave identical scores with no conversion step) |
| Machine-checked result contract (tooling writes scores, never the AI) | Prevents fabrication; a throwing or lying run is recorded FAILED | ✓ Good |
| CV-first scoring; ration submissions | Conserves the submission budget; watch the CV→LB gap | ✓ Good |
| Stdlib-only helper scripts | Portability, nothing to install | ⚠️ Revisit — dropped for v2: the `kaggle` package's SDK exposes structured facts the CLI hides, and it is the same dependency as the CLI |
| Regex-scrape competition type and daily limit from rules prose | The CLI's JSON lacked these fields | ⚠️ Revisit — it mislabelled Titanic; v2 reads SDK `is_kernels_submissions_only` and `max_daily_submissions` instead |
| Exit-code protocol across 28 scripts (65/69/75/77/78) | Machine-readable gates | ⚠️ Revisit — v2 consolidates into one `kx` CLI that prints JSON with `next_action` |
| Claude Code first for portability | Ship a working loop before multi-agent support | ✓ Good |
| Working project name "Kaggle Experimentation Framework" | Descriptive placeholder | — Pending |
| v2 pivot to "Kaggle-general" (2026-09-25) | v1 only covered Playground/Getting-Started-shaped competitions; most prize competitions are code, vision/NLP or simulation | — Pending |
| Kernel-first runtime with script kernels | Code comps accept script kernel versions, including API-served ones; no notebook conversion (spikes 002/003) | — Pending |
| Competition profile from SDK structured fields | Classified the submission mode correctly on 19 of 20 competitions without prose scraping (spike 001) | — Pending |
| Human-run submissions, confirmed by read-back | Irreversible and budgeted; auto-mode denies it; a code submit prints nothing on success (spike 003) | — Pending |
| One `kx` CLI with JSON `next_action` | Replaces 28 scripts and the exit-code protocol; a smaller SKILL.md | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-25 at the start of milestone v2.0 Kaggle-general*
