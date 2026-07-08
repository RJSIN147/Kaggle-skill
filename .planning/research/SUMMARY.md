# Project Research Summary

**Project:** Kaggle Experimentation Framework
**Domain:** AI-driven Kaggle competition experimentation framework, delivered as a standalone Claude Code skill
**Researched:** 2026-07-09
**Confidence:** MEDIUM-HIGH

## Executive Summary

This is a standalone Claude Code skill that turns an empty folder into an AI-driven Kaggle competition workspace and drives a documented experiment loop: propose an idea, run it (locally by default, or on a Kaggle Kernel for GPU), capture a machine-verified result, write a reasoned verdict, log it to a git-backed ledger, and update a living strategy doc. All four research tracks - stack, features, architecture, and pitfalls - independently converge on the same shape: one integration primitive (the kaggle CLI), one memory substrate (a plain-file ledger plus git), one MVP slice (a fully local, CV-only loop), and one non-negotiable discipline (tooling, not the AI, writes numeric results). The nearest reference point, shepsci/kaggle-skill, is a broad Kaggle operations toolkit (auth, downloads, kernels, submissions, badges, writeups, benchmarks); this project deliberately reimplements only the roughly six operations the experiment loop needs and leaves the rest as anti-features, because the value here is the documented, competition-aware, human-steerable reasoning loop - a lane no adjacent tool (generic trackers like MLflow/W&B, or autonomous agents like AIDE/AutoKaggle) currently occupies.

The recommended approach: author to the Agent Skills standard (SKILL.md + scripts/ + references/ + templates/), standardize all Kaggle integration on the kaggle CLI 2.x (not kagglehub-only, not the Kaggle MCP server - both are optional sugar, not the backbone), and split the workspace into two layers - a read-only, competition-agnostic skill package and a per-competition, git-backed workspace holding all mutable state (config, three context files split by volatility, one immutable folder per experiment, and a ledger that is a derived, regenerable projection over each experiment's canonical meta.json). The generated-notebook ML stack is the standard competition trio (LightGBM/XGBoost/CatBoost on pandas + scikit-learn), with sklearn.model_selection as the CV backbone and Optuna reserved for when tuning is the hypothesis. Every experiment notebook must resolve its data path and write its result through a fixed, backend-agnostic contract so the same code runs unchanged locally or on a Kaggle Kernel.

The dominant risk across all four tracks is "success theater": a kernel reporting complete or a notebook exiting 0 is not proof of a valid, reproducible score, and an LLM that writes its own numbers into the ledger will eventually hallucinate or drift from reality. Every research file arrives at the same countermeasure - a machine-checked result contract (result.json written last by the notebook, validated artifacts, provenance-linked ledger rows) where the AI supplies only idea/hypothesis/verdict prose and tooling supplies every numeric field. Layered on top: CV-first discipline must be mechanically enforced (not just documented) via CV-to-LB gap tracking and submission-budget gating; two UI-only Kaggle gates (rules acceptance, phone verification) must be preflighted before the loop's first download/submit; and the security guardrails already proven in the reference skill (egress allowlist, untrusted-content wrappers around all Kaggle-sourced text, credential-leak tests, zip-slip protection) should be reused wholesale rather than re-derived. Mitigating these risks is what makes the MVP slice safe to ship: a fully local, CV-only loop that never touches Kaggle compute or spends a submission, provable end-to-end before the harder kernel and submission paths are built.

## Key Findings

### Recommended Stack

The stack is deliberately thin and single-primitive. kaggle CLI 2.x (GA, Python 3.11+) is the sole Kaggle integration surface - it is the only tool that covers auth, data download, kernel push/status/output/pull, and submission/leaderboard read-back in one place, is shell-invokable (portable beyond Claude Code), and has a stable command surface post-1.x to 2.x GA. kagglehub is optional in-notebook download sugar; the Kaggle MCP server is explicitly not a dependency (host-coupled, historically drifting tool availability). Helper scripts are Python 3.11+ stdlib (anything with logic - ledger I/O, timeout-bounded polling, credential handling) with thin bash only for one-line CLI pipes; uv manages the environment. The experiment ledger is plain files, not a database: append-only JSONL plus per-experiment markdown verdicts plus a living STRATEGY.md, all git-backed - explicitly rejecting SQLite/MLflow/W&B as heavier than a single-practitioner, AI-readable, diffable tool needs. The generated-notebook ML stack is the standard tabular-competition trio (LightGBM default, XGBoost, CatBoost) on pandas/numpy/scikit-learn, with sklearn.model_selection as the CV backbone and Polars/pyarrow for large data; deep-learning competitions push to Kaggle Kernels for GPU and use the Kaggle-preinstalled PyTorch/transformers stack instead.

**Core technologies:**
- kaggle CLI 2.x - the single Kaggle integration primitive (auth, download, kernels, submit) - only tool covering the full loop, agent-agnostic, GA-stable
- Python 3.11+ stdlib - all helper-script logic (ledger, polling, credential handling) - avoids a second scripting language; matches the CLI's floor
- JSONL + markdown ledger, git-backed - experiment memory substrate - append-friendly, diffable, AI-parseable, no server/daemon
- scikit-learn model_selection + LightGBM/XGBoost/CatBoost - CV backbone and default models for generated notebooks - standard, low-tuning, well-understood tabular baseline
- Agent Skills format (SKILL.md + scripts/references/templates) - delivery vehicle - native to Claude Code, portable to 35+ agents, progressive disclosure keeps token cost low

### Expected Features

The feature landscape triangulates against three adjacent classes - shepsci's ops breadth, generic trackers' metric logging, and autonomous agents' unsupervised optimization - and finds an open lane: documented, competition-aware, human-steerable reasoning, which no adjacent tool owns. Table-stakes features map 1:1 to PROJECT.md's Active requirements; differentiators are mostly cheap read-side/schema layers over a well-designed ledger, so the real engineering risk concentrates in getting the ledger schema and the score-capture contract right early.

**Must have (table stakes):** workspace init/scaffold; Kaggle auth setup + validation; static competition-context file (schema, metric, rules, submission limit); execution-target config (local/kernel, overridable); experiment representation (idea + hypothesis + fresh notebook + result + verdict); local run producing CV score + artifacts; Kaggle Kernel push/poll/pull for GPU; submit + record LB score; git-backed structured ledger; living strategy doc; history reasoning so the AI never re-proposes a tried idea.

**Should have (differentiators):** mandatory idea-to-verdict reasoning capture (the product's soul - no generic tracker records why); CV-to-LB gap tracking (no generic tracker has this notion at all); submission-budget-aware gating (refuse low-value submits); comparison/summary views over the ledger; strategy synthesis that ranks the hypothesis queue from observed ledger movement.

**Defer (v1.x / v2+):** semantic idea dedup (start prompt-driven; add only if duplicates slip through); hyperparameter-sweep as a first-class experiment type; writeup/forum-knowledge retrieval feeding the context file; multi-agent/cross-runtime portability. Permanently out of scope: badges, forum/writeup discovery as a v1 surface, competition-landscape discovery reports, model/dataset publishing, hosted dashboards/team collaboration, fully autonomous unsupervised optimization.

### Architecture Approach

The system splits into two layers that must never be conflated: Layer A, the skill package (installed, read-only, competition-agnostic - SKILL.md, deterministic scripts, on-demand reference docs, workspace-scaffold templates) and Layer B, the scaffolded workspace (the user's own git repo, holding all mutable state - one small always-tracked control plane, three context files split by volatility, one immutable directory per experiment, and a gitignored local data cache). The load-bearing design decision inside Layer B is a three-way volatility split: competition.md (write-once facts), strategy.md (small, rewritten-not-appended living plan), and a ledger (append-only, structured). The ledger itself follows a second load-bearing pattern - meta.json per experiment is canonical; ledger.jsonl is a derived, regenerable projection carrying just enough fields for cross-experiment reasoning, never hand-edited, always rebuildable. A third pattern makes local/Kaggle interchangeable: the execution backend is a swappable adapter (LocalRunner/KernelRunner implement one contract - dir + slug in, artifacts/ + terminal status out), unlocked by every authored notebook using a fixed backend-agnostic data-path resolver cell so the same code runs unchanged on either backend.

**Major components:**
1. Kaggle Gateway - sole wrapper over the kaggle CLI (auth, download, kernel push/status/output/pull, submit/leaderboard); every egress call funnels through here
2. Workspace Scaffolder - turns an empty folder into a valid workspace (dirs, config, context-file stubs, git init) from Layer-A templates
3. Ledger (meta.json canonical + ledger.jsonl derived index) - the AI's cross-experiment memory surface, rebuildable and provenance-linked
4. Execution Runner adapter (LocalRunner / KernelRunner) - the only place local/kernel logic diverges; everything downstream (verdict, ledger, submission) is backend-agnostic
5. Experiment Orchestrator - drives the lifecycle state machine (proposed to authored to running to results_captured to verdict_written to ledger_updated to strategy_updated) and persists a resumability cursor (state.json)

### Critical Pitfalls

1. **"Success theater" - kernel/exit status does not equal a valid result.** A complete status or 0 exit code proves the machine finished, not that the score is real (swallowed exceptions, degenerate submissions, stuck-status API bugs). Avoid by: a machine-checked result contract - the notebook writes a structured result.json as its last action, artifacts are validated (row counts, no NaN, finite score), and status-only logging is never treated as success.
2. **Hallucinated scores / ledger-reality drift.** LLMs fluently write plausible numbers; once one fabricated score enters the ledger, all later reasoning compounds the error. Avoid by: the AI never writes numeric fields - only tooling (a recorder script reading result.json) does, every row carries provenance (run id, artifact hash, git commit, seed), and the strategy doc is derived from the ledger, never hand-edited.
3. **Overfitting the public leaderboard / ignoring the CV-to-LB gap.** Chasing visible LB feedback is a crowdsourced overfitting engine; CV-first only holds if mechanically enforced. Avoid by: CV is the decision metric everywhere (strategy "current best," final-submission selection), LB is a diagnostic shown alongside a tracked, alarmed CV-to-LB gap.
4. **CV leakage / wrong CV scheme.** Preprocessing fit outside the fold, or a plain KFold on grouped/temporal data, produces an optimistic CV that silently stops predicting the LB. Avoid by: capturing the correct CV scheme as a first-class competition fact at setup (from data structure + metric), injecting it into every notebook scaffold, and enforcing fold-internal preprocessing.
5. **UI-only Kaggle gates block the loop's first cycle.** Rules acceptance and phone verification have no CLI equivalent - a 403 on the first automated download/submit is an external constraint, not a bug. Avoid by: an init-time preflight that detects the 403 and gives a one-time browser instruction, verified before proceeding.
6. **Broad permissions / untrusted Kaggle content treated as instructions.** The framework holds a Kaggle credential and ingests a lot of Kaggle-sourced text (rules, data descriptions); unscoped egress plus unwrapped content is a prompt-injection/exfiltration path. Avoid by: reusing the reference skill's proven guardrails wholesale - egress allowlist in settings.json, untrusted-content wrappers around all Kaggle-sourced text, credential-leak tests, zip-slip-safe extraction, slug validation.

## Implications for Roadmap

All four researchers, working independently, converge on essentially the same phase order - a local-loop-first critical path that proves the whole reasoning cycle before any Kaggle compute or submission budget is spent, followed by the GPU/kernel path, then submission/LB tracking, then AI-loop hardening. This convergence is strong signal for the roadmap.

### Phase 1: Scaffold, Auth & Egress
**Rationale:** Nothing else can be written without a valid workspace, and no Kaggle operation is safe without credential validation and a scoped egress allowlist in place first. All four research files put this first.
**Delivers:** init_workspace.py (empty folder to directory layout, config.json, context-file stubs, git init), a credential checker/auto-mapper (detect + validate kaggle.json/token, chmod 600, live validation call, never echo), and an egress allowlist (Bash(kaggle *), scoped WebFetch to *.kaggle.com/package sources) baked into .claude/settings.json.
**Addresses:** FEATURES T1 (workspace init), T2 (auth validation).
**Avoids:** PITFALLS #9 (over-broad permissions/egress), #12 (credential setup failures & token leakage), #17 (discipline must be on-disk/tooling, not chat memory - design this in from the start, not retrofitted).

### Phase 2: Competition Context & Data
**Rationale:** The static competition-context file is the AI's "constitution" - every downstream notebook, CV scheme, and submission-budget check reads it. It must exist, and be correct, before any experiment is authored. This phase also absorbs the two UI-only Kaggle gates that block automation entirely if hit unprepared.
**Delivers:** capture_competition.py populating competition.md (eval metric, data schema, submission-day limit, rules, CV scheme derived from data structure, adversarial-validation finding), a rules-acceptance/phone-verification preflight check, and local competition-data download with safe (zip-slip-protected) extraction.
**Addresses:** FEATURES T3 (static competition-context file), T4 (local data download).
**Uses:** ARCHITECTURE's Context Manager component; STACK's kaggle competitions files/download command surface.
**Avoids:** PITFALLS #3 (CV leakage / wrong scheme - capture the correct scheme as a fact here), #10 (untrusted Kaggle content - wrap all ingested text), #11 (rules/phone UI-only gates), #19 (known CLI quirks: no reliable --unzip for competitions, competition-linked-dataset 403s).

### Phase 3: Local Experiment Loop, Ledger & Strategy (MVP / Core-Value Milestone)
**Rationale:** This is the fully local, CV-only slice every research track independently identifies as the thing to prove first: it exercises the entire idea-to-run-to-verdict-to-ledger-to-strategy cycle without ever touching Kaggle compute or spending a submission, fully de-risking the project before the harder, quota-bound paths are built.
**Delivers:** the experiment schema + fresh-notebook scaffold (with a mandatory machine-checked result contract: result.json written last, seed/environment captured), a backend-agnostic CV harness enforcing fold-internal preprocessing, a local runner, the meta.json-canonical / ledger.jsonl-derived ledger with rebuild_ledger.py, a mandatory verdict field, a living strategy doc regenerated (not hand-edited) from the ledger, and prompt-driven history-reasoning so the AI doesn't re-propose a tried idea.
**Addresses:** FEATURES T5 (execution-target config), T6 (experiment representation + scaffold), T7 (local run to CV + artifacts), T10 (ledger), T11 (strategy doc), T12 (history reasoning), D1 (idea-to-verdict capture).
**Implements:** ARCHITECTURE's Notebook Authoring, Execution Runner adapter (local half), Ledger, and Experiment Orchestrator components; the backend-agnostic data-path resolver pattern (built now so Phase 4 is a pure addition, not a rewrite).
**Avoids:** PITFALLS #1 (success theater - the result contract is defined here), #4 (hallucinated scores - tooling, not the AI, writes numbers), #6 (non-reproducible runs - seed + noise floor), #8 (context bloat - design the volatility split from day one), #18 (fragile path assumptions - the resolver pattern).

### Phase 4: Kaggle Kernel Execution (GPU path)
**Rationale:** With the local loop proven and the result contract established, the kernel path is an additive extension of the same adapter contract, not a parallel workflow - it only needs to satisfy the same artifacts/ + status contract Phase 3 defined.
**Delivers:** kernel-metadata.json generation (validated template - competition_sources, enable_gpu, enable_internet false default), kaggle kernels push, timeout-bounded status polling with backoff, kernels output/pull, and extending the result-contract validation to parse the pulled run log for tracebacks even when status reports complete.
**Addresses:** FEATURES T8 (kernel push/poll/pull).
**Uses:** STACK's kernel-metadata schema and accelerator IDs; ARCHITECTURE's KernelRunner adapter implementation.
**Avoids:** PITFALLS #1 (kernel "complete" does not equal success - the hardest instance of this pitfall), #13 (kernel metadata/attachment mistakes), #14 (GPU weekly quota exhaustion / session timeouts), #15 (API rate limiting from chatty polling).

### Phase 5: Submission & Leaderboard Tracking
**Rationale:** Submission is backend-independent (whichever runner produced submission.csv, the CLI submit path is identical), so it layers onto either Phase 3 or Phase 4's output without further branching - but it introduces the project's real leaderboard signal and its scarcest resource (the daily submission budget), so it needs its own discipline.
**Delivers:** kaggle competitions submit + async LB read-back into submissions.jsonl, CV-to-LB gap computed and trended per experiment with divergence alarms, submission-budget tracking against the daily limit with CV-improvement-gated submission policy, pre-submit file validation, and a CV-based (not LB-based) final-selection rule.
**Addresses:** FEATURES T9 (submit + record LB), D3 (CV-to-LB gap tracking), D4 (submission-budget awareness).
**Avoids:** PITFALLS #2 (public-LB overfitting), #5 (burning the daily submission budget), #15 (rate limiting on submission/LB reconciliation).

### Phase 6: AI-Loop Hardening & Analysis
**Rationale:** These features are read-side or consistency layers over an already-stable ledger; building them last avoids retrofitting cost and lets real usage (experiment count, observed duplicate-idea near-misses) inform which enhancements actually matter.
**Delivers:** a fingerprinted "tried" index for structured dedup (upgrading Phase 3's prompt-only dedup once it proves insufficient), comparison/summary views over the ledger (best-so-far, deltas), strategy synthesis that ranks the hypothesis queue from ledger evidence, a cross-consistency check (every strategy claim resolves to a verified ledger row), and resumability hardening (state.json cursor semantics, submission dedup by file hash).
**Addresses:** FEATURES D2 (semantic idea dedup), D5 (comparison/summary views), D6 (strategy synthesis).
**Avoids:** PITFALLS #7 (loop amnesia / re-proposing tried ideas), #8 (context bloat at scale - tiered loading), #16 (strategy/ledger drift).

### Phase Ordering Rationale

- Dependency chain is strict through Phase 3: workspace to auth/egress to competition facts/data to experiment schema/ledger/local-run contract. Every research file places this chain first because nothing downstream is buildable or safe without it.
- The local-only MVP (Phase 3) is a deliberate de-risking milestone, not just "phase 3 of N." FEATURES.md's MVP Definition, ARCHITECTURE.md's "MVP / core-value milestone," and PITFALLS.md's phase-topic ordering (P4 before P6/P7) all independently land here - it proves the entire reasoning loop (propose, run, verdict, ledger, strategy) with zero Kaggle compute or submission spend, which is exactly why it should gate all later work.
- Kernel execution (Phase 4) and submission (Phase 5) are additive, not parallel rewrites, because Phase 3 establishes the backend-agnostic adapter contract and the machine-checked result contract up front - this is the payoff of ARCHITECTURE's swappable-adapter pattern.
- Hardening (Phase 6) is deliberately last because its features (D2/D5/D6) are cheap read-side layers over a well-designed ledger - FEATURES.md explicitly notes the engineering risk concentrates in T10's schema and T7/T8's score-capture contract, not in the differentiators.
- Security and integrity guardrails are threaded through every phase, not batched at the end - egress scoping and credential hygiene start in Phase 1; untrusted-content wrapping starts in Phase 2 (first ingestion of Kaggle text); the result-contract/no-AI-writes-scores discipline is established in Phase 3 and merely extended (never re-derived) in Phase 4.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (Kernel Execution):** the exact kaggle kernels status output format/JSON shape was not confirmable from docs (STACK Open Risks); known API bugs (#473 stuck status, #509 blank error fields) need live verification before the polling/log-parsing logic is finalized.
- **Phase 5 (Submission & LB Tracking):** the code-competition submission path (notebook-only submission, no CSV-via-CLI) needs validation for the specific competition type at implementation - v1's CLI-CSV submit assumption targets standard competitions only, and code-competitions need either a warning or a kernel-routed submission flow.
- **Phase 2 (Competition Context & Data):** kaggle competitions download --unzip reliability and competition-linked-dataset 403s are flagged inconsistently across sources as CLI-version-dependent - verify current CLI 2.x behavior directly.
- **Phase 6 (AI-Loop Hardening):** the timing and technique for semantic idea dedup (D2) is explicitly deferred - decide the exact trigger ("prompt-only dedup proves insufficient") and implementation (embedding similarity vs. rule-based fingerprinting) once real duplicate near-misses are observed, not speculatively.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Scaffold, Auth & Egress):** workspace scaffolding and Kaggle credential setup are well-documented against the reference skill and official Kaggle docs; low ambiguity.
- **Phase 3 (Local Experiment Loop):** the CV harness (sklearn.model_selection), the meta.json-canonical/ledger-derived pattern, and the result-contract design are all well-specified by research with concrete schemas already drafted in ARCHITECTURE.md.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Skill authoring + kaggle CLI/kagglehub verified against official docs and live PyPI (2026-07-09); ledger/notebook-execution choices are opinionated best-practice at MEDIUM within an overall HIGH file. Kernel status-string format and code-competition submit flow flagged as open risks. |
| Features | HIGH-MEDIUM | HIGH for the ops surface and shepsci comparison (read source directly); MEDIUM-HIGH for competition workflow discipline and adjacent-tool landscape (web-verified, well-established practice). |
| Architecture | MEDIUM-HIGH | HIGH on Kaggle mechanics (verified vs. official CLI docs plus the audited reference package); MEDIUM-HIGH on the workspace/ledger/adapter design - an opinionated synthesis not yet validated by a shipped loop. |
| Pitfalls | MEDIUM-HIGH | HIGH on Kaggle CLI/kernel/submission mechanics and skill-security patterns (verified against the reference skill, official docs, and open kaggle-api issues); HIGH on competition methodology (multiple independent sources agree); MEDIUM on AI-loop failure modes (hallucination, dedup, context bloat) - reasoned from first principles and PROJECT.md's own constraints, since few external post-mortems exist for this novel workflow shape. |

**Overall confidence:** MEDIUM-HIGH - the Kaggle-mechanics and security layers are HIGH confidence (verified against official docs and a working reference implementation); the AI-loop-specific design (ledger schema, dedup, context-volatility split, result-contract discipline) is an opinionated but internally consistent synthesis that all four researchers converged on independently - a strong signal, but genuinely untested until the first end-to-end cycle ships.

### Gaps to Address

- Kernel status output format: exact 2.x string/JSON shape unconfirmed from docs - verify against a live kaggle kernels push/status run early in Phase 4 planning, before finalizing the poller's parsing logic.
- Code-competition submission flow: whether standard competitions vs. code-competitions need materially different submission code paths - validate against a real code-competition (or its docs) before Phase 5 implementation; may need a competition-type flag captured in Phase 2's context file.
- Kaggle kaggle/python image version pins: confirm current pandas/numpy/scikit-learn versions preinstalled on Kaggle Kernels at build time, to set safe generated-code version floors and protect CV-to-LB parity - a quick check at Phase 4 planning, not a deep research task.
- Semantic-dedup approach and trigger (D2): deliberately left open - decide the concrete technique only after Phase 3's prompt-only dedup is observed to miss real near-duplicates; premature to research now.
- competitions download --unzip behavior on current CLI 2.x: sources note it was removed/unreliable as of CLI 1.8+; confirm current 2.x behavior directly rather than assuming, since it affects Phase 2's extraction code path.

## Sources

### Primary (HIGH confidence)
- Claude Code - Agent Skills (official docs, code.claude.com/docs/en/skills) - frontmatter fields, 1,536-char description cap, progressive disclosure, allowed-tools, ${CLAUDE_SKILL_DIR}, dynamic context injection
- Kaggle CLI on PyPI (fetched 2026-07-09) - version 2.2.3, GA/out-of-beta, Python 3.11+ requirement
- Kaggle CLI GitHub + kernel-metadata docs (github.com/Kaggle/kaggle-cli) - command surface, kernel-metadata schema, competition_sources
- shepsci/kaggle-skill v2.3.0 (read directly on disk, audited 2026-05/2026-07-09) - SKILL.md structure, egress allowlist, credential-check scripts, security test taxonomy (test_no_credential_leakage.py, test_untrusted_content_wrappers.py, test_zip_slip_protection.py), known CLI quirks - used as a structural exemplar only, not a dependency
- PyPI live versions (fetched 2026-07-09) - pandas 3.0.3, numpy 2.5.1, scikit-learn 1.9.0, lightgbm 4.6.0, xgboost 3.3.0, catboost 1.2.10, polars 1.42.1, optuna 4.9.0
- Official Kaggle competition/notebook docs (kaggle.com/docs) - submission limits, GPU/TPU quotas, hardware, code-competition debugging guide
- kaggle-api GitHub issues #473, #509, #530, #621 - concrete bug reports on kernel-status staleness and blank submission error codes
- .planning/PROJECT.md - project constraints, key decisions, scope boundaries

### Secondary (MEDIUM confidence)
- Kaggle Grandmasters Playbook (NVIDIA) and multiple Medium writeups (CV-to-LB gap, shakeup risk, "don't trust the CV") - competition methodology, cross-referenced across several independent sources
- Tracker feature-surface comparisons (MLflow vs. W&B vs. DVC) - establishes the "metric logger, not a reasoning tool" baseline
- AIDE / AutoKaggle / MLE-bench (arXiv, aide.ml) - autonomous-agent landscape, establishes the human-in-the-loop contrast

### Tertiary (LOW confidence)
- AI-loop failure modes (hallucinated scores, loop amnesia, context bloat) - reasoned from PROJECT.md's own constraints and general LLM-agent behavior; genuinely novel enough that little external validation exists - flagged as the highest-value items to confirm empirically during the first shipped local loop (Phase 3)

---
*Research completed: 2026-07-09*
*Ready for roadmap: yes*
