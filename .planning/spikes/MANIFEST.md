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
- Never submit to a competition the user is actively competing in (e.g. rsna-knee-abnormality-detection, cooked-or-not) — spikes use closed competitions (late submissions) or perpetual sandboxes (ConnectX, Titanic).

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | competition-profile-from-api | standard | Given SDK metadata + files summary + root tree, when classifying 20 mixed comps, then mode/modality/API-served/size are right without prose scraping | ✓ VALIDATED (mode 19/20, residual = safe `unknown`) | kaggle-api, competition-profile |
