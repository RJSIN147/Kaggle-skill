---
phase: 7
status: passed
verified: 2026-09-25
method: live runs (tests/live/test_live_profiles.py; workspaces /tmp/kx-live/{titanic,nemotron,store-sales}) + offline suite (153 passed)
---

# Phase 7 verification — profiles & template selection

| Criterion | Evidence |
|---|---|
| 1. Live profiles of the 20 spike-001 competitions match the truth table | `uv run pytest -m live tests/live/test_live_profiles.py`: **mode 20/20** (19 truth rows + the Nemotron residual as `unknown`, never a wrong mode), **api_served 20/20** (jane-street, um-mcts), zero drift vs the spike facts on bytes, file count, local feasibility, daily limit, code-only, late status, metric and expected output (ARC → `submission.json`, API-served → `submission.parquet`). Canonical refs keep case (equity-post-HCT-…). No `description` in any profile. |
| 2. Confirmation gates every decision; unknown residual resolved from the Evaluation page | `kx new` / `kx run` refuse `profile_unconfirmed` (tests). Live Nemotron: sync → `unknown` → `next_action: kx research pages` → Evaluation page (fenced as untrusted) says "submit a LoRA adapter … submission.zip" → `kx confirm --mode artifact_upload --modality text --note …`. Confirmations in these live checks were recorded by the AI acting for the user; the mechanism requires `--note` and refuses an `unknown` mode. |
| 3. Pass-2 sync adds nested listing; feasible comp downloads one bundle safely | Live: joined comps (cooked-or-not, rsna-knee, connectx, …) sync at pass 2 with depth-1 listings (cooked-or-not's sample file found in `crash_competition_data/`). `kx sync titanic --download` → one bundle via `competition_download_files`, zip-slip-safe extraction to `data/titanic/` (3 files), no per-file loop. Unjoined comps warn with the rules URL. |
| 4. Template selection, no-template path, recorded override, live walk-forward | Titanic → `tabular` ("profile is tabular + csv_upload"). Nemotron (artifact_upload) → `kx new` returns `invalid/no_template` with guidance. Live store-sales-time-series-forecasting: `--template timeseries --template-reason …` recorded as "AI override of 'tabular': …"; private CPU kernel ran walk-forward (3 × 16-day expanding windows) → SUCCESS RMSLE 0.837 ± 0.018. Fact learned: an unjoined Getting-Started competition still mounts in a kernel. |
| 5. SKILL.md ≤ 150 lines; only the matching type guide loads | SKILL.md is ~115 lines with a type → guide table; `kx confirm` returns `type_guides` and its `next_action` says to read only those (Titanic → `references/types/tabular.md` only, live). |
