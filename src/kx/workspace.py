"""Workspace layout, control-plane files and the git scaffold.

Layout (cwd = workspace):
  .gitignore  .githooks/pre-commit  README.md  strategy.md
  control/config.json  state.json  profile.json  ledger.jsonl  raw/ (ignored)
  experiments/exp-NNN/  experiment.json  train.py  kernel-metadata.json
                        kernel_run.json  meta.json  VERDICT.md  output/
"""

from __future__ import annotations

import re
import secrets
import shutil
from importlib import resources
from pathlib import Path
from string import Template

from kx import __version__
from kx.util import KxError, git, read_json, utc_now, write_json

WORKSPACE_VERSION = 2
EXP_RE = re.compile(r"^exp-\d{3,}$")


def template_text(rel: str) -> str:
    return resources.files("kx").joinpath("templates", rel).read_text()


def render(rel: str, **values) -> str:
    return Template(template_text(rel)).safe_substitute(**values)


def control(ws: Path) -> Path:
    return ws / "control"


def is_workspace(ws: Path) -> bool:
    return (control(ws) / "config.json").is_file()


def require_workspace(ws: Path) -> None:
    if not is_workspace(ws):
        raise KxError("invalid", "not a kx workspace (no control/config.json)",
                      errors=["not_a_workspace"],
                      next_action={"kind": "run", "command": "kx init"})
    cfg = read_json(control(ws) / "config.json", what="control/config.json")
    if cfg.get("workspace_version") != WORKSPACE_VERSION:
        raise KxError("invalid", "this workspace was made by kx v1; v2 does not migrate it",
                      errors=["workspace_version_mismatch"],
                      next_action={"kind": "ask_user",
                                   "instruction": "Start a fresh v2 workspace in a new empty folder."})


def load_config(ws: Path) -> dict:
    return read_json(control(ws) / "config.json", what="control/config.json")


def save_config(ws: Path, cfg: dict) -> None:
    write_json(control(ws) / "config.json", cfg)


def load_state(ws: Path) -> dict:
    return read_json(control(ws) / "state.json", what="control/state.json")


def save_state(ws: Path, state: dict) -> None:
    write_json(control(ws) / "state.json", state)


def load_profile(ws: Path) -> dict:
    p = control(ws) / "profile.json"
    if not p.exists():
        raise KxError("invalid", "no competition profile yet", errors=["missing:control/profile.json"],
                      next_action={"kind": "run", "command": "kx sync <competition>"})
    return read_json(p, what="control/profile.json")


def create_if_absent(path: Path, text: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return True


def _ensure_git_identity(ws: Path) -> None:
    if git(ws, "config", "user.email").returncode != 0:
        git(ws, "config", "user.email", "kx@localhost")
    if git(ws, "config", "user.name").returncode != 0:
        git(ws, "config", "user.name", "kx")


def scaffold(ws: Path) -> list[str]:
    """Create the workspace skeleton; never overwrites an existing file. Returns created paths."""
    created: list[str] = []
    ctrl = control(ws)
    for d in (ctrl, ctrl / "raw", ws / "experiments", ws / ".githooks"):
        d.mkdir(parents=True, exist_ok=True)
    if not (ctrl / "config.json").exists():
        write_json(ctrl / "config.json", {
            "workspace_version": WORKSPACE_VERSION,
            "workspace_id": secrets.token_hex(2),
            "kx_version": __version__,
            "created": utc_now(),
            "competition": None,
            "metric": None,
        })
        created.append("control/config.json")
    if not (ctrl / "state.json").exists():
        write_json(ctrl / "state.json", {"next_exp_id": 1, "credentials": {"status": "UNVALIDATED"}})
        created.append("control/state.json")
    for rel, text in (
        ("control/ledger.jsonl", ""),
        (".gitignore", template_text("gitignore.tmpl")),
        ("strategy.md", template_text("strategy.md.tmpl")),
        ("README.md", template_text("README.md.tmpl")),
    ):
        if create_if_absent(ws / rel, text):
            created.append(rel)
    hook = ws / ".githooks" / "pre-commit"
    if not hook.exists():
        shutil.copyfile(resources.files("kx").joinpath("leak_scan.py"), hook)
        hook.chmod(0o755)
        created.append(".githooks/pre-commit")
    if not (ws / ".git").exists():
        git(ws, "init", "-q")
    git(ws, "config", "core.hooksPath", ".githooks")
    _ensure_git_identity(ws)
    return created


def exp_dir(ws: Path, exp_id: str) -> Path:
    if not EXP_RE.match(exp_id or ""):
        raise KxError("invalid", f"bad experiment id {exp_id!r} (expected exp-NNN)",
                      errors=["bad_exp_id"])
    d = ws / "experiments" / exp_id
    if not d.is_dir():
        raise KxError("invalid", f"no such experiment: {exp_id}", errors=[f"missing:{exp_id}"],
                      next_action={"kind": "run", "command": "kx status"})
    return d


def list_experiments(ws: Path) -> list[str]:
    root = ws / "experiments"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and EXP_RE.match(p.name))


def mint_exp_id(ws: Path) -> str:
    state = load_state(ws)
    n = int(state.get("next_exp_id") or 1)
    existing = list_experiments(ws)
    while f"exp-{n:03d}" in existing:
        n += 1
    state["next_exp_id"] = n + 1
    save_state(ws, state)
    return f"exp-{n:03d}"
