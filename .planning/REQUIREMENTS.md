# Requirements: Kaggle Experimentation Framework

**Defined:** 2026-09-25 (milestone v2.0 Kaggle-general)
**Core Value:** One clean end-to-end experiment cycle — from an empty folder to an idea run, its result and reasoning logged to the ledger, and the strategy doc updated.

**Definition of done:** a requirement is Complete only after a **live** demonstration on a real Kaggle
competition, recorded in the phase verification. Fixtures guard against regressions but never count as done.
Live checks use CPU kernels where possible, and never submit to a competition the user is actively competing in.

**Evidence base:** the Phase 0 spikes (`.planning/spikes/`, and the `spike-findings-kaggle-skill` skill).

## v2.0 Requirements

### Core (`kx` CLI)

- [ ] **CORE-01**: The user drives every step of the loop through one `kx` CLI. Every subcommand prints one JSON object with a `status` and a `next_action` for the AI to follow, replacing v1's 28 scripts and its exit-code protocol.
- [ ] **CORE-02**: The user can set up a workspace and validate their Kaggle credential in one step with `kx init`. The credential is masked and never echoed, and there are no consent prompts.
- [ ] **CORE-03**: Each experiment is declared in an `experiment.json`, which kx validates before any run. It holds the idea, hypothesis, template, runtime target, data/kernel/model sources, accelerator and runtime limit.
- [ ] **CORE-04**: v1's fail-closed result contract, version-controlled ledger, never-repeat digest and regenerated strategy doc keep working unchanged under `kx`.
- [ ] **CORE-05**: `SKILL.md` covers the loop in about 150 lines or fewer. Type-specific guidance lives in `references/types/*.md` and is loaded only for the confirmed competition type.
- [ ] **CORE-06**: The user installs everything the skill needs with one command: `uv sync` on the skill's locked environment, which includes the `kaggle` package (CLI and SDK).
- [ ] **CORE-07**: v1 code paths that v2 supersedes are removed along with their tests:
  - rules-prose regex scraping, exit-78 and "assumed 5/day"
  - jupytext notebook conversion
  - the credential consent flows
  - the default egress allowlist, which remains a documented opt-in
  - the fold-noise margin in the submission gate

### Competition Profile (`kx sync`)

- [ ] **PROF-01**: The user can run `kx sync <competition>` before joining and get a `profile.json` built only from structured Kaggle API facts (competition fields, the data-files summary, the root file listing). Nothing is scraped from prose.
- [ ] **PROF-02**: The profile assigns exactly one submission mode (`csv_upload | code_kernel | agent | writeup | artifact_upload | unknown`), gives readable reasons, and flags API-served (`kaggle_evaluation`) competitions.
- [ ] **PROF-03**: The profile records:
  - modality, total data size, file count and local feasibility
  - the daily submission limit, the code-only flag and whether late submissions are open
  - the evaluation metric, the canonical competition ref and the expected output file name
- [ ] **PROF-04**: The AI shows the profile's evidence, and the user confirms or corrects it before any template, runtime or submission decision uses it. An `unknown` mode makes the AI read the Evaluation page and propose a mode.
- [ ] **PROF-05**: After the user joins (a browser step), re-running `kx sync` adds the nested file listing. When local runs are feasible, it also downloads the data as one bundle with safe extraction.

### Experiment Templates (`kx new`)

- [ ] **TMPL-01**: The user can scaffold a tabular experiment whose CV scheme is AI-written code, with its reasoning recorded in the experiment. This replaces the four-option CV enum.
- [ ] **TMPL-02**: The user can scaffold a PyTorch image or text experiment with a fold loop that:
  - saves OOF predictions
  - uses mixed precision
  - checkpoints to `/kaggle/working`, so a cancelled run can resume
- [ ] **TMPL-03**: The user can scaffold a time-series experiment with walk-forward validation.
- [ ] **TMPL-04**: The user can scaffold a code-competition inference script that writes the profile's expected output file. For API-served competitions, it starts the `kaggle_evaluation` server first: `serve()` on the scoring rerun, otherwise the local gateway with explicit data paths.
- [ ] **TMPL-05**: The user can scaffold a single-file simulation agent. Its local evaluation runs self-play validation and measures the win rate against a pool of the agent's own previous versions plus baseline agents, using `kaggle-environments` in a throwaway environment.
- [ ] **TMPL-06**: `kx new` picks the template that matches the confirmed profile (modality plus submission mode). The AI can override it, and the reason is recorded.

### Runtime (`kx run`)

- [ ] **RUN-01**: `kx run` pushes an experiment as a private script kernel, with internet off by default. It waits with bounded polling, pulls the outputs and records the result, with no notebook conversion.
- [ ] **RUN-02**: The user can end a session while a kernel is running, then resume polling and recording later without pushing again.
- [ ] **RUN-03**: Experiment code finds competition data through one resolver, both on Kaggle (`/kaggle/input/competitions/<canonical-ref>`, falling back to the legacy mount) and locally (`data/`).
- [ ] **RUN-04**: A kernel that errors or hits its runtime limit is recorded as FAILED, with its traceback, its log and any partial outputs it wrote.
- [ ] **RUN-05**: The user can run a two-stage pipeline in which an inference kernel reads a training kernel's output through `kernel_sources`:
  - kx pushes the downstream kernel only after the upstream one completes
  - each kernel writes `kx_manifest.json`
  - the downstream result records which upstream version it actually used
- [ ] **RUN-06**: The user can run an experiment locally instead, on a subsample when the profile marks the data as too large. The ledger marks subsample results as such.
- [ ] **RUN-07**: Every kernel run records the kernel's Docker image digest and the versions of key libraries, so local and Kaggle environments can be compared.

### Submission & Leaderboard (`kx submit` / `kx lb`)

- [ ] **SUB-01**: `kx submit` checks a candidate against the profile (file name, columns and row count against the sample), the remaining daily slots and its CV against the best submitted CV. It then gives the user the exact `kaggle competitions submit` command to run; kx never submits by itself.
- [ ] **SUB-02**: For `csv_upload` competitions, the handed-over command uploads the validated file.
- [ ] **SUB-03**: For `code_kernel` competitions, including API-served ones, kx first verifies that the kernel version is complete, ran with internet off and produced the expected output file. Only then does it hand over `submit <canonical-ref> -k <owner/slug> -v <N> -f <file>`.
- [ ] **SUB-04**: After the user runs a submit, kx confirms it by reading back the submissions list. It polls until the submission is scored (minutes for tabular, tens of minutes for API-served) and records the public and private scores with provenance: kernel slug and version, or file hash.
- [ ] **SUB-05**: For `agent` competitions, kx hands over the file-upload command after local validation. It then reads back the rating and episodes, and derives win/loss/draw from the replays.
- [ ] **SUB-06**: `kx lb` shows leaderboard scores, or agent ratings, next to CV, and trends the CV→LB gap with a divergence alarm.
- [ ] **SUB-07**: For `writeup` competitions, kx produces a drafting checklist from the competition's evaluation criteria and the ledger. The user submits it by hand on the website.

### Research (`kx research`)

- [ ] **RES-01**: `kx research` fetches the top discussion threads, with full bodies read through the SDK, and summarizes each one into a `research/` note labelled as external content. The content is never executed or obeyed.
- [ ] **RES-02**: `kx research` lists and pulls top public notebooks (by score after the competition closes, by votes while it runs). It summarizes them, including the sources they attach (metric kernels, offline wheels, pretrained weights). Raw pulled content stays in an uncommitted cache.
- [ ] **RES-03**: Research notes feed the strategy doc's hypothesis queue, with each idea tagged by its source.
- [ ] **RES-04**: kx finds the host's `metric/*` kernel for the profile's metric, and CV uses its `score()` once the AI confirms the match. When no metric kernel exists, the AI implements the metric from the Evaluation page and the user confirms it.

### Ensembling (`kx ensemble`)

- [ ] **ENS-01**: Every template saves OOF and test predictions in one standard format, so any set of experiments can be blended.
- [ ] **ENS-02**: `kx ensemble` blends the saved OOF predictions of the chosen experiments, by hill-climbing or optimized weights, and records the blend as a new experiment with its own CV.

## Future Requirements

Deferred. Tracked, but not in the v2.0 roadmap.

### Submission & Compute

- **SEL-01**: `kx select` proposes the two final submissions (one best-CV, one robust or diverse) with reasoning.
- **RUN-F1**: Upload weights or intermediate outputs as a private dataset or model version, for pinned reuse across kernels. This first needs a live spike on dataset version pinning.
- **RUN-F2**: Pin the kernel `docker_image` on push, for reproducible environments.
- **RUN-F3**: Verified multi-GPU accelerator choices (e.g. T4×2).
- **SUB-F1**: Guidance for `artifact_upload` competitions (e.g. a LoRA adapter upload), never exercised live.

### Analysis & Loop Hardening (carried from v1)

- **ANLY-01**: Semantic idea deduplication (embedding or fingerprint), going beyond the prompt-driven never-repeat rule.
- **ANLY-02**: Comparison and summary views over the ledger (best so far, deltas, trends).
- **ANLY-03**: Strategy synthesis that orders the hypothesis queue by the evidence of observed ledger movement.
- **EXT-02**: Hyperparameter sweeps as a first-class experiment type.
- **EXT-03**: Multi-agent and cross-runtime portability (opencode, other agents).

## Out of Scope

Explicitly excluded, and documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| kx running `kaggle competitions submit` itself | Submissions are irreversible and budgeted. The human runs every submit, and Claude Code auto-mode also blocks it as a real-world transaction. |
| Live checks that submit to competitions the user is actively in | Could disturb their real standing. Checks use closed competitions still open to late submissions, or perpetual sandboxes (Titanic, ConnectX). |
| Committing third-party notebook code or forum text | Not ours to redistribute. Only listings, metadata and our own summaries are kept. |
| Badges, benchmarks, model/dataset publishing | Kaggle-ops features that don't help win a competition |
| Hosted dashboards / team collaboration | Built by design as a file-based, AI-readable tool for a single practitioner |
| Dependency on shepsci/kaggle-skill | Standalone by decision |
| General (non-competition) ML R&D workflows | Competition-focused |

## Traceability

Which phases cover which requirements. Filled in during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CORE-01 | Phase 6 | Pending |
| CORE-02 | Phase 6 | Pending |
| CORE-03 | Phase 6 | Pending |
| CORE-04 | Phase 6 | Pending |
| CORE-05 | Phase 7 | Pending |
| CORE-06 | Phase 6 | Pending |
| CORE-07 | Phase 6 | Pending |
| PROF-01 | Phase 6 | Pending |
| PROF-02 | Phase 7 | Pending |
| PROF-03 | Phase 7 | Pending |
| PROF-04 | Phase 7 | Pending |
| PROF-05 | Phase 7 | Pending |
| TMPL-01 | Phase 6 | Pending |
| TMPL-02 | Phase 8 | Pending |
| TMPL-03 | Phase 7 | Pending |
| TMPL-04 | Phase 9 | Pending |
| TMPL-05 | Phase 9 | Pending |
| TMPL-06 | Phase 7 | Pending |
| RUN-01 | Phase 6 | Pending |
| RUN-02 | Phase 8 | Pending |
| RUN-03 | Phase 8 | Pending |
| RUN-04 | Phase 8 | Pending |
| RUN-05 | Phase 8 | Pending |
| RUN-06 | Phase 8 | Pending |
| RUN-07 | Phase 8 | Pending |
| SUB-01 | Phase 9 | Pending |
| SUB-02 | Phase 9 | Pending |
| SUB-03 | Phase 9 | Pending |
| SUB-04 | Phase 9 | Pending |
| SUB-05 | Phase 9 | Pending |
| SUB-06 | Phase 9 | Pending |
| SUB-07 | Phase 9 | Pending |
| RES-01 | Phase 10 | Pending |
| RES-02 | Phase 10 | Pending |
| RES-03 | Phase 10 | Pending |
| RES-04 | Phase 10 | Pending |
| ENS-01 | Phase 6 | Pending |
| ENS-02 | Phase 10 | Pending |

**Coverage:**
- v2.0 requirements: 38 total
- Mapped to phases: 38 (100%)
- Unmapped: 0
- By phase:
  - Phase 6: 10 (CORE-01..04, CORE-06, CORE-07, PROF-01, RUN-01, TMPL-01, ENS-01)
  - Phase 7: 7 (PROF-02..05, CORE-05, TMPL-03, TMPL-06)
  - Phase 8: 7 (RUN-02..07, TMPL-02)
  - Phase 9: 9 (SUB-01..07, TMPL-04, TMPL-05)
  - Phase 10: 5 (RES-01..04, ENS-02)

---
*Requirements defined: 2026-09-25*
*Last updated: 2026-09-25 after v2.0 roadmap creation (traceability filled)*
