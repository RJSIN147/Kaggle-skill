"""test_scaffold_experiment.py — mint exp-NNN + render the harness (EXP-01, D-02).

Exercises scaffold_experiment.py as a SUBPROCESS (the documented invocation contract),
mirroring the rest of the loop-script suite. The scaffolder is stdlib-only (it renders the
template but never executes ML code), so these run in the default offline suite.
"""

import json
from pathlib import Path

import pytest


def _seed_workspace(ws: Path, *, metric="roc_auc", cv_scheme="StratifiedKFold",
                    next_exp_id=1, slug="titanic"):
    """Create a minimal post-Phase-2 control-plane with metric + cv.scheme committed."""
    ctrl = ws / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    (ctrl / "config.json").write_text(
        json.dumps(
            {
                "workspace_version": 1,
                "competition_slug": slug,
                "execution_target": "local",
                "cv": {"scheme": cv_scheme},
                "metric": {"name": metric, "greater_is_better": True},
                "created": "2026-01-01T00:00:00Z",
            },
            indent=2,
        )
        + "\n"
    )
    (ctrl / "state.json").write_text(
        json.dumps({"credentials": "UNVALIDATED", "next_exp_id": next_exp_id}) + "\n"
    )
    (ctrl / "ledger.jsonl").write_text("")
    return ws


def _read_state(ws: Path):
    return json.loads((ws / "control" / "state.json").read_text())


def test_scaffold_mints_exp_001(run_script, tmp_path):
    ws = _seed_workspace(tmp_path)
    r = run_script(
        "scaffold_experiment.py", "--workspace", ws,
        "--idea", "LightGBM baseline on raw features",
        "--hypothesis", "GBDT beats a constant-rate baseline",
        cwd=ws,
    )
    assert r.returncode == 0, r.stderr
    exp = ws / "experiments" / "exp-001"
    assert (exp / "experiment.py").is_file()
    assert (exp / "meta.json").is_file()
    assert (exp / "artifacts").is_dir()
    assert _read_state(ws)["next_exp_id"] == 2


def test_minted_experiment_carries_helpers_and_registry_literal(run_script, tmp_path):
    ws = _seed_workspace(tmp_path, metric="roc_auc")
    r = run_script("scaffold_experiment.py", "--workspace", ws,
                   "--idea", "i", "--hypothesis", "h", cwd=ws)
    assert r.returncode == 0, r.stderr
    src = (ws / "experiments" / "exp-001" / "experiment.py").read_text()
    assert "def run_cv" in src
    assert "def resolve_data_dir" in src
    assert "registry_entry = {" in src
    # The rendered literal's sklearn_callable matches REGISTRY[config metric name].
    assert "roc_auc_score" in src


def test_minted_experiment_is_kernel_portable(run_script, tmp_path):
    ws = _seed_workspace(tmp_path)
    r = run_script("scaffold_experiment.py", "--workspace", ws,
                   "--idea", "i", "--hypothesis", "h", cwd=ws)
    assert r.returncode == 0, r.stderr
    src = (ws / "experiments" / "exp-001" / "experiment.py").read_text()
    assert "import metric_registry" not in src
    assert "from metric_registry" not in src


def test_meta_stub_fields(run_script, tmp_path):
    ws = _seed_workspace(tmp_path)
    r = run_script(
        "scaffold_experiment.py", "--workspace", ws,
        "--idea", 'idea with "quotes" and, commas',
        "--hypothesis", "the hypothesis",
        cwd=ws,
    )
    assert r.returncode == 0, r.stderr
    meta = json.loads((ws / "experiments" / "exp-001" / "meta.json").read_text())
    assert meta["exp_id"] == "exp-001"
    assert meta["idea"] == 'idea with "quotes" and, commas'
    assert meta["hypothesis"] == "the hypothesis"
    assert meta["created"]  # non-empty timestamp
    # Numeric result fields are null/empty in a stub — the recorder fills them (D-05).
    assert meta["metric"] is None
    assert meta["cv_mean"] is None
    assert meta["cv_std"] is None
    assert meta["n_folds"] is None
    assert meta["fold_scores"] == []


def test_second_scaffold_mints_exp_002_and_never_clobbers(run_script, tmp_path):
    ws = _seed_workspace(tmp_path)
    r1 = run_script("scaffold_experiment.py", "--workspace", ws,
                    "--idea", "first", "--hypothesis", "h1", cwd=ws)
    assert r1.returncode == 0, r1.stderr
    first_bytes = (ws / "experiments" / "exp-001" / "experiment.py").read_bytes()

    r2 = run_script("scaffold_experiment.py", "--workspace", ws,
                    "--idea", "second", "--hypothesis", "h2", cwd=ws)
    assert r2.returncode == 0, r2.stderr
    assert (ws / "experiments" / "exp-002" / "experiment.py").is_file()
    assert _read_state(ws)["next_exp_id"] == 3
    # exp-001 is never re-consumed or overwritten (D-02 idempotency).
    assert (ws / "experiments" / "exp-001" / "experiment.py").read_bytes() == first_bytes


def test_corrupt_state_json_is_left_intact_and_blocks(run_script, tmp_path):
    ws = _seed_workspace(tmp_path)
    corrupt = "{ this is not valid json"
    (ws / "control" / "state.json").write_text(corrupt)
    r = run_script("scaffold_experiment.py", "--workspace", ws,
                   "--idea", "i", "--hypothesis", "h", cwd=ws)
    assert r.returncode != 0
    # Bytes untouched (fail-clear) and no experiment folder was created.
    assert (ws / "control" / "state.json").read_text() == corrupt
    assert not (ws / "experiments" / "exp-001").exists()
