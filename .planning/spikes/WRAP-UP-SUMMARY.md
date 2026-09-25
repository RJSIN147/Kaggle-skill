# Spike Wrap-Up Summary

**Date:** 2026-09-25
**Spikes processed:** 5 (7 experiments: 003 ran as 003a, 003b and 003c)
**Feature areas:** Competition profile, Script kernels, Code-competition submission, Simulation agents, Research ingestion
**Skill output:** `./.claude/skills/spike-findings-kaggle-skill/`

## Processed Spikes

| # | Name | Type | Verdict | Feature Area |
|---|------|------|---------|--------------|
| 001 | competition-profile-from-api | standard | ✓ VALIDATED (mode 19/20; the residual is a safe `unknown`) | Competition profile |
| 002 | script-kernel-chaining | standard | ✓ VALIDATED; the version-pin sub-assumption was ✗ INVALIDATED | Script kernels |
| 003 | code-comp-submit (a script / b notebook / c API-served) | comparison | ✓ VALIDATED; script WINS | Code-competition submission |
| 004 | connectx-agent | standard | ✓ VALIDATED | Simulation agents |
| 005 | research-ingestion | standard | ✓ VALIDATED | Research ingestion |

## Key Findings

1. **Classification from structured facts works.**
   - The profile uses SDK `get_competition` (`is_kernels_submissions_only`, `max_daily_submissions`,
     `evaluation_metric`, `tags`, `submissions_disabled`), the files summary (bytes per extension) and the root tree.
   - Its mode was right for 19 of 20 comps. The discriminator is whether a sample-submission file exists; the
     `games` tag is a trap.
   - The residual, Nemotron, comes out `unknown`, and the AI resolves it to `artifact_upload`.
   - Nested tree listing returns 403 until the user joins, so the sync runs in two passes.
2. **Script kernels are the runtime.**
   - They run `/kaggle/src/script.py` with `__file__` set and no ipykernel. Data is at
     `/kaggle/input/competitions/<Canonical-Slug>/`.
   - Upstream kernel outputs are at `/kaggle/input/notebooks/<owner>/<slug>/`.
   - `kernel_sources` version pins are silently dropped: downstream gets the latest COMPLETE upstream version.
   - `push -t` ends in `CANCEL_ACKNOWLEDGED`, and an exception ends in `ERROR`. Partial outputs survive both.
3. **Code competitions accept script kernel versions:** `submit <ref> -k -v -f`.
   - Script and notebook scored identically (0.64754 / 0.65377) within 3 minutes.
   - The API-served `kaggle_evaluation` comp scored in about 20 minutes, with `serve()` on rerun and
     `run_local_gateway(explicit paths)` otherwise.
   - A code submit prints nothing, so it must be confirmed by read-back.
4. **Submissions are human actions.** Auto-mode denies `kaggle competitions submit`. kx prepares, validates and
   hands over the command, then reads back. `submissions.date` is UTC (Phase 5 A1 confirmed live).
5. **The simulation loop is fully observable from the CLI:** submissions/rating, episodes (needs `raw_decode`),
   replay and logs.
   - `kaggle-environments` is 117 packages, so it only runs via ephemeral `uv run --with`.
   - Local wins against the built-in bots did not predict the ladder rating (600 → 528.6).
6. **Research ingestion works without joining.**
   - The SDK `list_topic_messages(page_size=-1)` returns thread bodies. The CLI `topics show` drops the original
     post.
   - Public notebooks can be listed and pulled.
   - Host `metric/*` kernels expose `score(solution, submission, row_id_column_name)` for exact-metric CV.

## Frontier (unverified; candidates for the next spikes or build-time checks)

- Dataset-version pinning, the only reproducible way to pin a pipeline's upstream.
- Mount paths for `dataset_sources` and `model_sources`.
- Pinning `docker_image` on push, for environment reproducibility.
- The accelerator string for T4×2 and other GPU shapes (`--accelerator` / `machine_shape`).
- The `artifact_upload` submission path (e.g. Nemotron LoRA) and writeup guidance. Neither was exercised live.
- An end-to-end `csv_upload` through a v2 profile and kx. It has not been run live (the spikes only file-uploaded ConnectX's `main.py`).
