"""SETUP-01/02 scaffolder contract (D-01/D-02) + git init + review-driven pins.

GREEN targets: test_full_layout / test_safe_merge_idempotent / the three merge
pins land in 01-02; test_git_init / test_scaffold_commit_excludes_stray_files
land in 01-03. All RED now (init_workspace.py does not exist yet).
"""

import json
import subprocess
from pathlib import Path


def _read_json(p):
    return json.loads(Path(p).read_text())


def test_full_layout(tmp_workspace, run_script):
    """SETUP-01 (D-10): empty dir -> full workspace layout + control-plane + slug recorded."""
    ws = tmp_workspace
    res = run_script(
        "init_workspace.py", "--workspace", ws,
        "--slug", "titanic", "--execution-target", "local", cwd=ws,
    )
    assert res.returncode == 0, res.stderr

    # control-plane (tracked)
    assert (ws / "control" / "config.json").is_file()
    assert (ws / "control" / "state.json").is_file()
    assert (ws / "control" / "ledger.jsonl").is_file()
    # human docs at root
    assert (ws / "competition.md").is_file()
    assert (ws / "strategy.md").is_file()
    assert (ws / "README.md").is_file()
    # secrets + config surface
    assert (ws / ".env").is_file()
    assert (ws / ".gitignore").is_file()
    assert (ws / ".claude" / "settings.json").is_file()
    assert (ws / "pyproject.toml").is_file()
    # directories
    assert (ws / "data").is_dir()
    assert (ws / "experiments").is_dir()

    cfg = _read_json(ws / "control" / "config.json")
    assert cfg["competition_slug"] == "titanic"
    assert cfg["execution_target"] == "local"


def test_safe_merge_idempotent(tmp_workspace, run_script):
    """D-02: a second run creates nothing new and preserves a user edit."""
    ws = tmp_workspace
    r1 = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert r1.returncode == 0, r1.stderr

    strat = ws / "strategy.md"
    strat.write_text("MY CUSTOM STRATEGY\n")

    r2 = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert r2.returncode == 0, r2.stderr
    assert strat.read_text() == "MY CUSTOM STRATEGY\n"  # never overwritten


def test_git_init(tmp_workspace, run_script):
    """SETUP-01: git repo on branch `main` + one `chore: scaffold workspace` commit."""
    ws = tmp_workspace
    res = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert res.returncode == 0, res.stderr
    assert (ws / ".git").is_dir()

    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ws, capture_output=True, text=True
    )
    assert branch.stdout.strip() == "main"

    log = subprocess.run(["git", "log", "--oneline"], cwd=ws, capture_output=True, text=True)
    assert "scaffold workspace" in log.stdout


def test_refuses_creation_without_slug(tmp_workspace, run_script):
    """D-01 mechanical gate: a fresh workspace WITHOUT --slug creates nothing, exits non-zero."""
    ws = tmp_workspace
    res = run_script("init_workspace.py", "--workspace", ws, "--execution-target", "local", cwd=ws)
    assert res.returncode != 0
    # the refusal must be about the missing slug (distinguishes from a crash)
    assert "slug" in (res.stdout + res.stderr).lower()
    # nothing scaffolded
    assert not (ws / "control").exists()
    assert not (ws / ".git").exists()
    assert not (ws / "competition.md").exists()


def test_safe_merge_deep_preserves_nested(tmp_workspace, run_script):
    """D-02 deep-merge: a nested user edit (cv.scheme) survives; missing top-level keys are re-added."""
    ws = tmp_workspace
    r1 = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert r1.returncode == 0, r1.stderr

    cfg_path = ws / "control" / "config.json"
    cfg = _read_json(cfg_path)
    cfg["cv"] = {"scheme": "custom"}
    cfg.pop("workspace_version", None)  # drop a top-level key to prove it's re-added
    cfg_path.write_text(json.dumps(cfg))

    r2 = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert r2.returncode == 0, r2.stderr
    merged = _read_json(cfg_path)
    assert merged["cv"]["scheme"] == "custom"   # nested user edit preserved
    assert "workspace_version" in merged        # missing known key re-added


def test_safe_merge_malformed_json_fails_clearly(tmp_workspace, run_script):
    """D-02 fail-clear: a corrupt control/config.json is not overwritten; non-zero exit; path named."""
    ws = tmp_workspace
    r1 = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert r1.returncode == 0, r1.stderr

    cfg_path = ws / "control" / "config.json"
    corrupt = b"{ this is not valid json "
    cfg_path.write_bytes(corrupt)

    r2 = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert r2.returncode != 0                                   # fail-clear
    assert "config.json" in (r2.stdout + r2.stderr)             # offending path named
    assert cfg_path.read_bytes() == corrupt                     # byte-for-byte unchanged


def test_scaffold_commit_excludes_stray_files(tmp_workspace, run_script):
    """D-02 / git-staging scope: a stray user file is not swept into the scaffold commit."""
    ws = tmp_workspace
    stray = ws / "notes.txt"
    stray.write_text("my private notes\n")

    res = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert res.returncode == 0, res.stderr

    committed = subprocess.run(
        ["git", "log", "-1", "--name-only", "--pretty=format:"],
        cwd=ws, capture_output=True, text=True,
    ).stdout
    assert "notes.txt" not in committed          # never `git add -A`

    status = subprocess.run(
        ["git", "status", "--porcelain", "--", "notes.txt"],
        cwd=ws, capture_output=True, text=True,
    ).stdout
    assert status.startswith("??")               # stray file stays untracked
