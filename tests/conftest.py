"""Shared fixtures: a hermetic environment, a fake Kaggle adapter, workspaces.

Unit tests never reach Kaggle: every command takes the adapter as an argument,
and ``FakeAdapter`` answers from recorded fixtures (the spike-001 competition
facts, stripped of prose) and scripted kernel behaviour.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
KX_DIR = REPO_ROOT / "src" / "kx"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _base_env(extra_env=None, home: Path | None = None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("KAGGLE")}
    env.update({
        "GIT_AUTHOR_NAME": "Test User", "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test User", "GIT_COMMITTER_EMAIL": "test@example.com",
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
    })
    if home is not None:
        env["HOME"] = str(home)
        env["XDG_CONFIG_HOME"] = str(home / ".config")
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    return env


@pytest.fixture(autouse=True)
def hermetic(tmp_path_factory, monkeypatch):
    """No test may see the developer's real Kaggle credential or git identity."""
    home = tmp_path_factory.mktemp("home")
    for k in list(os.environ):
        if k.startswith("KAGGLE"):
            monkeypatch.delenv(k)
    for k, v in _base_env(home=home).items():
        monkeypatch.setenv(k, v)
    return home


@pytest.fixture
def run_script():
    """Run a standalone module from src/kx as a subprocess (e.g. the leak hook)."""

    def _run(script_name, *args, cwd=None, extra_env=None):
        cmd = [sys.executable, str(KX_DIR / script_name), *[str(a) for a in args]]
        return subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                              text=True, env=_base_env(extra_env))

    return _run


class GitRepo:
    def __init__(self, path):
        self.path = Path(path)
        subprocess.run(["git", "init", "-q"], cwd=self.path, check=True, env=_base_env())

    def stage(self, filename, content):
        p = self.path / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content) if isinstance(content, bytes) else p.write_text(content)
        subprocess.run(["git", "add", filename], cwd=self.path, check=True, env=_base_env())
        return p


@pytest.fixture
def git_repo(tmp_path):
    return GitRepo(tmp_path)


# --------------------------------------------------------------------------- #
# Fake Kaggle
# --------------------------------------------------------------------------- #
def competition_fixture(slug: str) -> dict:
    return json.loads((FIXTURES / "competitions" / f"{slug}.json").read_text())


class FakeAdapter:
    """Same method names as KaggleAdapter; records every call."""

    def __init__(self, username="tester", comp_slug="titanic"):
        self.username = username
        self.calls: list[tuple] = []
        self.raw = competition_fixture(comp_slug)
        self.push_response = {"version_number": 1, "error": None}
        self.kernel_meta = {"current_version_number": 1, "is_private": True,
                            "enable_internet": False,
                            "docker_image": "gcr.io/kaggle-images/python@sha256:abc",
                            "machine_shape": None}
        self.statuses = ["RUNNING", "COMPLETE"]
        self.outputs: dict[str, bytes] = {}
        self.log = json.dumps([{"stream_name": "stdout", "time": 1.0, "data": "ok\n"}])
        self.valid = True

    def load(self):
        return self

    def validate(self):
        self.calls.append(("validate",))
        if not self.valid:
            from kx.adapter import CredentialUnavailable
            raise CredentialUnavailable("bad")
        return self.username

    def competition(self, slug):
        self.calls.append(("competition", slug))
        return self.raw["competition"]

    def files_summary(self, slug):
        self.calls.append(("files_summary", slug))
        return self.raw["files_summary"]

    def list_tree(self, slug, path=None):
        self.calls.append(("list_tree", slug, path))
        if path is None:
            return {"files": self.raw["tree_root"].get("files", []),
                    "directories": self.raw["tree_root"].get("directories", [])}
        listing = (self.raw.get("tree_depth1") or {}).get(path, {"files": []})
        if "error" in listing:
            from kx.util import KxError
            raise KxError("needs_user", "403", errors=["http_403:list_data_tree_files"])
        return {"files": [{"name": n} for n in listing.get("files", [])], "directories": []}

    def push(self, meta, code_text, timeout_s=None):
        self.calls.append(("push", meta, timeout_s))
        return dict(self.push_response)

    def get_kernel(self, owner, slug):
        self.calls.append(("get_kernel", owner, slug))
        return dict(self.kernel_meta)

    def kernel_status(self, owner, slug):
        self.calls.append(("kernel_status", owner, slug))
        s = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return {"status": s, "failure_message": None}

    def list_output(self, owner, slug):
        self.calls.append(("list_output", owner, slug))
        return {"files": [{"file_name": n, "url": f"fake://{n}"} for n in self.outputs],
                "log": self.log}

    def download(self, url, dest, timeout=600):
        name = url.split("fake://", 1)[1]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.outputs[name])
        return len(self.outputs[name])

    def pushed(self):
        return [c for c in self.calls if c[0] == "push"]


@pytest.fixture
def fake():
    return FakeAdapter()


def kx(ws: Path, adapter, *argv) -> dict:
    """Dispatch one kx command in-process and return its envelope."""
    from kx.cli import dispatch

    return dispatch([str(a) for a in argv], ws, adapter)


@pytest.fixture
def token_home(hermetic):
    """A HOME holding a fabricated access_token (mode 600)."""
    d = hermetic / ".kaggle"
    d.mkdir(exist_ok=True)
    tok = d / "access_token"
    tok.write_text("KGAT_" + "f" * 28 + "9z9z")
    tok.chmod(0o600)
    return hermetic


@pytest.fixture
def ready_ws(tmp_path, token_home, fake):
    """A workspace that is initialised, synced (titanic), confirmed, with a metric."""
    ws = tmp_path / "ws"
    assert kx(ws, fake, "init", "titanic")["status"] == "ok"
    assert kx(ws, fake, "sync")["status"] == "ok"
    assert kx(ws, fake, "confirm", "--note", "test")["status"] == "ok"
    assert kx(ws, fake, "metric", "accuracy")["status"] == "ok"
    return ws
