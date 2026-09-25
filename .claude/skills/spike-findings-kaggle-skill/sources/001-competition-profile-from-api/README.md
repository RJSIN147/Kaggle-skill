---
spike: 001
name: competition-profile-from-api
type: standard
validates: "Given kaggle.api structured metadata + the data-files summary + the root file tree, when classifying 20 mixed competitions, then submission mode, modality, API-served flag and data size come out right without scraping any prose"
verdict: VALIDATED
related: [003, 004]
tags: [kaggle-api, competition-profile, classification, metadata]
---

# Spike 001: Competition profile from kaggle.api metadata

## What This Validates

Given `kaggle.api` structured competition metadata, the data-files summary and the root file
tree, when classifying 20 competitions spanning every Kaggle type, then submission mode,
modality, API-served flag and data size are derived correctly **without scraping rules/overview
prose** (v1's regex approach mislabelled Titanic as a code competition).

## Research

- The `kaggle` CLI's `competitions list --format json` exposes only 6 fields
  (`ref, deadline, category, reward, teamCount, userHasEntered`).
- The **Python SDK** (`kagglesdk`, shipped inside the same `kaggle` package — no new dependency)
  exposes far more through `KaggleApi().build_kaggle_client().competitions.competition_api_client`:

| Call | Useful fields |
|------|---------------|
| `get_competition(ApiGetCompetitionRequest(competition_name=slug))` | `is_kernels_submissions_only`, `max_daily_submissions`, `evaluation_metric`, `tags[].name`, `category`, `deadline`, `submissions_disabled`, `max_team_size`, `host_name` |
| `get_competition_data_files_summary(...)` | `file_summary_info.total_file_count`, `file_types[] {extension, file_count, total_size}`, `column_summary_info.column_types[]` |
| `list_data_tree_files(ApiListDataTreeFilesRequest(competition_name, path, page_size))` | root/dir listing: `files[] {name, total_bytes}`, `directories[] {name}` |

| Approach | Pros | Cons | Status |
|---|---|---|---|
| Regex over rules/overview prose (v1) | no SDK | brittle; boilerplate ("submission code requirements") mislabels Titanic | rejected |
| CLI JSON only | stays on the CLI | only 6 fields — no code-only flag, no limit, no metric | insufficient |
| **SDK structured fields + files summary + tree** | exact flags, sizes by extension, one call each | uses SDK types (same package as CLI) | **chosen** |

## How to Run

```bash
cd .planning/spikes/001-competition-profile-from-api
../../../.venv/bin/python probe.py titanic connectx ...   # → raw/<slug>.json (live, read-only)
python3 classify.py                                      # → profiles.json + results.md (offline)
```

## What to Expect

`classify.py` prints `mode 19/20 · modality 19/20 · api_served 20/20` and the table in `results.md`.

## Investigation Trail

1. **CLI JSON is too thin** — `competitions list --format json` has no type/limit/metric fields.
2. **SDK probe of `ApiCompetition`** — found `is_kernels_submissions_only`, `max_daily_submissions`,
   `evaluation_metric`, `tags`, `submissions_disabled`. Titanic: `is_kernels_submissions_only=False`,
   `max_daily_submissions=10` — the two facts v1 regex-scraped (and got the first one wrong).
3. **Files summary** carries `file_count` + `total_size` per extension → modality AND total data
   size from ONE call (no paging through 819,640 files for rsna-knee = 530.6 GB).
4. **First classifier pass: mode 18/20.** Misses:
   - `cooked-or-not`: sample submission lives in `crash_competition_data/`, not the root.
   - `nvidia-nemotron…`: no sample submission, metric present, not code-only → `unknown`.
5. **Depth-1 listing** fixes cooked-or-not — but **surprise: listing inside a directory returns
   HTTP 403 unless the user has joined the competition** (verified: rsna-knee/cooked-or-not OK
   (joined); birdclef/um-mcts/connectx/jane-street 403 (not joined)). Root listing + files summary
   work without joining. → mode 19/20.
6. **Ground truth for 3 ambiguous comps** read from their Evaluation / Submission-Requirements
   pages (`pages/`): Nemotron = **LoRA-adapter upload** (a 5th mode, `artifact_upload`, not a
   prediction file); Pokémon TCG *Strategy* = Kaggle Writeup (sibling of a separate simulation
   comp); Measuring AGI = Writeup + Kaggle Benchmark attachment.
7. **Trap found:** tag `games` does NOT imply simulation — `um-game-playing-strength-of-mcts-variants`
   is tabular regression. The reliable discriminator is *presence of a sample submission file*.

## Results

**Verdict: VALIDATED.** Structured metadata classifies competitions reliably; prose is needed only
for the rare residual (`unknown` → AI reads the Evaluation page).

Decision rules that worked (strongest evidence first):

1. A `*submission*` file exists (root, or depth-1 once joined) → prediction competition:
   `code_kernel` if `is_kernels_submissions_only` else `csv_upload`; `api_served` if a root
   `kaggle_evaluation/` dir exists. The sample file's name/extension is the expected OUTPUT
   (ARC = `sample_submission.json`, not CSV).
2. No sample file and `evaluation_metric == ""` → `writeup` (hackathons, benchmark comps).
3. No sample file + simulation signal (`simulations` tag, `kaggle-environments*` dir, root
   `main.py`/`agents.md`) → `agent`.
4. Otherwise → `unknown`: the AI must read the Evaluation page (Nemotron → `artifact_upload`).

Other facts the profile gets for free: `max_daily_submissions` (Titanic 10, ARC 1, ConnectX 2),
`submissions_disabled` (**True = late submissions closed**: jane-street, orbit-wars; False on
closed equity-post-hct, isic, birdclef, um-mcts, llm-prompt-recovery → candidates for spike 003),
data size (rsna-knee 530.6 GB/819,640 files, birdclef 11.5 GB, jane-street 11.5 GB → kernel-only;
Titanic 0.00 GB → local fine), `custom metric` tag.

Residual misses: Nemotron mode (correctly deferred as `unknown`) and Nemotron modality
(`tabular` vs truth `text` — its tags `general knowledge and reasoning`/`pre-trained model` aren't
in the tag map; the AI should confirm modality anyway).

**Signal for the build:**

- Profile = SDK fields + files summary + depth-≤1 tree. No regex over rules text. Delete v1's
  limit-regex / exit-78 / "assumed 5/day" machinery.
- Two-pass sync: pass 1 before joining (enough for 19/20 here), pass 2 after the user joins
  (nested listing, data download). Joining is a browser-only human step either way.
- Submission modes = `csv_upload | code_kernel(+api_served) | agent | writeup | artifact_upload | unknown`.
- The AI confirms every profile (it's advisory evidence, never an auto-commit).
