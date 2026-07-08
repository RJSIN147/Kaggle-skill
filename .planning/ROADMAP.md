# Roadmap: Kaggle Experimentation Framework

## Overview

This roadmap follows a **local-loop-first vertical MVP**: prove the entire reasoning cycle — propose an idea, run it, capture a machine-verified result, write a verdict, log it to a git-backed ledger, regenerate the strategy — on local, CV-only compute *before* any Kaggle GPU or submission budget is spent. Phases 1–3 build that fully local, CV-only slice (the core-value milestone). Phase 4 adds the Kaggle Kernel GPU path as a pure extension of the same result contract, and Phase 5 layers submission and leaderboard tracking on top with mechanical CV-first discipline. Security and integrity guardrails are threaded through every phase (egress + credential hygiene from Phase 1; untrusted-content wrapping from Phase 2; the machine-checked result contract from Phase 3, extended — never re-derived — in Phase 4). The v2 AI-loop hardening/analysis features (semantic dedup, comparison views, evidence-ranked synthesis) are deliberately out of this roadmap.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Workspace, Credentials & Egress Guardrails** - Empty folder to a validated, git-tracked workspace with locked-down egress
- [ ] **Phase 2: Competition Context & Data** - Machine-derived competition "constitution" plus local data, UI gates cleared
- [ ] **Phase 3: Local Experiment Loop, Ledger & Strategy** - The full idea-to-verdict-to-ledger-to-strategy cycle, local & CV-only (MVP / core value)
- [ ] **Phase 4: Kaggle Kernel Execution (GPU Path)** - Run the same experiment on Kaggle GPU compute, silent-failure caught
- [ ] **Phase 5: Submission & Leaderboard Tracking** - Submit under CV-first discipline with budget gating and CV-to-LB gap tracking

## Phase Details

### Phase 1: Workspace, Credentials & Egress Guardrails
**Goal**: A single init turns an empty folder into a valid, git-tracked experiment workspace with a live-validated Kaggle connection and a locked-down network egress allowlist.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: SETUP-01, SETUP-02, SETUP-03, SETUP-04
**Success Criteria** (what must be TRUE):
  1. Running init on an empty folder produces the full workspace layout — control plane (config.json, ledger.jsonl, state.json), context-file stubs, .gitignore, and an initialized git repo.
  2. User can set the execution target to local (default) or kernel at init and change it later — globally in config.json or overridden per experiment — and the setting is honored by whatever runner exists.
  3. The framework validates the Kaggle credential with a live call and reports a clear pass/fail, giving exact remediation for each common failure (wrong env var, missing chmod 600, 401, command-not-found).
  4. Credentials are chmod 600 and never echoed, logged, or committed (.gitignore covers .env/kaggle.json/access_token); a credential-leak check passes.
  5. Network egress is restricted to a Kaggle + package-source allowlist in .claude/settings.json — an off-allowlist fetch is refused, not silently allowed.
**Plans**: 4 plans

Plans:
- [ ] 01-01-PLAN.md — Skill package skeleton + Nyquist Wave 0 test harness (SKILL.md guided-init orchestration contract, pytest live marker, RED suite)
- [ ] 01-02-PLAN.md — Workspace scaffolder (init_workspace.py): D-10 layout, control-plane, docs/.env/pyproject stubs, execution-target + setter, safe-merge idempotency
- [ ] 01-03-PLAN.md — Egress allowlist (sandbox.network.allowedDomains) + secret-aware .gitignore + stdlib leak-guard hook + git init + scanned initial commit + portability doc
- [ ] 01-04-PLAN.md — Kaggle credential connect + live exit-code validation + four remediation branches + chmod-600/no-echo hardening

### Phase 2: Competition Context & Data
**Goal**: Before any experiment is authored, the workspace holds a correct, machine-derived competition "constitution" and the data needed to run locally — with the UI-only Kaggle gates cleared and all ingested Kaggle text treated as untrusted.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: COMP-01, COMP-02, COMP-03
**Success Criteria** (what must be TRUE):
  1. capture_competition populates competition.md with eval metric, data schema, rules, daily submission limit, and a correct CV scheme derived from the data structure (grouped/temporal/stratified) plus an adversarial-validation finding.
  2. All Kaggle-sourced text is wrapped in untrusted-content markers with source attribution before it reaches the agent — no directive embedded in competition text can drive a file path, shell command, or fetch.
  3. On a 403, the framework detects the UI-only gate (rules acceptance / phone verification), surfaces one clear browser instruction with the exact URL, and verifies acceptance with a probe before proceeding — it never busy-loops the download.
  4. Competition data downloads locally and is extracted with zip-slip-protected extraction, so no file can escape the data directory.
**Plans**: TBD (suggested 3)

Plans:
- [ ] 02-01: Kaggle Gateway competition ops + rules/phone-verification 403 preflight with one-time browser instruction
- [ ] 02-02: Competition-context capture (metric, schema, limits, CV scheme, adversarial validation) with untrusted-content wrapping
- [ ] 02-03: Local data download + safe (zip-slip-protected) extraction, handling no-`--unzip` CLI quirk

### Phase 3: Local Experiment Loop, Ledger & Strategy
**Goal**: The full idea-to-run-to-verdict-to-ledger-to-strategy cycle works end-to-end on local compute alone — machine-verified scores, never a fabricated number, never a Kaggle submission spent. This is the core-value milestone.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: EXP-01, EXP-02, EXP-03, EXP-04, MEM-01, MEM-02, MEM-03
**Success Criteria** (what must be TRUE):
  1. The AI authors a fresh notebook per experiment from the scaffold using a backend-agnostic data-path resolver and result contract, and runs it locally to produce a cross-validation score plus artifacts (fold-internal preprocessing enforced).
  2. An experiment is captured as idea + hypothesis + machine-captured result + a written verdict (worked / didn't / why) in an immutable per-experiment folder.
  3. Numeric fields are written only by tooling from a machine-checked result.json — a deliberately-throwing notebook is recorded as a failure, not a success — and every ledger row carries provenance (run id, artifact hash, git commit, seed).
  4. Every experiment lands in a git-backed ledger (meta.json canonical + derived ledger.jsonl index of score/verdict/artifact links) that fully rebuilds from the per-experiment folders.
  5. The strategy doc (current best, hypothesis queue, next action) is regenerated from the ledger each cycle — never hand-edited — and the AI reasons over history so it does not re-propose an already-tried idea.
**Plans**: TBD (suggested 4)

Plans:
- [ ] 03-01: Ledger schema — meta.json canonical + derived ledger.jsonl + rebuild_ledger.py + provenance fields
- [ ] 03-02: Notebook template with backend-agnostic path resolver, CV harness (fold-internal), seed/env capture, result.json contract
- [ ] 03-03: Local runner + recorder script (tooling writes scores from result.json) + artifact validation + silent-failure detection
- [ ] 03-04: Experiment orchestrator lifecycle (state.json cursor) + strategy regeneration from ledger + prompt-driven never-repeat

### Phase 4: Kaggle Kernel Execution (GPU Path)
**Goal**: The same experiment can run on Kaggle GPU compute as a pure addition to the proven loop — push, poll, pull — reusing (never re-deriving) the machine-checked result contract, with silent kernel failure caught.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: EXP-05
**Success Criteria** (what must be TRUE):
  1. User can push an experiment to a Kaggle Kernel with valid kernel-metadata (correct id/code_file, competition_sources, GPU on, internet off by default) and it runs on Kaggle compute.
  2. The framework polls to completion with backoff (no 429 storm) and pulls results/artifacts back into the same artifacts/ contract the local runner uses.
  3. A kernel reporting "complete" is not trusted as success — the pulled run log is scanned for tracebacks and artifacts are validated against the same result contract before any score is recorded.
**Plans**: TBD (suggested 2)

Plans:
- [ ] 04-01: kernel-metadata.json generation from validated template (competition_sources, accelerator, internet-off) + kaggle kernels push
- [ ] 04-02: Timeout-bounded status polling with backoff + output/pull + run-log traceback scan extending the result contract

### Phase 5: Submission & Leaderboard Tracking
**Goal**: Predictions reach the competition leaderboard under mechanical CV-first discipline — the scarce daily submission budget is gated and tracked, and the CV-to-LB gap is trended with a divergence alarm.
**Mode:** mvp
**Depends on**: Phase 3 (submission is backend-independent; consumes Phase 4 kernel output when a kernel produced the submission)
**Requirements**: SCORE-01, SCORE-02, SCORE-03
**Success Criteria** (what must be TRUE):
  1. User can submit a validated submission.csv via the Kaggle CLI and the resulting LB score is recorded to submissions.jsonl with the experiment id and file hash.
  2. CV remains the decision metric everywhere; the framework computes and trends the CV-to-LB gap per experiment and raises a divergence alarm when CV and LB disagree.
  3. Submissions are gated on meaningful CV improvement (or an explicit stated calibration reason) and blocked otherwise; remaining daily budget is tracked with UTC-aware reset.
  4. A malformed submission file (wrong row count, NaNs, misaligned ids) is caught by pre-submit validation so a budget slot is never wasted.
**Plans**: TBD (suggested 3)

Plans:
- [ ] 05-01: kaggle competitions submit + async LB read-back into submissions.jsonl + pre-submit file validation
- [ ] 05-02: CV-to-LB gap computation and trend per experiment with divergence alarm; CV-based final-selection rule
- [ ] 05-03: Submission-budget model (UTC reset) + CV-improvement gating policy + remaining-slots tracking

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Workspace, Credentials & Egress Guardrails | 0/4 | Not started | - |
| 2. Competition Context & Data | 0/3 | Not started | - |
| 3. Local Experiment Loop, Ledger & Strategy | 0/4 | Not started | - |
| 4. Kaggle Kernel Execution (GPU Path) | 0/2 | Not started | - |
| 5. Submission & Leaderboard Tracking | 0/3 | Not started | - |

## Coverage

- v1 requirements: 18 total
- Mapped to phases: 18 (100%)
- Orphaned: 0

| Phase | Requirements |
|-------|--------------|
| 1 | SETUP-01, SETUP-02, SETUP-03, SETUP-04 |
| 2 | COMP-01, COMP-02, COMP-03 |
| 3 | EXP-01, EXP-02, EXP-03, EXP-04, MEM-01, MEM-02, MEM-03 |
| 4 | EXP-05 |
| 5 | SCORE-01, SCORE-02, SCORE-03 |

v2 requirements (ANLY-01/02/03, EXT-01/02/03) are deferred and intentionally not mapped to a v1 phase.

---
*Roadmap created: 2026-07-09*
*Granularity: standard | Mode: mvp*
