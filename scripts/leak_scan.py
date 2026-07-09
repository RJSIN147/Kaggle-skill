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
staged path (``git -c core.quotePath=false diff --cached --name-only -z
--diff-filter=ACMR``) and read each staged blob via ``git show :<path>``, then
scan the full text. ``ACMR`` includes renames (matching the "renamed file"
rationale above); the destination path is a real index entry, so ``git show``
reads it.

FAIL CLOSED (CR-01): this is the last automated secret defense for any file not
covered by ``.gitignore``, so it must never treat its OWN failure as "clean":

  * paths are enumerated NUL-delimited with ``core.quotePath=false`` so a
    non-ASCII / space / newline filename is returned as its RAW bytes — git's
    default ``core.quotePath=true`` C-quotes such names (e.g. ``"caf\303\251.env"``),
    which is not a usable pathspec and silently skipped the blob (fail-open);
  * a non-zero return from the path enumeration OR from reading any staged blob
    raises ``SystemExit(1)`` (block the commit) — an error is NEVER "no secrets";
  * the ONLY exit-0 path is "every staged blob was read, scanned, and none matched".

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


def _fail_closed(message: str) -> None:
    """Block the commit on any scanner error — a failure is NEVER treated as clean."""
    print(
        f"[BLOCKED] {message} — refusing the commit (fail-closed). Fix the issue, "
        "or override a genuine false positive with `git commit --no-verify`.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def staged_files() -> list[str]:
    """Return the RAW staged paths (added/copied/modified/renamed) — fail closed on error.

    ``-z`` + ``core.quotePath=false`` yields NUL-delimited, UN-quoted paths, so a
    non-ASCII / space / newline filename round-trips as its real bytes (decoded
    with ``surrogateescape`` so it re-encodes byte-for-byte when handed back to
    ``git show``). A non-zero git return (e.g. not a repo, corrupt index) BLOCKS
    the commit rather than yielding an empty list that would exit 0 (fail-open).
    """
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false",
         "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"],
        capture_output=True,
    )
    if result.returncode != 0:
        _fail_closed("could not enumerate staged files from the git index")
    out = result.stdout.decode("utf-8", errors="surrogateescape")
    return [p for p in out.split("\0") if p]


def staged_blob(path: str) -> str:
    """Return the STAGED content of ``path`` (index version) as text — fail closed on error.

    ``path`` is a RAW pathspec from :func:`staged_files` passed as a distinct argv
    element (never shell-interpolated), so spaces/newlines/non-ASCII are literal.
    Bytes are decoded with ``errors='replace'`` so a binary / non-UTF-8 blob never
    crashes the scan (any embedded ASCII assignment is still matched). A blob that
    cannot be read (non-zero git return) BLOCKS the commit — an ACMR path we could
    not read is never silently skipped (deletes are excluded by the filter).
    """
    result = subprocess.run(["git", "show", f":{path}"], capture_output=True)
    if result.returncode != 0:
        _fail_closed(f"could not read the staged blob for {path!r}")
    return result.stdout.decode("utf-8", errors="replace")


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
