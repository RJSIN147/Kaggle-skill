"""test_record_kernel.py — RED (Wave 0). Pins the headline silent-failure property for EXP-05
(D-11/D-12): a kernel that reports COMPLETE but actually threw is recorded FAILED(kernel_error),
even when a VALID result.json is present.

`record_experiment.py` EXISTS but does not yet accept ``--kernel-log`` nor carry the
``kernel_error`` rung — so passing ``--kernel-log`` errors now (RED) until plan 04-04 adds the
new FIRST rung of the fail-closed ladder (scan log → hit ⇒ FAILED(kernel_error) BEFORE
result.json is trusted). Fixtures are synthetic (no live GPU) per the phase's headline goal.

Seeding mirrors test_record_experiment.py (real git repo for honest provenance).
"""

import json
import os
import subprocess
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
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
        ["git", "-c", "user.email=t@e.com", "-c", "user.name=t", "commit", "-qm", "seed"],
        cwd=ws, check=True, env=_GIT_ENV,
    )


def _seed(ws: Path) -> Path:
    ctrl = ws / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    (ctrl / "config.json").write_text(
        json.dumps(
            {
                "competition_slug": "titanic",
                "metric": {"name": "roc_auc", "greater_is_better": True},
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
        "idea": "LightGBM baseline on a Kaggle GPU kernel",
        "hypothesis": "the same experiment runs on Kaggle compute and pulls back a CV score",
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


def _write_kernel_run(exp: Path, status: str) -> None:
    """Write a minimal kernel_run.json carrying a given poll-written status.

    Mirrors what poll_kernel.py leaves behind on a terminal poll (status set to one of
    COMPLETE/ERROR/CANCEL_ACKNOWLEDGED). Only the fields the recorder reads for the status
    rung + provenance merge are populated.
    """
    (exp / "kernel_run.json").write_text(
        json.dumps(
            {
                "backend": "kernel",
                "kernel_slug": "tuser/exp-001",
                "status": status,
            },
            indent=2,
        )
        + "\n"
    )


def _record(run_script, ws, *extra):
    return run_script(
        "record_experiment.py", "--workspace", ws, "--exp-dir", "experiments/exp-001",
        *extra, cwd=ws,
    )


def test_traceback_beats_valid_result(run_script, tmp_path):
    """THE headline: a VALID result.json is on disk, but the pulled kernel log carries a
    traceback ⇒ FAILED(kernel_error); the log scan runs BEFORE result.json is trusted (D-12)."""
    ws = tmp_path
    exp = _seed(ws)
    _write_result(exp)  # a perfectly valid result on disk — must NOT rescue the run
    _git_init(ws)
    log = FIXTURES / "kernel_logs" / "complete_but_threw.txt"
    r = _record(run_script, ws, "--kernel-log", str(log))
    assert r.returncode == 0, r.stderr  # recording a failure IS a successful cycle

    meta = _read_meta(exp)
    assert meta["status"] == "FAILED"
    assert meta["failure_reason"] == "kernel_error"


def test_clean_log_success(run_script, tmp_path):
    """A clean kernel log + a valid result.json ⇒ SUCCESS on the kernel path (fall through
    to the existing D-06 ladder)."""
    ws = tmp_path
    exp = _seed(ws)
    _write_result(exp)
    _git_init(ws)
    log = FIXTURES / "kernel_logs" / "clean.txt"
    r = _record(run_script, ws, "--kernel-log", str(log))
    assert r.returncode == 0, r.stderr

    meta = _read_meta(exp)
    assert meta["status"] == "SUCCESS"
    assert meta["failure_reason"] is None


def test_oom_marker(run_script, tmp_path):
    """An OOM / process-killed kernel log ⇒ FAILED(kernel_error), even with a valid result."""
    ws = tmp_path
    exp = _seed(ws)
    _write_result(exp)
    _git_init(ws)
    log = FIXTURES / "kernel_logs" / "oom.txt"
    r = _record(run_script, ws, "--kernel-log", str(log))
    assert r.returncode == 0, r.stderr

    meta = _read_meta(exp)
    assert meta["status"] == "FAILED"
    assert meta["failure_reason"] == "kernel_error"


def test_source_has_kernel_error_rung():
    """Source-invariant (goes GREEN in 04-04): the ONE new reason `kernel_error` lives in the
    single recorder (D-12: one ladder, one enum — extended, never re-derived)."""
    src = (SCRIPTS_DIR / "record_experiment.py").read_text()
    assert "kernel_error" in src


# --------------------------------------------------------------------------- #
# 04-06 gap-closure regression tests (CR-01 + WR-03). RED against the pre-fix
# recorder: Tests A/B/D would record SUCCESS off the stale valid result.json and
# Tests A/B/C/E find no meta["kernel"]["status"] key.
# --------------------------------------------------------------------------- #


def test_status_error_beats_valid_result(run_script, tmp_path):
    """CR-01 (Test A): kernel_run.json.status == ERROR ⇒ FAILED(kernel_error), even with a
    marker-free (clean) log AND a perfectly valid result.json on disk. The Kaggle-confirmed
    terminal failure is authoritative BEFORE result.json is validated."""
    ws = tmp_path
    exp = _seed(ws)
    _write_result(exp)  # a valid result that must NOT rescue the confirmed failure
    _write_kernel_run(exp, "ERROR")
    _git_init(ws)
    log = FIXTURES / "kernel_logs" / "clean.txt"  # marker-free ⇒ only the status rung can fire
    r = _record(run_script, ws, "--kernel-log", str(log))
    assert r.returncode == 0, r.stderr

    meta = _read_meta(exp)
    assert meta["status"] == "FAILED"
    assert meta["failure_reason"] == "kernel_error"


def test_status_cancel_acknowledged_beats_valid_result(run_script, tmp_path):
    """CR-01 (Test B): kernel_run.json.status == CANCEL_ACKNOWLEDGED ⇒ FAILED(kernel_error),
    same as ERROR — the second Kaggle-confirmed FAILED-terminal state."""
    ws = tmp_path
    exp = _seed(ws)
    _write_result(exp)
    _write_kernel_run(exp, "CANCEL_ACKNOWLEDGED")
    _git_init(ws)
    log = FIXTURES / "kernel_logs" / "clean.txt"
    r = _record(run_script, ws, "--kernel-log", str(log))
    assert r.returncode == 0, r.stderr

    meta = _read_meta(exp)
    assert meta["status"] == "FAILED"
    assert meta["failure_reason"] == "kernel_error"


def test_status_copied_into_meta_kernel_on_failed_path(run_script, tmp_path):
    """CR-01 (Test C): the confirmed status is copied verbatim into meta["kernel"]["status"]
    on the FAILED path — provenance audit of WHY the run was failed."""
    ws = tmp_path
    exp = _seed(ws)
    _write_result(exp)
    _write_kernel_run(exp, "ERROR")
    _git_init(ws)
    log = FIXTURES / "kernel_logs" / "clean.txt"
    r = _record(run_script, ws, "--kernel-log", str(log))
    assert r.returncode == 0, r.stderr

    meta = _read_meta(exp)
    assert meta["status"] == "FAILED"
    assert meta["kernel"]["status"] == "ERROR"


def test_unreadable_kernel_log_fails_closed(run_script, tmp_path):
    """WR-03 (Test D): an unreadable/missing --kernel-log ⇒ FAILED(kernel_error), NEVER SUCCESS
    off a stale valid result.json. No kernel_run.json (or one without a failed status) — the
    unreadable-log rung alone must fail closed."""
    ws = tmp_path
    exp = _seed(ws)
    _write_result(exp)  # a stale valid result that must NOT rescue an unverifiable log
    _git_init(ws)
    missing_log = exp / "kernel_log.txt"  # never pulled — does not exist
    assert not missing_log.exists()
    r = _record(run_script, ws, "--kernel-log", str(missing_log))
    assert r.returncode == 0, r.stderr

    meta = _read_meta(exp)
    assert meta["status"] == "FAILED"
    assert meta["failure_reason"] == "kernel_error"


def test_status_complete_success_and_audit_copy(run_script, tmp_path):
    """CR-01 (Test E): a clean log + valid result.json + kernel_run.json status COMPLETE ⇒
    SUCCESS, AND meta["kernel"]["status"] == COMPLETE — the status copy fires on the SUCCESS
    path too and COMPLETE never fails."""
    ws = tmp_path
    exp = _seed(ws)
    _write_result(exp)
    _write_kernel_run(exp, "COMPLETE")
    _git_init(ws)
    log = FIXTURES / "kernel_logs" / "clean.txt"
    r = _record(run_script, ws, "--kernel-log", str(log))
    assert r.returncode == 0, r.stderr

    meta = _read_meta(exp)
    assert meta["status"] == "SUCCESS"
    assert meta["failure_reason"] is None
    assert meta["kernel"]["status"] == "COMPLETE"
