---
name: spike-findings-kaggle-skill
description: Implementation blueprint from the v2 Phase 0 spike experiments. It holds the requirements, proven patterns and live-verified Kaggle facts (competition profiles from kagglesdk, script kernels and kernel_sources chaining, code-competition and API-served submission, simulation agents, discussion and notebook research) for building kaggle-exp v2. Auto-loaded during implementation work on kx, kernels, submissions or competition profiles.
---

<context>
## Project: kaggle-skill (kaggle-exp v2, "Kaggle-general")

Phase 0 of the v2 "Kaggle-general" direction for the `kaggle-exp` skill, decided on 2026-09-25:
- A Kaggle **kernel** becomes the default runtime.
- Every competition is driven through a **profile**. The profile selects type-specific templates and a
  submission mode:
  - `csv_upload`
  - `code_kernel` (+ `api_served`)
  - `agent`
  - `writeup`
  - `artifact_upload`
  - `unknown`
- One `kx` CLI, printing JSON with `next_action`, replaces v1's 28 scripts.

These spikes live-verified the Kaggle primitives v2 depends on before any design was locked:
- structured competition metadata
- script kernels and kernel-output chaining
- code-competition submission of a kernel version, including API-served comps
- simulation agent submission and episode read-back
- discussion and public-notebook ingestion

Spike sessions wrapped: 2026-09-25
</context>

<requirements>
## Requirements

These are non-negotiable design decisions, accepted by the user on 2026-09-25 ("go with your recommendations") and
refined by the spikes:

- **Runtime:**
  - The Kaggle kernel is the DEFAULT runtime.
  - Local execution stays an OPTION for small or tabular data.
- **Dependencies:** the skill MAY use the `kaggle` Python package (`kaggle.api`, `kagglesdk`), which is the same
  dependency as the CLI. The "stdlib-only" rule is dropped.
- **Scope:**
  - Simulations are in v2 scope, with ConnectX as the test bed.
  - Analytics and writeup competitions get guidance only, with no CLI submit.
- **Done:** "Done" means a live run on a real competition, never a fixture count. Fixtures only guard against
  regressions.
- **Live checks:** use CPU kernels wherever possible, because the GPU quota is shared with the user's other work.
- **Competition profile:**
  - It comes from SDK structured fields, the files summary and a file tree at most one level deep, never from regex
    over prose.
  - The AI confirms it.
- **Submission modes:** `csv_upload | code_kernel (+api_served) | agent | writeup | artifact_upload | unknown`.
- **Kernels:**
  - Kernels default to `kernel_type: "script"`, with no notebook conversion.
  - The data resolver checks `/kaggle/input/competitions/<slug>` first.
- **Pipelines:**
  - Wait for upstream COMPLETE before pushing downstream.
  - Record the upstream `kx_manifest.json` actually consumed, because `kernel_sources` version pins are silently
    dropped.
- **Research ingestion:**
  - It reads discussions and public notebooks, labelled external and never executed or obeyed.
  - Thread bodies come via the SDK `list_topic_messages(page_size=-1)`.
  - CV uses the host `metric/*` kernel's `score()` when one exists.
- **Third-party content:** notebook code and forum text are read live but never committed.
- **Code competitions:**
  - They submit a SCRIPT kernel version: `submit <canonical-ref> -k -v -f <profile output file>`.
  - Success is confirmed by read-back only.
- **Every submission is executed by the human.** Auto-mode classifies it as a real-world transaction. kx prepares
  and validates, hands over the exact command, then reads back.
- **Simulation comps** get an agent track:
  - ephemeral `kaggle-environments` evaluation against a strong pool
  - file-upload submit
  - rating and episode read-back
- **Never submit to a competition the user is actively competing in** (e.g. rsna-knee-abnormality-detection,
  cooked-or-not). Live checks use closed competitions (late submissions) or perpetual sandboxes (ConnectX, Titanic).
</requirements>

<findings_index>
## Feature Areas

| Area | Reference | Key Finding |
|------|-----------|-------------|
| Competition profile | references/competition-profile.md | Structured SDK fields classify comps with mode accuracy 19/20. The presence of a sample-submission file is the key discriminator. Nested listing returns 403 until the user joins. |
| Script kernels | references/script-kernels.md | Script kernels need no papermill workarounds. Data is at `/kaggle/input/competitions/<Canonical>`. Chained outputs are at `/kaggle/input/notebooks/<owner>/<slug>`. Version pins are silently dropped. Partial outputs survive `ERROR` and `-t` cancellation. |
| Code-competition submission | references/code-competition-submission.md | A script kernel version submits and scores: tabular in ≤ 3 min, API-served in ~20 min. Submit prints nothing, so confirm by read-back. The human runs the submit. |
| Simulation agents | references/simulation-agents.md | The full loop is reachable from the CLI. `episodes --format json` needs `raw_decode`. Local wins against the built-in bots don't predict the ladder rating. |
| Research ingestion | references/research-ingestion.md | Topics and notebooks are readable without joining. The CLI `topics show` drops the original post, so use the SDK. Host `metric/*` kernels give exact-metric CV. |

## Source Files

The original spike source files are preserved in `sources/` for complete reference, and `sources/_shared/` holds
the poll and read-back helpers. These are reference copies: their `.venv` paths are relative to
`.planning/spikes/`, so run the originals there. Pulled evidence (logs, raw API JSON) stays in
`.planning/spikes/NNN-*/`.
</findings_index>

<metadata>
## Processed Spikes

- 001-competition-profile-from-api
- 002-script-kernel-chaining
- 003-code-comp-submit
- 004-connectx-agent
- 005-research-ingestion
</metadata>
