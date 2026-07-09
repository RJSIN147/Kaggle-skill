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

Guardrails added in plan 01-03 (this file now owns them):
  * ``git init -b main`` (portable fallback) + the idempotent, scaffold-scoped
    ``chore: scaffold workspace`` commit,
  * the pre-commit credential-leak guard (``leak_scan.py`` copied to
    ``.githooks/pre-commit``, wired via ``core.hooksPath``),
  * the egress allowlist DEEP-MERGE into ``.claude/settings.json`` (D-08/D-09) —
    unions the required hosts into any existing settings, fail-clear on a corrupt
    one, and warns (never installs) when ``socat`` is missing so the operator
    knows sandbox egress is inert until it is present.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATES = SCRIPT_DIR / "templates"
LEAK_SCANNER = SCRIPT_DIR / "leak_scan.py"

EXECUTION_TARGETS = ("local", "kernel")

# Scaffold-owned paths staged for the initial commit (D-02 / git-staging scope):
# ONLY these are `git add --`'d — never `git add -A` — so a stray user file is
# never swept into the scaffold commit. `.env` is deliberately absent (secret,
# gitignored). Paths are workspace-relative; missing/ignored ones are skipped.
SCAFFOLD_COMMIT_PATHS = (
    "control/config.json",
    "control/state.json",
    "control/ledger.jsonl",
    "competition.md",
    "strategy.md",
    "README.md",
    ".gitignore",
    ".claude/settings.json",
    "pyproject.toml",
    ".githooks/pre-commit",
)

SCAFFOLD_COMMIT_MESSAGE = "chore: scaffold workspace"

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


def _union_list(base: list, additions) -> list:
    """Return ``base`` with each of ``additions`` appended iff not already present.

    Order-preserving, de-duplicating union: the user's existing entries stay first
    and in place; the required entries are added only when missing (D-09 UNION).
    """
    result = list(base)
    seen = set(result)
    for item in additions:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def merge_settings(current: dict, template: dict) -> dict:
    """Deep-merge the egress allowlist into an existing settings dict (D-09).

    Idempotent and non-destructive:
      * ``sandbox.enabled`` is forced True (set if missing/false);
      * ``sandbox.network.allowedDomains`` is UNIONED with the template's hosts
        (pre-existing/extra domains preserved, required hosts added, de-duped);
      * ``permissions.allow`` is UNIONED with the template's entries;
      * every other user key (e.g. an unrelated ``env`` block) is left untouched.

    A slot whose value is the wrong type (not a dict/list where one is expected)
    is replaced with the correct container so the allowlist is never silently
    skipped; the required hosts are always installed. Mutates and returns
    ``current``.
    """
    tmpl_domains = (
        template.get("sandbox", {}).get("network", {}).get("allowedDomains", [])
    )
    sandbox = current.get("sandbox")
    if not isinstance(sandbox, dict):
        sandbox = {}
        current["sandbox"] = sandbox
    sandbox["enabled"] = True
    network = sandbox.get("network")
    if not isinstance(network, dict):
        network = {}
        sandbox["network"] = network
    existing_domains = network.get("allowedDomains")
    if not isinstance(existing_domains, list):
        existing_domains = []
    network["allowedDomains"] = _union_list(existing_domains, tmpl_domains)

    tmpl_allow = template.get("permissions", {}).get("allow", [])
    permissions = current.get("permissions")
    if not isinstance(permissions, dict):
        permissions = {}
        current["permissions"] = permissions
    existing_allow = permissions.get("allow")
    if not isinstance(existing_allow, list):
        existing_allow = []
    permissions["allow"] = _union_list(existing_allow, tmpl_allow)

    return current


def write_settings_json(path: Path, template: dict) -> str:
    """Create-or-deep-merge the workspace ``.claude/settings.json`` (D-08/D-09).

    * absent            -> write the egress ``template`` verbatim.
    * present & valid   -> deep-merge the allowlist in (``merge_settings``),
                           preserving all user keys; write back.
    * present & corrupt -> raise ``MalformedControlJSON`` (fail-clear; bytes
                           intact) — the SAME guarantee the control-plane JSON
                           gets in 01-02, so a broken settings file is never
                           clobbered.
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(template, indent=2) + "\n")
        return "create"

    raw = path.read_text()
    try:
        current = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MalformedControlJSON(path, exc) from exc

    merge_settings(current, template)
    path.write_text(json.dumps(current, indent=2) + "\n")
    return "merge"


def warn_if_socat_missing() -> bool:
    """Detect ``socat`` and, on absence, print the consent-based install command.

    On Linux the Claude Code sandbox network proxy needs both ``bubblewrap`` AND
    ``socat``; without ``socat`` the sandbox silently degrades to unsandboxed and
    ``sandbox.network.allowedDomains`` is INERT (egress unenforced). Detect via
    ``shutil.which`` and instruct — NEVER auto-install (D-03, CLAUDE.md §What NOT
    to Use). Returns True when socat is present.
    """
    if shutil.which("socat") is not None:
        return True
    print(
        "warning: `socat` is not installed. The egress allowlist in "
        ".claude/settings.json (sandbox.network.allowedDomains) is INERT until "
        "socat is present — the sandbox silently falls back to UNSANDBOXED and "
        "network egress is NOT enforced. Install it (with consent):\n"
        "    sudo apt-get install socat\n"
        "This scaffolder will NOT install it for you.",
        file=sys.stderr,
    )
    return False


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

    # Egress allowlist (D-08/D-09): create-or-deep-merge the real
    # sandbox.network.allowedDomains into .claude/settings.json (NOT create-if-
    # absent — an existing settings.json is topped up, never skipped; a corrupt
    # one fails clear via MalformedControlJSON).
    settings_tmpl = json.loads((TEMPLATES / "settings.json.tmpl").read_text())
    write_settings_json(ws / ".claude" / "settings.json", settings_tmpl)

    # Workspace directories.
    for d in WORKSPACE_DIRS:
        (ws / d).mkdir(parents=True, exist_ok=True)

    # git init + leak guard + idempotent scaffold-scoped commit (SETUP-01, D-15).
    git_init_and_commit(ws)

    # Surface the socat gap so the operator knows egress is unenforced until it is
    # installed — consent-based instruction, never a silent install.
    warn_if_socat_missing()

    return 0


def git_init_and_commit(ws: Path) -> None:
    """Placeholder — implemented in Task 2 (git init + leak guard + commit)."""
    return None


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
