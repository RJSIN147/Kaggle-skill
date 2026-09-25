# Code-Competition Submission (`code_kernel`, incl. API-served) and file-upload submission

## Requirements

- Code competitions submit a **script kernel version**:
  `kaggle competitions submit <canonical-ref> -k <owner/slug> -v <N> -f <output-file> -m "<msg>"`.
- **The human runs every submission.** Claude Code's auto-mode classifies `kaggle competitions submit` as a
  real-world transaction and denies it. kx **prepares and validates**, hands over the exact command for the user to
  run with `! <cmd>`, then **confirms by read-back only**.
- Never submit to a competition the user is actively competing in (e.g. rsna-knee-abnormality-detection,
  cooked-or-not) for testing. Live checks use closed comps with `submissions_disabled=False` (late submissions), or
  perpetual sandboxes (Titanic, ConnectX).
- Respect the profile's `max_daily_submissions`.

## How to Build It

1. **Preconditions from the profile:**
   - `submission_mode == "code_kernel"`
   - `api_served` flag
   - the canonical ref
   - the expected output file: `submission.parquet` if `api_served`, else the sample file's name
2. **Kernel.** A script kernel with internet off and `competition_sources: ["<slug>"]`. Use GPU only if the
   profile or modality needs it. See `script-kernels.md`.
3. **Tabular / file-output template** (`sources/003-*/a-script/predict.py`):
   - Resolve data (`/kaggle/input/competitions/<canonical>` first).
   - Train or load the model and predict on `test.*`.
   - Write `/kaggle/working/<expected file>` using the sample file's column names.

   On the scoring rerun Kaggle swaps in the hidden test set, so the same code must just work. Never hard-code the
   row counts.
4. **API-served template** (`kaggle_evaluation` gateway; `sources/003-*/c-api-served/predict.py`):

   ```python
   sys.path.append(str(comp))                        # kaggle_evaluation ships INSIDE the competition data
   import kaggle_evaluation.mcts_inference_server    # module/class name comes from the comp's own package

   def predict(test: pl.DataFrame, sample_sub: pl.DataFrame) -> pl.DataFrame: ...

   server = kaggle_evaluation.mcts_inference_server.MCTSInferenceServer(predict)
   if os.getenv("KAGGLE_IS_COMPETITION_RERUN"):
       server.serve()                                # hidden-test scoring rerun
   else:                                             # our own run: exercise the gateway locally
       server.run_local_gateway((str(comp / "test.csv"), str(comp / "sample_submission.csv")))
   ```

   - **Start the server before any time-consuming step.** The host enforces a startup limit, so load models lazily
     inside `predict` or after constructing the server.
   - The gateway writes `submission.parquet` to cwd (`/kaggle/working`).
5. **Validate before handing over:**
   - Push, wait for `COMPLETE`, then pull the output.
   - Check that the expected file exists and that its columns and row shape match the sample.
   - Parse the kernel version `N` from the push output (see `script-kernels.md`).
6. **Hand over** the exact command, with the canonical ref and the verified version:

   ```
   ! .venv/bin/kaggle competitions submit <canonical-ref> -k <owner>/<slug> -v <N> -f submission.csv -m "<exp id>: <msg>"
   ```

7. **Read back.** Run `kaggle competitions submissions <ref> --format json`.
   - The new row appears **immediately** as `SubmissionStatus.PENDING`, with `description` and `fileName`.
   - Poll until it leaves PENDING (`sources/_shared/subwait.py`), then record `publicScore` and `privateScore`.
8. **Provenance record:**
   - `(competition ref, kernel owner/slug, kernel version, output file, submission ref, date UTC, public, private)`
   - A kernel-version submission is reproducible by construction: Kaggle reruns *that* version.
9. **`csv_upload` mode.** Run `kaggle competitions submit <ref> -f <file> -m "<msg>"`, which is also human-run.
   - On success, a file upload prints an upload progress bar and `Successfully submitted to <Competition Title>`.
   - Still confirm by read-back.

## What to Avoid

- **Trusting submit's exit code or stdout.** A code-competition submit (`-k -v -f`) prints **nothing** on success
  and exits 0, so only the read-back proves it landed.
- **Running `kaggle competitions submit` from Claude.** Auto-mode denies it. Do not work around the denial.
- **Notebook kernels for submission.** They give an identical score with extra conversion risk. Script wins.
- **The host gateway's default data paths.** They point at the retired `/kaggle/input/<slug>/` mount. Pass
  `data_paths` explicitly to `run_local_gateway` on today's layout.
- **Committing the host's `kaggle_evaluation` code.** Read it live from the competition data.
- **Blocking the session on scoring.** Report PENDING, poll with a budget, and resume.

## Constraints

- **Scoring latency after submit:**
  - Tabular (equity): PENDING → COMPLETE in **≤ 3 min**.
  - API-served (um-mcts): **~20 min**, since the hidden test streams through the gRPC gateway in batches.
- **Live results:**
  - equity script and notebook: 0.64754 public / 0.65377 private (identical).
  - um-mcts constant-0: 0.57164 / 0.57683.
- **`submissions.date` is UTC** (confirmed live: read-back `00:56:32` vs `date -u` `00:56:52`).
- Commands accept the lowercase slug, but the joined-list ref and the on-disk mount use the canonical case.
- Joining is a browser-only human step, and submitting requires it.

## Origin

Synthesized from spikes: 003 (a script, b notebook, c API-served), 001 (`submissions_disabled`, daily limits)
Source files available in: sources/003-code-comp-submit/, sources/_shared/subs.py, sources/_shared/subwait.py
