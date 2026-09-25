"""Small shared helpers: atomic writes, fail-clear JSON reads, git, time."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


class KxError(Exception):
    """A refusal or failure that maps to one envelope.

    ``status`` is one of invalid / needs_user / error; ``errors`` are short,
    machine-readable strings that never carry secrets or server text.
    """

    def __init__(self, status: str, summary: str, *, errors=None, next_action=None, data=None,
                 quarantine: str | None = None):
        super().__init__(summary)
        self.status = status
        self.summary = summary
        self.errors = list(errors or [])
        self.next_action = next_action
        self.data = data or {}
        # Raw server text: written to control/raw/last-error.txt (gitignored), never printed.
        self.quarantine = quarantine


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_write(path: Path, text: str) -> None:
    """Crash-safe overwrite: write a sibling .tmp then os.replace it onto path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def write_json(path: Path, obj) -> None:
    atomic_write(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def read_json(path: Path, *, what: str | None = None):
    """Parse a control JSON file or raise KxError (never a raw traceback)."""
    label = what or path.name
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise KxError("invalid", f"{label} not found", errors=[f"missing:{label}"])
    except (OSError, json.JSONDecodeError):
        raise KxError("invalid", f"{label} is not valid JSON (left untouched)",
                      errors=[f"malformed:{label}"])


def git(ws: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run git in ws with output captured (never reaches kx's stdout)."""
    return subprocess.run(["git", *args], cwd=str(ws), capture_output=True, text=True, check=check)


def git_head(ws: Path) -> str:
    proc = git(ws, "rev-parse", "--short", "HEAD")
    return proc.stdout.strip() if proc.returncode == 0 else ""


def git_commit_paths(ws: Path, message: str, paths: list[str]) -> str | None:
    """Stage exactly the named existing paths and commit them. Returns the short
    sha, or None when nothing changed. Never a blanket ``git add``: the leak hook
    guards what is staged, and control/raw/ stays out."""
    if not (ws / ".git").exists():
        return None
    present = [p for p in paths if (ws / p).exists()]
    if not present:
        return None
    git(ws, "add", "--", *present)
    if git(ws, "diff", "--cached", "--quiet").returncode == 0:
        return None
    proc = git(ws, "commit", "-q", "-m", message)
    if proc.returncode != 0:
        raise KxError("error", "git commit failed (the leak guard may have blocked it)",
                      errors=["git_commit_failed"],
                      next_action={"kind": "ask_user",
                                   "instruction": "Inspect `git status` in the workspace; if the pre-commit "
                                                  "leak guard blocked a credential, remove it and re-run."})
    return git_head(ws)
