#!/usr/bin/env python3
"""leak_scan.py — pre-commit credential-leak guard (SETUP-04, D-15).

Defense-in-depth companion to ``.gitignore``: a stdlib-only, portable pre-commit
hook that scans **staged CONTENT** for Kaggle credential patterns and blocks the
commit on a hit. It is both:

  * importable/runnable by ``tests/test_leak_scan.py`` (``python3 leak_scan.py``), and
  * the hook body itself — ``init_workspace.py`` copies this file verbatim to
    ``<workspace>/.githooks/pre-commit`` and wires it via
    ``git config core.hooksPath .githooks`` (so the copied hook already contains
    the ``git show :<path>`` scan).

Why staged CONTENT, not just the unified diff: a secret can hide in a renamed
file, a multiline blob, or a line the diff does not surface. We enumerate every
staged path (``git diff --cached --name-only --diff-filter=ACM``) and read each
staged blob via ``git show :<path>``, then scan the full text.

Patterns (stdlib ``re``) — pattern NAMES only are ever printed, never the value:
  * OAuth access/refresh tokens (``kag`` a/r ``t_…``),
  * legacy scoped tokens (``KGAT_…``),
  * Kaggle credential env assignments — export / quoted / spaced / lowercase
    variants are all caught (case-insensitive),
  * the legacy JSON credential field — a 32-hex value ONLY inside the ``"key":``
    context, so an unrelated 32-hex hash / commit SHA in other JSON fields does
    NOT false-positive.

Escape hatch for a genuine false positive: ``git commit --no-verify`` (documented
in references/egress-allowlist.md). The hook itself never bakes in a bypass.
"""

from __future__ import annotations

import re
import subprocess
import sys

# (name, compiled pattern). Names are printed on a hit; the secret value never is.
# Metacharacters are used deliberately so this file does not match ITSELF when the
# hook scans its own staged copy during the scaffold commit.
PATTERNS = [
    ("oauth-token", re.compile(r"\bkag(?:a|r)t_[A-Za-z0-9]+")),
    ("legacy-scoped-token", re.compile(r"\bKGAT_[A-Za-z0-9]+")),
    (
        "kaggle-env-assignment",
        re.compile(r"(?i)(?:export\s+)?KAGGLE_(?:KEY|API_TOKEN)\s*=\s*['\"]?\S"),
    ),
    ("kaggle-json-key", re.compile(r'"key"\s*:\s*"[0-9a-f]{32}"')),
]


def staged_files() -> list[str]:
    """Return the workspace-relative paths staged for commit (added/copied/modified)."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def staged_blob(path: str) -> str:
    """Return the STAGED content of ``path`` (index version) as text.

    Reads bytes and decodes with ``errors='ignore'`` so a binary-ish staged blob
    never crashes the scan. An unreadable path (e.g. a delete) yields ``""``.
    """
    result = subprocess.run(["git", "show", f":{path}"], capture_output=True)
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8", errors="ignore")


def scan_text(text: str) -> list[str]:
    """Return the NAMES of every pattern that matches ``text`` (secret never returned)."""
    return [name for name, pattern in PATTERNS if pattern.search(text)]


def scan_staged() -> list[str]:
    """Scan every staged blob; return the sorted set of matched pattern names."""
    hits: set[str] = set()
    for path in staged_files():
        hits.update(scan_text(staged_blob(path)))
    return sorted(hits)


def main(argv=None) -> int:
    hits = scan_staged()
    if hits:
        print(
            "[BLOCKED] possible Kaggle credential in staged content "
            f"(patterns: {', '.join(hits)}). Remove the secret before committing, "
            "or override a genuine false positive with `git commit --no-verify`.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
