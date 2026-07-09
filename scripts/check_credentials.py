#!/usr/bin/env python3
"""check_credentials.py — SETUP-03/04 Kaggle credential detect + validate.

Stdlib-only, self-locating (``Path(__file__)``), ``--workspace``-driven checker
that the SKILL runs as ``python3 scripts/check_credentials.py --workspace <dir>
[--yes]``. It:

  * detects which credential source the ``kaggle`` CLI would use, in CLI 2.x
    precedence order — ``~/.kaggle/access_token`` -> ``KAGGLE_API_TOKEN`` env ->
    ``KAGGLE_USERNAME``/``KAGGLE_KEY`` env -> ``~/.kaggle/kaggle.json`` — and
    reports the ACTIVE one (env beats a file; D-04 env-canonical);
  * reports the token TYPE and a MASKED value — a raw secret value is NEVER
    printed (``_mask`` + env-var-name-only output; T-01-02 / D-04);
  * consent-gates every mutation (D-03/D-06): without ``--yes`` a world/group
    readable ``kaggle.json`` chmod-600 self-heal and a ``.env`` population from a
    ``kaggle.json`` are only *reported/offered*, never applied;
  * validates LIVE by exit code (Task 2): ``kaggle competitions list`` exit 0 ->
    ``control/state.json.credentials=VALIDATED``; the captured subprocess
    stdout/stderr is buffered and NEVER surfaced raw (remediation is derived by
    matching, not echoing);
  * degrades safely when the CLI is absent (D-07): writes ``UNVALIDATED`` and
    prints ``uv pip install kaggle`` remediation instead of crashing.

SECURITY NOTE — credential FILES (``access_token`` / ``kaggle.json``) are detected
by EXISTENCE (and size/mode) only; their CONTENT is read solely under ``--yes``
(to populate ``.env``). Reading env vars is fine (the caller supplies them). This
keeps a plain check from ever reading a real secret file off disk.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


# --------------------------------------------------------------------------- #
# Masking + token-type (reimplemented independently; NOT imported from shepsci)
# --------------------------------------------------------------------------- #
def _mask(value: str, prefix: int = 0) -> str:
    """Return a masked secret: first ``prefix`` chars + stars + last 4.

    Never returns the raw value: a value short enough to be un-maskable collapses
    to ``****``. Callers print ONLY this (or an env-var name), never the raw secret.
    """
    if not value or len(value) <= prefix + 4:
        return "****"
    return value[:prefix] + "*" * (len(value) - prefix - 4) + value[-4:]


def _detect_token_type(tok: str) -> str:
    """Classify a Kaggle token by prefix/shape (no secret is returned)."""
    if tok.startswith("kagat_"):
        return "OAuth access token"
    if tok.startswith("kagrt_"):
        return "OAuth refresh token"
    if tok.startswith("KGAT_"):
        return "legacy scoped API token"
    if len(tok) == 32 and all(c in "0123456789abcdef" for c in tok.lower()):
        return "legacy API key (32-hex)"
    return "API token"


# --------------------------------------------------------------------------- #
# Source detection (existence-only for files; env reads allowed) — D-04
# --------------------------------------------------------------------------- #
def _home(env) -> Path:
    return Path(env.get("HOME") or Path.home())


def _access_token_path(home: Path) -> Path:
    return home / ".kaggle" / "access_token"


def _kaggle_json_path(home: Path) -> Path:
    return home / ".kaggle" / "kaggle.json"


def detect_source(home: Path, env) -> tuple[str, str | None]:
    """Return ``(source_id, active_env_value_or_None)`` in CLI 2.x precedence.

    Files are detected by existence + non-zero size ONLY (their bytes are never
    read here). The env-var VALUE is returned only for the two env sources, so
    the caller can report a masked token type without touching any file.
    """
    at = _access_token_path(home)
    if at.is_file() and at.stat().st_size > 0:
        return ("access_token", None)  # file content deliberately NOT read
    if env.get("KAGGLE_API_TOKEN"):
        return ("env_token", env["KAGGLE_API_TOKEN"])
    if env.get("KAGGLE_USERNAME") and env.get("KAGGLE_KEY"):
        return ("env_pair", env["KAGGLE_KEY"])
    if _kaggle_json_path(home).is_file():
        return ("kaggle_json", None)  # content read only under --yes (D-06b)
    return ("none", None)


# Each label states — accurately — whether THIS tool reads the credential value.
#   * access_token file: NEVER read by this tool (only the kaggle CLI reads it),
#     independent of --yes — so a fixed "not read" claim is always true.
#   * env sources: the value IS read into memory (to classify + mask it, printed
#     masked on the following line), never shown raw — so the label says so.
#   * kaggle.json: read-status DEPENDS on consent (see _kaggle_json_label) — the
#     content is read only under --yes (to populate .env); without --yes it is not
#     read at all. A fixed "not read" claim would be FALSE under --yes.
_SOURCE_LABELS = {
    "access_token": (
        "[credentials] source: access_token file (~/.kaggle/access_token) "
        "— value not read by this tool (security); the kaggle CLI reads + validates it."
    ),
    "env_token": (
        "[credentials] source: environment (KAGGLE_API_TOKEN) "
        "— env takes precedence over any kaggle.json (D-04); "
        "value read to classify + mask it, never shown raw."
    ),
    "env_pair": (
        "[credentials] source: environment (KAGGLE_USERNAME/KAGGLE_KEY) "
        "— env takes precedence over any kaggle.json (D-04); "
        "value read to classify + mask it, never shown raw."
    ),
    "none": "[credentials] source: NONE detected.",
}


def _kaggle_json_label(consent: bool) -> str:
    """kaggle.json source line — read-status is honest about the --yes consent gate.

    Without ``--yes`` the file content is never read (existence-only detection);
    with ``--yes`` it IS read to populate ``.env`` (never printed). A single fixed
    "value not read" line would assert something FALSE in the consent case.
    """
    if consent:
        return (
            "[credentials] source: kaggle.json (~/.kaggle/kaggle.json) "
            "— value read under your --yes consent (to populate the workspace .env); "
            "never printed."
        )
    return (
        "[credentials] source: kaggle.json (~/.kaggle/kaggle.json) "
        "— value not read (no --yes); re-run with --yes to populate .env from it."
    )


def report_source(source: str, active_value: str | None, consent: bool) -> None:
    if source == "kaggle_json":
        print(_kaggle_json_label(consent))
    else:
        print(_SOURCE_LABELS[source])
    if active_value:
        ttype = _detect_token_type(active_value)
        # NOTE: uses _mask(...) — output is masked; the raw value never appears.
        print(f"[credentials] token type: {ttype}; value {_mask(active_value)}")


# --------------------------------------------------------------------------- #
# Consent-gated fixes (D-03 / D-06) — reported without --yes, applied with it
# --------------------------------------------------------------------------- #
def handle_chmod(home: Path, consent: bool) -> None:
    """D-06a: a group/world-readable kaggle.json is chmod-600'd ONLY with consent.

    Without consent the fix is reported (mode is left untouched). Mode is read via
    ``stat`` only — the file's content is never read here.
    """
    kj = _kaggle_json_path(home)
    if not kj.is_file():
        return
    mode = stat.S_IMODE(kj.stat().st_mode)
    if mode == 0o600:
        return
    if consent:
        try:
            kj.chmod(0o600)
            print(f"[fix-applied] chmod 600 applied to ~/.kaggle/kaggle.json (was {oct(mode)}).")
        except OSError as exc:
            print(f"[warn] could not chmod ~/.kaggle/kaggle.json: {exc}")
    else:
        print(
            f"[proposed-fix] ~/.kaggle/kaggle.json mode is {oct(mode)} "
            f"(group/world-readable). Re-run with --yes to chmod 600, or run: chmod 600 {kj}"
        )


def _env_creds_present(env) -> bool:
    return bool(
        (env.get("KAGGLE_USERNAME") and env.get("KAGGLE_KEY"))
        or env.get("KAGGLE_API_TOKEN")
    )


def _populate_env_file(env_path: Path, username: str, secret: str) -> None:
    """Write KAGGLE_USERNAME/KAGGLE_KEY into ``.env`` (values go to the gitignored
    file, never to stdout). Existing non-Kaggle lines are preserved."""
    existing = env_path.read_text().splitlines() if env_path.exists() else []
    out: list[str] = []
    seen_user = seen_key = False
    for line in existing:
        if line.startswith("KAGGLE_USERNAME="):
            out.append("KAGGLE_USERNAME=" + username)
            seen_user = True
        elif line.startswith("KAGGLE_KEY="):
            out.append("KAGGLE_KEY=" + secret)
            seen_key = True
        else:
            out.append(line)
    if not seen_user:
        out.append("KAGGLE_USERNAME=" + username)
    if not seen_key:
        out.append("KAGGLE_KEY=" + secret)
    env_path.write_text("\n".join(out) + "\n")


def handle_env_population(ws: Path, home: Path, env, consent: bool) -> None:
    """D-06b: populate the workspace .env from a kaggle.json ONLY with consent.

    Without consent the fix is OFFERED based on kaggle.json EXISTENCE only — the
    file content is not read, and nothing is written. With consent the kaggle.json
    is read and the .env is populated (values go to the file, never to output).
    """
    kj = _kaggle_json_path(home)
    if not kj.is_file() or _env_creds_present(env):
        return
    env_path = ws / ".env"
    if not consent:
        print(
            "[offer] a kaggle.json is present but env vars / .env are unset. "
            f"Re-run with --yes to populate {env_path} from it (no secret shown)."
        )
        return
    try:
        data = json.loads(kj.read_text())
    except (json.JSONDecodeError, OSError):
        print("[warn] kaggle.json present but unreadable/invalid; not populating .env.")
        return
    username = data.get("username")
    secret = data.get("key")
    if not (username and secret):
        print("[warn] kaggle.json missing username/key; not populating .env.")
        return
    _populate_env_file(env_path, username, secret)
    print(
        f"[fix-applied] populated {env_path} (KAGGLE_USERNAME/KAGGLE_KEY) "
        "from kaggle.json — values written to the gitignored .env, not shown."
    )


def print_no_credentials_instructions() -> None:
    """D-06c: nothing set — instruct how to set env vars / fill .env (no secret)."""
    print("[action-needed] No Kaggle credential detected. Set the canonical env vars:")
    print("    export KAGGLE_USERNAME=<your-kaggle-username>")
    print("    export KAGGLE_KEY=<your-api-token>          # kaggle.com/settings -> Create/Generate token")
    print("  or fill the workspace .env with the same KAGGLE_USERNAME / KAGGLE_KEY, then re-run.")


# --------------------------------------------------------------------------- #
# state.json (D-07) — flip credentials VALIDATED|UNVALIDATED, preserve keys
# --------------------------------------------------------------------------- #
class MalformedStateJSON(Exception):
    """control/state.json exists but is not parseable — fail-clear (WR-02, D-02).

    Mirrors ``init_workspace.MalformedControlJSON``: a corrupt/partially-written
    state.json must NOT be silently rewritten, because that resets ``next_exp_id``
    to 1 (later phases derive ``exp-NNN`` dir names from it — a reset risks
    colliding with / overwriting existing experiment directories) and discards any
    other machine keys. The bytes are preserved and the caller exits non-zero.
    """

    def __init__(self, path: Path, exc: Exception):
        self.path = path
        self.exc = exc
        super().__init__(f"{path}: {exc}")


def write_credentials_state(ws: Path, status: str) -> None:
    """Flip ``credentials`` to ``status`` in control/state.json, preserving keys.

    Fail-clear (WR-02): if an existing state.json is unparseable (JSONDecodeError)
    or unreadable (OSError), raise ``MalformedStateJSON`` WITHOUT writing — the
    corrupt bytes are left intact and ``next_exp_id`` is never reset. A missing
    file is created fresh; a valid dict is topped up (credentials + a default
    next_exp_id) without clobbering existing keys.
    """
    state_path = ws / "control" / "state.json"
    data: dict = {}
    if state_path.exists():
        try:
            loaded = json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            raise MalformedStateJSON(state_path, exc) from exc
        if isinstance(loaded, dict):
            data = loaded
    data["credentials"] = status
    data.setdefault("next_exp_id", 1)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(data, indent=2) + "\n")


def print_install_remediation() -> None:
    print("[UNVALIDATED] kaggle CLI not found on PATH. Install it (with your consent):")
    print("    uv pip install kaggle")
    print(
        "  then re-run this check. (D-07: the workspace scaffold is unaffected; "
        "only credential-dependent ops — data download, submit — are blocked.)"
    )


# --------------------------------------------------------------------------- #
# Live validation (Task 2) — exit-code only; captured output NEVER surfaced raw
# --------------------------------------------------------------------------- #
def run_kaggle_list() -> tuple[int, str]:
    """Run ``kaggle competitions list``; return ``(returncode, combined_output)``.

    BOTH stdout and stderr are captured to buffers (never inherited to the
    terminal). The combined text is used ONLY for the exit-code decision + pattern
    matching; it is NEVER printed. It can embed a token-shaped string — CLI 2.2.3
    prints its auth guidance to STDOUT (see references/kaggle-cli-behavior.md) —
    so the caller derives secret-free remediation from matches only (T-01-02).

    Bounded by ``timeout=`` (WR-01): references/egress-allowlist.md documents that
    the sandbox denies off-allowlist egress by STALLING the proxy CONNECT until the
    client times out, so an indefinite hang is the EXPECTED failure shape here. A
    ``TimeoutExpired`` is mapped to a non-zero (UNVALIDATED) result with a fixed,
    secret-free marker; the partial captured output on the exception is NEVER
    surfaced (it could embed a token-shaped string).
    """
    try:
        proc = subprocess.run(
            ["kaggle", "competitions", "list"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        # 124 = conventional timeout exit code; the marker is fixed + secret-free
        # (never the captured partial stdout/stderr carried on the exception).
        return 124, "kaggle competitions list timed out"
    return proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")


def branch_remediation(combined: str, source: str) -> None:
    """Print secret-free remediation for a failed live call (four branches).

    ``combined`` (captured stdout+stderr) is MATCHED but NEVER echoed. Observed
    signatures — kaggle CLI 2.2.3, references/kaggle-cli-behavior.md:
      * auth failure -> exit 1 + 'Authentication required to call the Kaggle API'
        on stdout (stderr empty); an unauth'd request gets HTTP 401 server-side.
    The command-not-found branch is handled earlier by the ``shutil.which`` guard.
    """
    low = combined.lower()
    auth_fail = (
        "401" in combined
        or "403" in combined
        or "unauthorized" in low
        or "forbidden" in low
        or "authentication required" in low
    )
    readable = (
        "world-readable" in low
        or "group-readable" in low
        or "insecure" in low
        or "permission" in low
    )
    if readable:
        # Branch: missing chmod 600 (kaggle warns a credential file is readable).
        print(
            "[UNVALIDATED] kaggle reports your ~/.kaggle credential file is "
            "group/world-readable. Re-run with --yes to chmod 600, or run: "
            "chmod 600 ~/.kaggle/kaggle.json (or ~/.kaggle/access_token)."
        )
    elif source == "none":
        # Branch: wrong/missing env var (no credential detected at all).
        print(
            "[UNVALIDATED] no Kaggle credential detected. Set a token, e.g.: "
            "export KAGGLE_API_TOKEN=<token>  (or KAGGLE_USERNAME + KAGGLE_KEY, "
            "or save it to ~/.kaggle/access_token), then re-run."
        )
    elif auth_fail:
        # Branch: 401 / Unauthorized (a credential is present but rejected).
        print(
            "[UNVALIDATED] 401 / authentication rejected — the Kaggle token is "
            "invalid or expired. Regenerate one at kaggle.com/settings/api "
            '("Generate New Token") and re-run.'
        )
    else:
        # Fall-through: unknown non-zero exit (output withheld to avoid a leak).
        print(
            "[UNVALIDATED] kaggle validation failed (non-zero exit). The CLI's "
            "output is withheld to avoid leaking a secret; see "
            "references/kaggle-cli-behavior.md for observed failure signatures."
        )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def _parse_args(argv):
    ap = argparse.ArgumentParser(description="Detect + validate the Kaggle credential.")
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="workspace root holding control/state.json and .env")
    ap.add_argument("--yes", action="store_true",
                    help="consent to apply fixes (chmod 600, populate .env); "
                         "without it, fixes are only reported (D-03)")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    ws = args.workspace.resolve()
    consent = bool(args.yes)
    env = os.environ
    home = _home(env)

    source, active_value = detect_source(home, env)
    report_source(source, active_value, consent)

    handle_chmod(home, consent)
    handle_env_population(ws, home, env, consent)
    if source == "none":
        print_no_credentials_instructions()

    try:
        # Live validation guard (D-07): missing CLI degrades to UNVALIDATED, no crash.
        if shutil.which("kaggle") is None:
            write_credentials_state(ws, "UNVALIDATED")
            print_install_remediation()
            return 1

        # Live exit-code validation (SETUP-03): decide STRICTLY by exit code; the
        # captured CLI output is never surfaced raw (T-01-10 spoofing, T-01-02 leak).
        returncode, combined = run_kaggle_list()
        if returncode == 0:
            write_credentials_state(ws, "VALIDATED")
            print("[VALIDATED] kaggle credential works (kaggle competitions list exit 0).")
            return 0
        write_credentials_state(ws, "UNVALIDATED")
        branch_remediation(combined, source)
        return 1
    except MalformedStateJSON as err:
        # Fail-clear (WR-02, D-02): the corrupt state.json was NOT overwritten and
        # next_exp_id was NOT reset. Name the path and exit non-zero for repair.
        print(
            f"[BLOCKED] {err.path} is not valid JSON and was left untouched "
            f"(fail-clear, D-02): {err.exc}. The credential status was NOT written "
            "and next_exp_id was NOT reset. Fix or remove the file and re-run.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
