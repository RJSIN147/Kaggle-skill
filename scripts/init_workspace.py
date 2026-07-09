#!/usr/bin/env python3
"""init_workspace.py — kaggle-exp workspace scaffolder (SETUP-01 / SETUP-02).

Self-locating, stdlib-only (D-14). Turns an empty (or partial) folder into the
D-10 workspace layout: a machine control-plane (``control/{config,state,ledger}``),
human doc stubs, a ``.env`` credential stub, and a minimal workspace
``pyproject.toml`` — all under idempotent safe-merge (D-02), so re-running repairs
a partial workspace without clobbering user edits.

Portability (CLAUDE.md §Stack Patterns): the script resolves its own directory via
``Path(__file__)`` for template access and takes an explicit ``--workspace`` path;
it never relies on ``${CLAUDE_SKILL_DIR}`` / ``${CLAUDE_PROJECT_DIR}``.

Ownership boundary — what plan 01-03 layers on top of this:
  * ``git init -b main`` + the ``chore: scaffold workspace`` commit,
  * the pre-commit credential-leak guard (``core.hooksPath``),
  * the egress allowlist DEEP-MERGE into ``.claude/settings.json`` (D-08/D-09).
This plan (01-02) only lays the *static* files. To keep the D-10 layout complete
for the layout contract, it also writes a create-if-absent ``.gitignore`` (final
D-12/D-13 content) and an EMPTY ``.claude/settings.json`` stub that 01-03
deep-merges the real allowlist into. Nothing here runs git or writes an egress
policy.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATES = SCRIPT_DIR / "templates"

EXECUTION_TARGETS = ("local", "kernel")

# (template filename, output path relative to the workspace). Text templates are
# create-if-absent (D-02): an existing file is never overwritten.
TEXT_TEMPLATES = (
    ("competition.md.tmpl", "competition.md"),
    ("strategy.md.tmpl", "strategy.md"),
    ("README.md.tmpl", "README.md"),
    ("env.tmpl", ".env"),
    ("pyproject.toml.tmpl", "pyproject.toml"),
    ("gitignore.tmpl", ".gitignore"),
)

# Directories that must exist in a scaffolded workspace (D-10).
WORKSPACE_DIRS = ("data", "experiments")


class MalformedControlJSON(Exception):
    """A control-plane JSON file exists but is not parseable.

    Raised to trigger a fail-clear exit (D-02): the corrupt file is preserved
    byte-for-byte for user repair and never silently overwritten.
    """

    def __init__(self, path: Path, exc: json.JSONDecodeError):
        self.path = path
        self.exc = exc
        super().__init__(f"{path}: {exc}")


def _iso_now() -> str:
    """UTC ISO-8601 timestamp (seconds precision, trailing Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _render_text(template_name: str, mapping: dict) -> str:
    """Read a text template and substitute ``$slug`` / ``$created`` placeholders.

    ``safe_substitute`` leaves any unrelated ``$`` tokens intact (templates that
    carry no placeholders — .env, pyproject, .gitignore — pass through unchanged).
    """
    raw = (TEMPLATES / template_name).read_text()
    return Template(raw).safe_substitute(mapping)


def create_if_absent(path: Path, content: str) -> str:
    """D-02 safe-merge for flat files: only create what is missing; never overwrite."""
    if path.exists():
        return "skip"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return "create"


def deep_merge_add_missing(base: dict, template: dict) -> bool:
    """Recursively add keys from ``template`` that are ABSENT in ``base``.

    Existing keys are never mutated — not even when the value type differs — so a
    hand-edited nested value (e.g. ``cv.scheme``) survives while a missing
    key/subkey is filled in. Returns True iff ``base`` was modified (D-02).
    """
    changed = False
    for key, tmpl_val in template.items():
        if key not in base:
            base[key] = tmpl_val
            changed = True
        elif isinstance(base[key], dict) and isinstance(tmpl_val, dict):
            if deep_merge_add_missing(base[key], tmpl_val):
                changed = True
    return changed


def write_control_json(path: Path, desired: dict) -> str:
    """Create-or-deep-merge a control-plane JSON file (config.json / state.json).

    * absent            -> write ``desired`` from the template.
    * present & valid   -> deep-merge: add missing keys only, preserve edits.
    * present & corrupt -> raise ``MalformedControlJSON`` (fail-clear; bytes intact).
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(desired, indent=2) + "\n")
        return "create"

    raw = path.read_text()
    try:
        current = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MalformedControlJSON(path, exc) from exc

    if deep_merge_add_missing(current, desired):
        path.write_text(json.dumps(current, indent=2) + "\n")
        return "merge"
    return "skip"


def _load_config_template(slug: str, execution_target: str, created: str) -> dict:
    cfg = json.loads((TEMPLATES / "config.json.tmpl").read_text())
    cfg["competition_slug"] = slug
    cfg["execution_target"] = execution_target
    cfg["created"] = created
    return cfg


def _existing_slug(config_path: Path):
    """Best-effort read of the recorded slug from an existing config.json.

    Returns the slug string, or None when the file is absent/malformed/lacks it.
    A malformed file is handled (fail-clear) by ``write_control_json`` later.
    """
    if not config_path.exists():
        return None
    try:
        return json.loads(config_path.read_text()).get("competition_slug")
    except json.JSONDecodeError:
        return None


def scaffold(ws: Path, slug: str, execution_target: str) -> int:
    """Create the D-10 layout under ``ws``. Assumes the slug gate has passed."""
    mapping = {"slug": slug, "created": _iso_now(), "execution_target": execution_target}

    # Control-plane JSON (create-or-deep-merge; fail-clear on corrupt).
    ctrl = ws / "control"
    write_control_json(ctrl / "config.json", _load_config_template(slug, execution_target, mapping["created"]))
    write_control_json(ctrl / "state.json", json.loads((TEMPLATES / "state.json.tmpl").read_text()))
    create_if_absent(ctrl / "ledger.jsonl", "")  # append-only; starts empty

    # Human docs + secrets/config surface (create-if-absent).
    for template_name, out_rel in TEXT_TEMPLATES:
        create_if_absent(ws / out_rel, _render_text(template_name, mapping))

    # Empty egress-settings stub so the D-10 layout is complete; 01-03 deep-merges
    # the real allowlist (D-08/D-09) into it. Minimal valid JSON, create-if-absent.
    create_if_absent(ws / ".claude" / "settings.json", "{}\n")

    # Workspace directories.
    for d in WORKSPACE_DIRS:
        (ws / d).mkdir(parents=True, exist_ok=True)

    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="init_workspace.py",
        description="Scaffold a kaggle-exp competition workspace (SETUP-01/02).",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    ap.add_argument("--slug",
                    help="Competition slug. REQUIRED on a fresh workspace (D-01).")
    ap.add_argument("--execution-target", choices=EXECUTION_TARGETS, default="local",
                    help="Execution target recorded at creation (default: local).")
    ap.add_argument("--set-execution-target", choices=EXECUTION_TARGETS, default=None,
                    help="Change the GLOBAL execution target on an existing workspace. "
                         "This is the ONLY path allowed to overwrite an existing value "
                         "(an explicit user change, distinct from safe-merge). Enum-validated.")
    return ap


def set_execution_target(config_path: Path, target: str) -> int:
    """SETUP-02 setter: overwrite ``execution_target`` on an existing config.json.

    This is the ONLY code path allowed to overwrite an existing value, and only
    the ``execution_target`` key — an explicit user-driven change, never triggered
    by the scaffold/deep-merge path. The enum is already validated by argparse
    ``choices`` (a non-enum value is rejected before we get here, with no write).
    Only the Phase-1 GLOBAL default is owned here; per-experiment override is
    Phase 3 (out of scope).
    """
    if not config_path.exists():
        print(
            f"cannot set execution target: no {config_path} — run init first.",
            file=sys.stderr,
        )
        return 1
    try:
        cfg = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        print(
            f"cannot set execution target: {config_path.name} is not valid JSON "
            f"and was left untouched (fail-clear): {exc}.",
            file=sys.stderr,
        )
        return 1
    cfg["execution_target"] = target
    config_path.write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"execution_target set to {target}")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()
    config_path = ws / "control" / "config.json"

    # Setter mode: change the global execution target on an existing workspace and
    # return. Runs BEFORE the slug gate (no --slug needed for a target change).
    if args.set_execution_target is not None:
        return set_execution_target(config_path, args.set_execution_target)

    is_fresh = not config_path.exists()

    # D-01 mechanical gate: a FRESH workspace refuses to create anything without a
    # slug. Enforced BEFORE any file/dir is written — nothing exists without the
    # slug answer from the guided flow.
    slug = args.slug
    if is_fresh and slug is None:
        print(
            "init refused: a competition --slug is required to scaffold a fresh "
            "workspace (D-01 guided-then-scaffold). Nothing was created. Re-run "
            "through the guided init flow, e.g. "
            "`python3 scripts/init_workspace.py --workspace . --slug <competition-slug>`.",
            file=sys.stderr,
        )
        return 2

    # Re-run/repair: slug may be omitted; read it from the existing config so
    # D-02 top-up keeps working.
    if slug is None:
        slug = _existing_slug(config_path)

    try:
        return scaffold(ws, slug, args.execution_target)
    except MalformedControlJSON as err:
        print(
            f"init refused: {err.path.name} is not valid JSON and was left "
            f"untouched (fail-clear, D-02): {err.exc}. Fix or remove "
            f"{err.path} and re-run.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
