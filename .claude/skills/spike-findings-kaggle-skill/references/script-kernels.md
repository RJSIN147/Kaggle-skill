# Script Kernels (runtime, push/poll/pull, chaining)

## Requirements

- A Kaggle **kernel is the default runtime**. Local execution stays an option for small or tabular data (see
  `local_feasible` in the competition profile).
- Kernels default to **`kernel_type: "script"`**. There is no notebook conversion.
- Kernel defaults:
  - private
  - `enable_internet: false`, since many code comps forbid internet
  - CPU for live checks, because the GPU quota is shared with the user's other work
- The data resolver checks `/kaggle/input/competitions/<canonical-slug>` **first**.
- Pipelines wait for upstream `COMPLETE` before pushing downstream. Every kernel writes a `kx_manifest.json`, and the
  downstream kernel records the upstream manifest it actually consumed.
- "Done" means a live run on a real competition, never a fixture count.

## How to Build It

1. **`kernel-metadata.json`.** One folder per kernel, containing this file and one code file:

   ```json
   {
     "id": "<owner>/<slug>", "title": "<slug>", "code_file": "train.py",
     "language": "python", "kernel_type": "script",
     "is_private": true, "enable_gpu": false, "enable_internet": false,
     "competition_sources": ["<slug>"], "dataset_sources": [], "kernel_sources": [], "model_sources": []
   }
   ```

2. **Runtime facts on a script kernel** (observed live):
   - `argv=['/kaggle/src/script.py']`, and `__file__` is set.
   - cwd is `/kaggle/working`.
   - Python 3.12.13 (local is 3.13, a parity note).
   - `ipykernel` is NOT loaded, so `SystemExit` is fine.
   - `KAGGLE_KERNEL_RUN_TYPE=Batch`.

   None of v1's papermill workarounds apply.

3. **Data resolver** (from `sources/003-*/a-script/predict.py`):

   ```python
   CANDIDATES = [Path(f"/kaggle/input/competitions/{SLUG}"),   # current mount (canonical case)
                 Path(f"/kaggle/input/{SLUG}")]                  # legacy mount seen in older notebooks
   base = next((p for p in CANDIDATES if p.is_dir()), None)
   if base is None:  # case-insensitive fallback: canonical refs carry capitals (equity-post-HCT-...)
       base = next((p.parent for p in Path("/kaggle/input").rglob("sample_submission.csv")
                    if p.parent.name.lower() == SLUG.lower()), None)
   if base is None:
       raise FileNotFoundError(f"competition data not found; tried {CANDIDATES}")
   ```

   Other kernels' outputs mount at **`/kaggle/input/notebooks/<owner>/<slug>/`**. Subdirectories are preserved,
   and Kaggle adds `__script__.py`, `__script__.ipynb`, `__results__.html`, `__output__.json` and `custom.css`.

4. **Push.** Run `kaggle kernels push -p <dir> [-t <seconds>]`.
   - Parse the version from stdout: `Kernel version (\d+) successfully pushed.  Please check progress at <url>`.
   - The CLI can also print the line with no number. In that case, don't guess the version; read it back.
   - `-t` bounds the run time.

5. **Poll.** Run `kaggle kernels status <owner/slug>` and regex `KernelWorkerStatus\.([A-Z_]+)`.
   - Terminal states: `{COMPLETE, ERROR, CANCEL_ACKNOWLEDGED, CANCEL_REQUESTED}`.
   - Always bound the poll with a timeout budget. See `sources/_shared/kwait.py`.

6. **Pull.** Run `kaggle kernels output <owner/slug> -p <dir> --force`.
   - It downloads `/kaggle/working` **recursively**, plus `<slug>.log`.
   - The log is a JSON array of `{stream_name, time, data}`, the same shape as notebook kernels.
   - Stderr carries benign `mistune`/`nbconvert` SyntaxWarnings, because scripts are still rendered to
     `__results__.html`. Whitelist them in the log scanner.

7. **Print markers.** One grep-able line per fact: `print("KX_<WHAT>=" + json.dumps(...), flush=True)`.

8. **Chaining (`kernel_sources`).**
   - List `"<owner>/<slug>"` with **no version**.
   - kx must wait for the upstream kernel to be `COMPLETE` before pushing downstream.
   - Every kernel writes `kx_manifest.json` (exp id, git commit, kernel version, created) into `/kaggle/working`.
     The downstream kernel copies the upstream manifest it read into its own output.
   - For reproducible pinning, snapshot the upstream output into a **dataset version**. Dataset version pinning is
     still unverified (frontier).

9. **Timeouts and failures.**
   - `push -t 60` on a 300-second script ends in **`CANCEL_ACKNOWLEDGED`** at about 70 seconds.
   - A raised exception ends in **`ERROR`**, with a clean `Traceback` in stderr.
   - **Both keep partial outputs** written before the stop, so checkpoint to `/kaggle/working` to make long GPU runs
     resumable.
   - Status is the first failure signal for scripts. The log scanner is the second.

10. **Provenance.** `kaggle kernels pull <ref> -m` returns the server's stored metadata, including `docker_image`:
    - CPU: `gcr.io/kaggle-images/python@sha256:…`
    - GPU: `gcr.io/kaggle-private-byod/python@sha256:…`
    - `machine_shape: "None"` for CPU

    Record the image digest per run.

## What to Avoid

- **Notebook kernels and jupytext/papermill conversion.** They caused 4 live bugs in v1: a missing kernelspec,
  papermill's `-f` argv, `SystemExit` under ipykernel, and a flat-output fix. A notebook scored **identically** to a
  script on a real code comp (spike 003), so they bring nothing.
- **Resolving data only at `/kaggle/input/<slug>`.** That mount is retired. Falling back to
  `Path(__file__).parents[2]/data` gives `/data` on a script kernel.
- **Version-pinning `kernel_sources`:**
  - `owner/slug/versions/N` is rejected by the CLI.
  - `owner/slug/N` is accepted, but **the server silently drops the pin** and mounts the latest version. `kernels
    pull -m` shows it stored unpinned.
- **Pushing downstream while upstream is RUNNING.** Downstream does NOT wait; it consumes the **last COMPLETE**
  version.
- **Pickle for model hand-off between kernels.** Prefer json, npz or safetensors. Pickle is acceptable only for
  our own trusted kernel output.
- **Logging environment values.** Record `KAGGLE*` env **keys only**, because values include
  `KAGGLE_USER_SECRETS_TOKEN`.
- **Trusting a kernel's exit code or stdout without the status.** Poll the status, then pull the output.

## Constraints

- Quotas (platform): GPU 30 h/week, TPU 20 h/week, 12 h maximum session, 20 GB `/kaggle/working`.
- A trivial CPU script kernel reaches COMPLETE in about 30 s, including queueing.
- The kernel image's Python (3.12.13) and package pins differ from the local uv env. Treat this as a CV→LB parity
  risk.
- Unverified (frontier):
  - mount paths for `dataset_sources` and `model_sources` (likely `/kaggle/input/datasets/…` and
    `/kaggle/input/models/…`)
  - dataset version pinning
  - pinning `docker_image` on push
  - the T4×2 accelerator string

## Origin

Synthesized from spikes: 002, 003 (script vs notebook comparison)
Source files available in: sources/002-script-kernel-chaining/, sources/003-code-comp-submit/, sources/_shared/kwait.py
