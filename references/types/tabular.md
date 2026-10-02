# Tabular competitions

Template: `tabular` (`train.py`, a CPU script kernel by default).

## The AI block

- `assign_folds(train, y)` **is** the CV scheme. Mirror how test differs from train, as
  `kx diagnose` measured it (`control/facts.json` findings):
  - iid rows: `StratifiedKFold` for classification, `KFold` for regression;
  - repeated entities (users, patients, stores): `GroupKFold` / `StratifiedGroupKFold` on the entity;
  - time-ordered data: use the `timeseries` template instead (`--template timeseries`) and
    read `timeseries.md`.
  Write the reason in `experiment.json` → `cv.reasoning`.
- `build_features(train, test)` returns `(X, X_test)` with the same columns. Target
  encodings belong inside the fold loop (a model or a pipeline), never fitted on all rows.
- `make_model(seed)` returns a fresh estimator with `fit`/`predict` (+`predict_proba` for
  classification). LightGBM is the default first model; XGBoost and CatBoost are also in
  the Kaggle image.
- Optional `custom_score(y_true, pred, rows)` scores with the exact host metric (required for
  `kx metric custom`; `rows` are the validation rows, `host_metric.score` is inlined after
  `kx research metric --use-metric`); optional `postprocess_submission(sub, test_pred, classes)` reshapes
  the submission.

## Kaggle image parity

The kernel runs Python 3.12 with Kaggle's pins (seen live: numpy 2.0.2, pandas 2.3.3,
scikit-learn 1.6.1, lightgbm 4.6.0). Write code that works on pandas 2.x and 3.x; no
Python 3.13-only syntax. `kx_manifest.json` records the versions of every run.

## Discipline

- One idea per experiment, so the CV delta is attributable. `kx new` starts from the
  parent's AI block and folds: change only what the idea changes.
- Pre-register the effect (`--expect`), then read kx's paired comparison
  (`data.vs_parent`): `inconclusive` is not an improvement, however good the mean looks.
  A small effect needs more folds to confirm: rerun the parent's model on more folds
  (`kx new --cv-check --parent exp-NNN --folds 10 …`), then build the child from that run
  (children inherit its folds), rather than repeating a run.
- Submit only when CV beats the best submitted CV on the same folds (`kx submit` checks
  this).
