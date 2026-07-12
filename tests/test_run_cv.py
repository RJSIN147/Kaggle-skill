"""test_run_cv.py — the leakage-safe-by-construction CV harness (D-07, criterion 1).

Skips CLEANLY when the ML env is absent: ``run_cv`` needs numpy + scikit-learn (the
scaffold's harness runs under ``uv run`` in the workspace ML env). The default offline
suite therefore reports these as SKIPPED, never RED (Pattern: the plumbing/ML split, D-06).

Phase 5 (D-09) extends the harness to emit fold-averaged TEST predictions to
``experiments/exp-NNN/submission.csv``. Those tests live at the bottom of this file and are
RED until 05-02 Task 1 — but they keep the same ``importorskip`` gating, so an offline run
still SKIPs them rather than reddening.
"""

import csv
import json
import math
import statistics
from pathlib import Path

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


# =========================================================================== #
# D-09 (Phase 5, RED until 05-02 Task 1): fold-averaged TEST predictions.
#
# `run_cv` gains OPTIONAL kwargs — X_test, test_ids, id_column, target_column,
# submission_agg — all defaulting to None, so the extension is backward-compatible BY
# CONSTRUCTION and a pure-diagnostic experiment still records a valid CV result (D-09's
# "optional/graceful" requirement).
#
# The submission is written FLAT at `<exp_dir>/submission.csv` (NOT under artifacts/), which
# is exactly where `pull_kernel.py` deposits flat kernel output — so the Kaggle-Kernel path
# lands the file in the same place as the local path with ZERO changes to pull_kernel.
# =========================================================================== #
def _read_submission(exp_dir):
    with open(Path(exp_dir) / "submission.csv", newline="") as f:
        return list(csv.reader(f))


def _titanic_like(seed=0, n=60, n_test=12):
    """A tiny binary-label dataset + a disjoint test set (ids 1000+ so a spy can see them)."""
    rng = np.random.RandomState(seed)
    X = rng.randn(n, 3)
    y = (X[:, 0] + rng.randn(n) * 0.1 > 0).astype(int)
    X_test = rng.randn(n_test, 3)
    test_ids = list(range(1000, 1000 + n_test))
    return X, y, X_test, test_ids


def test_submission_optional(tmp_path):
    """WITHOUT X_test: a valid CV result and NO submission.csv. WITH it: a FLAT submission.csv."""
    from sklearn.linear_model import LogisticRegression

    from metric_registry import REGISTRY

    mod = render_experiment(tmp_path)
    X, y, X_test, test_ids = _titanic_like()

    # --- the DIAGNOSTIC path: no test data, no submission, still a valid CV result -----
    diag_dir = tmp_path / "experiments" / "exp-001"
    result = mod.run_cv(
        X=X, y=y,
        model_factory=lambda: LogisticRegression(max_iter=500),
        metric="accuracy", registry_entry=REGISTRY["accuracy"],
        cv_scheme="StratifiedKFold", n_splits=5, exp_dir=str(diag_dir),
    )
    assert not (diag_dir / "submission.csv").exists(), (
        "a diagnostic experiment (no X_test) must NOT emit a submission — and must NOT fail"
    )
    assert result["submission_path"] is None
    assert "submission.csv" not in result["artifacts"]
    written = json.loads((diag_dir / "result.json").read_text())
    assert abs(written["cv_mean"] - statistics.mean(written["fold_scores"])) < 1e-6

    # --- the SUBMISSION path -----------------------------------------------------------
    sub_dir = tmp_path / "experiments" / "exp-002"
    (sub_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    result = mod.run_cv(
        X=X, y=y,
        model_factory=lambda: LogisticRegression(max_iter=500),
        metric="accuracy", registry_entry=REGISTRY["accuracy"],
        cv_scheme="StratifiedKFold", n_splits=5, exp_dir=str(sub_dir),
        X_test=X_test, test_ids=test_ids,
        id_column="PassengerId", target_column="Survived",
    )

    sub_path = sub_dir / "submission.csv"
    assert sub_path.exists(), "X_test given => submission.csv must be emitted"
    assert not (sub_dir / "artifacts" / "submission.csv").exists(), (
        "the submission is written FLAT at the experiment root, NOT under artifacts/ — that "
        "is where pull_kernel.py deposits flat kernel output (the kernel path rides free)"
    )

    rows = _read_submission(sub_dir)
    assert rows[0] == ["PassengerId", "Survived"], "the header is the sample file's header"
    assert len(rows) == len(test_ids) + 1, "one row per test id, plus the header"
    assert [r[0] for r in rows[1:]] == [str(i) for i in test_ids]

    assert result["submission_path"] == "submission.csv"
    assert "submission.csv" in result["artifacts"]
    written = json.loads((sub_dir / "result.json").read_text())
    assert written["submission_path"] == "submission.csv"


def test_label_aggregation_is_not_mean(tmp_path):
    """⚠ THE SLOT-WASTING TRAP: averaging fold HARD LABELS is wrong.

    `accuracy` — TITANIC'S DEFAULT METRIC — is `prediction_type == "label"`. Averaging five
    folds' 0/1 predictions yields 0.4 / 0.6, which is not a member of the label set. Kaggle
    expects 0/1. And D-02's pre-submit validator (headers, row count, id set, no blanks)
    would happily PASS such a file — so a real, irreversible slot gets spent on garbage.

    The aggregation MUST be type-aware: soft-vote-then-argmax (preferred) or a majority vote.
    """
    from sklearn.linear_model import LogisticRegression

    from metric_registry import REGISTRY

    entry = REGISTRY["accuracy"]
    assert entry["prediction_type"] == "label", (
        "titanic's default metric is a LABEL metric — this is the broken path, not an edge case"
    )

    mod = render_experiment(tmp_path, metric_name="accuracy")
    X, y, X_test, test_ids = _titanic_like(seed=3)
    train_labels = set(np.unique(y).tolist())
    assert train_labels == {0, 1}

    exp_dir = tmp_path / "experiments" / "exp-001"
    mod.run_cv(
        X=X, y=y,
        model_factory=lambda: LogisticRegression(max_iter=500),
        metric="accuracy", registry_entry=entry,
        cv_scheme="StratifiedKFold", n_splits=5, exp_dir=str(exp_dir),
        X_test=X_test, test_ids=test_ids,
        id_column="PassengerId", target_column="Survived",
    )

    rows = _read_submission(exp_dir)
    values = [r[1] for r in rows[1:]]
    assert values, "the submission must carry predictions"

    for v in values:
        f = float(v)
        assert f in train_labels, (
            f"emitted prediction {v!r} is NOT a member of the training label set "
            f"{sorted(train_labels)} — the fold predictions were MEAN-aggregated. A label "
            "metric must VOTE (soft-vote-then-argmax / majority), never average."
        )
        assert f == int(f), f"a label metric must emit integral labels, got {v!r}"
    assert not any(0.0 < float(v) < 1.0 for v in values), "no 0.4/0.6-style averages"

    # A `proba` metric, by contrast, SHOULD mean across folds — and legitimately produces
    # values strictly between 0 and 1.
    proba_dir = tmp_path / "experiments" / "exp-002"
    mod_proba = render_experiment(tmp_path / "proba_ws", metric_name="roc_auc")
    mod_proba.run_cv(
        X=X, y=y,
        model_factory=lambda: LogisticRegression(max_iter=500),
        metric="roc_auc", registry_entry=REGISTRY["roc_auc"],
        cv_scheme="StratifiedKFold", n_splits=5, exp_dir=str(proba_dir),
        X_test=X_test, test_ids=test_ids,
        id_column="PassengerId", target_column="Survived",
    )
    proba_vals = [float(r[1]) for r in _read_submission(proba_dir)[1:]]
    assert any(0.0 < v < 1.0 for v in proba_vals), (
        "a `proba` metric averages fold probabilities — soft values are CORRECT there"
    )


def test_test_preds_use_fold_preprocessor(tmp_path):
    """The anti-leakage contract holds for TEST too: each fold's test prediction goes through
    THAT fold's fitted preprocessor.

    Extends the spy-transformer pattern above. A fold's `pp` is fitted on the TRAIN fold only;
    the test rows must be pushed through that same fitted `pp` (never through a pp fitted on
    anything that saw the val rows, and never raw).
    """
    from sklearn.linear_model import LogisticRegression

    from metric_registry import REGISTRY

    mod = render_experiment(tmp_path)

    n, n_test = 40, 8
    ids = np.arange(n)  # column 0 = a row-id the spy reads back
    feats = np.random.RandomState(0).randn(n, 3)
    X = np.column_stack([ids, feats])
    y = np.array([0, 1] * (n // 2))

    test_ids = list(range(1000, 1000 + n_test))  # disjoint from the train ids by construction
    X_test = np.column_stack(
        [np.array(test_ids), np.random.RandomState(1).randn(n_test, 3)]
    )

    spies = []

    class Spy:
        def __init__(self):
            self.fit_ids = None
            self.transform_calls = []
            spies.append(self)

        def fit_transform(self, X, y=None):
            self.fit_ids = set(np.asarray(X)[:, 0].astype(int).tolist())
            return X

        def transform(self, X):
            self.transform_calls.append(set(np.asarray(X)[:, 0].astype(int).tolist()))
            return X

    exp_dir = tmp_path / "experiments" / "exp-001"
    mod.run_cv(
        X=X, y=y,
        model_factory=lambda: LogisticRegression(max_iter=200),
        preprocess_factory=Spy,
        metric="roc_auc", registry_entry=REGISTRY["roc_auc"],
        cv_scheme="StratifiedKFold", n_splits=4, seed=42, exp_dir=str(exp_dir),
        X_test=X_test, test_ids=test_ids,
        id_column="PassengerId", target_column="Survived",
    )

    assert spies, "preprocess_factory() was never invoked"
    test_id_set = set(test_ids)

    for spy in spies:
        assert spy.fit_ids is not None
        # The fold's pp was fitted on TRAIN rows only — it never saw a test row...
        assert spy.fit_ids.isdisjoint(test_id_set), "the preprocessor must never FIT on test"
        # ...and the TEST rows were pushed through THAT fold's fitted pp.
        assert any(call == test_id_set for call in spy.transform_calls), (
            "each fold's test prediction must be transformed by THAT fold's fitted "
            "preprocessor — otherwise the test path silently bypasses the anti-leakage "
            "contract the val path enforces"
        )
        # The val rows still go through it too (the original contract is unbroken).
        val_calls = [c for c in spy.transform_calls if c != test_id_set]
        assert val_calls, "the val fold must still be transformed"
        for val_ids in val_calls:
            assert spy.fit_ids.isdisjoint(val_ids)

    assert (exp_dir / "submission.csv").exists()
