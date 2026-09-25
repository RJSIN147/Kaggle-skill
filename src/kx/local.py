"""Local runs: the same script, run on this machine against data/<canonical_ref>/.

The script finds its data through the shared resolver (KX_DATA_DIR) and writes
into experiments/exp-NNN/output/ (KX_OUTPUT_DIR). KX_SUBSAMPLE trains on a
fraction of the rows; the result, meta.json and ledger row say so.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from kx import envelope as E
from kx.data import data_dir
from kx.profile import effective
from kx.util import KxError, git_commit_paths, git_head, utc_now

ML_MODULES = ("pandas", "numpy", "sklearn", "lightgbm")


def missing_ml_modules() -> list[str]:
    return [m for m in ML_MODULES if importlib.util.find_spec(m) is None]


def run_local(ws: Path, exp_dir: Path, spec: dict, profile: dict, timeout: float = 3000):
    """Run the experiment script locally. Returns (run record, log text)."""
    missing = missing_ml_modules()
    if missing:
        raise KxError("invalid", f"local runs need {', '.join(missing)} in the skill environment",
                      errors=["local_deps_missing"],
                      next_action=E.ask_user(
                          "Ask the user to run: uv sync --project <skill dir> --extra local",
                          then=f"kx run {exp_dir.name}"))
    ddir = data_dir(ws, profile)
    if not ddir.is_dir():
        raise KxError("invalid", "no local data yet", errors=["no_local_data"],
                      next_action=E.run(f"kx sync {profile['slug']} --download"))
    sub = (spec.get("local") or {}).get("subsample")
    if not effective(profile).get("local_feasible") and not sub:
        raise KxError("invalid", "the profile marks this data as too large: set local.subsample",
                      errors=["subsample_required"],
                      next_action=E.edit(f"Set local.subsample (e.g. 0.1) in "
                                         f"experiments/{exp_dir.name}/experiment.json.",
                                         then=f"kx run {exp_dir.name}"))
    rel = f"experiments/{exp_dir.name}"
    commit = git_commit_paths(ws, f"kx: {exp_dir.name} code before local run",
                              [f"{rel}/experiment.json", f"{rel}/{spec['code_file']}"]) or git_head(ws)
    out = exp_dir / "output"
    out.mkdir(exist_ok=True)
    env = dict(os.environ)
    env.update({"KX_DATA_DIR": str(ddir.resolve()), "KX_OUTPUT_DIR": str(out.resolve()),
                "PYTHONUNBUFFERED": "1", "PYTHON_COLORS": "0", "NO_COLOR": "1"})
    env.pop("FORCE_COLOR", None)
    if sub:
        env["KX_SUBSAMPLE"] = str(sub)
    else:
        env.pop("KX_SUBSAMPLE", None)
    started = time.monotonic()
    t0 = utc_now()
    try:
        proc = subprocess.run([sys.executable, spec["code_file"]], cwd=str(exp_dir), env=env,
                              capture_output=True, text=True, timeout=timeout)
        rc, so, se = proc.returncode, proc.stdout, proc.stderr
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        rc, timed_out = None, True
        so = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        se = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    records = [{"stream_name": "stdout", "time": 0.0, "data": so},
               {"stream_name": "stderr", "time": 0.0, "data": se}]
    log_text = json.dumps(records)
    (out / "local.log").write_text(log_text)
    run = {
        "backend": "local",
        "status": "CANCEL_ACKNOWLEDGED" if timed_out else ("COMPLETE" if rc == 0 else "ERROR"),
        "exit_code": -1 if timed_out else rc,
        "timed_out": timed_out,
        "subsample": sub,
        "git_commit": commit or "uncommitted",
        "started_at": t0,
        "seconds": round(time.monotonic() - started, 1),
        "python": sys.version.split()[0],
        "log_file": f"{rel}/output/local.log",
        "recorded": False,
    }
    return run, log_text
