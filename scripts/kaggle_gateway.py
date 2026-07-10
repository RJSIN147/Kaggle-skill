#!/usr/bin/env python3
"""kaggle_gateway.py — the single Kaggle CLI gateway (D-16).

Every Phase 2 entry point (``capture_competition.py`` / ``download_data.py`` /
``analyze_data.py``) routes its ``kaggle`` CLI calls through THIS module. It
generalises Phase 1's ``check_credentials.run_kaggle_list()`` so the
subprocess / no-echo / timeout / exit-code contract lives in exactly ONE place,
and it owns the UI-gate (403) classification (D-11 / D-12) plus the reserved
gate exit codes that ``SKILL.md`` and downstream plans branch on.

Contract inherited from Phase 1 (do NOT fork — generalise):
  * captured stdout+stderr is NEVER echoed — a token-shaped string can ride on
    either stream (CLI 2.2.3 prints auth guidance to stdout); T-01-02 / T-02-LEAK.
    Remediation is derived by MATCHING; the raw text is quarantined to a
    gitignored ``control/raw/last-error.txt`` (D-11), never the terminal;
  * every call is timeout-bounded — a stalled off-allowlist egress (the
    documented proxy-CONNECT stall) maps to a fixed, secret-free
    ``(124, "kaggle timed out")``, never the partial captured output;
  * decisions are exit-code-only; a missing CLI degrades to ``127`` (D-07),
    never a crash.

Portability + safety: stdlib-only, self-locating (``Path(__file__)``), and
import-safe — this is a LIBRARY (no argparse ``main``); importing it has no side
effects. It never derives an executed path / command / URL from competition text
(D-02): the only variable in a gate URL is the ``slug``, which comes from
``control/config.json`` + argv, never from Kaggle prose.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- #
# Reserved exit codes (D-10, §17) — sysexits.h-aligned. SKILL.md branches on the
# EXACT values; downstream plan 02-02 imports LIMIT_NEEDS_USER.
#   77 = EX_NOPERM  ("did not have sufficient permission") — the 403 UI gate.
#   78 = EX_CONFIG  ("configuration error") — submission-limit extraction failed
#        → the SKILL must ask the user (D-13 step 2).
# 124 is ALREADY the TimeoutExpired code (GNU-timeout convention) — do NOT reuse;
# 126/127/128+ are bash-reserved — never used for app signals.
# --------------------------------------------------------------------------- #
UI_GATE = 77
LIMIT_NEEDS_USER = 78

# Human-facing UI-gate URL for phone verification (framework constant, D-02).
_PHONE_URL = "https://www.kaggle.com/settings/phone"


def _rules_url(slug: str) -> str:
    """The competition rules-acceptance page for ``slug`` (framework-built, D-02).

    The slug is the only variable and it originates from config/argv — never from
    competition text — so no executed/printed URL is derived from Kaggle prose.
    """
    return f"https://www.kaggle.com/competitions/{slug}/rules"


# --------------------------------------------------------------------------- #
# The gateway: one timeout-bounded, no-echo runner for any kaggle subcommand.
# --------------------------------------------------------------------------- #
def run_kaggle(*argv: str, timeout: int = 60) -> tuple[int, str]:
    """Run ``kaggle <argv>``; return ``(returncode, combined_stdout_stderr)``.

    Generalises ``check_credentials.run_kaggle_list()`` — only the argv was
    hardcoded there. BOTH streams are captured to buffers (never inherited to the
    terminal); the combined text is used ONLY for exit-code decisions + signature
    matching and is NEVER printed by this gateway (it can embed a token-shaped
    string).

      * ``kaggle`` absent from PATH → ``(127, "kaggle CLI not found on PATH")``
        (D-07 degrade — the caller never crashes on a missing CLI).
      * ``TimeoutExpired``          → ``(124, "kaggle timed out")`` — a fixed,
        secret-free marker (never the partial captured output carried on the
        exception). An off-allowlist proxy-CONNECT stall is the EXPECTED shape.
      * otherwise                   → ``(returncode, stdout + "\n" + stderr)``.
    """
    if shutil.which("kaggle") is None:
        return 127, "kaggle CLI not found on PATH"
    try:
        proc = subprocess.run(
            ["kaggle", *argv],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, "kaggle timed out"
    return proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")


# --------------------------------------------------------------------------- #
# Cheap rules-gate preflight (D-10) — a single `list --search`, no busy-loop.
# --------------------------------------------------------------------------- #
def _parse_json_array(text: str):
    """Parse a JSON array from CLI output, tolerating a leading banner line.

    CLI 2.2.3 **pretty-prints** the array across MANY lines (VERIFIED-LIVE: a
    ``competitions list --search titanic --format json`` result is 162 lines,
    ``[`` … ``]``), so a last-line-only parse fails on the closing ``]``. Parse the
    WHOLE payload; if that fails because a banner precedes the array, retry from the
    first ``[``. Returns the list, or ``None`` when no JSON array can be recovered.
    """
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        if start == -1:
            return None
        try:
            parsed = json.loads(text[start:])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, list) else None


def preflight_entered(slug: str) -> bool | None:
    """Return the exact-slug ``userHasEntered`` flag: ``True`` | ``False`` | ``None``.

    A single cheap ``competitions list --search <slug> --format json`` — it never
    403s on an un-entered competition and never busy-loops (D-10; this is the
    fail-safe alternative to a poll). ``--search`` is FUZZY (a "titanic" search
    also returns "spaceship-titanic"), so match the EXACT slug via
    ``ref.rsplit('/', 1)[-1]`` and NEVER trust ``rows[0]``.

      * ``True``  — the exact-slug row reports ``userHasEntered == true``.
      * ``False`` — the exact-slug row reports ``userHasEntered == false`` (the
        positively-classifiable rules gate).
      * ``None``  — indeterminate: non-zero rc, empty/unparseable output, wrong
        JSON shape, or the exact slug is absent from a fuzzy result. Callers MUST
        fail closed on ``None`` (D-12).
    """
    rc, out = run_kaggle("competitions", "list", "--search", slug, "--format", "json")
    if rc != 0:
        return None
    stripped = out.strip()
    if not stripped:
        return None
    # CLI 2.2.3 PRETTY-PRINTS the array across many lines (VERIFIED-LIVE), so a
    # last-line-only parse would fail on the closing ``]`` and wrongly return None
    # for EVERY slug — defeating the whole rules-gate classifier. Parse the full
    # payload (banner-tolerant) instead.
    rows = _parse_json_array(stripped)
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("ref", "")).rsplit("/", 1)[-1] == slug:
            return bool(row.get("userHasEntered"))
    return None


# --------------------------------------------------------------------------- #
# Gate classification (D-11 + D-12) — mirrors branch_remediation: MATCH, never
# echo. classify_gate + dump_last_error together ARE D-11's posture: classify →
# author our own framework-written, secret-free message → quarantine the raw CLI
# output to control/raw/ (never the terminal).
# --------------------------------------------------------------------------- #
def classify_gate(combined: str, slug: str) -> str:
    """Return a framework-authored, secret-free message for a 403 / gate response.

    ``combined`` (captured stdout+stderr) is accepted for interface parity with
    ``check_credentials.branch_remediation`` and MUST NEVER be echoed — a
    token-shaped string can ride on it (T-02-LEAK). Classification is POSITIVE
    for the rules gate ONLY, via the cheap ``userHasEntered`` preflight:

      * preflight ``False`` → the rules gate is positively identified: name the
        rules URL and instruct the one-time browser acceptance.
      * preflight ``True`` or ``None`` → the download 403 is GENERIC and cannot be
        attributed to a specific gate (VERIFIED-LIVE, RESEARCH §5): FAIL CLOSED
        (D-12) — name BOTH the rules URL and the phone-verification URL, state
        plainly the gate could not be classified, and note it may instead be a
        genuine permission error. NEVER pattern-match "phone" out of the 403.

    The raw ``combined`` is meant to be quarantined by :func:`dump_last_error` —
    this function only returns the safe message.
    """
    rules_url = _rules_url(slug)
    entered = preflight_entered(slug)
    if entered is False:
        return (
            f"Kaggle refused this request and the preflight probe shows you have "
            f"NOT accepted the competition rules for '{slug}'. Open {rules_url} in "
            "a browser, accept the rules, then re-run — the preflight probe is the "
            "verification (nothing polls or waits in-script)."
        )
    # entered is True or None → the 403 is unclassifiable. Fail closed (D-12):
    # name BOTH gates, do not guess.
    return (
        f"Kaggle returned a gate/permission error for '{slug}' that could NOT be "
        "classified from the CLI output (the 403 is generic — it does not name a "
        "gate). Clear whichever UI-only gate applies in a browser, then re-run:\n"
        f"  - competition rules not accepted: {rules_url}\n"
        f"  - phone verification required:    {_PHONE_URL}\n"
        "If neither applies, this may be a genuine permission error (a private or "
        "restricted competition you cannot access). The raw CLI output was withheld "
        "to avoid leaking a secret and quarantined to control/raw/last-error.txt."
    )


# --------------------------------------------------------------------------- #
# Transient-error quarantine (D-11) — write the raw buffer to a GITIGNORED file
# and retrofit the ignore line into an existing workspace's create-if-absent
# .gitignore (line-level append-if-absent — editing gitignore.tmpl alone does NOT
# retrofit an already-scaffolded workspace).
# --------------------------------------------------------------------------- #
LAST_ERROR_REL = "control/raw/last-error.txt"


def _append_line_if_absent(path: Path, line: str) -> bool:
    """Append ``line`` to ``path`` iff no equal (stripped) line already exists.

    Line-level analog of ``init_workspace.create_if_absent`` (which is whole-file
    granular). Idempotent: a re-run never duplicates the entry. Creates the file
    (and parents) when absent. Returns ``True`` iff the file was modified.
    """
    existing: list[str] = []
    if path.exists():
        existing = path.read_text().splitlines()
        if any(e.strip() == line for e in existing):
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = ("\n".join(existing) + "\n") if existing else ""
    path.write_text(prefix + line + "\n")
    return True


def dump_last_error(ws: Path, combined: str) -> Path:
    """Quarantine the raw CLI ``combined`` to ``ws/control/raw/last-error.txt`` (D-11).

    Ensures the transient dump is GITIGNORED BEFORE writing the (possibly
    token-shaped) content: the ignore line ``control/raw/last-error.txt`` is
    appended to ``ws/.gitignore`` if absent — retrofitting an existing workspace
    whose create-if-absent ``.gitignore`` predates this pattern. Provenance JSON
    under ``control/raw/`` stays TRACKED (D-03); only this ``.txt`` dump is
    ignored. Returns the path written.
    """
    _append_line_if_absent(ws / ".gitignore", LAST_ERROR_REL)
    dump_path = ws / LAST_ERROR_REL
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    dump_path.write_text(combined)
    return dump_path
