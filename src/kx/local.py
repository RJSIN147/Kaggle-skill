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
from kx.util import KxError, git_commit_paths, git_head, skill_path, utc_now

ML_MODULES = ("pandas", "numpy", "sklearn", "lightgbm")


def missing_ml_modules() -> list[str]:
    return [m for m in ML_MODULES if importlib.util.find_spec(m) is None]


def run_agent_eval(ws: Path, exp_dir: Path, spec: dict, profile: dict, timeout: float = 3000):
    """Self-play validation + win rate vs a pool, in a throwaway kaggle-environments env."""
    import shutil

    uv = shutil.which("uv")
    if uv is None:
        raise KxError("invalid", "agent evaluation needs `uv` on PATH", errors=["uv_missing"])
    rel = f"experiments/{exp_dir.name}"
    commit = git_commit_paths(ws, f"kx: {exp_dir.name} agent before evaluation",
                              [f"{rel}/experiment.json", f"{rel}/{spec['code_file']}"]) or git_head(ws)
    pool = []
    for other in sorted((ws / "experiments").glob("exp-*/experiment.json")):
        o = json.loads(other.read_text())
        if o.get("template") == "agent" and o.get("exp_id") != spec["exp_id"] and \
                (other.parent / o.get("code_file", "main.py")).exists() and \
                (other.parent / "meta.json").exists():
            pool.append(str(other.parent / o.get("code_file", "main.py")))
    env_name = (spec.get("local") or {}).get("env") or profile["slug"]
    out = exp_dir / "output"
    out.mkdir(exist_ok=True)
    cmd = [uv, "run", "--no-project", "--with", "kaggle-environments", "python",
           str(Path(__file__).with_name("agent_eval.py")), "--env", env_name,
           "--agent", str(exp_dir / spec["code_file"]), "--episodes", "10",
           "--exp-id", spec["exp_id"], "--out", str(out / "result.json"), "--pool", *pool]
    started = time.monotonic()
    env = dict(os.environ, PYTHON_COLORS="0", NO_COLOR="1")
    try:
        proc = subprocess.run(cmd, cwd=str(exp_dir), capture_output=True, text=True,
                              timeout=timeout, env=env)
        rc, so, se, timed_out = proc.returncode, proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired as exc:
        rc, timed_out = None, True
        so = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        se = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    log_text = json.dumps([{"stream_name": "stdout", "time": 0.0, "data": so},
                           {"stream_name": "stderr", "time": 0.0, "data": se}])
    (out / "local.log").write_text(log_text)
    return {"backend": "local", "kind": "agent_eval",
            "status": "CANCEL_ACKNOWLEDGED" if timed_out else ("COMPLETE" if rc == 0 else "ERROR"),
            "exit_code": -1 if timed_out else rc, "timed_out": timed_out, "subsample": None,
            "git_commit": commit or "uncommitted", "started_at": utc_now(),
            "seconds": round(time.monotonic() - started, 1), "pool": [Path(p).parent.name for p in pool],
            "log_file": f"{rel}/output/local.log", "recorded": False}, log_text


def run_local(ws: Path, exp_dir: Path, spec: dict, profile: dict, timeout: float = 3000):
    """Run the experiment script locally. Returns (run record, log text)."""
    from kx.templates_registry import TEMPLATES

    needs_stack = TEMPLATES.get(spec.get("template"), {}).get("ml_stack", True)
    missing = missing_ml_modules() if needs_stack else []
    if missing:
        raise KxError("invalid", f"local runs need {', '.join(missing)} in the skill environment",
                      errors=["local_deps_missing"],
                      next_action=E.ask_user(
                          f"Ask the user to run: uv sync --project {skill_path()} --extra local",
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
