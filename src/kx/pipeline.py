"""Two-stage pipelines: a downstream kernel reads an upstream kernel's output.

`kernel_sources` mounts the upstream's **latest COMPLETE** version and silently
drops version pins, so kx (1) pushes downstream only after the upstream run is
COMPLETE and recorded, (2) checks that no newer upstream version exists, and
(3) after the run, matches the upstream manifest the downstream copied into its
output against the one kx pulled for the upstream, to record which upstream
version was actually consumed. A kernel with no COMPLETE version is rejected as
a source by Kaggle.
"""

from __future__ import annotations

import json
from pathlib import Path

from kx import envelope as E
from kx.util import read_json


def _upstreams(spec: dict) -> list[str]:
    return [k[1:] for k in (spec.get("sources") or {}).get("kernels") or [] if k.startswith("@")]


def resolve_upstream(ws: Path, spec: dict, adapter) -> dict:
    kernel_sources = [k for k in spec["sources"]["kernels"] if not k.startswith("@")]
    used = []
    for up in _upstreams(spec):
        d = ws / "experiments" / up
        rp = d / "kernel_run.json"
        run = read_json(rp) if rp.exists() else None
        if not run or run.get("status") != "COMPLETE" or run.get("record_status") != "SUCCESS":
            state = (run or {}).get("status") or "not pushed"
            return {"status": "blocked", "envelope": E.make(
                "run", "invalid", f"upstream {up} is not COMPLETE and recorded ({state}); the "
                                  "downstream kernel is pushed only after it",
                errors=["upstream_not_ready"], data={"upstream": up, "upstream_status": state},
                next_action=E.run(f"kx run {up}", "Finish the upstream first."))}
        owner, slug = run["kernel_ref"].split("/", 1)
        md = adapter.get_kernel(owner, slug)
        current = md.get("current_version_number")
        warnings = []
        if current != run["kernel_version"]:
            warnings.append(f"{up}: Kaggle's latest version is v{current}, the recorded run is "
                            f"v{run['kernel_version']}; the mount serves the latest COMPLETE one")
        manifest = {}
        mp = d / "output" / "kx_manifest.json"
        if mp.exists():
            manifest = json.loads(mp.read_text())
        kernel_sources.append(run["kernel_ref"])
        used.append({"exp_id": up, "ref": run["kernel_ref"], "recorded_version": run["kernel_version"],
                     "latest_version_at_push": current, "manifest_nonce": manifest.get("run_nonce"),
                     "warnings": warnings})
    return {"status": "ready", "kernel_sources": kernel_sources, "used": used}


def consumed(ws: Path, exp_dir: Path, run: dict) -> list[dict]:
    """After the downstream run: which upstream run did it actually read?"""
    out = []
    upm = exp_dir / "output" / "upstream_manifest.json"
    got = json.loads(upm.read_text()) if upm.exists() else None
    for u in run.get("upstream") or []:
        entry = dict(u)
        if got is None:
            entry["consumed"] = "unknown (the downstream wrote no upstream_manifest.json)"
        elif got.get("run_nonce") and got.get("run_nonce") == u.get("manifest_nonce"):
            entry["consumed"] = f"v{u['recorded_version']}"
            entry["consumed_version"] = u["recorded_version"]
        else:
            entry["consumed"] = (f"a different upstream run (manifest {got.get('created')}), not "
                                 f"the recorded v{u['recorded_version']}")
        out.append(entry)
    return out


def upstream_template(ws: Path, exp_id: str) -> str | None:
    p = ws / "experiments" / exp_id / "experiment.json"
    if not p.exists():
        return None
    return json.loads(p.read_text()).get("template")

