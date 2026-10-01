# kx reference

## Envelope

```json
{"kx": "0.3.0", "command": "run", "status": "ok",
 "summary": "exp-001 recorded SUCCESS: accuracy 0.8215±0.02 (5 folds)",
 "data": {"exp_id": "exp-001", "result": "SUCCESS", "cv_mean": 0.8215},
 "warnings": [], "errors": [],
 "next_action": {"kind": "edit", "instruction": "Write the verdict …",
                 "then": "kx strategy --reasoning-file experiments/exp-001/reasoning.md"}}
```

Exit code 0 iff `status` is `ok` or `running`. Server text, tracebacks and signed URLs never
appear in an envelope; they go to `control/raw/last-error.txt` (gitignored).

## Commands

| Command | Does |
|---|---|
| `kx init [comp]` | Scaffold the workspace, install the leak hook, validate the credential live. |
| `kx status` | Recompute where the loop is and the next action (local only). |
| `kx sync [comp] [--download] [--force-download] [--files F …]` | Build `control/profile.json` from `get_competition`, the data-files summary and the file tree (depth 1 once joined). `--download` fetches the data bundle (joined + locally feasible); `--force-download` ignores the feasibility flag; `--files` fetches only those files (≤10). |
| `kx confirm [--mode M] [--modality X] [--expected-output F] --note "…"` | Record the user's confirmation (and corrections) of the profile. |
| `kx metric <key> [--direction higher/lower] [--range LO HI] [--prediction-type proba/label/raw]` | Set the CV metric. `custom` needs a direction. |
| `kx new --idea … --hypothesis … [--template T --template-reason …] [--folds N] [--accelerator cpu/NvidiaTeslaT4] [--limit S] [--local [--subsample F]] [--after exp-NNN …] [--from-idea N] [--model HANDLE …] [--dataset owner/slug …]` | Scaffold `experiments/exp-NNN/`. `--model`/`--dataset` attach Kaggle Models/datasets as read-only kernel inputs. `--after` (repeatable) chains this kernel after upstream experiments' kernels (a deep/tabular upstream gives a `deep-infer`/`inference` stage); `--from-idea` runs research idea #N and marks it tried. |
| `kx run exp-NNN [--wait S] [--wait-local S] [--rerun] [--resume]` | Validate, push, poll (bounded), pull, record. Re-running resumes polling and never re-pushes; `--rerun` pushes a new version; `--resume` continues a time-budget stop from its checkpoints. |
| `kx strategy --reasoning-file F` | Regenerate `strategy.md` and commit the cycle. Refuses while a verdict has `_TODO`. |
| `kx submit exp-NNN [--force-cv] [--file F] [--message M]` / `kx submit --writeup` | Validate a candidate and propose it (confirmation details + one-time token; `--message` replaces the idea after the `kx:` marker) / write the writeup checklist. |
| `kx submit exp-NNN --confirm TOKEN [--force-cv] [--file F]` | After the user's explicit yes: re-check and submit the proposed candidate once (refuses a changed file/kernel version or a proposal over 1 h old). |
| `kx lb [--wait S]` | Read back submissions, record scores next to CV, trend the gap. |
| `kx research [all/pages/discussions/notebooks/metric/idea] [--limit N] [--use-metric owner/slug] [--idea "…" --source "…"]` | Research ingestion (see SKILL.md). `--use-metric` adopts a host metric kernel for CV; `idea --idea … --source …` queues an idea. |
| `kx env` | Kernel image + library versions of each run next to this machine's. |
| `kx ensemble exp-A exp-B … [--method hill/weights] [--idea "…"]` | Blend OOF predictions into a new experiment. |

## experiment.json

| Field | Rule |
|---|---|
| `exp_id` | `exp-NNN`, equal to the folder name |
| `idea`, `hypothesis` | non-empty |
| `template` | a registered template; `template_reason` records why (and any override) |
| `runtime.target` | `kernel` (default) or `local` |
| `runtime.accelerator` | `cpu` or `NvidiaTeslaT4` (live-verified ids only) |
| `runtime.limit_s` | 60 … 43200 (Kaggle's 12 h cap); a run that hits it ends CANCEL_ACKNOWLEDGED → FAILED(runtime_limit) |
| `runtime.internet` | `false` by default; `true` (e.g. to download weights not on Kaggle) is warned about, read back from Kaggle and recorded; refused for a code competition's `inference`/`deep-infer` stage, and `kx submit` refuses a code-competition kernel that ran with it on |
| `sources.competition` | the synced competition |
| `sources.datasets` / `models` / `kernels` | `owner/slug`; models `owner/model/framework/variation/version`; kernels may be `@exp-NNN` |
| `cv.n_folds`, `cv.reasoning` | why this split mirrors train vs test |
| `cv.scheme` | optional short name of the split (e.g. `group_kfold`) |
| `local.subsample` | local runs: fraction of train rows; the ledger marks the result as subsampled |
| `local.env` | agent experiments: the `kaggle-environments` environment name to evaluate in (default: the competition slug, e.g. `connectx`) |
| `code_file` | the file the template wrote (`train.py`, `predict.py` or `main.py`) |
| `schema_version`, `created` | set by `kx new` |
| `harness_sha256` | set by `kx new`; `kx run` refuses a modified harness |

No `<TODO>` anywhere, and unknown keys are rejected.

## kx-preds/1

Written by every predictive template into the kernel's output:

| File | Columns | Rows |
|---|---|---|
| `oof.csv` | `row_id, fold, target, pred` or `pred_0 … pred_{K-1}` | one per train row; `fold` = -1 when never validated |
| `test_preds.csv` | `row_id, <same pred columns>` | one per test row |

Predictions are continuous (probabilities or regression values), never hard labels, so
experiments can be blended. `result.json.predictions` declares the files, columns, classes
and row counts; the recorder rejects mismatches as FAILED(predictions_invalid).

## Recorder ladder

status ERROR → `kernel_error`; CANCEL_ACKNOWLEDGED → `runtime_limit`; log traceback / OOM
marker or an unreadable log → `kernel_error`; `result.json` missing / malformed /
non-finite / mean ≠ mean(folds) / wrong metric / out of range; then the predictions check.
A FAILED record keeps the idea, carries `cv_mean: null`, and points at the traceback, log
and partial outputs.
