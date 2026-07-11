"""test_run_cv.py — the leakage-safe-by-construction CV harness (D-07, criterion 1).

Skips CLEANLY when the ML env is absent: ``run_cv`` needs numpy + scikit-learn (the
scaffold's harness runs under ``uv run`` in the workspace ML env). The default offline
suite therefore reports these as SKIPPED, never RED (Pattern: the plumbing/ML split, D-06).
"""

import math
import statistics

import pytest

pytest.importorskip("numpy")
pytest.importorskip("sklearn")

import numpy as np  # noqa: E402  (gated by importorskip above)

from test_resolve_data_dir import render_experiment  # noqa: E402  (shared renderer)


def test_preprocess_fits_on_train_fold_only(tmp_path):
    """A spy transformer must see ONLY train-fold rows at fit — never a val row.

    Leakage-safety is structural: the harness owns ``fit_transform(train)`` /
    ``transform(val)``, so a fresh spy per fold records disjoint fit/transform row sets.
    """
    from sklearn.linear_model import LogisticRegression

    from metric_registry import REGISTRY

    mod = render_experiment(tmp_path)
    n = 40
    ids = np.arange(n)  # column 0 = a row-id the spy can read back
    feats = np.random.RandomState(0).randn(n, 3)
    X = np.column_stack([ids, feats])
    y = np.array([0, 1] * (n // 2))

    spies = []

    class Spy:
        def __init__(self):
            self.fit_ids = None
            self.transform_ids = None
            spies.append(self)

        def fit_transform(self, X, y=None):
            self.fit_ids = set(np.asarray(X)[:, 0].astype(int).tolist())
            return X

        def transform(self, X):
            self.transform_ids = set(np.asarray(X)[:, 0].astype(int).tolist())
            return X

    exp_dir = tmp_path / "experiments" / "exp-001"
    mod.run_cv(
        X=X, y=y,
        model_factory=lambda: LogisticRegression(max_iter=200),
        preprocess_factory=Spy,
        metric="roc_auc", registry_entry=REGISTRY["roc_auc"],
        cv_scheme="StratifiedKFold", n_splits=4, seed=42, exp_dir=str(exp_dir),
    )

    assert spies, "preprocess_factory() was never invoked"
    for spy in spies:
        assert spy.fit_ids is not None and spy.transform_ids is not None
        # fit saw only train rows -> disjoint from this fold's val rows (no leakage).
        assert spy.fit_ids.isdisjoint(spy.transform_ids)


def test_named_metric_roc_auc_writes_recorder_acceptable_result(tmp_path):
    """NAMED metric resolves via registry_entry['sklearn_callable'] and emits a valid result.json."""
    import json

    from sklearn.linear_model import LogisticRegression

    from metric_registry import REGISTRY

    mod = render_experiment(tmp_path)
    rng = np.random.RandomState(1)
    n = 60
    X = rng.randn(n, 4)
    y = (X[:, 0] + rng.randn(n) * 0.1 > 0).astype(int)
    exp_dir = tmp_path / "experiments" / "exp-001"

    result = mod.run_cv(
        X=X, y=y,
        model_factory=lambda: LogisticRegression(max_iter=500),
        metric="roc_auc", registry_entry=REGISTRY["roc_auc"],
        cv_scheme="StratifiedKFold", n_splits=5, exp_dir=str(exp_dir),
    )

    assert result["metric"] == "roc_auc"
    assert result["seed"] == 42  # D-09 default
    assert len(result["fold_scores"]) == result["n_folds"] == 5
    assert all(math.isfinite(s) and 0.0 <= s <= 1.0 for s in result["fold_scores"])

    written = json.loads((exp_dir / "result.json").read_text())
    assert written["metric"] == "roc_auc"
    # The recorder recomputes mean(fold_scores) and cross-checks — must match (anti-lie).
    assert abs(written["cv_mean"] - statistics.mean(written["fold_scores"])) < 1e-6


def test_custom_splitter_and_callable_metric(tmp_path):
    """A custom splitter AND a callable metric are both first-class (D-07 tension)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import KFold

    from metric_registry import REGISTRY

    mod = render_experiment(tmp_path)
    rng = np.random.RandomState(2)
    n = 50
    X = rng.randn(n, 3)
    y = (rng.randn(n) > 0).astype(int)

    def accuracy(y_true, y_pred):
        return float((np.asarray(y_true) == np.asarray(y_pred)).mean())

    exp_dir = tmp_path / "experiments" / "exp-001"
    result = mod.run_cv(
        X=X, y=y,
        model_factory=lambda: LogisticRegression(max_iter=200),
        metric=accuracy, registry_entry=REGISTRY["accuracy"],
        cv_scheme="KFold",
        splitter=KFold(n_splits=3, shuffle=True, random_state=0),
        exp_dir=str(exp_dir),
    )

    assert result["metric"] == "custom"  # a callable metric records as "custom"
    assert result["n_folds"] == 3
    assert all(math.isfinite(s) for s in result["fold_scores"])
    assert abs(result["cv_mean"] - statistics.mean(result["fold_scores"])) < 1e-9
