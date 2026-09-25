# Code competitions (`code_kernel`, incl. API-served)

You submit a **kernel version**, not a file: Kaggle reruns that version on the hidden test
set (internet off). kx prepares and verifies it; the **user runs the submit command**.

## Two stages

1. A training experiment (`tabular`, `timeseries` or `deep`) records CV and saves its fold
   models (`models/fold<k>.joblib`, or `checkpoints/fold<k>/model.pt`).
2. `kx new --idea "…" --hypothesis "…" --after exp-NNN` scaffolds the inference stage
   (`inference` for tabular, `deep-infer` for deep). It copies the upstream AI block (so
   `build_features` matches training), mounts the upstream output through
   `kernel_sources`, inherits its CV, and writes the profile's expected output file.

A tabular training kernel that itself writes the expected file is also submittable (it
retrains on the rerun); the two-stage split keeps the rerun fast.

## API-served (`api_served: true`, output `submission.parquet`)

The inference template finds the host's `kaggle_evaluation/*_inference_server.py` inside the
competition data, **starts the server before any slow step** (models load lazily on the
first batch), `serve()`s on the scoring rerun (`KAGGLE_IS_COMPETITION_RERUN`), and otherwise
runs the local gateway with explicit data paths (`GATEWAY_DATA_PATHS`, relative to the data
dir; the host defaults point at the retired `/kaggle/input/<slug>/`). Scoring takes ~20 min.

## Submitting

`kx submit exp-NNN` checks: the kernel version is COMPLETE and is Kaggle's latest, it ran
with internet off, the expected file exists with the sample's columns (and rows, except
API-served), daily slots are left, and the CV beats the best submitted CV. It returns:

`! <skill>/.venv/bin/kaggle competitions submit <Canonical-Ref> -k <owner/slug> -v <N> -f <file> -m "kx:exp-NNN:…"`

Show it to the user; they run it with `!`. A code submit prints nothing on success: only
`kx lb` (read-back) proves it landed.
