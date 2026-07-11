"""test_run_local.py — run_local.py bounded `uv run --no-sync` + exit-code capture (EXP-03).

Exercises run_local.py as a SUBPROCESS (the documented invocation contract). run_local
NEVER installs packages (`--no-sync`) and NEVER scrapes stdout for a score — it captures
ONLY the child exit code and hands off to record_experiment.py, which reads the on-disk
result.json (D-05). To exercise the shell-out without a real ML env we shim `uv` onto PATH:
a tiny wrapper that drops the leading `run --no-sync` and execs the rest with real python.
"""

import json
import os
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _make_uv_shim(bindir: Path) -> None:
    """A fake `uv` on PATH: `uv run --no-sync python foo ...` -> `python foo ...`."""
    bindir.mkdir(parents=True, exist_ok=True)
    shim = bindir / "uv"
    shim.write_text('#!/usr/bin/env bash\nshift 2\nexec "$@"\n')
    shim.chmod(0o755)


def _seed_config(ws: Path, slug: str = "titanic") -> None:
    ctrl = ws / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    (ctrl / "config.json").write_text(
        json.dumps(
            {
                "competition_slug": slug,
                "metric": {"name": "roc_auc", "greater_is_better": True},
                "cv": {"scheme": "StratifiedKFold"},
            },
            indent=2,
        )
        + "\n"
    )


def _make_exp(ws: Path, exp_id: str = "exp-001", body: str = "import sys; sys.exit(0)") -> Path:
    exp = ws / "experiments" / exp_id
    (exp / "artifacts").mkdir(parents=True, exist_ok=True)
    (exp / "experiment.py").write_text(body + "\n")
    return exp


def _path_with_shim(bindir: Path) -> dict:
    return {"PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"}


def test_throwing_experiment_returns_nonzero_no_fabricated_score(run_script, tmp_path):
    ws = tmp_path
    _seed_config(ws)
    _make_exp(ws, body="import sys; sys.exit(1)")
    bindir = tmp_path / "bin"
    _make_uv_shim(bindir)
    r = run_script(
        "run_local.py", "--workspace", ws, "--exp-dir", "experiments/exp-001",
        cwd=ws, extra_env=_path_with_shim(bindir),
    )
    assert r.returncode != 0
    # run_local must never invent a score (it captures only the exit code).
    assert "cv_mean" not in r.stdout


def test_uv_absent_prints_uv_sync_remediation(run_script, tmp_path):
    ws = tmp_path
    _seed_config(ws)
    _make_exp(ws)
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    r = run_script(
        "run_local.py", "--workspace", ws, "--exp-dir", "experiments/exp-001",
        cwd=ws, extra_env={"PATH": str(empty)},
    )
    assert r.returncode != 0
    assert "uv sync" in (r.stdout + r.stderr)


def test_successful_run_returns_zero(run_script, tmp_path):
    ws = tmp_path
    _seed_config(ws)
    _make_exp(ws, body="import sys; sys.exit(0)")
    bindir = tmp_path / "bin"
    _make_uv_shim(bindir)
    r = run_script(
        "run_local.py", "--workspace", ws, "--exp-dir", "experiments/exp-001",
        cwd=ws, extra_env=_path_with_shim(bindir),
    )
    assert r.returncode == 0, r.stderr


def test_missing_experiment_py_fails_clear(run_script, tmp_path):
    ws = tmp_path
    _seed_config(ws)
    (ws / "experiments" / "exp-001" / "artifacts").mkdir(parents=True, exist_ok=True)
    bindir = tmp_path / "bin"
    _make_uv_shim(bindir)
    r = run_script(
        "run_local.py", "--workspace", ws, "--exp-dir", "experiments/exp-001",
        cwd=ws, extra_env=_path_with_shim(bindir),
    )
    assert r.returncode != 0


def test_source_has_no_sync_and_no_pip_install():
    src = (SCRIPTS_DIR / "run_local.py").read_text()
    assert "--no-sync" in src
    assert "pip install" not in src


def test_source_only_uses_returncode_never_scrapes_stdout():
    src = (SCRIPTS_DIR / "run_local.py").read_text()
    assert "returncode" in src
    # The runner never parses the child's stdout to obtain a numeric score (D-05).
    assert "proc.stdout" not in src
