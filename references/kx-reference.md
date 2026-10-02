# kx reference

## Envelope

```json
{"kx": "0.4.0", "command": "run", "status": "ok",
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
| `kx metric <key> [--direction higher/lower] [--range LO HI] [--prediction-type proba/label/raw] [--label NAME]` | Set the CV metric. `custom` needs a direction; `--label` names it in summaries (e.g. `dice`). |
| `kx diagnose [--local] [--limit S]` | Scaffold a diagnostic experiment (template `diagnose`); `kx run` it. See "Diagnose" below. |
| `kx new --idea … --hypothesis … [--expect better/worse/same [--expect-delta D]] [--parent exp-NNN/none] [--evidence REF …] [--cv-check] [--template T --template-reason …] [--folds N] [--accelerator cpu/NvidiaTeslaT4] [--limit S] [--local [--subsample F]] [--after exp-NNN …] [--from-idea N] [--model HANDLE …] [--dataset owner/slug …]` | Scaffold `experiments/exp-NNN/`. The parent defaults to the current best (within the reference CV scheme); `--expect` is required whenever there is one. Without `--template`, the child uses the parent's template and starts from its AI block (`data.ai_block_from`); a diagnostic cannot be a parent. `--evidence` (repeatable) is `facts:<dotted.path>`, `exp-NNN:<meta key>` or `idea:<n>`; kx stores the value it reads. `--cv-check` reruns the parent's model (its AI block) so only `assign_folds` changes. `--model`/`--dataset` attach Kaggle Models/datasets as read-only kernel inputs. `--after` (repeatable) chains this kernel after upstream experiments' kernels (deep → `deep-infer`, tabular → `inference`, custom → custom); `--from-idea` runs research idea #N and marks it tried. |
| `kx run exp-NNN [--wait S] [--wait-local S] [--rerun] [--resume]` | Validate, push, poll (bounded), pull, record. Re-running resumes polling and never re-pushes; `--rerun` pushes a new version; `--resume` continues a time-budget stop from its checkpoints. |
| `kx strategy --reasoning-file F` | Regenerate `strategy.md` and commit the cycle. Refuses while a verdict has `_TODO`. |
| `kx validation [show]` / `kx validation ok --note "…" [--scheme exp-NNN]` | Show the validation status / record that CV can be trusted (acknowledges the event; `--scheme` adopts that run's folds as the reference CV scheme). |
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
| `kind` | `experiment` / `diagnostic` (`kx diagnose`) / `cv_check` (`kx new --cv-check`); set by kx |
| `parent` | the `exp-NNN` this run changes, or null (a baseline) |
| `expected_effect` | `{"direction": "better"/"worse"/"same", "delta": number/null}`: the pre-registered prediction vs the parent |
| `evidence` | `[{"ref", "value"}]` written by `kx new --evidence` |
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
| `code_file` | the file the template wrote (`train.py`, `predict.py`, `main.py` or `diagnose.py`) |
| `schema_version`, `created` | set by `kx new` |
| `harness_sha256` | set by `kx new`; `kx run` refuses a modified harness |

No `<TODO>` anywhere (and no `KX_TODO` stub left in the code file); unknown keys are rejected.

## Parent comparison

When a run and its parent assign every row to the same fold (`fold_hash`: sha256 of the
sorted `(row_id, fold)` pairs of `oof.csv`), kx compares them per fold: deltas oriented so
+ = better, a paired t with the Nadeau-Bengio correction (se = sd·√(1/k + 1/(k−1))) against
the two-sided 95 % t value → `better` / `worse` / `inconclusive` (`identical` when every
delta is equal). Otherwise `vs_parent` says why not (CV scheme changed, parent FAILED,
another metric or subsample, no predictions). The prediction is then `matched`, `missed` (a change it ruled out) or `unresolved` (a change was predicted, the comparison is inconclusive).
All of it is in `meta.json`, the ledger row, the `kx run` envelope, the VERDICT stub and
`strategy.md` (with a calibration line). It is informational: it gates nothing.

## Diagnose (`kx-facts/1`)

`output/facts.json` holds `n_train`, `n_test`, `target`, `columns` (per column: dtype, unique
counts, missing rates, mean shift or unseen-in-train share), `time` (date-like columns:
train/test ranges, `relation`), `entities` (repeating columns: rows per value, test
overlap), `duplicates`, `single_feature` (one-feature target AUC or |Spearman|) and
`adversarial` (LightGBM train-vs-test: `fold_aucs`, `auc_mean`, `top_features`; `skipped`
with a reason when test has < 200 rows). The recorder fails it closed like a result.json;
the recorded CV is the adversarial AUC (`adv_auc`, lower is better). kx derives `findings`
(high: adversarial AUC ≥ 0.70, test after train, unseen entities, a single-feature leak ≥
0.98; medium: AUC ≥ 0.60, ≥ 1 % test rows in train) and publishes `control/facts.json`.
A diagnostic is never a parent, a blend member or a submission candidate.

## Validation status

`control/state.json → validation`: `unchecked` → `ok` / `suspect`. Suspect after a diagnose
with a high finding or a CV-vs-LB rank inversion (`kx lb`); ok after a clean diagnose or
`kx validation ok`. Warn-only: `kx new` / `run` / `strategy` / `lb` warn, `kx submit` adds a
WARNING confirmation line, `kx status` steers to a diagnosis or a `--cv-check`. With a
reference scheme, the current best is ranked within it and the submit CV bar compares only
runs on the same folds.

## custom template

`main.py`; `run()` is the whole pipeline. Harness (stdlib-only): `DATA_DIR`, `OUT`,
`IS_RERUN`, `time_left()`, `model_dirs()`, `upstream_dir()`, `previous_output()`,
`report(fold_scores, **extra)` (once, `N_FOLDS` finite scores; kx computes mean/std),
`report_upstream()`, `write_preds(oof_rows, test_rows, classes)` (optional kx-preds/1),
`stop_incomplete(stopped_at)`. The run fails unless `report()` ran (not on a rerun) and
`EXPECTED_OUTPUT` exists in `OUT`. See `types/custom.md`.

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
non-finite / mean ≠ mean(folds) / wrong metric / out of range (a diagnostic: `facts.json`
instead); then the predictions check (templates that make them optional: only when
declared).
A FAILED record keeps the idea, carries `cv_mean: null`, and points at the traceback, log
and partial outputs.
