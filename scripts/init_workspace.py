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
import os
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
      * ``sandbox.failIfUnavailable`` is forced from the template (fail-closed:
        the sandbox refuses to run unsandboxed when socat/bubblewrap are absent,
        mitigating T-01-09 natively rather than by an advisory warning alone);
      * ``sandbox.network.allowedDomains`` is UNIONED with the template's hosts
        (pre-existing/extra domains preserved, required hosts added, de-duped);
      * ``permissions.allow`` is UNIONED with the template's entries;
      * every other user key (e.g. an unrelated ``env`` block) is left untouched.

    A slot whose value is the wrong type (not a dict/list where one is expected)
    is replaced with the correct container so the allowlist is never silently
    skipped; the required hosts are always installed. Mutates and returns
    ``current``.
    """
    tmpl_sandbox = template.get("sandbox", {})
    tmpl_domains = tmpl_sandbox.get("network", {}).get("allowedDomains", [])
    sandbox = current.get("sandbox")
    if not isinstance(sandbox, dict):
        sandbox = {}
        current["sandbox"] = sandbox
    sandbox["enabled"] = True
    # Fail-closed hardening: force the template's failIfUnavailable so a merged
    # (pre-existing) settings.json also refuses to silently degrade to unsandboxed.
    if "failIfUnavailable" in tmpl_sandbox:
        sandbox["failIfUnavailable"] = tmpl_sandbox["failIfUnavailable"]
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
    ``socat``. When either is absent, Claude Code WARNS and (by default) falls
    back to running commands UNSANDBOXED — so ``sandbox.network.allowedDomains``
    is INERT and egress is unenforced. The scaffolded settings.json sets
    ``sandbox.failIfUnavailable: true`` (fail-closed), which converts that
    fallback into a HARD FAILURE instead of a silent degrade, so a missing socat
    surfaces loudly rather than leaving egress quietly open. Detect via
    ``shutil.which`` and instruct — NEVER auto-install (D-03, CLAUDE.md §What NOT
    to Use). Returns True when socat is present.
    (See https://code.claude.com/docs/en/sandboxing.md.)
    """
    if shutil.which("socat") is not None:
        return True
    print(
        "warning: `socat` is not installed. The egress allowlist in "
        ".claude/settings.json (sandbox.network.allowedDomains) is INERT until "
        "socat is present. Claude Code will WARN and, without the fail-closed "
        "guard, fall back to running commands UNSANDBOXED (egress NOT enforced); "
        "the scaffolded `sandbox.failIfUnavailable: true` instead makes sandboxed "
        "commands FAIL until socat is installed. Install it (with consent):\n"
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


def _git(ws: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git subcommand inside ``ws`` (captured, text)."""
    return subprocess.run(
        ["git", *args],
        cwd=str(ws),
        capture_output=True,
        text=True,
        check=check,
    )


def _git_init_main(ws: Path) -> None:
    """``git init`` on branch ``main``, portably.

    Prefer ``git init -b main``; fall back for an older git that lacks ``-b`` by
    running plain ``git init`` then pointing HEAD at ``refs/heads/main`` before the
    first commit (so the default ``master`` is never left behind).
    """
    result = subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=str(ws),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return
    _git(ws, "init")
    _git(ws, "symbolic-ref", "HEAD", "refs/heads/main")


def _install_leak_hook(ws: Path) -> None:
    """Copy ``leak_scan.py`` -> ``.githooks/pre-commit`` (0755) and set core.hooksPath.

    Commit-after-hook-install (D-15): the guard is in place BEFORE the scaffold
    commit, so the baseline commit is itself scanned. The hook body IS the copied
    scanner (self-contained ``git show :<path>`` staged-content scan).
    """
    hooks_dir = ws / ".githooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "pre-commit"
    shutil.copyfile(LEAK_SCANNER, hook)
    hook.chmod(0o755)
    _git(ws, "config", "core.hooksPath", ".githooks")


def _ensure_git_identity(ws: Path) -> None:
    """Set a repo-local git identity only if none resolves, so the commit can't fail.

    Real use inherits the user's global identity; a bare CI/test env may have none.
    A repo-local default is harmless — ``GIT_AUTHOR_*`` / ``GIT_COMMITTER_*`` env
    vars still take precedence for authorship when present.
    """
    email = _git(ws, "config", "user.email", check=False).stdout.strip()
    env_identity = os.environ.get("GIT_COMMITTER_EMAIL") or os.environ.get(
        "GIT_AUTHOR_EMAIL"
    )
    if not email and not env_identity:
        _git(ws, "config", "user.email", "kaggle-exp@localhost")
        _git(ws, "config", "user.name", "kaggle-exp")


def _scaffold_commit_exists(ws: Path) -> bool:
    """True iff a prior ``chore: scaffold workspace`` commit already exists."""
    result = _git(
        ws,
        "log",
        "--all",
        f"--grep={SCAFFOLD_COMMIT_MESSAGE}",
        "--fixed-strings",
        "--pretty=format:%H",
        check=False,
    )
    return bool(result.stdout.strip())


def _stage_scaffold_paths(ws: Path) -> None:
    """``git add --`` ONLY the scaffold-owned paths that exist (never ``git add -A``).

    Staging an explicit path list is the second HIGH-confirmed fix: a stray user
    file present before init must not be swept into the scaffold commit. Gitignored
    paths (e.g. a present ``.env``) are refused by ``git add`` and simply skipped.
    """
    present = [rel for rel in SCAFFOLD_COMMIT_PATHS if (ws / rel).exists()]
    if not present:
        return
    _git(ws, "add", "--", *present)


def _has_staged_changes(ws: Path) -> bool:
    """True iff there is anything staged to commit."""
    return _git(ws, "diff", "--cached", "--quiet", check=False).returncode != 0


def git_init_and_commit(ws: Path) -> None:
    """Init the workspace repo, install the leak guard, make the scaffold commit.

    Idempotent and scaffold-scoped (SETUP-01, D-15):
      * ``git init`` is skipped when ``.git`` already exists (D-02);
      * the leak-guard hook is (re)installed BEFORE any commit;
      * the ``chore: scaffold workspace`` commit is made ONLY when no prior scaffold
        commit exists AND there is something staged — so a re-run never creates a
        second scaffold commit and never sweeps the user's later edits into one.
    """
    if not (ws / ".git").exists():
        _git_init_main(ws)

    _install_leak_hook(ws)
    _ensure_git_identity(ws)

    # Re-run guard: a prior scaffold commit means init already ran here. Do not
    # stage or re-commit (would risk sweeping the user's subsequent edits into a
    # duplicate scaffold commit).
    if _scaffold_commit_exists(ws):
        return

    _stage_scaffold_paths(ws)
    if _has_staged_changes(ws):
        # Runs the just-installed pre-commit leak guard against the baseline.
        _git(ws, "commit", "-m", SCAFFOLD_COMMIT_MESSAGE)


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


def set_config_field(config_path: Path, key_path: tuple[str, ...], value) -> int:
    """Direct read-mutate-write setter for ONE config.json leaf (the general setter).

    This is the write mechanism the Phase-2 machine fields need: ``write_control_json``
    → ``deep_merge_add_missing`` only ADDS absent keys, so a key that already exists
    as ``null`` (``cv.scheme``, ``submission.daily_limit``, ``competition.type`` —
    all reserved by the template) can NEVER be filled by the merge. This setter
    overwrites the leaf directly: it walks ``key_path``, creating any missing
    intermediate dicts, and sets the final key to ``value``.

    Same fail-clear posture as before (D-02): a missing ``config.json`` prints an
    error and returns non-zero with NO write; malformed JSON is left untouched
    byte-for-byte (MalformedControlJSON posture) and returns non-zero. Returns 0 on
    success. Enum validation stays at the argparse ``choices`` boundary in every
    caller, so a non-enum value is rejected before any write — the AI never
    hand-writes a field; it passes a validated flag and tooling writes.
    """
    dotted = ".".join(key_path)
    if not config_path.exists():
        print(
            f"cannot set {dotted}: no {config_path} — run init first.",
            file=sys.stderr,
        )
        return 1
    try:
        cfg = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        print(
            f"cannot set {dotted}: {config_path.name} is not valid JSON and was "
            f"left untouched (fail-clear, D-02): {exc}.",
            file=sys.stderr,
        )
        return 1

    node = cfg
    for key in key_path[:-1]:
        child = node.get(key)
        if not isinstance(child, dict):
            child = {}
            node[key] = child
        node = child
    node[key_path[-1]] = value

    config_path.write_text(json.dumps(cfg, indent=2) + "\n")
    return 0


def set_execution_target(config_path: Path, target: str) -> int:
    """SETUP-02 setter: overwrite ``execution_target`` — a thin enum-validated wrapper.

    No longer *the* overwrite path — it is *an* explicit, enum-validated wrapper over
    the general :func:`set_config_field`. The enum is validated by argparse
    ``choices`` (a non-enum value is rejected before we get here, with no write).
    Only the Phase-1 GLOBAL default is owned here; per-experiment override is
    Phase 3 (out of scope). ``set_config_field`` supplies the identical fail-clear
    semantics (missing/corrupt config.json → error + non-zero, no write).
    """
    rc = set_config_field(config_path, ("execution_target",), target)
    if rc == 0:
        print(f"execution_target set to {target}")
    return rc


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
