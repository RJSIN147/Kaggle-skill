"""SETUP-02 execution-target schema + no-overwrite-outside-setter pin (D-02).

GREEN target: 01-02. All RED now (init_workspace.py does not exist yet).
"""

import json
from pathlib import Path


def _read_json(p):
    return json.loads(Path(p).read_text())


def test_execution_target(tmp_workspace, run_script):
    """SETUP-02: default `local`; --set-execution-target changes it; non-enum rejected."""
    ws = tmp_workspace
    r1 = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert r1.returncode == 0, r1.stderr

    cfg_path = ws / "control" / "config.json"
    assert _read_json(cfg_path)["execution_target"] == "local"   # default

    r2 = run_script(
        "init_workspace.py", "--workspace", ws, "--set-execution-target", "kernel", cwd=ws
    )
    assert r2.returncode == 0, r2.stderr
    assert _read_json(cfg_path)["execution_target"] == "kernel"

    r3 = run_script(
        "init_workspace.py", "--workspace", ws, "--set-execution-target", "banana", cwd=ws
    )
    assert r3.returncode != 0                                    # enum-validated
    assert _read_json(cfg_path)["execution_target"] == "kernel"  # unchanged on bad value


def test_no_overwrite_outside_setter(tmp_workspace, run_script):
    """D-02: only --set-execution-target may overwrite; a plain re-run never resets a manual change."""
    ws = tmp_workspace
    r1 = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert r1.returncode == 0, r1.stderr

    cfg_path = ws / "control" / "config.json"
    cfg = _read_json(cfg_path)
    cfg["execution_target"] = "kernel"          # manual edit
    cfg_path.write_text(json.dumps(cfg))

    # plain re-run (no setter) must NOT reset it back to local
    r2 = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert r2.returncode == 0, r2.stderr
    assert _read_json(cfg_path)["execution_target"] == "kernel"
