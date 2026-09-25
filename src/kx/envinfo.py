"""kx env: each run's environment next to this machine's (RUN-07).

Kernel runs record the Docker image digest (read back from Kaggle) and the key
library versions the script saw (kx_manifest.json). Local versions come from the
skill environment's installed distributions, without importing them.
"""

from __future__ import annotations

import json
import platform
from importlib import metadata
from pathlib import Path

from kx import envelope as E
from kx import workspace

LIBS = {"numpy": "numpy", "pandas": "pandas", "sklearn": "scikit-learn", "lightgbm": "lightgbm",
        "xgboost": "xgboost", "catboost": "catboost", "torch": "torch", "timm": "timm",
        "transformers": "transformers"}


def local_versions() -> dict:
    out = {"python": platform.python_version()}
    for mod, dist in LIBS.items():
        try:
            out[mod] = metadata.version(dist)
        except metadata.PackageNotFoundError:
            out[mod] = None
    return out


def cmd_env(ws: Path, args, adapter) -> dict:
    workspace.require_workspace(ws)
    local = local_versions()
    rows = []
    for exp in workspace.list_experiments(ws):
        mp = ws / "experiments" / exp / "meta.json"
        if not mp.exists():
            continue
        meta = json.loads(mp.read_text())
        env = meta.get("environment") or {}
        libs = env.get("libraries") or {}
        rows.append({"exp_id": exp, "backend": meta.get("backend"),
                     "docker_image": env.get("docker_image"), "python": env.get("python"),
                     "libraries": libs,
                     "differs_from_local": sorted(k for k, v in libs.items()
                                                  if local.get(k) and v and v != local[k])})
    lines = []
    for r in rows:
        diff = ", ".join(f"{k} {r['libraries'][k]} vs local {local[k]}"
                         for k in r["differs_from_local"]) or "same as local"
        lines.append(f"{r['exp_id']} [{r['backend']}] py {r['python']} "
                     f"image {(r['docker_image'] or '-')[-20:]}: {diff}")
    return E.make("env", "ok", f"environments of {len(rows)} recorded run(s) vs local",
                  data={"local": local, "runs": rows, "table": lines},
                  next_action=E.run("kx status", "Version gaps are a CV→LB parity risk: prefer "
                                                 "APIs that behave the same on both."))
