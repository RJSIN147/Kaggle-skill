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


def test_re_recording_success_is_idempotent_single_ledger_row(run_script, tmp_path):
    """WR-01: re-recording an already-recorded SUCCESS must NOT duplicate the ledger row
    (which would double-count it in regen_strategy). Exactly one row after two records."""
    ws = tmp_path
    exp = _seed(ws)
    _write_result(exp)
    _git_init(ws)
    r1 = _record(run_script, ws)
    assert r1.returncode == 0, r1.stderr
    assert len(_ledger_rows(ws)) == 1
    # Re-record the SAME SUCCESS exp — the canonical meta still carries exp_id/idea, so
    # classification re-runs and reaches SUCCESS again. It must overwrite, not append.
    r2 = _record(run_script, ws)
    assert r2.returncode == 0, r2.stderr
    rows = _ledger_rows(ws)
    assert len(rows) == 1
    assert rows[0]["exp_id"] == "exp-001"


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
    # THE anti-lie assertion (post MEM-01/MEM-02 fix): a FAILED experiment DOES land a
    # ledger row so the never-repeat tried-list sees it, but that row carries NO
    # fabricated score — cv_mean is null, never invented from thin air.
    rows = _ledger_rows(ws)
    assert len(rows) == 1
    assert rows[0]["exp_id"] == "exp-001"
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["cv_mean"] is None


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
    # A FAILED row lands, but the lying mean is NOT carried into it (null cv_mean).
    rows = _ledger_rows(ws)
    assert len(rows) == 1
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["cv_mean"] is None


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


def test_custom_metric_cannot_bypass_bounded_range_gate(run_script, tmp_path):
    """WR-03: config declares a bounded metric (roc_auc in [0,1]); a result that
    self-reports metric='custom' with an implausible score must NOT bypass the range gate.
    It is FAILED (schema_invalid), never appended as a success row."""
    ws = tmp_path
    exp = _seed(ws, metric="roc_auc")
    # Would sail through the range gate as "custom" (range (-inf, inf)) under the old code.
    _write_result(exp, metric="custom", cv_mean=5.0, fold_scores=[5.0, 5.0, 5.0], n_folds=3)
    _git_init(ws)
    r = _record(run_script, ws)
    assert r.returncode == 0, r.stderr

    meta = _read_meta(exp)
    assert meta["status"] == "FAILED"
    assert meta["failure_reason"] == "schema_invalid"
    # The implausible custom score never reaches the ledger as a number (null cv_mean).
    rows = _ledger_rows(ws)
    assert len(rows) == 1
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["cv_mean"] is None


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
    # criterion 3 demonstrated: the throwing run lands a FAILED row (visible to the
    # never-repeat tried-list) but with NO fabricated score.
    rows = _ledger_rows(ws)
    assert len(rows) == 1
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["cv_mean"] is None


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
    # A valid-on-disk result cannot upgrade a nonzero run: the row is FAILED and its
    # score fields stay null (the disk numbers are never carried into a FAILED row).
    rows = _ledger_rows(ws)
    assert len(rows) == 1
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["cv_mean"] is None


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


# --------------------------------------------------------------------------- #
# FAILED experiments MUST land in the ledger too (MEM-01 / MEM-02).
#
# The historical gap (03-VERIFICATION.md): record_experiment.py gated its ledger
# write behind `if status == "SUCCESS":`, so a FAILED experiment produced a
# canonical meta.json but NEVER a ledger row in the normal scaffold->run->record
# loop. That made the incremental ledger diverge from a full rebuild_ledger.py of
# the same folders (Criterion 4) and hid tried-and-FAILED ideas from
# regen_strategy's never-repeat tried-list (Criterion 5). The fix: record delegates
# to the same full-derivation path rebuild uses, so incremental == rebuild by
# construction — for SUCCESS and FAILED alike — while a FAILED row still carries a
# null cv_mean (a recorded fact, never a fabricated score).
# --------------------------------------------------------------------------- #
def _stub_for(exp_id, *, idea, hypothesis):
    return {
        "schema_version": 1,
        "exp_id": exp_id,
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
        "result_path": f"experiments/{exp_id}/result.json",
        "verdict_path": f"experiments/{exp_id}/VERDICT.md",
        "artifacts": [],
    }


def _add_exp(ws, exp_id, *, idea, hypothesis):
    """Scaffold a second experiment folder (experiment.py anchor + meta.json stub)."""
    exp = ws / "experiments" / exp_id
    (exp / "artifacts").mkdir(parents=True, exist_ok=True)
    (exp / "experiment.py").write_text(f"# minted {exp_id}\nprint('hi')\n")
    (exp / "meta.json").write_text(
        json.dumps(_stub_for(exp_id, idea=idea, hypothesis=hypothesis), indent=2) + "\n"
    )
    return exp


def _record_dir(run_script, ws, exp_id, *extra):
    return run_script(
        "record_experiment.py", "--workspace", ws, "--exp-dir", f"experiments/{exp_id}",
        *extra, cwd=ws,
    )


def test_failed_experiment_appends_single_null_score_row(run_script, tmp_path):
    """(a)+(d): a FAILED experiment appends EXACTLY ONE ledger row with a null cv_mean
    (no fabricated score) and honest provenance, so the never-repeat tried-list sees it."""
    ws = tmp_path
    _seed(ws)  # exp-001, no result.json → FAILED (missing_result)
    _git_init(ws)
    r = _record(run_script, ws)
    assert r.returncode == 0, r.stderr

    rows = _ledger_rows(ws)
    assert len(rows) == 1
    row = rows[0]
    assert row["exp_id"] == "exp-001"
    assert row["status"] == "FAILED"
    # (d) no fabricated numeric score on the FAILED row.
    assert row["cv_mean"] is None
    assert row["cv_std"] is None
    # Real provenance carried through so the row is auditable (EXP-04).
    assert row["idea"] == "LightGBM baseline on raw features"
    assert row["git_commit"] not in (None, "")
    assert row["seed"] is not None


def test_re_recording_failed_is_idempotent_single_ledger_row(run_script, tmp_path):
    """(b) WR-01 for the FAILED path: re-recording an already-recorded FAILED experiment
    must NOT duplicate its row — still exactly one FAILED/null-score row."""
    ws = tmp_path
    _seed(ws)
    _git_init(ws)
    assert _record(run_script, ws).returncode == 0
    rows1 = _ledger_rows(ws)
    assert len(rows1) == 1 and rows1[0]["status"] == "FAILED"
    # Re-record the SAME FAILED exp — must overwrite, not append.
    assert _record(run_script, ws).returncode == 0
    rows2 = _ledger_rows(ws)
    assert len(rows2) == 1
    assert rows2[0]["exp_id"] == "exp-001"
    assert rows2[0]["status"] == "FAILED"
    assert rows2[0]["cv_mean"] is None


def test_incremental_ledger_equals_full_rebuild_for_mixed_statuses(run_script, tmp_path):
    """(c) The canonical MEM-01 invariant: after recording a mix of SUCCESS + FAILED
    experiments through the normal loop, control/ledger.jsonl is BYTE-IDENTICAL to a
    fresh rebuild_ledger.py of the same folders — incremental and full-derivation ledgers
    can never diverge (the exact gap this fix closes)."""
    ws = tmp_path
    exp1 = _seed(ws)  # seeds control + exp-001 stub (will be SUCCESS)
    _write_result(exp1)
    _add_exp(  # exp-002 will be FAILED (no result.json)
        ws, "exp-002",
        idea="XGBoost on target-encoded cats",
        hypothesis="target encoding beats one-hot",
    )
    _git_init(ws)

    assert _record_dir(run_script, ws, "exp-001").returncode == 0
    assert _record_dir(run_script, ws, "exp-002").returncode == 0

    incremental = (ws / "control" / "ledger.jsonl").read_bytes()

    rows = _ledger_rows(ws)
    assert {r["exp_id"]: r["status"] for r in rows} == {
        "exp-001": "SUCCESS",
        "exp-002": "FAILED",
    }
    # The FAILED row still carries no fabricated score; the SUCCESS row keeps its number.
    by_id = {r["exp_id"]: r for r in rows}
    assert by_id["exp-002"]["cv_mean"] is None
    assert by_id["exp-001"]["cv_mean"] == 0.81

    # A full rebuild of the IDENTICAL folder set must reproduce the SAME bytes.
    (ws / "control" / "ledger.jsonl").unlink()
    assert run_script("rebuild_ledger.py", "--workspace", ws, cwd=ws).returncode == 0
    rebuilt = (ws / "control" / "ledger.jsonl").read_bytes()

    assert incremental == rebuilt
