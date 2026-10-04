# Bring your own pipeline (`custom`)

Template: `custom` (`main.py`). kx picks it when no specialised template fits (for example
ARC's `structured` JSON tasks or an `artifact_upload` competition). Choose it yourself for
anything the other templates cannot express: segmentation, detection, LLM fine-tuning or
generation, audio, multimodal:

```
kx new --idea "…" --hypothesis "…" --template custom --template-reason "<why>"
```

The whole pipeline is the AI block's `run()`. The harness is stdlib-only (it runs on any
Kaggle image, vLLM included) and enforces just the output contract; kx records the run
fail-closed like any other.

## The contract

| You do in `run()` | Why |
|---|---|
| Train with CV and call `report(fold_scores)` once: `N_FOLDS` finite scores in `METRIC` (never in a `--no-cv` run) | kx computes the mean and std; a missing or second call fails the run |
| Write `EXPECTED_OUTPUT` into `OUT` (the submission file or the artifact) | the harness fails the run when it is missing |
| On `IS_RERUN` (a code competition's scoring rerun), only predict and write `EXPECTED_OUTPUT` | Kaggle reruns the submitted version on the hidden test set |
| Optional: `write_preds(oof_rows, test_rows, classes)` before `report()` | kx-preds/1 files: `kx ensemble` can blend the run (row-level tasks only) |
| Optional: `report(fold_scores, folds=[(row_id, fold), …])` | saves the fold assignment (`folds.csv`): kx compares this run with its parent fold by fold without `write_preds` |
| Near the limit: `stop_incomplete({...})` and return, when `time_left()` runs low | recorded resumable; `kx run exp-NNN --resume` mounts the previous output: `previous_output()` |

Helpers: `DATA_DIR` (competition data), `OUT` (the output dir), `SUBSAMPLE` (the
`--local --subsample F` fraction, else None: a local smoke run loads only that share of the
rows, so it fits in memory), `model_dirs()` (Kaggle
Models from `kx new --model`), `upstream_dir()` (an `--after` upstream's output),
`host_metric` (an adopted host metric kernel).

## No honest CV

When no CV can stand in for the leaderboard (a ported public engine, a rule-based
submission tweak), scaffold it with `kx new --no-cv` (custom template; children of a no-CV
run inherit it). `run()` then never calls `report()`; it only writes `EXPECTED_OUTPUT`. kx
records SUCCESS with no score, keeps it out of CV rankings, the submit CV bar and the
CV-vs-LB check, and its leaderboard score is the signal. Never invent a smoke-test "CV" to
satisfy `report()`: a fake score poisons every comparison it touches.

## Metric

Use a registry key when one fits (`kx metric roc_auc`). Otherwise
`kx metric custom --direction higher|lower --range LO HI --label dice`: `report()` scores are
then whatever your `run()` computes, so implement the host's metric faithfully (adopt the
host metric kernel with `kx research metric` when there is one) and say how in
`cv.reasoning`.

## Patterns

- **Segmentation / detection:** the fold score is the competition metric (Dice, mAP, …)
  computed on the validation fold's masks or boxes; write the submission (RLE, box strings)
  in the sample's format. kx-preds/1 does not apply (not row-level): skip `write_preds`.
- **LLM generation / reasoning:** "folds" are disjoint validation splits of the train tasks
  (or several seeds of one split); score generations with the metric. For a code
  competition, attach weights as a Kaggle Model (internet off when submitted).
- **Audio:** decode to spectrograms inside `run()`; CV grouped by recording or site.
- **Artifact uploads** (e.g. a LoRA adapter as `submission.zip`): set `EXPECTED_OUTPUT` to
  the artifact. kx records the CV, but the user uploads the artifact on the website
  (`kx submit` has no live-verified upload path for this mode).

## Two stages

`kx new --after exp-NNN` (a custom upstream) scaffolds another custom stage that mounts the
upstream output (`upstream_dir()`) and starts from its AI block. An inference stage calls
`report_upstream()` to carry the upstream's CV and record which run it read. In a code
competition, the stage that is submitted must keep internet off (`kx run` refuses it on).
