# Kaggle Experimentation Framework

## What This Is

A standalone Claude Code skill that turns an empty folder into an AI-driven Kaggle
**competition** experimentation workspace. It connects to the user's Kaggle account via the
Kaggle CLI/API, scaffolds a structured workspace, and drives a well-documented experiment loop:
the AI proposes an idea, runs it (locally by default or pushed to a Kaggle Kernel for GPU),
captures the result and a written verdict, versions it in a ledger backed by git, and updates a
living strategy. Built first for a single practitioner competing on Kaggle through Claude Code.

## Core Value

One clean end-to-end experiment cycle must work reliably — from an empty folder to an idea run,
its result and reasoning logged to the ledger, and the strategy doc updated. Everything else in
the framework exists to serve that loop.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- [x] Capture static competition context — data schema, eval metric, rules, submission limits — in a dedicated file at setup — *Validated in Phase 2: Competition Context & Data (COMP-01, machine-derived "constitution" with provenance-tagged limits and untrusted-content wrapping)*
- [x] Download competition data for local runs — *Validated in Phase 2: Competition Context & Data (COMP-02, UI-only rules gate cleared, zip-slip-protected extraction, never busy-loops)*

### Active

<!-- Current scope. Building toward these. All are hypotheses until shipped and validated. -->

- [ ] Initialize an experiment workspace in an empty folder (directory structure, config, context files)
- [ ] Connect to the user's Kaggle account via the Kaggle CLI/API (credential setup + validation)
- [ ] Choose a default execution target (local vs Kaggle Kernel) at init; overridable anytime, globally or per-experiment
- [ ] Represent an experiment as an idea + hypothesis, its generated notebook/script, its result, and a written verdict (worked / didn't / why)
- [ ] AI authors a fresh notebook/script per experiment from a template scaffold
- [ ] Run an experiment locally (the default path), producing a cross-validation score and artifacts
- [ ] Push a notebook to a Kaggle Kernel, run it on Kaggle compute (GPU), and pull results/artifacts back
- [ ] Log every experiment to a structured ledger (metadata, CV score, links to artifacts), backed by git
- [ ] CV-first scoring: local cross-validation is the primary signal; submissions rationed against the daily limit; track the CV→LB gap
- [ ] Submit predictions to the competition via the Kaggle CLI and record the resulting LB score
- [ ] Maintain a living strategy doc the AI updates each cycle (current best, hypothesis queue, what to try next)
- [ ] Maintain experiment history the AI reasons over so it never re-proposes an already-tried idea

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Dependency on shepsci/kaggle-skill — building fully standalone; reimplement only the Kaggle ops actually needed
- Broad Kaggle toolkit features (badges, forum/writeup discovery, benchmarks, model publishing) — not core to the experiment loop; revisit in v2 (writeup retrieval could feed competition knowledge)
- Proven multi-agent portability (opencode / other agents) in v1 — Claude Code first; keep structure portable and port later
- General (non-competition) ML R&D workflows — competition-optimized for v1
- Automated hyperparameter sweeps as a first-class feature — an experiment is a single idea + verdict for v1; sweeps can layer on later

## Context

- **Reference point:** `shepsci/kaggle-skill` is installed in this environment (the `kaggle-skill:kaggle` plugin) and is a broad Kaggle *operations* toolkit (setup, downloads, notebooks, submissions, writeups, benchmarks, badges). This project targets a different layer — the *experimentation loop* — and is deliberately built standalone rather than on top of it.
- **Kaggle integration** relies on the Kaggle CLI/API and a user API token (`~/.kaggle/kaggle.json`). Kernel execution requires kernel metadata, competition-dataset attachment, and completion polling to pull outputs.
- **Data flow follows the execution target:** local runs download competition data locally; Kaggle-Kernel runs attach data on Kaggle. Submissions always route through the Kaggle CLI regardless of where code ran.
- **Delivery form:** the framework ships as a skill (SKILL.md + supporting scripts and reference docs) that scaffolds and then operates on the user's workspace folder.
- **Guiding principle:** AI-driven workflow — results and reasoning must be documented well enough that the AI (and the user) can pick smart next moves and avoid repetition.

## Constraints

- **Runtime**: Claude Code first — avoid hard dependencies that would block porting to opencode/other agents later.
- **Dependencies**: Kaggle CLI/API only; no dependency on external skills (standalone).
- **Compute**: Kaggle Kernels for GPU/heavy compute and official submissions; local execution for fast default iteration.
- **Kaggle limits**: Respect competition submission limits and kernel quotas; CV-first discipline conserves submission budget.
- **Security**: Requires a Kaggle API token; network egress scoped to Kaggle and standard package sources.

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Build fully standalone (no shepsci/kaggle-skill dependency) | Full control; avoid coupling to another skill's surface and lifecycle | — Pending |
| Competition-focused for v1 | Tightest, most valuable loop; general R&D would dilute it | — Pending |
| Local-first default, Kaggle Kernels for GPU/submissions; execution target set at init and changeable anytime | Fast local iteration, free GPU when needed, flexibility per experiment | — Pending |
| Experiment = idea + hypothesis + result + written verdict | Matches the documented-reasoning vision; the unit the AI reasons over | — Pending |
| Versioning = structured ledger + git | Queryable/summarizable for the AI, with diffable code history underneath | — Pending |
| Context split: static comp file / experiment history / living strategy doc | Separates rarely-changing facts from evolving state; keeps AI context clean | — Pending |
| AI authors a fresh notebook per experiment from a scaffold | Maximum flexibility; the AI owns the code each cycle | — Pending |
| CV-first scoring; ration submissions | Standard competition discipline; conserves submission budget; watch the CV→LB gap | — Pending |
| Claude Code first for portability | Ship a working loop before investing in multi-agent support | — Pending |
| Working project name "Kaggle Experimentation Framework" | Descriptive placeholder; final skill name can be chosen at packaging | — Pending |

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
*Last updated: 2026-07-11 after Phase 2 (Competition Context & Data) complete — machine-derived competition constitution + local data download shipped; CV scheme is AI-decided (D-05), tooling only persists the validated choice.*
