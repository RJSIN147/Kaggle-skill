"""test_record_experiment.py — the anti-lie recorder (EXP-04, criterion 3, D-05/D-06).

Exercises record_experiment.py as a SUBPROCESS. The recorder is the integrity spine of the
phase: numeric fields are TOOLING-WRITTEN from a schema-validated result.json (the AI never
hand-writes a score), a throwing/invalid/lying run is recorded as FAILED **with a verdict**
(never upgraded to success, never appended as a success ledger row), and every row carries
provenance. The scaffold-written idea/hypothesis/created/exp_id are carried forward on BOTH
the SUCCESS and FAILED paths so a failed attempt never loses its hypothesis (D-13 tried-list).

The workspace is a real git repo so provenance (git_commit) is honest.
"""

import json
import os
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

_GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def _git_init(ws: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=ws, check=True, env=_GIT_ENV)
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True, env=_GIT_ENV)
    subprocess.run(
        ["git", "-c", "user.email=t@e.com", "-c", "user.name=t",
         "commit", "-qm", "seed"],
        cwd=ws, check=True, env=_GIT_ENV,
    )


def _seed(ws: Path, *, metric: str = "roc_auc",
          idea: str = "LightGBM baseline on raw features",
          hypothesis: str = "GBDT beats a constant-rate baseline") -> Path:
    ctrl = ws / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    (ctrl / "config.json").write_text(
        json.dumps(
            {
                "competition_slug": "titanic",
                "metric": {"name": metric, "greater_is_better": True},
                "cv": {"scheme": "StratifiedKFold"},
            },
            indent=2,
        )
        + "\n"
    )
    (ctrl / "ledger.jsonl").write_text("")
    exp = ws / "experiments" / "exp-001"
    (exp / "artifacts").mkdir(parents=True, exist_ok=True)
    (exp / "experiment.py").write_text("# a minted experiment\nprint('hello')\n")
    stub = {
        "schema_version": 1,
        "exp_id": "exp-001",
        "created": "2026-01-01T00:00:00Z",
        "idea": idea,
        "hypothesis": hypothesis,
        "status": "pending",
        "failure_reason": None,
        "metric": None,
        "greater_is_better": None,
        "cv_scheme": None,
        "n_folds": None,
        "fold_scores": [],
        "cv_mean": None,
        "cv_std": None,
        "provenance": {
            "run_id": "", "artifact_hash": "", "git_commit": "",
            "git_dirty": False, "seed": "",
        },
        "result_path": "experiments/exp-001/result.json",
        "verdict_path": "experiments/exp-001/VERDICT.md",
        "artifacts": [],
    }
    (exp / "meta.json").write_text(json.dumps(stub, indent=2) + "\n")
    return exp


def _write_result(exp: Path, **over) -> None:
    result = {
        "schema_version": 1,
        "metric": "roc_auc",
        "greater_is_better": True,
        "cv_scheme": "StratifiedKFold",
        "n_folds": 3,
        "fold_scores": [0.80, 0.82, 0.81],
        "cv_mean": 0.81,
        "cv_std": 0.008,
        "seed": 42,
        "artifacts": ["artifacts/oof.npy"],
    }
    result.update(over)
    (exp / "result.json").write_text(json.dumps(result) + "\n")


def _read_meta(exp: Path) -> dict:
    return json.loads((exp / "meta.json").read_text())


def _ledger_rows(ws: Path) -> list:
    text = (ws / "control" / "ledger.jsonl").read_text()
    return [json.loads(ln) for ln in text.splitlines() if ln.strip()]


def _record(run_script, ws, *extra):
    return run_script(
        "record_experiment.py", "--workspace", ws, "--exp-dir", "experiments/exp-001",
        *extra, cwd=ws,
    )


def test_success_writes_meta_ledger_verdict_and_provenance(run_script, tmp_path):
    ws = tmp_path
    exp = _seed(ws)
    _write_result(exp)
    _git_init(ws)
    r = _record(run_script, ws)
    assert r.returncode == 0, r.stderr

    meta = _read_meta(exp)
    assert meta["status"] == "SUCCESS"
    assert meta["failure_reason"] is None
    # Carried forward from the scaffold stub (criterion 2 / EXP-01).
    assert meta["idea"] == "LightGBM baseline on raw features"
    assert meta["hypothesis"] == "GBDT beats a constant-rate baseline"
    assert meta["exp_id"] == "exp-001"
    assert meta["created"] == "2026-01-01T00:00:00Z"
    # Tooling-written numbers.
    assert meta["cv_mean"] == 0.81
    assert meta["n_folds"] == 3
    # Provenance: all four auditable fields present and non-empty (EXP-04).
    prov = meta["provenance"]
    for key in ("run_id", "artifact_hash", "git_commit", "seed"):
        assert prov[key] not in (None, ""), key
    assert prov["artifact_hash"].startswith("sha256:")
    assert prov["seed"] == 42

    rows = _ledger_rows(ws)
    assert len(rows) == 1
    assert rows[0]["idea"] == "LightGBM baseline on raw features"
    assert rows[0]["status"] == "SUCCESS"

    assert (exp / "VERDICT.md").is_file()


def test_missing_result_is_failed_with_verdict_no_success_row(run_script, tmp_path):
    ws = tmp_path
    exp = _seed(ws)  # NO result.json — the throwing-notebook headline
    _git_init(ws)
    r = _record(run_script, ws)
    assert r.returncode == 0, r.stderr  # recording a failure IS a successful cycle

    meta = _read_meta(exp)
    assert meta["status"] == "FAILED"
    assert meta["failure_reason"] == "missing_result"
    # idea/hypothesis STILL present on the FAILED path (D-13 tried-list).
    assert meta["idea"]
    assert meta["hypothesis"]
    assert (exp / "VERDICT.md").is_file()
    # THE anti-lie assertion: no success row was fabricated.
    assert _ledger_rows(ws) == []


def test_lying_mean_is_failed_schema_invalid(run_script, tmp_path):
    ws = tmp_path
    exp = _seed(ws)
    # emitted cv_mean disagrees with mean(fold_scores)=0.80 — the recompute catches it.
    _write_result(exp, cv_mean=0.99, fold_scores=[0.80, 0.80, 0.80], n_folds=3)
    _git_init(ws)
    r = _record(run_script, ws)
    assert r.returncode == 0, r.stderr

    meta = _read_meta(exp)
    assert meta["status"] == "FAILED"
    assert meta["failure_reason"] == "schema_invalid"
    assert meta["idea"] and meta["hypothesis"]
    assert _ledger_rows(ws) == []


def test_out_of_range_mean_is_failed(run_script, tmp_path):
    ws = tmp_path
    exp = _seed(ws)
    _write_result(exp, cv_mean=1.7, fold_scores=[1.7, 1.7, 1.7], n_folds=3)
    _git_init(ws)
    r = _record(run_script, ws)
    assert r.returncode == 0, r.stderr

    meta = _read_meta(exp)
    assert meta["status"] == "FAILED"
    assert meta["failure_reason"] == "out_of_range"


def test_non_finite_fold_is_failed(run_script, tmp_path):
    ws = tmp_path
    exp = _seed(ws)
    _write_result(exp, fold_scores=[0.80, float("nan"), 0.82], n_folds=3, cv_mean=0.81)
    _git_init(ws)
    r = _record(run_script, ws)
    assert r.returncode == 0, r.stderr

    meta = _read_meta(exp)
    assert meta["status"] == "FAILED"
    assert meta["failure_reason"] == "non_finite"


def test_e2e_throwing_run_recorded_failed_with_hypothesis(run_script, tmp_path):
    """A deliberately-throwing run (nonzero exit, no result.json) → FAILED + verdict."""
    ws = tmp_path
    exp = _seed(ws)  # scaffold stub with idea/hypothesis, no result.json
    _git_init(ws)
    r = _record(run_script, ws, "--run-exit-code", "1")
    assert r.returncode == 0, r.stderr

    meta = _read_meta(exp)
    assert meta["status"] == "FAILED"
    assert meta["idea"]
    assert meta["hypothesis"]
    assert (exp / "VERDICT.md").is_file()
    assert _ledger_rows(ws) == []  # criterion 3 demonstrated


def test_nonzero_run_never_upgraded_to_success(run_script, tmp_path):
    """Even with a perfectly valid result.json, a nonzero run exit forces FAILED."""
    ws = tmp_path
    exp = _seed(ws)
    _write_result(exp)  # a valid result on disk
    _git_init(ws)
    r = _record(run_script, ws, "--run-exit-code", "1")
    assert r.returncode == 0, r.stderr

    meta = _read_meta(exp)
    assert meta["status"] == "FAILED"
    assert _ledger_rows(ws) == []


def test_missing_stub_meta_fails_clear(run_script, tmp_path):
    ws = tmp_path
    _seed(ws)
    _git_init(ws)
    # Remove the scaffold stub — the recorder cannot carry forward idea/hypothesis.
    (ws / "experiments" / "exp-001" / "meta.json").unlink()
    r = _record(run_script, ws)
    assert r.returncode != 0


def test_source_recompute_present_no_git_add_all_no_sklearn():
    src = (SCRIPTS_DIR / "record_experiment.py").read_text()
    assert "statistics.mean" in src
    assert "git add -A" not in src
    assert "import sklearn" not in src
    assert "from sklearn" not in src
