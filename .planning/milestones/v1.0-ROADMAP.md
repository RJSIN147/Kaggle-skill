# Roadmap: Kaggle Experimentation Framework

## Overview

This roadmap follows a **local-loop-first vertical MVP**: prove the entire reasoning cycle — propose an idea, run it, capture a machine-verified result, write a verdict, log it to a git-backed ledger, regenerate the strategy — on local, CV-only compute *before* any Kaggle GPU or submission budget is spent. Phases 1–3 build that fully local, CV-only slice (the core-value milestone). Phase 4 adds the Kaggle Kernel GPU path as a pure extension of the same result contract, and Phase 5 layers submission and leaderboard tracking on top with mechanical CV-first discipline. Security and integrity guardrails are threaded through every phase (egress + credential hygiene from Phase 1; untrusted-content wrapping from Phase 2; the machine-checked result contract from Phase 3, extended — never re-derived — in Phase 4). The v2 AI-loop hardening/analysis features (semantic dedup, comparison views, evidence-ranked synthesis) are deliberately out of this roadmap.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Workspace, Credentials & Egress Guardrails** - Empty folder to a validated, git-tracked workspace with locked-down egress (completed 2026-07-10)
- [x] **Phase 2: Competition Context & Data** - Machine-derived competition "constitution" plus local data, UI gates cleared (verification gaps_found 2026-07-10 — gap closure pending) (completed 2026-07-10)
- [x] **Phase 3: Local Experiment Loop, Ledger & Strategy** - The full idea-to-verdict-to-ledger-to-strategy cycle, local & CV-only (MVP / core value) (completed 2026-07-11)
- [x] **Phase 4: Kaggle Kernel Execution (GPU Path)** - Run the same experiment on Kaggle GPU compute, silent-failure caught (all 5 plans executed; verification gaps_found 2026-07-12 — gap closure pending: anti-silent-failure guarantee has a hole, CR-01/VERIFICATION) (completed 2026-07-11)
- [x] **Phase 5: Submission & Leaderboard Tracking** - Submit under CV-first discipline with budget gating and CV-to-LB gap tracking (completed 2026-07-12)

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
**Wave 1**

- [x] 01-01-PLAN.md — Skill package skeleton + Nyquist Wave 0 test harness (SKILL.md guided-init orchestration contract, pytest live marker, RED suite)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Workspace scaffolder (init_workspace.py): D-10 layout, control-plane, docs/.env/pyproject stubs, execution-target + setter, safe-merge idempotency

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Egress allowlist (sandbox.network.allowedDomains) + secret-aware .gitignore + stdlib leak-guard hook + git init + scanned initial commit + portability doc
- [x] 01-04-PLAN.md — Kaggle credential connect + live exit-code validation + four remediation branches + chmod-600/no-echo hardening

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

**Plans**: 5 plans + 2 gap-closure

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Egress unblock (api.kaggle.com) + Kaggle Gateway (D-16: run_kaggle/preflight/classify_gate, fail-closed 403)

**Wave 2** *(blocked on Wave 1)*

- [x] 02-02-PLAN.md — Competition-context capture (metric, rules, provenance-tagged limit, competition.type) + untrusted-content boundary (fence + no-derived-execution)
- [x] 02-03-PLAN.md — Local data download + gate flow (exit-77, never busy-loops) + zip-slip-protected extraction (no `--unzip`)

**Wave 3** *(blocked on Wave 2)*

- [x] 02-04-PLAN.md — Analyze data: CV scheme (tooling-written enum) + adversarial validation (uv run, graceful SKIPPED)

**Wave 4** *(blocked on Wave 3)*

- [x] 02-05-PLAN.md — SKILL.md three-stage flow + gate protocol + opt-in live CLI-shape verification + rules/phone human-action gate

**Gap closure (Wave 1 — parallel; from 02-VERIFICATION.md gaps_found 2026-07-10)**

- [x] 02-06-PLAN.md — Gap 1 (COMP-01): cv.scheme becomes an enum-validated AI decision (remove auto-commit), label the mechanical recommendation an advisory hint, tighten detect_group_candidates + pin a titanic fixture, wire the D-05 flow into SKILL.md
- [x] 02-07-PLAN.md — Gap 2 (COMP-02 / WR-01): mirror capture_competition._gateway_failure's rc==127/rc==124 branches into download_data.py so a missing CLI / timeout gets correct remediation instead of the misleading exit-77 UI-gate instruction (no busy-loop)

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

**Plans**: 5 plans

Plans:

**Wave 1** *(foundations, parallel — no file overlap)*

- [x] 03-01-PLAN.md — Metric registry + config.metric setter (D-08) + workspace ML floors
- [x] 03-02-PLAN.md — Ledger schema: experiment_meta module + rebuild_ledger.py + meta/VERDICT templates (MEM-01, provenance)

**Wave 2** *(blocked on 03-01)*

- [x] 03-03-PLAN.md — experiment.py.tmpl (resolve_data_dir + leakage-safe run_cv harness) + scaffold_experiment.py (EXP-01/02)

**Wave 3** *(blocked on 03-01, 03-02, 03-03 — the anti-lie headline slice)*

- [x] 03-04-PLAN.md — run_local.py + record_experiment.py: fail-closed result contract, provenance, throwing-notebook = FAILURE-with-verdict (EXP-03/04)

**Wave 4** *(blocked on 03-02, 03-04)*

- [x] 03-05-PLAN.md — regen_strategy.py (ledger facts + AI reasoning, full overwrite) + SKILL.md loop wiring + prompt-driven never-repeat (MEM-02/03)

### Phase 4: Kaggle Kernel Execution (GPU Path)

**Goal**: The same experiment can run on Kaggle GPU compute as a pure addition to the proven loop — push, poll, pull — reusing (never re-deriving) the machine-checked result contract, with silent kernel failure caught.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: EXP-05
**Success Criteria** (what must be TRUE):

  1. User can push an experiment to a Kaggle Kernel with valid kernel-metadata (correct id/code_file, competition_sources, GPU on, internet off by default) and it runs on Kaggle compute.
  2. The framework polls to completion with backoff (no 429 storm) and pulls results/artifacts back into the same artifacts/ contract the local runner uses.
  3. A kernel reporting "complete" is not trusted as success — the pulled run log is scanned for tracebacks and artifacts are validated against the same result contract before any score is recorded.

**Plans**: 5 plans

Plans:

**Wave 1**

- [x] 04-01-PLAN.md — Nyquist Wave 0 kernel test harness: fixtures (logs/status/golden metadata) + RED stubs pinning every EXP-05 test-map row

**Wave 2** *(blocked on 04-01)*

- [x] 04-02-PLAN.md — Convert + push slice: convert_notebook.py (jupytext, non-destructive) + push_kernel.py (metadata gen + non-blocking quota + push + kernel_run.json) + kernel-metadata template + config internet toggle

**Wave 3** *(blocked on 04-02; parallel — no file overlap)*

- [x] 04-03-PLAN.md — Poll + pull slice: poll_kernel.py (enum classify + exponential backoff/budget + detach-not-cancel) + pull_kernel.py (output/logs/image provenance) + gitignore kernel artifacts
- [x] 04-04-PLAN.md — Recorder extension (headline): record_experiment.py silent-failure first rung (scan_kernel_log + one kernel_error reason, log scanned before result.json is trusted)

**Wave 4** *(blocked on 04-03, 04-04)*

- [x] 04-05-PLAN.md — SKILL.md kernel-path sequencing (convert→push→poll→pull→record, detach/resume, quota + internet notes) + one opt-in live-push human-verify checkpoint (T4×2 string / log format / status render)

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

**Plans**: 7 plans in 4 waves

> **Deliberate deviation from the suggested 3-plan split (recorded, not forgotten):**
> (a) roadmap plan `05-02` named a *"CV-based final-selection rule"* — the user **explicitly scoped
> final selection / nomination OUT of v1** (05-CONTEXT D-12). It is **not planned anywhere**; the
> submissions history + the divergence alarm are what the user nominates from, manually, in the
> Kaggle UI.
> (b) 05-CONTEXT D-09 surfaced a **discovered gap the roadmap did not anticipate**: Phase 3's `run_cv`
> harness is CV-only, so **`submission.csv` does not exist today**. Producing it is a prerequisite for
> everything else here and gets its own early-wave plan (05-02).
> (c) The Nyquist Wave-0 RED suite is split out (05-01) because a real `competitions submit` is
> irreversible: the tests that make the submit path provably slot-free must exist before it does.

Plans:

**Wave 1**

- [x] 05-01-PLAN.md — Nyquist Wave 0: live-captured submissions fixtures + every RED test module (fail-open guards, budget, gate matrix, alarm, source guard forbidding any live test from submitting)

**Wave 2** *(blocked on Wave 1 — parallel)*

- [x] 05-02-PLAN.md — D-09: extend `run_cv` to emit fold-averaged `submission.csv` (type-aware: `label` metrics vote, never mean) + scaffold the submission header
- [x] 05-03-PLAN.md — Foundation: reserved exit codes 65/69/75 + `submissions_log.py` (row schema, status/score parse, UTC-safe Kaggle-authoritative budget count, atomic I/O) + configurable `noise_k`

**Wave 3** *(blocked on Wave 2 — parallel)*

- [x] 05-04-PLAN.md — `check_submission.py` (FREE — never spends a slot): D-01 type refusal, D-02 file validation, D-04 budget, D-05/D-06/D-08 block-by-default gate + decision material
- [x] 05-05-PLAN.md — `submit.py` (⚠ the CLI is FAIL-OPEN — success is confirmed by READ-BACK, never by rc==0; PENDING row written before the poll) + `fetch_lb.py` (detach fallback + `--reconcile`)
- [x] 05-06-PLAN.md — CV→LB gap trend + D-10 rank-inversion divergence alarm (derived join on `exp_id`; `meta.json` never written) spliced into the strategy-regen contract

**Wave 4** *(blocked on Wave 3)*

- [x] 05-07-PLAN.md — SKILL.md gate protocol (65/69/75; the human decides, `--reason` optional) + `references/kaggle-cli-behavior.md` submit/submissions entries + stated `.gitignore` decision + **blocking human-verify checkpoint: the first real submission verifies assumption A1 (is `submissions.date` UTC?)**
## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Workspace, Credentials & Egress Guardrails | 4/4 | Complete   | 2026-07-09 |
| 2. Competition Context & Data | 7/7 | Complete   | 2026-07-10 |
| 3. Local Experiment Loop, Ledger & Strategy | 5/5 | Complete   | 2026-07-11 |
| 4. Kaggle Kernel Execution (GPU Path) | 6/6 | Complete   | 2026-07-11 |
| 5. Submission & Leaderboard Tracking | 7/7 | Complete   | 2026-07-12 |

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
