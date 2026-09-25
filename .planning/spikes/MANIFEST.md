# Spike Manifest

## Idea

Phase 0 of the v2 "Kaggle-general" direction for the `kaggle-exp` skill (decided 2026-09-25). v2 makes a
Kaggle **kernel** the default runtime and drives every competition through a **profile** that selects
type-specific templates and a submission mode (`csv_upload` | `code_kernel` | `agent` | `writeup`).
Before any design is locked, these spikes live-verify the Kaggle primitives v2 depends on: structured
competition metadata, script kernels + kernel-output chaining, code-competition submission of a kernel
version, simulation agent submission + episode read-back, and discussion/public-notebook ingestion.

## Requirements

Design decisions accepted by the user (2026-09-25, "go with your recommendations"):

- Kaggle kernel is the DEFAULT runtime; local execution stays an OPTION for small/tabular data.
- The skill MAY use the `kaggle` Python package (`kaggle.api`) — same dependency as the CLI; "stdlib-only" is dropped.
- Simulations are in v2 scope (ConnectX = test bed); analytics/writeup competitions get guidance only (no CLI submit).
- "Done" = a live run on a real competition, never a fixture count. Fixtures only guard regressions.
- Live checks use CPU kernels wherever possible (GPU quota is shared with the user's other work).
- Competition profile comes from SDK structured fields (+ files summary + depth-≤1 tree), never regex over prose; the AI confirms it (spike 001).
- Submission modes: `csv_upload | code_kernel (+api_served) | agent | writeup | artifact_upload | unknown` (spike 001 found `artifact_upload`, e.g. a LoRA adapter).
- Kernels default to `kernel_type: "script"` (no notebook conversion); data resolver checks `/kaggle/input/competitions/<slug>` first (spike 002).
- Pipelines wait for upstream COMPLETE before pushing downstream, and record the upstream `kx_manifest.json` actually consumed — `kernel_sources` version pins are silently dropped (spike 002).
- Research ingestion reads discussions + public notebooks (labelled external, never executed/obeyed); thread bodies via SDK `list_topic_messages(page_size=-1)`; CV uses the host `metric/*` kernel's `score()` when one exists (spike 005).
- Third-party notebook code / forum text is read live but never committed to this repo.
- Code competitions submit a SCRIPT kernel version (`submit <canonical-ref> -k -v -f <profile output file>`); success confirmed by read-back only (spike 003).
- Every submission is executed by the human (auto-mode classifies it as a real-world transaction): kx prepares + validates, hands over the exact command, then reads back (spikes 003/004).
- Simulation comps get an agent track: ephemeral kaggle-environments eval vs a strong pool, file-upload submit, rating/episode read-back (spike 004).
- Never submit to a competition the user is actively competing in (e.g. rsna-knee-abnormality-detection, cooked-or-not) — spikes use closed competitions (late submissions) or perpetual sandboxes (ConnectX, Titanic).

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | competition-profile-from-api | standard | Given SDK metadata + files summary + root tree, when classifying 20 mixed comps, then mode/modality/API-served/size are right without prose scraping | ✓ VALIDATED (mode 19/20, residual = safe `unknown`) | kaggle-api, competition-profile |
| 002 | script-kernel-chaining | standard | Given a CPU script kernel A writing artifacts, when kernel B lists A in kernel_sources, then B reads A's output at a discoverable path | ✓ VALIDATED (version pin silently dropped — ✗ sub-assumption) | kaggle-kernels, script-kernel, kernel-sources |
| 003a | code-comp-submit (script) | comparison | Given a closed code comp, when a SCRIPT kernel version is submitted via `submit -k -v -f`, then it is rerun on hidden test and scored | ✓ WINNER (scored 0.64754/0.65377) | code-competition, script-kernel |
| 003b | code-comp-submit (notebook) | comparison | Same, NOTEBOOK kernel | ✓ VALIDATED (identical score; no advantage) | code-competition, notebook |
| 003c | code-comp-submit (API-served) | standard | Given a kaggle_evaluation comp, when a script kernel that `serve()`s on rerun is submitted, then it is scored | ✓ VALIDATED (~20 min, 0.57164/0.57683) | api-served, kaggle-evaluation |
| 004 | connectx-agent | standard | Given a locally validated ConnectX agent, when main.py is submitted via CLI, then validation/ladder episodes, replays, logs and rating are readable via CLI | ✓ VALIDATED (local baselines ≠ ladder strength) | simulation, connectx, episodes |
| 005 | research-ingestion | standard | Given a competition, when reading top topics + public notebooks via CLI/SDK, then full write-ups and code are retrievable without joining | ✓ VALIDATED (thread bodies need SDK; host metric kernels found) | research, discussions, metric-kernels |
