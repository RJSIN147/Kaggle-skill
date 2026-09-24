#!/usr/bin/env python3
"""convert_notebook.py — regenerate experiment.ipynb from experiment.py (EXP-05, D-02).

The `convert` entry point of the kernel-path front half
(`scaffold -> convert -> push -> poll -> pull -> record`). It shells the SAME
scaffold-minted `experiment.py` through `uv run --no-sync jupytext --to notebook`
to (re)produce `experiment.ipynb` — the notebook `push_kernel.py` uploads as the
kernel's `code_file`. The `.ipynb` is a REGENERABLE BUILD ARTIFACT: every convert
overwrites it from the unchanged `.py`, and the `.py` seam (`resolve_data_dir()`)
is NEVER mutated (D-02 non-destructive). Re-running convert is always safe.

Two load-bearing postures, copied verbatim from `run_local.py` (the skill's only
other `uv run --no-sync` caller):

  * `--no-sync` (Pitfall 5): a workspace whose ML env is not synced degrades cleanly
    to a non-zero exit — NEVER a silent network package fetch of jupytext. On a
    missing `uv` the converter prints the `run `uv sync`` remediation and converts
    nothing. Declare deps, validate, instruct — never install at runtime (CLAUDE.md).
  * timeout-bounded: a runaway convert is a clean handled error, not a hang.

Kernelspec (live-observed 2026-09-25, quick 260925-66x): `jupytext --to notebook`
writes NO `kernelspec` into the notebook metadata, and Kaggle executes notebooks with
papermill, which then fails with "No kernel name found in notebook and no override
provided." The converter therefore passes a python3 kernelspec via jupytext's
`--update-metadata` (one argv element, never a shell string) and FAILS CLOSED (exit 1)
if the regenerated notebook still lacks one, so an unexecutable notebook is never pushed.

Portability (CLAUDE.md §Stack Patterns): stdlib-only, self-locating via
`Path(__file__)`, `--workspace`-driven, non-interactive (argparse in / exit-code out).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

# jupytext's `--to notebook` writes no kernelspec; Kaggle's papermill then fails with
# "No kernel name found in notebook and no override provided." (live-observed 2026-09-25,
# BUG 1). This exact payload is the live-verified fix. It is a module CONSTANT, passed to
# jupytext as ONE argv element via json.dumps — never user/Kaggle input, never shell-quoted.
_NOTEBOOK_METADATA = {
    "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
    "language_info": {"name": "python"},
}


def _notebook_kernel_name(path: Path) -> str | None:
    """Return metadata.kernelspec.name of the notebook at `path`, or None if absent/unreadable."""
    try:
        nb = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(nb, dict):
        return None
    meta = nb.get("metadata")
    spec = meta.get("kernelspec") if isinstance(meta, dict) else None
    name = spec.get("name") if isinstance(spec, dict) else None
    return name if isinstance(name, str) and name else None


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="convert_notebook.py",
        description="Regenerate experiments/exp-NNN/experiment.ipynb from the "
                    "scaffold-minted experiment.py via `uv run --no-sync jupytext` "
                    "(non-destructive, re-runnable; EXP-05, D-02).",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    ap.add_argument("--exp-dir", required=True,
                    help="Experiment folder relative to the workspace "
                         "(e.g. experiments/exp-001).")
    ap.add_argument("--timeout", type=int, default=300,
                    help="Seconds to bound the convert before it is a clean handled "
                         "error (default: 300).")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()

    # The exp dir is workspace-relative; the subprocess runs with cwd=ws so relative
    # paths keep both experiment.py and experiment.ipynb under the experiment folder.
    exp_rel = args.exp_dir
    exp_dir = (ws / exp_rel).resolve()
    exp_py = exp_dir / "experiment.py"
    if not exp_py.is_file():
        print(
            f"cannot convert: {exp_rel}/experiment.py not found — scaffold the "
            f"experiment first (scaffold_experiment.py).",
            file=sys.stderr,
        )
        return 1

    exp_ipynb = exp_dir / "experiment.ipynb"

    # `--no-sync` is LOAD-BEARING (Pitfall 5): a missing ML env yields a clean non-zero,
    # never a network install of jupytext. Without `uv` on PATH there is no synced env
    # at all — print the remediation and convert nothing.
    if shutil.which("uv") is None:
        print(
            "workspace ML env not synced — run `uv sync` (uv is not on PATH). "
            "Nothing was converted.",
            file=sys.stderr,
        )
        return 1

    # jupytext regenerates the .ipynb from the UNCHANGED experiment.py every call
    # (D-02 GUARD): this is a build artifact — overwrite it, never create_if_absent it,
    # and NEVER modify experiment.py.
    cmd = [
        "uv", "run", "--no-sync", "jupytext", "--to", "notebook",
        "--update-metadata", json.dumps(_NOTEBOOK_METADATA),
        str(exp_py), "-o", str(exp_ipynb),
    ]

    try:
        proc = subprocess.run(
            cmd, cwd=str(ws), capture_output=True, text=True, timeout=args.timeout
        )
    except subprocess.TimeoutExpired:
        print(
            f"convert timed out after {args.timeout}s — treated as a failed convert "
            f"(no notebook produced).",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"could not launch `uv run`: {exc} — nothing converted.", file=sys.stderr)
        return 1

    exit_code = proc.returncode
    if exit_code != 0:
        # Surface a short stderr tail for debugging — never fabricate anything. A
        # non-zero convert is a clean handled failure (possibly a missing/unsynced ML
        # env); the remediation for the env case is the same `uv sync`.
        tail = (proc.stderr or "").strip().splitlines()[-5:]
        if tail:
            print("\n".join(tail), file=sys.stderr)
        print(
            f"jupytext exited {exit_code} — no notebook produced. If the ML env is "
            f"absent, run `uv sync`.",
            file=sys.stderr,
        )
        return exit_code

    # Fail closed (BUG 1): a notebook without a kernelspec cannot be executed by papermill
    # on Kaggle — refuse to report success so nothing unexecutable is handed to push.
    if _notebook_kernel_name(exp_ipynb) is None:
        print(
            f"convert produced {exp_rel}/experiment.ipynb without a kernelspec — papermill on "
            f"Kaggle cannot execute a notebook without one. Do not push it.",
            file=sys.stderr,
        )
        return 1

    print(
        f"convert ok (exit 0) — regenerated {exp_rel}/experiment.ipynb from "
        f"experiment.py. push_kernel.py consumes it as the kernel code_file."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
