"""Metric registry: the one source of direction, valid range and scorer name.

The recorder gates a result with ``range`` + ``greater_is_better``; the kernel
template resolves ``sklearn_callable`` into a real scikit-learn function. This
module never imports scikit-learn, so stdlib plumbing can use it freely.

``prediction_type`` tells the template whether the stored OOF value is a
probability (``proba``), a raw regression value (``raw``) or a probability that
is thresholded / arg-maxed only for scoring (``label``).
"""

from math import inf

REGISTRY = {
    "roc_auc":   {"greater_is_better": True,  "prediction_type": "proba", "range": (0.0, 1.0),  "sklearn_callable": "roc_auc_score"},
    "logloss":   {"greater_is_better": False, "prediction_type": "proba", "range": (0.0, inf),  "sklearn_callable": "log_loss"},
    "accuracy":  {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "accuracy_score"},
    "f1":        {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "f1_score"},
    "f1_macro":  {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "f1_score"},
    "precision": {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "precision_score"},
    "recall":    {"greater_is_better": True,  "prediction_type": "label", "range": (0.0, 1.0),  "sklearn_callable": "recall_score"},
    "rmse":      {"greater_is_better": False, "prediction_type": "raw",   "range": (0.0, inf),  "sklearn_callable": "root_mean_squared_error"},
    "mse":       {"greater_is_better": False, "prediction_type": "raw",   "range": (0.0, inf),  "sklearn_callable": "mean_squared_error"},
    "mae":       {"greater_is_better": False, "prediction_type": "raw",   "range": (0.0, inf),  "sklearn_callable": "mean_absolute_error"},
    "rmsle":     {"greater_is_better": False, "prediction_type": "raw",   "range": (0.0, inf),  "sklearn_callable": "root_mean_squared_log_error"},
    "mape":      {"greater_is_better": False, "prediction_type": "raw",   "range": (0.0, inf),  "sklearn_callable": "mean_absolute_percentage_error"},
    "r2":        {"greater_is_better": True,  "prediction_type": "raw",   "range": (-inf, 1.0), "sklearn_callable": "r2_score"},
    "qwk":       {"greater_is_better": True,  "prediction_type": "label", "range": (-1.0, 1.0), "sklearn_callable": "cohen_kappa_score"},
    "mcc":       {"greater_is_better": True,  "prediction_type": "label", "range": (-1.0, 1.0), "sklearn_callable": "matthews_corrcoef"},
    # Escape hatch: the experiment supplies its own score(); direction and range
    # must be given explicitly to `kx metric custom`.
    "custom":    {"greater_is_better": None,  "prediction_type": None,    "range": (-inf, inf), "sklearn_callable": None},
}

SUPPORTED = tuple(REGISTRY)

# Exact-match map from Kaggle's structured `evaluation_metric` display names to a
# registry key. Only a suggestion: the AI confirms it with `kx metric <key>`.
# Unknown names map to None (never guessed).
DISPLAY_NAME_MAP = {
    "categorization accuracy": "accuracy",
    "accuracy": "accuracy",
    "accuracy score": "accuracy",
    "roc auc score": "roc_auc",
    "area under receiver operating characteristic curve": "roc_auc",
    "auc": "roc_auc",
    "log loss": "logloss",
    "logloss": "logloss",
    "binary log loss": "logloss",
    "multiclass loss": "logloss",
    "root mean squared error": "rmse",
    "rmse": "rmse",
    "mean squared error": "mse",
    "mean absolute error": "mae",
    "mae": "mae",
    "root mean squared logarithmic error": "rmsle",
    "rmsle": "rmsle",
    "mean absolute percentage error": "mape",
    "f1 score": "f1",
    "f-score": "f1",
    "mean f-score": "f1",
    "macro f1 score": "f1_macro",
    "quadratic weighted kappa": "qwk",
    "r2 score": "r2",
    "matthews correlation coefficient": "mcc",
}


def suggest(evaluation_metric) -> str | None:
    """Registry key for a Kaggle metric display name, or None when unknown."""
    if not isinstance(evaluation_metric, str):
        return None
    return DISPLAY_NAME_MAP.get(evaluation_metric.strip().lower())
