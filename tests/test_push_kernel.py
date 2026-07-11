"""test_push_kernel.py — RED (Wave 0). Pins the kernel-metadata generation + internet
provenance contract for EXP-05 (D-04/05/06/07).

`push_kernel.py` does NOT exist yet — this module FAILs/ERRORs until plan 04-02 builds it.
The script resolves ``<username>`` via ``kaggle config view`` (no secret), renders
``kernel-metadata.json`` (deterministic id ``<username>/<slug>-exp-NNN``, ``is_private:true``,
``enable_internet:false`` UNLESS overridden, ``competition_sources:[<slug>]``), records the
effective internet flag in ``experiments/exp-NNN/kernel_run.json`` (D-06 guard), and pushes via
``run_kaggle`` — never a live call here (a `kaggle` PATH shim intercepts every subcommand).
"""

import json
import os
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


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


def _make_exp(ws: Path, exp_id: str = "exp-001") -> Path:
    exp = ws / "experiments" / exp_id
    (exp / "artifacts").mkdir(parents=True, exist_ok=True)
    (exp / "experiment.py").write_text("print('hi')\n")
    (exp / "experiment.ipynb").write_text(
        json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5})
    )
    return exp


def _make_kaggle_shim(bindir: Path) -> None:
    """A fake `kaggle` on PATH: resolves username, answers quota, and accepts pushes —
    so the metadata/provenance contract is exercised with NO live Kaggle call."""
    bindir.mkdir(parents=True, exist_ok=True)
    shim = bindir / "kaggle"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "config" ] && [ "$2" = "view" ]; then\n'
        '  echo "- username: testuser"; exit 0\n'
        "fi\n"
        'if [ "$1" = "quota" ]; then\n'
        "  echo '{\"resource\":\"gpu\",\"used\":0.0,\"remaining\":30.0,"
        "\"total\":30.0,\"refreshAt\":\"2026-07-19T00:00:00Z\"}'; exit 0\n"
        "fi\n"
        'if [ "$1" = "kernels" ]; then echo "kernels $2 ok"; exit 0; fi\n'
        "exit 0\n"
    )
    shim.chmod(0o755)


def _path_with(bindir: Path) -> dict:
    return {"PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"}


def test_metadata_golden(run_script, tmp_path):
    """Generated kernel-metadata.json EQUALS the golden fixture for
    (username=testuser, slug=titanic, exp-001), internet-off, GPU default."""
    ws = tmp_path
    _seed_config(ws)
    _make_exp(ws)
    bindir = ws / "bin"
    _make_kaggle_shim(bindir)

    r = run_script(
        "push_kernel.py", "--workspace", ws, "--exp-dir", "experiments/exp-001",
        cwd=ws, extra_env=_path_with(bindir),
    )
    assert r.returncode == 0, r.stderr

    metas = list(ws.rglob("kernel-metadata.json"))
    assert metas, "push_kernel.py did not generate a kernel-metadata.json"
    generated = json.loads(metas[0].read_text())
    golden = json.loads((FIXTURES / "kernel-metadata.golden.json").read_text())
    assert generated == golden


def test_internet_provenance(run_script, tmp_path):
    """The EFFECTIVE enable_internet value (default false) is recorded in
    experiments/exp-001/kernel_run.json → downstream meta (D-06 guard)."""
    ws = tmp_path
    _seed_config(ws)
    _make_exp(ws)
    bindir = ws / "bin"
    _make_kaggle_shim(bindir)

    r = run_script(
        "push_kernel.py", "--workspace", ws, "--exp-dir", "experiments/exp-001",
        cwd=ws, extra_env=_path_with(bindir),
    )
    assert r.returncode == 0, r.stderr

    kr = ws / "experiments" / "exp-001" / "kernel_run.json"
    assert kr.is_file(), "push_kernel.py must persist kernel_run.json (D-03)"
    data = json.loads(kr.read_text())
    # Default is internet-off; the effective flag is an auditable recorded fact.
    assert data.get("enable_internet") is False


def _make_kaggle_shim_with_version(bindir: Path, version: int = 3) -> None:
    """Like `_make_kaggle_shim`, but the `kernels push` output names a version int
    so the D-05 provenance scrape has something to parse."""
    bindir.mkdir(parents=True, exist_ok=True)
    shim = bindir / "kaggle"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "config" ] && [ "$2" = "view" ]; then\n'
        '  echo "- username: testuser"; exit 0\n'
        "fi\n"
        'if [ "$1" = "quota" ]; then\n'
        "  echo '{\"resource\":\"gpu\",\"used\":0.0,\"remaining\":30.0,"
        "\"total\":30.0,\"refreshAt\":\"2026-07-19T00:00:00Z\"}'; exit 0\n"
        "fi\n"
        'if [ "$1" = "kernels" ] && [ "$2" = "push" ]; then\n'
        f'  echo "Kernel version {version} successfully pushed"; exit 0\n'
        "fi\n"
        'if [ "$1" = "kernels" ]; then echo "kernels $2 ok"; exit 0; fi\n'
        "exit 0\n"
    )
    shim.chmod(0o755)


def test_version_provenance(run_script, tmp_path):
    """kernel_run.json.kernel_version is the integer parsed from the push output when
    present, else null — provenance-only, never blocking the push exit code (D-05)."""
    # Version present in the push output → parsed as an int.
    ws = tmp_path / "with_version"
    ws.mkdir()
    _seed_config(ws)
    _make_exp(ws)
    bindir = ws / "bin"
    _make_kaggle_shim_with_version(bindir, version=7)
    r = run_script(
        "push_kernel.py", "--workspace", ws, "--exp-dir", "experiments/exp-001",
        cwd=ws, extra_env=_path_with(bindir),
    )
    assert r.returncode == 0, r.stderr
    data = json.loads((ws / "experiments" / "exp-001" / "kernel_run.json").read_text())
    assert data["kernel_version"] == 7

    # No parseable version in the push output → null, and the push still succeeds.
    ws2 = tmp_path / "no_version"
    ws2.mkdir()
    _seed_config(ws2)
    _make_exp(ws2)
    bindir2 = ws2 / "bin"
    _make_kaggle_shim(bindir2)  # emits "kernels push ok" — no version integer
    r2 = run_script(
        "push_kernel.py", "--workspace", ws2, "--exp-dir", "experiments/exp-001",
        cwd=ws2, extra_env=_path_with(bindir2),
    )
    assert r2.returncode == 0, r2.stderr
    data2 = json.loads((ws2 / "experiments" / "exp-001" / "kernel_run.json").read_text())
    assert data2["kernel_version"] is None


def test_source_routes_through_gateway():
    """Source-invariant (goes GREEN in 04-02): every kaggle call routes through the
    no-echo/timeout choke point, never a bare subprocess or a printed status buffer."""
    src = (SCRIPTS_DIR / "push_kernel.py").read_text()
    assert "run_kaggle" in src
