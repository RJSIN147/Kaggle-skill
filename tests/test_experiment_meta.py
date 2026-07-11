"""experiment_meta schema contract (MEM-01 / EXP-04 / D-10), plan 03-02 Task 1.

Pins the single-source ``meta.json`` ⇄ ``ledger.jsonl`` row schema:

  * ``to_ledger_row(meta)`` derives EXACTLY the 11-key one-line subset in
    03-RESEARCH.md §Ledger (line 486), sourcing ``git_commit`` + ``seed`` from
    ``meta["provenance"]`` (never top-level);
  * a FAILED meta (``cv_mean`` null) still yields a valid row (status carried);
  * ``validate_meta`` returns ``[]`` for a well-formed meta and a non-empty list of
    human-readable error strings for missing ``exp_id`` / ``status`` / a bad status
    enum / any missing provenance key (run_id/artifact_hash/git_commit/seed);
  * importing the module runs no I/O and pulls no third-party package.

The module is imported INSIDE each test (``_mod``) so collection never crashes
while ``scripts/experiment_meta.py`` is absent (RED). GREEN: Task 1.
"""

from __future__ import annotations

import importlib


def _mod():
    """Import experiment_meta (absent at RED → ModuleNotFoundError)."""
    return importlib.import_module("experiment_meta")


# The canonical sample from 03-RESEARCH.md §Ledger (lines 455-482).
SAMPLE_META = {
    "schema_version": 1,
    "exp_id": "exp-001",
    "created": "2026-07-11T14:22:07Z",
    "idea": "LightGBM baseline on raw features",
    "hypothesis": "GBDT with StratifiedKFold beats a constant-rate baseline",
    "status": "SUCCESS",
    "failure_reason": None,
    "metric": "roc_auc",
    "greater_is_better": True,
    "cv_scheme": "StratifiedKFold",
    "n_folds": 5,
    "fold_scores": [0.8201, 0.8134, 0.8290, 0.8055, 0.8188],
    "cv_mean": 0.81736,
    "cv_std": 0.00794,
    "provenance": {
        "run_id": "a1b2c3d4e5f6",
        "artifact_hash": "sha256:9f86d0818",
        "git_commit": "12fcc16",
        "git_dirty": False,
        "seed": 42,
    },
    "result_path": "experiments/exp-001/result.json",
    "verdict_path": "experiments/exp-001/VERDICT.md",
    "artifacts": ["artifacts/oof.npy"],
}

# The derived one-line subset, verbatim from 03-RESEARCH.md §Ledger line 486.
EXPECTED_ROW = {
    "exp_id": "exp-001",
    "status": "SUCCESS",
    "idea": "LightGBM baseline on raw features",
    "metric": "roc_auc",
    "greater_is_better": True,
    "cv_mean": 0.81736,
    "cv_std": 0.00794,
    "git_commit": "12fcc16",
    "seed": 42,
    "created": "2026-07-11T14:22:07Z",
    "verdict_path": "experiments/exp-001/VERDICT.md",
}


# --------------------------------------------------------------------------- #
# to_ledger_row.
# --------------------------------------------------------------------------- #
def test_to_ledger_row_produces_exact_11_key_subset():
    row = _mod().to_ledger_row(SAMPLE_META)
    assert row == EXPECTED_ROW


def test_to_ledger_row_sources_git_commit_and_seed_from_provenance():
    """git_commit/seed live under provenance, not top-level (T-03-02-01)."""
    meta = dict(SAMPLE_META)
    # A misleading top-level git_commit/seed must NOT be picked up.
    meta["git_commit"] = "DECOY"
    meta["seed"] = -999
    row = _mod().to_ledger_row(meta)
    assert row["git_commit"] == "12fcc16"
    assert row["seed"] == 42


def test_to_ledger_row_key_order_matches_research_sample():
    """Row key order is fixed so a rebuild is byte-stable."""
    row = _mod().to_ledger_row(SAMPLE_META)
    assert list(row.keys()) == list(EXPECTED_ROW.keys())


def test_failed_meta_still_produces_valid_row_with_null_cv_mean():
    meta = dict(SAMPLE_META)
    meta["status"] = "FAILED"
    meta["cv_mean"] = None
    meta["cv_std"] = None
    row = _mod().to_ledger_row(meta)
    assert row["status"] == "FAILED"
    assert row["cv_mean"] is None
    assert row["exp_id"] == "exp-001"


# --------------------------------------------------------------------------- #
# validate_meta.
# --------------------------------------------------------------------------- #
def test_validate_meta_valid_sample_returns_empty():
    assert _mod().validate_meta(SAMPLE_META) == []


def test_validate_meta_failed_sample_still_valid():
    meta = dict(SAMPLE_META)
    meta["status"] = "FAILED"
    meta["cv_mean"] = None
    assert _mod().validate_meta(meta) == []


def test_validate_meta_empty_dict_returns_nonempty():
    errors = _mod().validate_meta({})
    assert errors  # non-empty
    assert isinstance(errors, list)
    assert all(isinstance(e, str) for e in errors)


def test_validate_meta_missing_exp_id():
    meta = dict(SAMPLE_META)
    del meta["exp_id"]
    errors = _mod().validate_meta(meta)
    assert any("exp_id" in e for e in errors)


def test_validate_meta_bad_status_enum():
    meta = dict(SAMPLE_META)
    meta["status"] = "MAYBE"
    errors = _mod().validate_meta(meta)
    assert any("status" in e for e in errors)


def test_validate_meta_missing_provenance_run_id():
    meta = dict(SAMPLE_META)
    prov = dict(SAMPLE_META["provenance"])
    del prov["run_id"]
    meta["provenance"] = prov
    errors = _mod().validate_meta(meta)
    assert any("run_id" in e for e in errors)


def test_validate_meta_missing_provenance_object():
    meta = dict(SAMPLE_META)
    del meta["provenance"]
    errors = _mod().validate_meta(meta)
    assert any("provenance" in e for e in errors)


# --------------------------------------------------------------------------- #
# Purity: no third-party import, no main block.
# --------------------------------------------------------------------------- #
def test_module_is_pure_stdlib_no_ml_and_no_main():
    import pathlib

    src = pathlib.Path(_mod().__file__).read_text()
    assert "import sklearn" not in src
    assert "import pandas" not in src
    assert "import numpy" not in src
    assert "__main__" not in src  # no entry-point main block (pure helper)
