"""Shared pytest fixtures for the kaggle-exp Wave 0 (RED) suite.

These tests pin the behavioral contract that plans 01-02/03/04 turn GREEN. The
loop scripts (``init_workspace.py``, ``check_credentials.py``, ``leak_scan.py``)
do NOT exist yet, so every test here is expected to FAIL (RED) now.

Design notes:
- Scripts are exercised as SUBPROCESSES via ``run_script`` (the documented
  ``python3 scripts/<name>.py --workspace <dir>`` invocation contract), never
  imported at module top level — so collection never crashes on a missing
  module (clean assertion/exit-code failures instead of collection aborts).
- ``scripts/`` is inserted on ``sys.path`` so a test MAY import a script module
  directly once it exists; today that path is empty and unused.
- Credential subprocesses run with ``KAGGLE_*`` stripped from the inherited
  environment (hermetic) unless a test injects them via ``extra_env``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Allow a test to `import init_workspace` etc. once the module exists.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Credential env vars that must never leak from the developer's shell into a
# unit-test subprocess. Tests inject their own values via `extra_env`.
_KAGGLE_ENV_KEYS = ("KAGGLE_USERNAME", "KAGGLE_KEY", "KAGGLE_API_TOKEN")


def _base_env(extra_env=None):
    """A hermetic subprocess environment: real PATH + git identity, no creds."""
    env = dict(os.environ)
    for k in _KAGGLE_ENV_KEYS:
        env.pop(k, None)
    env.update(
        {
            "GIT_AUTHOR_NAME": "Test User",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test User",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            # keep git from reading the developer's ~/.gitconfig
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
        }
    )
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    return env


@pytest.fixture
def run_script():
    """Run a loop script as a subprocess and return the CompletedProcess.

    Usage: ``run_script("init_workspace.py", "--workspace", ws, "--slug", "x", cwd=ws)``
    Scripts self-locate, so the absolute script path is used; the venv Python
    (``sys.executable``) runs them (they are stdlib-only, D-14).
    """

    def _run(script_name, *args, cwd=None, extra_env=None):
        cmd = [sys.executable, str(SCRIPTS_DIR / script_name), *[str(a) for a in args]]
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            env=_base_env(extra_env),
        )

    return _run


@pytest.fixture
def tmp_workspace(tmp_path):
    """A fresh, empty workspace directory."""
    return tmp_path


@pytest.fixture
def seeded_workspace(tmp_path):
    """A minimal, already-scaffolded workspace control-plane.

    Lets credential tests exercise ``check_credentials.py`` in isolation without
    depending on ``init_workspace.py`` (built in a different plan). Schema matches
    the D-10 control-plane contract in 01-01-PLAN.md.
    """
    ws = tmp_path
    ctrl = ws / "control"
    ctrl.mkdir()
    (ctrl / "config.json").write_text(
        json.dumps(
            {
                "workspace_version": 1,
                "competition_slug": "titanic",
                "execution_target": "local",
                "cv": {"scheme": None},
                # Phase-2 reserved-null machine fields (matches init_workspace.py
                # output after Phase 2). They exist as `null` BEFORE capture runs —
                # the exact shape that exposes the write_control_json merge-skip
                # blocker: a value can only LAND via the direct set_config_field
                # setter, never via the add-missing-only deep merge. Additive, so
                # the Phase 1 credential tests are unaffected.
                "submission": {"daily_limit": None, "limit_provenance": None},
                "competition": {"type": None},
                "created": "2026-01-01T00:00:00Z",
            }
        )
    )
    (ctrl / "state.json").write_text(
        json.dumps({"credentials": "UNVALIDATED", "next_exp_id": 1})
    )
    (ctrl / "ledger.jsonl").write_text("")
    (ws / ".env").write_text("KAGGLE_USERNAME=\nKAGGLE_KEY=\n")
    return ws


class GitRepo:
    """A throwaway git repo for leak-scan / commit-scope tests."""

    def __init__(self, path):
        self.path = Path(path)
        subprocess.run(
            ["git", "init", "-q"], cwd=self.path, check=True, env=_base_env()
        )

    def stage(self, filename, content):
        """Write ``content`` to ``filename`` and ``git add`` it. Returns the path."""
        p = self.path / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content)
        subprocess.run(
            ["git", "add", filename], cwd=self.path, check=True, env=_base_env()
        )
        return p


@pytest.fixture
def git_repo(tmp_path):
    """A fresh, initialized git repo rooted at ``tmp_path``."""
    return GitRepo(tmp_path)


@pytest.fixture
def clean_kaggle_env(monkeypatch):
    """Strip KAGGLE_* from the in-process env (defense for import-based tests)."""
    for k in _KAGGLE_ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch
