"""metric_registry.py — the stdlib metric source of truth (D-06 split applied to metrics).

A stdlib dict keyed by the config metric name. It holds everything the *recorder*
(``record_experiment.py``) needs to gate a result — direction and valid range — plus
the *callable name string* the ML-env *harness* (the scaffold's ``run_cv``) resolves
into a real scikit-learn function. This module NEVER imports scikit-learn / pandas /
numpy: it only NAMES the callable, so importing it in stdlib plumbing (e.g.
``set_metric.py``) never pulls the ML stack (D-06).

Read by:
  * ``set_metric.py``          — ``SUPPORTED`` for the argparse enum + direction lookup.
  * ``record_experiment.py``   — ``range`` + ``greater_is_better`` result gate.
  * the scaffold's ``run_cv``  — resolves ``sklearn_callable`` to the real function.

No ``main()``, no I/O at import time (mirrors ``competition_doc.py``): an importable,
side-effect-free data module.
"""

from math import inf

# prediction_type ∈ {"label", "proba", "raw"} tells the harness's run_cv whether to
# call model.predict (label/raw) or model.predict_proba (proba). custom => None.
REGISTRY = {
    "roc_auc":       {"greater_is_better": True,  "prediction_type": "proba", "range": (0.0, 1.0),  "sklearn_callable": "roc_auc_score"},
    "logloss":       {"greater_is_better": False, "prediction_type": "proba", "range": (0.0, inf),  "sklearn_callable": "log_loss"},
    "accuracy":      {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "accuracy_score"},
    "f1":            {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "f1_score"},
    "f1_macro":      {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "f1_score"},   # average="macro" in harness
    "precision":     {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "precision_score"},
    "recall":        {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "recall_score"},
    "rmse":          {"greater_is_better": False, "prediction_type": "raw",   "range": (0.0, inf),  "sklearn_callable": "root_mean_squared_error"},
    "mae":           {"greater_is_better": False, "prediction_type": "raw",   "range": (0.0, inf),  "sklearn_callable": "mean_absolute_error"},
    "rmsle":         {"greater_is_better": False, "prediction_type": "raw",   "range": (0.0, inf),  "sklearn_callable": "root_mean_squared_log_error"},
    "mape":          {"greater_is_better": False, "prediction_type": "raw",   "range": (0.0, inf),  "sklearn_callable": "mean_absolute_percentage_error"},
    "r2":            {"greater_is_better": True,  "prediction_type": "raw",   "range": (-inf, 1.0), "sklearn_callable": "r2_score"},
    "qwk":           {"greater_is_better": True,  "prediction_type": "label", "range": (-1.0, 1.0), "sklearn_callable": "cohen_kappa_score"},  # weights="quadratic" in harness
    "mcc":           {"greater_is_better": True,  "prediction_type": "label", "range": (-1.0, 1.0), "sklearn_callable": "matthews_corrcoef"},
    # Escape hatch — NOT auto-mappable to a stock sklearn scorer. name="custom" means the
    # experiment.py supplies its own metric callable via run_cv(metric=...). Direction and
    # range MUST be given explicitly to set_metric.py (they cannot be looked up).
    "custom":        {"greater_is_better": None,  "prediction_type": None,    "range": (-inf, inf), "sklearn_callable": None},
}

SUPPORTED = tuple(REGISTRY)  # argparse choices for set_metric.py
