"""metric_registry.py — the stdlib metric source of truth (D-08).

GREEN target: 03-01 Task 1. RED until scripts/metric_registry.py exists.

The registry is the SINGLE source read by set_metric.py (enum + direction lookup),
record_experiment.py (range + direction gate), and the scaffold's run_cv (callable
name resolution). It is stdlib-ONLY (the D-06 split applied to metrics): importing it
must never pull scikit-learn / pandas / numpy — it only NAMES the sklearn callable.
"""

import re
from math import inf
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "metric_registry.py"


@pytest.fixture(scope="module")
def reg():
    import metric_registry  # importable once the module exists (scripts/ on sys.path)

    return metric_registry


def test_roc_auc_entry_exact(reg):
    """roc_auc: greater-is-better proba scorer, [0,1], mapped to roc_auc_score."""
    assert reg.REGISTRY["roc_auc"] == {
        "greater_is_better": True,
        "prediction_type": "proba",
        "range": (0.0, 1.0),
        "sklearn_callable": "roc_auc_score",
    }


def test_custom_escape_hatch_is_all_none(reg):
    """custom: no direction, no scorer, unbounded — direction MUST be given to the setter."""
    entry = reg.REGISTRY["custom"]
    assert entry["sklearn_callable"] is None
    assert entry["greater_is_better"] is None
    assert entry["prediction_type"] is None
    assert entry["range"] == (-inf, inf)


def test_supported_is_tuple_including_custom(reg):
    """SUPPORTED == tuple(REGISTRY); it is the argparse choices surface for set_metric.py."""
    assert isinstance(reg.SUPPORTED, tuple)
    assert reg.SUPPORTED == tuple(reg.REGISTRY)
    assert "custom" in reg.SUPPORTED


def test_supported_covers_the_documented_enum(reg):
    """The enum must include at least the D-08 metric names."""
    required = {
        "roc_auc", "logloss", "accuracy", "f1", "f1_macro", "precision",
        "recall", "rmse", "mae", "rmsle", "mape", "r2", "qwk", "mcc", "custom",
    }
    assert required <= set(reg.SUPPORTED)


@pytest.mark.parametrize(
    "name,gib",
    [
        ("roc_auc", True), ("accuracy", True), ("r2", True), ("qwk", True), ("mcc", True),
        ("logloss", False), ("rmse", False), ("mae", False), ("rmsle", False), ("mape", False),
    ],
)
def test_direction_correctness(reg, name, gib):
    assert reg.REGISTRY[name]["greater_is_better"] is gib


@pytest.mark.parametrize(
    "name,rng",
    [
        ("roc_auc", (0.0, 1.0)),
        ("logloss", (0.0, inf)),
        ("r2", (-inf, 1.0)),
        ("qwk", (-1.0, 1.0)),
        ("mcc", (-1.0, 1.0)),
    ],
)
def test_range_correctness(reg, name, rng):
    assert reg.REGISTRY[name]["range"] == rng


@pytest.mark.parametrize("name", ["roc_auc", "logloss"])
def test_probability_metrics_are_proba(reg, name):
    assert reg.REGISTRY[name]["prediction_type"] == "proba"


def test_every_entry_has_exactly_the_four_keys(reg):
    keys = {"greater_is_better", "prediction_type", "range", "sklearn_callable"}
    for name, entry in reg.REGISTRY.items():
        assert set(entry) == keys, name


def test_module_is_stdlib_only():
    """No third-party import anywhere in the module — importing it must not pull ML deps."""
    src = MODULE_PATH.read_text()
    assert not re.search(r"^\s*import\s+(sklearn|pandas|numpy)\b", src, re.M), src
    assert not re.search(r"^\s*from\s+(sklearn|pandas|numpy)\b", src, re.M), src
    assert "from math import inf" in src
