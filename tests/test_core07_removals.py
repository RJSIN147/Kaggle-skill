"""CORE-07: the v1 paths v2 supersedes are gone, with their tests."""

import ast

import pytest
from conftest import REPO_ROOT

SRC = REPO_ROOT / "src" / "kx"
SUPERSEDED = [
    # rules-prose regex scraping, exit-78, "assumed 5/day"
    "_LIMIT_RE", "_CODE_MARKERS", "extract_daily_limit", "classify_competition_type",
    "strip_html", "LIMIT_NEEDS_USER", "DEFAULT_ASSUMED_LIMIT", "assumed_default",
    "ASSUMED_PROVENANCE", "limit_provenance", "exit 78", "5/day",
    # jupytext notebook conversion
    "jupytext", "convert_notebook", ".ipynb", "kernelspec",
    # credential consent flows
    "handle_chmod", "handle_env_population", "--yes", "_populate_env_file",
    # the default egress allowlist
    "allowedDomains", "write_settings_json", "settings.json.tmpl",
    # the fold-noise margin
    "noise_k", "NOISE_K_DEFAULT", "is_meaningful",
]


def _scanned():
    files = [p for p in SRC.rglob("*") if p.is_file() and p.suffix in (".py", ".tmpl", ".md")]
    return files + [REPO_ROOT / "SKILL.md"]


@pytest.mark.parametrize("token", SUPERSEDED)
def test_superseded_token_is_gone(token):
    hits = [str(p.relative_to(REPO_ROOT)) for p in _scanned() if token in p.read_text()]
    assert hits == [], f"{token!r} still in {hits}"


def test_v1_scripts_and_their_tests_are_deleted():
    assert not (REPO_ROOT / "scripts").exists()
    for name in ("test_capture.py", "test_limit_regex.py", "test_convert_notebook.py",
                 "test_settings.py", "test_egress_allowlist.py", "test_gate_policy.py",
                 "test_credentials.py"):
        assert not (REPO_ROOT / "tests" / name).exists(), name


def test_kx_never_imports_jupytext():
    for p in SRC.rglob("*.py"):
        tree = ast.parse(p.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all("jupytext" not in a.name for a in node.names), p
            if isinstance(node, ast.ImportFrom):
                assert "jupytext" not in (node.module or ""), p


def test_egress_allowlist_is_a_documented_opt_in():
    doc = (REPO_ROOT / "references" / "egress-allowlist.md").read_text()
    assert "opt-in" in doc and "UNVERIFIED" in doc and "example.com" in doc
    ws_writer = (SRC / "workspace.py").read_text()
    assert "settings.json" not in ws_writer and ".claude" not in ws_writer


def test_leak_scan_stays_stdlib_only():
    """The hook runs under the system python3, not the skill venv."""
    tree = ast.parse((SRC / "leak_scan.py").read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods <= {"__future__", "re", "subprocess", "sys"}, mods
