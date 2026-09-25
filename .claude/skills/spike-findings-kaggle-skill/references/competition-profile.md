# Competition Profile (type detection from structured API facts)

## Requirements

- Build the profile from **SDK structured fields + the data-files summary + a file tree at most one level deep**.
  Never run regex over rules or overview prose. That approach is how v1 labelled Titanic a code competition.
- The skill may use the `kaggle` Python package, including `kagglesdk`, which ships inside it. The
  "stdlib-only" rule is dropped.
- The submission mode is one of `csv_upload | code_kernel (+api_served) | agent | writeup | artifact_upload | unknown`.
- The profile is advisory evidence. The AI confirms every profile with the user and never auto-commits one.
- Store the competition's **canonical ref** exactly as the API reports it, e.g.
  `equity-post-HCT-survival-predictions`. The on-disk data directory in a kernel uses that exact case.

## How to Build It

1. **Client.** The CLI's `competitions list --format json` has only 6 fields, so use the SDK:

   ```python
   from kaggle.api.kaggle_api_extended import KaggleApi
   from kagglesdk.competitions.types.competition_api_service import (
       ApiGetCompetitionDataFilesSummaryRequest, ApiGetCompetitionRequest, ApiListDataTreeFilesRequest)

   api = KaggleApi(); api.authenticate()
   with api.build_kaggle_client() as client:
       cc = client.competitions.competition_api_client
       r = ApiGetCompetitionRequest(); r.competition_name = slug
       comp = cc.get_competition(r)                               # flags, metric, tags, limits
       r = ApiGetCompetitionDataFilesSummaryRequest(); r.competition_name = slug
       summary = cc.get_competition_data_files_summary(r)         # sizes by extension
       r = ApiListDataTreeFilesRequest(); r.competition_name = slug; r.page_size = 200
       root = cc.list_data_tree_files(r)                          # root files[] + directories[]
   ```

   SDK objects are `KaggleObject`s. Convert them to plain JSON by walking `_fields`, as `plain()` does in
   `sources/001-*/probe.py`.

2. **Fields to keep** from `get_competition`:
   - `is_kernels_submissions_only`
   - `max_daily_submissions`
   - `evaluation_metric`
   - `tags[].name`
   - `category`
   - `deadline`
   - `submissions_disabled`
   - `max_team_size`
   - `host_name`

3. **Data size and modality in one call.** `file_summary_info.total_file_count` and `file_types[] {extension,
   file_count, total_size}` are enough. Never page through the tree to size the data: rsna-knee has 819,640 files
   (530.6 GB).

4. **Decision rules** (the order matters; strongest evidence first):

   ```python
   sample_sub = next((f for f in root_files if "submission" in f.lower()), None)  # then depth-1 (pass 2)
   api_served = "kaggle_evaluation" in root_dirs
   metric     = (comp.evaluation_metric or "").strip()
   agentish   = ("simulations" in tags or any(d.startswith("kaggle-environments") for d in root_dirs)
                 or {"main.py", "agents.md"} & {f.lower() for f in root_files})
   if sample_sub:  mode = "code_kernel" if comp.is_kernels_submissions_only else "csv_upload"
   elif not metric: mode = "writeup"
   elif agentish:   mode = "agent"
   else:            mode = "unknown"   # AI reads the Evaluation page (e.g. Nemotron → artifact_upload)
   ```

   **Expected output file:**
   - `api_served` comps: `submission.parquet`, written by the host gateway.
   - All others: the sample file's name and extension. ARC uses `sample_submission.json`, not CSV.

5. **Modality.**
   - Host-curated tags come first:
     - `nlp` / `text classification` / `text generation` → text
     - `audio` / `speech` → audio
     - `image` / `computer vision` / … → image
   - With no matching tag, use the largest byte share by extension:
     - image extensions (+ `.h5`/`.hdf5`) → image
     - audio extensions → audio
     - `.csv`/`.parquet`/`.feather`/`.tsv` → tabular
     - `.json`/`.jsonl` → structured
   - `agent`/`writeup` with no tabular bytes → `none`.

6. **Local feasibility:** the spike used ≤ 5 GB **and** ≤ 20,000 files. Above that, the comp is kernel-only
   unless the user explicitly asks for a local download.

7. **Two-pass sync.**
   - **Pass 1** runs before joining. The root tree and files summary work without joining, and they were enough
     for 19 of 20 comps.
   - **Pass 2** runs after the user joins. It adds the depth-1 listing (cooked-or-not keeps its sample file in
     `crash_competition_data/`) and the data download.
   - Joining is a browser-only human step: the user accepts the rules on the website.

8. **Profile record** (the shape `classify.py` emits):
   - `slug`, `category`, `submission_mode`, `api_served`, `sample_submission`
   - `nested_listing_forbidden`, `modality`, `metric`, `custom_metric` (from the `custom metric` tag)
   - `daily_limit`, `code_only`, `submissions_disabled`, `deadline`
   - `data_bytes`, `file_count`, `local_feasible`, `tags`
   - `reasons[]`: human-readable evidence the AI shows when confirming

## What to Avoid

- **Regex over rules or overview text.** Boilerplate like "submission code requirements" appears on non-code
  comps too.
- **Treating the `games` tag as a simulation signal.** `um-game-playing-strength-of-mcts-variants` is tabular
  regression. The reliable discriminator is **whether a sample-submission file exists**.
- **Assuming "5/day".** Read `max_daily_submissions`: Titanic 10, ARC 1, ConnectX 2, Playground 10. Delete v1's
  limit-regex / exit-78 / "assumed 5/day" machinery.
- **Assuming CSV output** (ARC is JSON; API-served comps are parquet).
- **Lower-casing the slug for on-disk paths.** Commands accept lowercase, but the mount uses the canonical case.
- **Downloading data files one at a time in a loop.** Per-file downloads of `kaggle_evaluation/*` hit
  **HTTP 429**. Download the competition bundle once and unzip it.

## Constraints

- **`submissions_disabled`:**
  - `True` means late submissions are **closed**: jane-street, orbit-wars.
  - `False` on a closed comp means late submissions are accepted: equity-post-hct, isic, birdclef, um-mcts,
    llm-prompt-recovery. These are the safe comps for live checks.
- **Depth-1 `list_data_tree_files(path=<dir>)` returns HTTP 403 unless the user has joined.** Root listing and files
  summary don't need joining.
- **Residual misses:**
  - Nemotron mode comes out `unknown`, which is the correct deferral. Its truth is `artifact_upload`, a LoRA
    adapter.
  - Nemotron modality comes out tabular vs a truth of text, because its tags aren't in the tag map. The AI confirms
    modality.
- **Accuracy on 20 mixed comps:** mode 19/20, modality 19/20, api_served 20/20. See `sources/001-*/results.md`.

## Origin

Synthesized from spikes: 001 (plus the canonical-ref finding from 003 and the 429 finding from 003c)
Source files available in: sources/001-competition-profile-from-api/
