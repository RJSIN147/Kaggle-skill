# Roadmap: Kaggle Experimentation Framework

## Milestones

- ✅ **v1.0 Experiment Loop MVP** — Phases 1-5 (shipped 2026-09-25)
- 🚧 **v2.0 Kaggle-general** — Phases 6-10 (in progress)

## Phases

<details>
<summary>✅ v1.0 Experiment Loop MVP (Phases 1-5) — SHIPPED 2026-09-25</summary>

- [x] Phase 1: Workspace, Credentials & Egress Guardrails (4/4 plans) — completed 2026-07-09
- [x] Phase 2: Competition Context & Data (7/7 plans) — completed 2026-07-10
- [x] Phase 3: Local Experiment Loop, Ledger & Strategy (5/5 plans) — completed 2026-07-11
- [x] Phase 4: Kaggle Kernel Execution (GPU Path) (6/6 plans) — completed 2026-07-11
- [x] Phase 5: Submission & Leaderboard Tracking (7/7 plans) — completed 2026-07-12

Full details: [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)

</details>

### 🚧 v2.0 Kaggle-general (In Progress)

**Milestone Goal:** kaggle-exp works across Kaggle competition types. It runs on a Kaggle kernel by default, a competition profile built from the API drives it, and a phase counts as done only when it has run live on a real competition.

- [ ] **Phase 6: kx Core & Live Kernel Loop** - One `kx` CLI drives empty folder → sync → new → script-kernel run → ledger → strategy, live on Titanic
- [ ] **Phase 7: Competition Profiles & Template Selection** - Profiles derived from the API and confirmed by the user, for any competition type, pick the guidance and the experiment template
- [ ] **Phase 8: Kaggle-First Compute** - Resumable, failure-honest kernels, train → inference pipelines, local subsample runs and environment provenance
- [ ] **Phase 9: Submission Modes** - csv_upload, code_kernel (incl. API-served) and agent submissions, prepared by kx, run by the human and confirmed by read-back; writeup guidance
- [ ] **Phase 10: Research & Ensembling** - Discussions, public notebooks and host metric kernels feed the strategy; OOF blends become experiments

**Overview:** Phase 6 rebuilds the core-value loop on v2 foundations: one `kx` CLI, a script kernel as the default runtime, and a profile of structured API facts. It proves the loop live on Titanic before any breadth is added. Phase 7 makes the profile classify any competition, has the user confirm it, and lets it pick the guidance and template. Phase 8 hardens Kaggle compute for real-size data: resumable and failure-honest runs, train → inference pipelines, local subsample runs and environment provenance. Phase 9 adds each competition's own kind of submission. kx prepares and validates it, the human runs it, and kx confirms it by read-back. Phase 10 adds the tools for winning: research ingestion, exact-metric CV and OOF ensembling.

**Mode: mvp on a CLI skill.** There is no UI, DB or deploy. In every phase the vertical slice is a real `kx` command invocation driving real Kaggle calls end to end. "Deployment" means `uv sync` plus a real `kx` run from a workspace. Every phase is non-frontend, so the UI-SPEC gate is N/A.

**Milestone-wide live-check rules** (these apply to every phase's success criteria):
- "Done" means a live run on a real competition, recorded in the phase verification. Fixtures only guard against regressions.
- Each phase runs its live checks inside the phase, never as a deferred "operator" step. The v1 lesson: 341 passing fixtures, then 4 live bugs on the first real run.
- Use CPU kernels wherever possible. The GPU quota (30 h/week) is shared with the user's other work, so GPU is only for short runs a template genuinely needs.
- Never submit to competitions the user is actively in (rsna-knee-abnormality-detection, cooked-or-not). Live submissions go to:
  - closed competitions with `submissions_disabled=False`: equity-post-HCT-survival-predictions, um-game-playing-strength-of-mcts-variants, isic-2024-challenge, birdclef-2025, llm-prompt-recovery
  - perpetual sandboxes: titanic, Playground Series, connectx
- The human runs every `kaggle competitions submit` with `!`, and kx confirms it by read-back. Joining a competition (accepting its rules) is also a browser-only human step.

**Requirement placement (dependency reasoning, including deviations from the suggested shape):**
- **RUN-01 → Phase 6.** The core-value cycle must run on a kernel by default, so the basic script-kernel push → poll → pull → record ships with the core. The other RUN items need the confirmed profile or a second runtime, so they go to Phase 8.
- **PROF-01 → Phase 6.** The first cycle needs the canonical ref (for `competition_sources` and the mount path) and the metric, and pass-1 structured facts supply both. Classification, confirmation and the pass-2 sync (PROF-02..05) go to Phase 7.
- **TMPL-01 → Phase 6** (suggested: 7). The first live cycle needs a tabular template. Porting v1's CV-enum scaffold only to replace it one phase later would be churn.
- **ENS-01 → Phase 6** (suggested: 10). The OOF/test prediction format is a contract every predictive template must meet. Fixing it with the first template, and having the recorder check it, avoids retrofitting TMPL-02/TMPL-03 in Phase 10.
- **CORE-05 → Phase 7** (suggested: 6). Its rule that type guidance loads "only for the confirmed competition type" needs PROF-04 confirmation. Phase 6 still rewrites SKILL.md around `kx` and keeps it lean; Phase 7 enforces the line budget and the per-type split.
- **TMPL-03 → Phase 7** (suggested: 8). It is a CPU, tabular-shaped template with no dependency on Phase 8 compute. It also gives TMPL-06's AI-override path a real second template to exercise live.
- **TMPL-06 → Phase 7.** Selection is built once against the confirmed profile, including an explicit "no template for this mode" path. writeup, artifact_upload and unknown never get a template in v2. Phases 8 and 9 each register their templates and prove that selection works for them.
- **RUN-03 → Phase 8.** The resolver's defining property is one code path for both kernel and local runs. Local data (PROF-05, Phase 7) and local runs (RUN-06, Phase 8) come later. Phase 6's template reads the spike-verified canonical mount directly.
- **CORE-07 → Phase 6.** By the end of Phase 6, every superseded path has a replacement or is dormant:
  - profile facts replace the regex scraping of type and limits
  - script kernels replace jupytext conversion
  - `kx init` replaces the consent flows
  - the egress allowlist becomes a documented opt-in
  - the submission gate stays dormant until Phase 9 and returns without the fold-noise margin
- **TMPL-04 and TMPL-05 → Phase 9.** Their live proof is a scored submission or a ladder rating.

## Phase Details

<!-- Parser note: each success criterion and each Goal/Mode/Depends on field must stay on ONE line (roadmap.cjs captures consecutive single-line numbered criteria). -->

### Phase 6: kx Core & Live Kernel Loop

**Goal**: As a Kaggle competitor, I want to go from an empty folder to a recorded experiment through one `kx` CLI that runs my idea on a Kaggle script kernel by default, so that the core loop (idea, kernel run, machine-checked score, verdict, ledger, strategy) works live on the v2 foundations.
**Mode:** mvp
**Depends on**: Nothing in v2.0; builds on v1.0's kept ledger, record, gateway and kernel modules (Phases 3-5) and the Phase 0 spike findings (`.claude/skills/spike-findings-kaggle-skill/`)
**Requirements**: CORE-01, CORE-02, CORE-03, CORE-04, CORE-06, CORE-07, PROF-01, RUN-01, TMPL-01, ENS-01
**Live slice**: On Titanic (or a Playground Series competition), with no submission: `uv sync` → `kx init` → `kx sync titanic` → `kx new` → `kx run` (private CPU script kernel, internet off) → record → verdict → ledger → strategy.
**Success Criteria** (what must be TRUE):

  1. From an empty folder, one `uv sync` installs everything the skill needs (including the `kaggle` CLI and SDK), and `kx init` sets up the workspace and validates the user's Kaggle credential live in one step: masked, never echoed, no consent prompts.
  2. Every `kx` subcommand prints exactly one JSON object with a `status` and a `next_action`, and the AI completes the loop by following `next_action` alone; each experiment is declared in an `experiment.json` (idea, hypothesis, template, runtime target, sources, accelerator, runtime limit) that kx validates, refusing an invalid one before anything is pushed.
  3. LIVE: `kx sync titanic` writes a `profile.json` built only from structured Kaggle API facts (competition fields including the canonical ref, `evaluation_metric`, `max_daily_submissions` and the code-only flag; the data-files summary; the root file listing), with nothing scraped from prose.
  4. LIVE core-value cycle on Titanic (or a Playground Series competition): `kx new` scaffolds the tabular template with AI-written CV code and records the reasoning behind it; `kx run` pushes it as a private CPU script kernel with internet off and no notebook conversion, polls with a bound, pulls the outputs and records a machine-checked CV score, with OOF and test predictions in the one standard format that the recorder validates; the verdict lands in the ledger and the strategy doc is regenerated.
  5. LIVE: v1's fail-closed contract holds under `kx`: a kernel run that throws, or writes an invalid `result.json`, is recorded FAILED and never with a score, and the never-repeat digest lists the ideas already tried. The superseded v1 paths are gone along with their tests: rules-prose scraping, exit-78 and "assumed 5/day"; jupytext conversion; the credential consent flows; the default egress allowlist (now a documented opt-in); the fold-noise margin.

**Plans**: TBD
**UI hint**: no. Non-frontend (Claude Code skill + `kx` CLI); UI-SPEC gate N/A.
**Risks carried in** (open questions, not requirements):
- Kernel image vs local env parity: the kernel runs Python 3.12.13 with Kaggle's own package pins, while local is 3.13 under `uv.lock`. The tabular template must not rely on 3.13-only or pandas-3-only behaviour.
- `kaggle kernels push` sometimes prints its success line with no version number. Read the version back; never guess it.
- Accelerator validation in `experiment.json` should accept only accelerator IDs verified live (CPU; T4 default). T4×2 and other GPU shapes are unverified (RUN-F3, future).
- Never record `KAGGLE*` env values, because they include `KAGGLE_USER_SECRETS_TOKEN`; record the keys only. The log scanner must whitelist the benign mistune/nbconvert SyntaxWarnings.
- The 01-03 egress `example.com` anomaly is unresolved. Once the allowlist is opt-in, its doc must say that enforcement is unverified.

### Phase 7: Competition Profiles & Template Selection

**Goal**: As a Kaggle competitor, I want to profile any competition from Kaggle's structured API facts and confirm that profile, so that kx loads the right guidance and scaffolds the right experiment template for the competition's type.
**Mode:** mvp
**Depends on**: Phase 6 (the `kx` core, the pass-1 `kx sync` facts, the tabular template and the kernel run)
**Requirements**: PROF-02, PROF-03, PROF-04, PROF-05, CORE-05, TMPL-03, TMPL-06
**Live slice**: `kx sync` over the spike-001 set of 20 competitions; confirmation of the Titanic profile and of the `unknown` residual; a pass-2 `kx sync` on a joined, locally feasible competition; `kx new` selection, plus an AI override to the walk-forward template run on a real time-series competition.
**Success Criteria** (what must be TRUE):

  1. LIVE: `kx sync` over the spike-001 set of 20 competitions produces profiles that match the spike-001 truth table (submission mode, the API-served flag, modality, data size, file count, local feasibility, daily limit, code-only flag, late-submission status, metric, canonical ref and expected output file), each with readable reasons and nothing scraped from prose; mode is right for at least 19 of 20, the residual comes out `unknown` (never a wrong mode), and the API-served flag is right for 20 of 20.
  2. LIVE: The AI shows each profile's evidence and the user confirms or corrects it, and kx refuses to use an unconfirmed profile for any template, runtime or submission decision; for the `unknown` residual, the AI reads the Evaluation page and proposes a mode, which the user confirms.
  3. LIVE: After the user joins a competition in the browser, re-running `kx sync` adds the nested file listing, and for a locally feasible competition such as Titanic it also downloads the data as one bundle with safe extraction, with no per-file download loop.
  4. LIVE: `kx new` picks the template that matches the confirmed profile (Titanic gets the tabular template), returns a clear `next_action` instead of a wrong template when the confirmed mode has none (e.g. writeup), and records the reason when the AI overrides the choice; the override is exercised by choosing the walk-forward time-series template on a real time-series competition (e.g. store-sales-time-series-forecasting), whose experiment runs on a kernel and records a walk-forward CV.
  5. `SKILL.md` covers the whole loop in about 150 lines or fewer, and after confirmation only the matching `references/types/<type>.md` is loaded; verified live: confirming Titanic loads the tabular guide and no other type guide.

**Plans**: TBD
**UI hint**: no. Non-frontend (Claude Code skill + `kx` CLI); UI-SPEC gate N/A.
**Risks carried in** (open questions, not requirements):
- The spike-001 truth set can drift: competitions change state, and `submissions_disabled` can flip. Re-confirm the truth table before scoring the classifier against it.
- The nested (depth-1) listing returns HTTP 403 until the user joins, and joining is browser-only. The two-pass sync must say so in its `next_action`.
- Per-file downloads (e.g. `kaggle_evaluation/*`) hit HTTP 429, and `competitions download --unzip` is unreliable on CLI 2.x (a STATE concern carried from v1 Phase 2). Download the bundle once and extract it with the zip-slip-safe extractor.
- `artifact_upload` (e.g. the Nemotron LoRA upload) and writeup have no v2 submission path (SUB-F1, future). A profile may name them, and `kx new` must then return a guidance-only `next_action`.
- The modality tag map has misses: Nemotron came out tabular, but its truth is text. The AI confirms modality.

### Phase 8: Kaggle-First Compute

**Goal**: As a Kaggle competitor, I want to run my experiments on Kaggle compute robustly (resumable, honest about failures, chained into train → inference pipelines, with a local subsample option), so that large vision and text competitions run through the same loop as tabular ones.
**Mode:** mvp
**Depends on**: Phase 7 (the confirmed profile's canonical ref, modality, local feasibility and template selection), and Phase 6's kernel run
**Requirements**: RUN-02, RUN-03, RUN-04, RUN-05, RUN-06, RUN-07, TMPL-02
**Live slice**: `kx new` (PyTorch image template) → a `kx run` training kernel → a `kx run` inference kernel chained through `kernel_sources`, on isic-2024-challenge; a text run on llm-prompt-recovery; failure, runtime-limit, detach/resume and local-subsample runs on real competitions.
**Success Criteria** (what must be TRUE):

  1. LIVE: A two-stage pipeline runs on a closed vision competition (e.g. isic-2024-challenge): a PyTorch image training kernel scaffolded from the new template (fold loop saving OOF predictions in the standard format, mixed precision, checkpoints to `/kaggle/working`) completes first; only then does kx push the inference kernel, which reads the training output through `kernel_sources`; both kernels write `kx_manifest.json`, and the downstream result records the upstream version it actually consumed.
  2. LIVE: The same PyTorch template scaffolds a text experiment that runs on a kernel for a real text competition (e.g. llm-prompt-recovery), and a training run cut off at its runtime limit resumes from the checkpoint it left in `/kaggle/working` instead of starting over.
  3. LIVE: A kernel that raises and a kernel stopped at its runtime limit are both recorded FAILED with the traceback, the log and the partial outputs they wrote; and the user can end the Claude session while a kernel is still running, after which a new session resumes polling and records the result without pushing again.
  4. LIVE: The same experiment code finds its data through one resolver, both on a kernel (including a mixed-case canonical ref such as `equity-post-HCT-survival-predictions`) and locally in `data/`; the user can run an experiment locally instead, on a subsample when the profile marks the data as too large, and the ledger marks that result as a subsample.
  5. LIVE: Every kernel run records the kernel's Docker image digest and the versions of key libraries, and kx shows them side by side with the local environment's versions.

**Plans**: TBD
**UI hint**: no. Non-frontend (Claude Code skill + `kx` CLI); UI-SPEC gate N/A.
**Risks carried in** (spike frontier; not requirements):
- **Mount paths for `dataset_sources` and `model_sources` are unverified.** They are likely `/kaggle/input/datasets/…` and `/kaggle/input/models/…`. With internet off, the PyTorch template's pretrained weights depend on them, so live-probe them before the template relies on them.
- **`kernel_sources` version pins are silently dropped.** Downstream mounts the latest COMPLETE upstream version, so the recorded `kx_manifest.json` is the only provenance. Dataset-version pinning (RUN-F1) is future.
- **Resume after a cancellation is unverified.** `kernel_sources` mounts only the latest COMPLETE upstream version, so it is unknown how the next run reads a cancelled version's checkpoint. Live-probe this early in the phase.
- **`docker_image` pinning on push (RUN-F2) is future.** RUN-07 records the image digest but cannot prevent the scoring rerun from using a different image.
- **T4×2 and multi-GPU accelerator strings are unverified (RUN-F3, future).** The GPU quota is shared, so keep the mixed-precision GPU check short.
- **Local subsampling is an open design question.** It is not yet settled how a subsample is obtained locally for a competition too large for local runs: a single-file download vs the bundle, given the 429 on per-file loops.

### Phase 9: Submission Modes

**Goal**: As a Kaggle competitor, I want to get each competition's own kind of submission prepared and validated for me to run, so that every submit I make is within budget, correct and confirmed by read-back, with its score recorded next to CV.
**Mode:** mvp
**Depends on**: Phase 7 (the confirmed submission mode, expected output file, daily limit and canonical ref) and Phase 8 (kernel failure capture, and train → inference pipelines feeding code-competition submissions)
**Requirements**: SUB-01, SUB-02, SUB-03, SUB-04, SUB-05, SUB-06, SUB-07, TMPL-04, TMPL-05
**Live slice**: `kx submit` → the human runs the handed-over command with `!` → read-back → `kx lb`, on Titanic (csv_upload), equity-post-HCT-survival-predictions (code_kernel), um-game-playing-strength-of-mcts-variants (API-served) and connectx (agent); plus a checklist for a real writeup competition.
**Success Criteria** (what must be TRUE):

  1. `kx submit` checks a candidate against the confirmed profile (the expected file name, and the columns and row count against the sample), the remaining daily slots (from `max_daily_submissions`) and its CV versus the best submitted CV; it refuses a failing candidate with the reason, and otherwise prints the exact `kaggle competitions submit` command for the human to run with `!`. kx never runs a submit itself.
  2. LIVE csv_upload on Titanic (a perpetual sandbox): the human runs the handed-over file-upload command; kx confirms it by reading back the submissions list, polls until it is scored and records the public score with the file hash; `kx lb` then shows the leaderboard score next to CV, with the CV→LB gap trend and the divergence alarm.
  3. LIVE code_kernel, on closed competitions with late submissions open: the inference script template writes the profile's expected output file, both on equity-post-HCT-survival-predictions (file output) and on um-game-playing-strength-of-mcts-variants (API-served: it starts the `kaggle_evaluation` server first, uses the local gateway with explicit data paths on its own run, and calls `serve()` on the scoring rerun). Before handing over `submit <canonical-ref> -k <owner/slug> -v <N> -f <file>`, kx verifies that each kernel version is COMPLETE, ran with internet off and produced the expected file; after the human runs it, read-back records the public and private scores with kernel slug and version provenance (API-served scoring takes about 20 minutes, polled within a budget).
  4. LIVE agent track on ConnectX: a single-file agent scaffolded from the template passes local self-play validation and reports its win rate against a pool of its own previous versions plus baseline agents, using `kaggle-environments` only in a throwaway environment; after the human uploads it, kx reads back the rating and the episodes and derives win/loss/draw from the replays, and `kx lb` trends the rating.
  5. LIVE: For a real writeup competition, kx produces a drafting checklist from the competition's evaluation criteria and the ledger, and tells the user to submit it by hand on the website.

**Plans**: TBD
**UI hint**: no. Non-frontend (Claude Code skill + `kx` CLI); UI-SPEC gate N/A.
**Risks carried in** (spike frontier; not requirements):
- Claude Code auto-mode denies `kaggle competitions submit` as a real-world transaction. Never work around the denial; the human runs every submit.
- A code-competition submit prints nothing and exits 0, so success is proven only by read-back. API-served scoring takes about 20 minutes, which needs budgeted polling with resume; never block the session on it.
- The host gateway's default data paths point at the retired `/kaggle/input/<slug>/` mount, so pass explicit paths to `run_local_gateway`. Start the server before any slow step, because the host enforces a startup limit.
- `competitions episodes --format json` prints a trailing prose line, so decode only the leading JSON value with `raw_decode`.
- `kaggle-environments` pulls in 117 packages, so run it only via `uv run --no-project --with`.
- Local wins against the built-in bots did not predict the ladder rating (600 → 528.6), and ConnectX allows 2 submissions per day.
- A csv_upload through a v2 profile and `kx` has never run live end to end (spike frontier); this phase closes that gap. Writeup guidance has never been exercised live, and `artifact_upload` stays guidance-only (SUB-F1, future).
- Replays and agent logs contain other players' names, so never commit them.

### Phase 10: Research & Ensembling

**Goal**: As a Kaggle competitor, I want to draw on the community's discussions, public notebooks and host metric kernels and to blend my own experiments, so that my ideas and my CV track what actually wins the competition.
**Mode:** mvp
**Depends on**: Phase 8 (`kernel_sources` attachment for host metric kernels), Phase 7 (the profile's metric and canonical ref) and Phase 6's standard OOF format; it does not need Phase 9's submission tracks
**Requirements**: RES-01, RES-02, RES-03, RES-04, ENS-02
**Live slice**: `kx research` on a closed competition (e.g. isic-2024-challenge or equity-post-HCT-survival-predictions); a host metric kernel used for CV; a research-sourced idea run as an experiment; `kx ensemble` on a Playground Series competition.
**Success Criteria** (what must be TRUE):

  1. LIVE: `kx research` on a closed competition fetches the top discussion threads, with full bodies read through the SDK, and writes one `research/` note per thread, labelled as external content; nothing in them is executed or obeyed.
  2. LIVE: `kx research` lists and pulls the top public notebooks (by score after the competition closes, by votes while it runs) and summarizes each one, including the sources it attaches (metric kernels, offline wheels, pretrained weights); the raw pulled content stays in an uncommitted cache that git never sees.
  3. LIVE: kx finds the host's `metric/*` kernel for the profile's metric (e.g. ISIC pAUC, or equity's concordance index), the AI confirms the match, and the experiment's CV is then computed by that kernel's `score()`; for a competition with no metric kernel, the AI implements the metric from the Evaluation page and the user confirms it.
  4. LIVE: Ideas from research enter the strategy doc's hypothesis queue, each tagged with its source, and at least one research-sourced idea is run as an experiment and recorded with its source tag.
  5. LIVE: On a Playground Series competition, `kx ensemble` blends the saved OOF predictions of the chosen experiments (by hill-climbing or optimized weights) and records the blend as a new experiment with its own CV, which beats the best single model's CV.

**Plans**: TBD
**UI hint**: no. Non-frontend (Claude Code skill + `kx` CLI); UI-SPEC gate N/A.
**Risks carried in** (spike frontier; not requirements):
- RES-04 executes host metric code, which is a trust boundary distinct from community content. Attach `metric/<slug>` through `kernel_sources` and run it on Kaggle, and only after the AI confirms the match. Community notebook code is never executed.
- Metric-search hits are unreliable: 3 of 7 were exact, and "Sharpened-Cosine" returned a generic orchestrator. The AI's confirmation is mandatory.
- The CLI's `competitions topics show` drops the original post, so thread bodies come only from the SDK's `list_topic_messages(page_size=-1)`.
- The research budget of 20 topics plus 10 notebooks comes to about 150–300k chars. Summarize each item into a note; never dump raw content into context.
- Blend weights are fit on the same OOF predictions they are scored on, so ensemble CV is optimistic. Record it honestly and watch the CV→LB gap. `kx select` (SEL-01) stays future.

## Progress

**Execution Order:**
Phases execute in numeric order: 6 → 7 → 8 → 9 → 10

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Workspace, Credentials & Egress Guardrails | v1.0 | 4/4 | Complete | 2026-07-09 |
| 2. Competition Context & Data | v1.0 | 7/7 | Complete | 2026-07-10 |
| 3. Local Experiment Loop, Ledger & Strategy | v1.0 | 5/5 | Complete | 2026-07-11 |
| 4. Kaggle Kernel Execution (GPU Path) | v1.0 | 6/6 | Complete | 2026-07-11 |
| 5. Submission & Leaderboard Tracking | v1.0 | 7/7 | Complete | 2026-07-12 |
| 6. kx Core & Live Kernel Loop | v2.0 | 0/TBD | Not started | - |
| 7. Competition Profiles & Template Selection | v2.0 | 0/TBD | Not started | - |
| 8. Kaggle-First Compute | v2.0 | 0/TBD | Not started | - |
| 9. Submission Modes | v2.0 | 0/TBD | Not started | - |
| 10. Research & Ensembling | v2.0 | 0/TBD | Not started | - |

## Coverage

- v2.0 requirements: 38 total
- Mapped to phases: 38 (100%)
- Orphaned: 0

| Phase | Requirements | Count |
|-------|--------------|-------|
| 6 | CORE-01, CORE-02, CORE-03, CORE-04, CORE-06, CORE-07, PROF-01, RUN-01, TMPL-01, ENS-01 | 10 |
| 7 | PROF-02, PROF-03, PROF-04, PROF-05, CORE-05, TMPL-03, TMPL-06 | 7 |
| 8 | RUN-02, RUN-03, RUN-04, RUN-05, RUN-06, RUN-07, TMPL-02 | 7 |
| 9 | SUB-01, SUB-02, SUB-03, SUB-04, SUB-05, SUB-06, SUB-07, TMPL-04, TMPL-05 | 9 |
| 10 | RES-01, RES-02, RES-03, RES-04, ENS-02 | 5 |

The future requirements (SEL-01, RUN-F1, RUN-F2, RUN-F3, SUB-F1, ANLY-01..03, EXT-02, EXT-03) are deferred and intentionally not mapped. The frontier risks behind RUN-F1..F3 and SUB-F1 appear as "Risks carried in" notes on the phases they touch.

---
*Roadmap created: 2026-07-09*
*v1.0 archived: 2026-09-25*
*v2.0 phases added: 2026-09-25 (Granularity: standard | Mode: mvp)*
