"""test_convert_notebook.py — RED (Wave 0). Pins the D-02 convert contract for EXP-05.

`convert_notebook.py` does NOT exist yet — this whole module is expected to FAIL/ERROR until
plan 04-02 builds it. The script mirrors ``run_local.py``'s posture: it shells
``uv run --no-sync jupytext --to notebook …`` to regenerate ``experiment.ipynb`` from the
scaffold-minted ``experiment.py`` (a build artifact), and MUST be re-runnable and
non-destructive — the ``.py`` seam (``resolve_data_dir()``) is never mutated (D-02).

We stub ``uv`` on PATH with a tiny jupytext emulator (mirrors ``test_run_local._make_uv_shim``)
so the shell-out exercises the contract without a real Jupyter/jupytext env. The script module
is never imported at top level (conftest discipline) — we drive it as a subprocess.
"""

import json
import os
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _make_jupytext_uv_shim(bindir: Path) -> None:
    """A fake `uv` on PATH that emulates `uv run --no-sync jupytext --to notebook <py>`.

    It finds the `.py` input (and optional `.ipynb` output) anywhere in the argv, writes a
    minimal-but-valid notebook next to the source, and NEVER touches the `.py` file.
    """
    bindir.mkdir(parents=True, exist_ok=True)
    shim = bindir / "uv"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        'inp=""; out=""\n'
        'for a in "$@"; do\n'
        "  case \"$a\" in\n"
        '    *.py) inp="$a" ;;\n'
        '    *.ipynb) out="$a" ;;\n'
        "  esac\n"
        "done\n"
        'if [ -z "$inp" ]; then echo "jupytext shim: no .py input" >&2; exit 3; fi\n'
        'if [ -z "$out" ]; then out="${inp%.py}.ipynb"; fi\n'
        'python3 - "$inp" "$out" <<\'PYEOF\'\n'
        "import json, sys\n"
        "src = open(sys.argv[1]).read()\n"
        "nb = {\n"
        '    "cells": [{"cell_type": "code", "metadata": {}, "execution_count": None,\n'
        '               "outputs": [], "source": src.splitlines(keepends=True)}],\n'
        '    "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"}},\n'
        '    "nbformat": 4, "nbformat_minor": 5,\n'
        "}\n"
        'open(sys.argv[2], "w").write(json.dumps(nb))\n'
        "PYEOF\n"
    )
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


def _path_with(bindir: Path) -> dict:
    return {"PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"}


def test_reconvert_idempotent(run_script, tmp_path):
    """Running convert twice on an UNCHANGED experiment.py regenerates experiment.ipynb
    non-destructively and leaves experiment.py byte-identical (D-02)."""
    ws = tmp_path
    _seed_config(ws)
    exp = ws / "experiments" / "exp-001"
    (exp / "artifacts").mkdir(parents=True, exist_ok=True)
    src = (
        "from pathlib import Path\n\n"
        "def resolve_data_dir():\n"
        "    return Path('/kaggle/input/titanic')\n\n"
        "print(resolve_data_dir())\n"
    )
    py = exp / "experiment.py"
    py.write_text(src)

    bindir = ws / "bin"
    _make_jupytext_uv_shim(bindir)
    env = _path_with(bindir)

    r1 = run_script(
        "convert_notebook.py", "--workspace", ws, "--exp-dir", "experiments/exp-001",
        cwd=ws, extra_env=env,
    )
    assert r1.returncode == 0, r1.stderr
    ipynb = exp / "experiment.ipynb"
    assert ipynb.is_file(), "convert must produce experiment.ipynb"
    nb1 = json.loads(ipynb.read_text())
    assert nb1.get("nbformat") == 4
    # non-destructive: the .py seam is untouched.
    assert py.read_text() == src

    # Re-run against the unchanged .py: regenerates cleanly, still valid, still non-destructive.
    r2 = run_script(
        "convert_notebook.py", "--workspace", ws, "--exp-dir", "experiments/exp-001",
        cwd=ws, extra_env=env,
    )
    assert r2.returncode == 0, r2.stderr
    assert py.read_text() == src
    json.loads(ipynb.read_text())  # still a valid notebook


def test_source_routes_through_uv_no_sync_no_pip_install():
    """Source-invariant (goes GREEN in 04-02): convert shells `uv run --no-sync` like
    run_local and never runtime-installs jupytext (CLAUDE.md never-runtime-install)."""
    src = (SCRIPTS_DIR / "convert_notebook.py").read_text()
    assert "--no-sync" in src
    assert "pip install" not in src
