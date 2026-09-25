---
spike: 002
name: script-kernel-chaining
type: standard
validates: "Given a CPU script kernel A that writes artifacts, when kernel B lists A in kernel_sources, then B reads A's output at a discoverable path — and script kernels return logs/output like notebooks"
verdict: VALIDATED
related: [001, 003]
tags: [kaggle-kernels, script-kernel, kernel-sources, pipelines, runtime-limit]
---

# Spike 002: Script kernels + kernel_sources chaining

## What This Validates

Given a CPU **script** kernel A (`kernel_type: "script"`) that writes artifacts to
`/kaggle/working`, when kernel B lists A in `kernel_sources`, then B can read A's output at a
discoverable path. Also: what a script kernel's runtime looks like, how failures and `push -t`
timeouts surface, and which upstream version a downstream kernel consumes.

## Research

- `kernel-metadata.json` spec (github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md):
  `kernel_type` ∈ {`script`, `notebook`}; `kernel_sources` = `username/kernel-slug`;
  also `dataset_sources`, `competition_sources`, `model_sources`, `machine_shape`.
- `kaggle kernels push -t TIMEOUT` — "limit the run time of a kernel to the given number of seconds".

| Approach | Pros | Cons | Status |
|---|---|---|---|
| Notebook kernels (v1: jupytext `.py`→`.ipynb`) | inspectable cells | papermill quirks — needed kernelspec, `parse_known_args`, no `SystemExit`, flat-output fix (4 live bugs, quick 260925-66x) | superseded |
| **Script kernels** | runs the `.py` as-is; no conversion dep | none found | **chosen** |
| Upload weights as a private dataset | versioned | extra create/version round-trip | fallback only |

## How to Run

```bash
K=.venv/bin/kaggle   # from the worktree root
$K kernels push -p .planning/spikes/002-script-kernel-chaining/a     # then b, c (-t 60), d, b_pin
python .planning/spikes/kwait.py ravijotsinha/kx-spike-002-a         # wait for terminal status
$K kernels output ravijotsinha/kx-spike-002-a -p .../out/a --force
```

Kernels created (all private, CPU, internet off): `kx-spike-002-{a,b,c,d,b-pin}`.

## Investigation Trail

1. **A (script, `competition_sources: [titanic]`)** → COMPLETE in ~30 s. Runtime facts (`out/a/info.json`):
   `argv=['/kaggle/src/script.py']`, `__file__='/kaggle/src/script.py'`, `cwd=/kaggle/working`,
   Python 3.12.13, `ipykernel` NOT loaded, `KAGGLE_KERNEL_RUN_TYPE=Batch`.
   → A plain script needs none of the papermill workarounds (no `-f` argv, `__file__` exists,
   `SystemExit` is fine).
2. **Surprise — competition data mounts at `/kaggle/input/competitions/titanic/`**, NOT
   `/kaggle/input/titanic/`. v1's original `resolve_data_dir` only checked the latter (then fell
   back to `Path(__file__).parents[2]/data`, which is `/data` on a script kernel). Quick
   260925-66x's hardening (checks both) was load-bearing.
3. **Output shape:** `kernels output` downloads `/kaggle/working` recursively (`sub/nested.txt`
   preserved) plus `<slug>.log` — the same JSON array `[{stream_name, time, data}]` as notebook
   kernels. Script kernels are still rendered to `__results__.html` via nbconvert (benign
   mistune/nbconvert SyntaxWarnings in stderr).
4. **B (`kernel_sources: [ravijotsinha/kx-spike-002-a]`)** → A's output mounted at
   **`/kaggle/input/notebooks/<owner>/<slug>/`** with subdirs preserved, plus Kaggle's own
   `__script__.py`, `__script__.ipynb`, `__results__.html`, `__output__.json`, `custom.css`.
   `model.pkl` loaded fine.
5. **Version race:** pushed A v3 (sleeps 120 s) and B v2 *while A v3 was RUNNING* → B did NOT
   wait; it consumed **A v2** (the last COMPLETE version).
6. **Version pin attempt:** `kernel_sources: ["…/kx-spike-002-a/versions/1"]` → CLI rejects:
   *"Kernel must be specified in the form of '{username}/{kernel-slug}' or
   '{username}/{kernel-slug}/{version}'"*. Retried with `…/kx-spike-002-a/1` → push accepted,
   **but B loaded A-v3** (latest). `kernels pull -m` shows the server stored
   `kernel_sources: ["ravijotsinha/kx-spike-002-a"]` — **the pin is silently dropped.**
7. **Pulled metadata carries `docker_image`** (`gcr.io/kaggle-images/python@sha256:dafd…` for a
   CPU kernel; the GPU run yesterday used `gcr.io/kaggle-private-byod/python@sha256:37c6…`) and
   `machine_shape: "None"` for CPU. Pinning the image on push is untested (frontier).
8. **C (`push -t 60`, script sleeps 300 s)** → status **`CANCEL_ACKNOWLEDGED`** at ~70 s; the log
   and **partial outputs written before the cut-off are still downloadable** (`progress.txt = 6`).
9. **D (raises `RuntimeError`)** → status **`ERROR`** (not COMPLETE); stderr has a clean
   `Traceback … RuntimeError`; `partial.txt` written before the crash is still downloadable.

## Results

**Verdict: VALIDATED** — script kernels + `kernel_sources` chaining work and are simpler than
notebooks; **one sub-assumption INVALIDATED: upstream version pinning is not honored.**

Evidence: `out/` (logs, `b_result.json`, pulled metadata). `model.pkl` excluded from git.

**Signal for the build:**

- **Default to `kernel_type: "script"`**; drop jupytext conversion and every papermill workaround.
  Keep notebooks only if a user explicitly wants rendered cells.
- **Data resolver must check `/kaggle/input/competitions/<slug>` first** (observed), then
  `/kaggle/input/<slug>`; kernel outputs live at `/kaggle/input/notebooks/<owner>/<slug>/`;
  datasets/models: verify in the build (likely `/kaggle/input/datasets/…`, `/kaggle/input/models/…`).
- **Pipelines:** push downstream only after upstream is COMPLETE (kx must wait/verify); the
  downstream gets the *latest completed* upstream — so **every kernel writes a
  `kx_manifest.json` (exp id, git commit, kernel version, created) into its output**, and the
  downstream records the upstream manifest it actually read. Reproducible pinning = snapshot
  into a dataset version (frontier: verify dataset version pinning).
- **Runtime limits:** `push -t <sec>` works → `CANCEL_ACKNOWLEDGED`; partial outputs survive →
  checkpoint-to-`/kaggle/working` makes long GPU runs resumable.
- **Failure detection:** script exceptions → `ERROR` status + traceback; the v1 log scanner still
  applies, but status is now a reliable first signal for scripts.
