#!/usr/bin/env python3
"""submissions_log.py — the ONE source of the control/submissions.jsonl schema.

The direct structural twin of ``experiment_meta.py`` (which owns the meta.json ⇄
ledger.jsonl schema). ``check_submission.py``, ``submit.py``, ``fetch_lb.py`` and
``regen_strategy.py`` all import THIS module, so the row schema, the Kaggle
status/score parse, the daily-budget count and the canonical-file I/O live in exactly
one place — never re-derived per caller.

``control/submissions.jsonl`` is CANONICAL and git-tracked: ONE ROW PER SUBMISSION,
mutated in place as it transitions PENDING → SCORED | FAILED (RESEARCH R5 option (a)),
not an append-only event log. One row per submission is what the D-11 CV↔LB join and
the D-10 divergence alarm actually want, and the atomic full-rewrite that makes an
in-place transition crash-safe is already an established pattern here
(``rebuild_ledger._atomic_write``).

DELIBERATELY EXCLUDED from the row: ``cv_mean`` / ``cv_std``. They are joinable from
``ledger.jsonl`` on ``exp_id``; denormalizing them here would create exactly the second
source of truth D-11 exists to prevent (a stale copy silently disagreeing with the
ledger would then poison the CV→LB gap the whole phase is built to measure).

THE THREE PARSE TRAPS this module exists to contain (05-RESEARCH §R2, live-verified
against CLI 2.2.3 — a `competitions submissions --format json` row has exactly seven
keys: ref, fileName, date, description, status, publicScore, privateScore):

  1. ``status`` is the enum rendered FULLY-QUALIFIED (``"SubmissionStatus.COMPLETE"``).
     :func:`parse_status` is an ANCHORED regex, never a substring grep — an ERROR row
     whose free-text ``description`` merely contains the word COMPLETE must still
     classify FAILED. An unparseable value is ``None`` == TRANSIENT (retry), NEVER a
     false terminal.
  2. ``publicScore`` is a **STRING**, and ``""`` for every not-yet-scored row.
     :func:`parse_score` maps ``""`` to ``None`` — NEVER ``0.0``. A defensive
     ``float(x or 0)`` would record a fabricated LB score of 0.0, poisoning the CV→LB
     gap and firing a bogus divergence alarm. Numbers are tooling-written.
  3. ``date`` is a NAIVE ISO string with NO tz suffix. :func:`parse_utc` reads it as
     UTC (assumption **A1** — UNVERIFIED until the first real submission; 05-07 gates
     it behind a human-verify checkpoint). ⚠ Comparing it against the LOCAL wall clock
     silently miscounts the budget near midnight, so every clock is INJECTED: callers
     pass a tz-aware ``now_utc``. This module never reads a clock.

There is NO submission-quota command (``kaggle quota`` is GPU/TPU hours ONLY,
live-verified), so the daily budget is DERIVED by counting Kaggle's own authoritative
rows — see :func:`charged_today`, which FAILS CLOSED (``-1``) rather than guess.

Portability (CLAUDE.md §Stack Patterns): stdlib-only, importable, NO side effects on
import, NO ``main()`` — mirrors ``experiment_meta.py``. Importing it drags in no ML
stack. Every Kaggle call routes through ``kaggle_gateway.run_kaggle`` (D-16): this
module never shells out itself (it imports no process-spawning machinery — grep it) and
never echoes a raw CLI buffer.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from kaggle_gateway import _parse_json_array, run_kaggle  # noqa: E402

# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
# OUR terminal vocabulary — never Kaggle's raw literal (parse_status has already
# mapped COMPLETE → SCORED / ERROR → FAILED before a row is ever written).
SUB_STATUSES = ("PENDING", "SCORED", "FAILED")

# The exact, ORDERED key set of a control/submissions.jsonl row. The fixed order is
# load-bearing: it is what makes a full atomic rewrite BYTE-STABLE (same rationale as
# experiment_meta.LEDGER_ROW_KEYS).
SUBMISSION_ROW_KEYS = (
    "schema_version",
    "exp_id",
    "kaggle_ref",
    "competition_slug",
    "file",
    "file_sha256",
    "message",
    "submitted_at",
    "status",
    "public_score",
    "private_score",
    "scored_at",
    "override_reason",
    "error_description",
)

SCHEMA_VERSION = 1

# Keys that must additionally be non-empty for the row to be auditable: which
# experiment, which Kaggle submission, which competition, which file, when, and what
# state. The score keys are legitimately null on a PENDING row, so they are NOT here.
REQUIRED_NONEMPTY_KEYS = (
    "exp_id",
    "kaggle_ref",
    "competition_slug",
    "file",
    "submitted_at",
    "status",
)

SUBMISSIONS_REL = "control/submissions.jsonl"

# Kaggle-authored `description` text is UNTRUSTED. The correlation match is a STRICT
# ANCHORED regex (`^exp-\d{3}\b`): no filesystem path and no executed argv is ever
# derived from it (the scripts/untrusted.py posture). The trailing `\b` is what stops
# `exp-007` matching a prefix-colliding `exp-0071`.
def _exp_id_re(exp_id: str) -> re.Pattern:
    """An anchored matcher for one exact exp_id (``^exp-007\\b``)."""
    return re.compile(r"^" + re.escape(exp_id) + r"\b")


# --------------------------------------------------------------------------- #
# Parse — the three traps.
# --------------------------------------------------------------------------- #
# ANCHORED on the WHOLE value, tolerating both the `SubmissionStatus.NAME` render
# (the live one) and a bare `NAME` (mirrors poll_kernel._STATUS_RE's posture). Never a
# substring grep: a status field is classified from itself alone, so no free-text
# description embedding "COMPLETE" can ever produce a false terminal.
_SUB_STATUS_RE = re.compile(r"^(?:SubmissionStatus\.)?(PENDING|COMPLETE|ERROR)$")

# Kaggle's word → ours.
_TO_OURS = {"PENDING": "PENDING", "COMPLETE": "SCORED", "ERROR": "FAILED"}


def parse_status(raw) -> str | None:
    """Map a Kaggle ``status`` literal to ``PENDING`` | ``SCORED`` | ``FAILED``.

    ``None`` means UNPARSEABLE — the caller must treat it as TRANSIENT (retry) or FAIL
    CLOSED. It is NEVER a false terminal. An unknown-but-future Kaggle literal (say
    ``SubmissionStatus.QUARANTINED``) lands here deliberately: guessing would be worse
    than admitting we cannot classify it.
    """
    if not isinstance(raw, str):
        return None
    m = _SUB_STATUS_RE.match(raw.strip())
    if m is None:
        return None
    return _TO_OURS[m.group(1)]


def parse_score(raw) -> float | None:
    """Parse Kaggle's STRING ``publicScore`` / ``privateScore`` to a float, else ``None``.

    ``""`` (every not-yet-scored row) → ``None``, NEVER ``0.0``. A fabricated zero would
    be indistinguishable from a genuinely terrible score, poisoning the CV→LB gap and
    firing a bogus D-10 divergence alarm. A non-numeric string → ``None`` for the same
    reason: we do not invent a number we were not given.
    """
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_utc(raw) -> datetime | None:
    """Parse Kaggle's ``date`` into a tz-AWARE UTC datetime, else ``None``.

    Kaggle serializes ``date`` as a NAIVE ISO string with no tz suffix
    (``"2026-07-12T23:15:42.123000"``). We attach UTC deliberately — **assumption A1**,
    UNVERIFIED until the first real submission (05-07 gates it behind a human-verify
    checkpoint). An already-aware value (e.g. our own ``...Z`` ``submitted_at``) is
    converted to UTC rather than re-stamped.

    ``None`` on anything unparseable — the caller FAILS CLOSED rather than guess a day.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# --------------------------------------------------------------------------- #
# Row construction + validation (validate, never fabricate — experiment_meta posture).
# --------------------------------------------------------------------------- #
def file_sha256(path: Path) -> str:
    """``"sha256:" + hexdigest`` of ``path`` — the same format as
    ``record_experiment`` provenance.artifact_hash, so the two are comparable."""
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def new_row(
    *,
    exp_id: str,
    kaggle_ref,
    competition_slug: str,
    file: str,
    file_sha256: str,
    message: str,
    submitted_at: str,
    status: str = "PENDING",
    public_score: float | None = None,
    private_score: float | None = None,
    scored_at: str | None = None,
    override_reason: str | None = None,
    error_description: str | None = None,
) -> dict:
    """Build a row carrying EVERY key in ``SUBMISSION_ROW_KEYS``, in that exact order.

    Scores are PARSED FLOATS or ``None`` — never Kaggle's ``""`` string (numbers are
    tooling-written). Callers pass ``parse_score(...)`` output, not the raw field.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "exp_id": exp_id,
        "kaggle_ref": kaggle_ref,
        "competition_slug": competition_slug,
        "file": file,
        "file_sha256": file_sha256,
        "message": message,
        "submitted_at": submitted_at,
        "status": status,
        "public_score": public_score,
        "private_score": private_score,
        "scored_at": scored_at,
        "override_reason": override_reason,
        "error_description": error_description,
    }


def validate_row(row: dict) -> list[str]:
    """Return human-readable error strings; ``[]`` means well-formed.

    The CALLER decides to skip/block — a row that fails validation is NEVER fabricated
    into a plausible one (the ``experiment_meta.validate_meta`` contract).

    Checks: the row is an object; every one of the 14 schema keys is PRESENT; the
    auditable subset is non-empty; ``status`` is one of OUR ``SUB_STATUSES`` (Kaggle's
    raw ``"SubmissionStatus.COMPLETE"`` / bare ``"COMPLETE"`` is REFUSED — the parse
    belongs upstream, at :func:`parse_status`, never in the persisted row).
    """
    if not isinstance(row, dict):
        return [f"row must be a JSON object, got {type(row).__name__}"]

    errors: list[str] = []

    for key in SUBMISSION_ROW_KEYS:
        if key not in row:
            errors.append(f"missing required key: {key}")

    for key in REQUIRED_NONEMPTY_KEYS:
        if key in row and row[key] in (None, ""):
            errors.append(f"required key must not be empty: {key}")

    status = row.get("status")
    if status is not None and status not in SUB_STATUSES:
        errors.append(
            f"status must be one of {SUB_STATUSES}, got {status!r} "
            "(Kaggle's literal is mapped by parse_status before a row is written)"
        )

    return errors


# --------------------------------------------------------------------------- #
# Budget (SCORE-03, D-04 + D-13) — Kaggle-authoritative, UTC-safe, FAIL CLOSED.
# --------------------------------------------------------------------------- #
# The sentinel returned when the charged count CANNOT be established. It is not a
# count: callers MUST fail closed on it and never coerce it into arithmetic.
COUNT_UNAVAILABLE = -1


def charged_today(rows, now_utc: datetime) -> int:
    """Count TODAY's CHARGED submissions from Kaggle's own rows; ``-1`` if uncountable.

    ``rows`` are RAW Kaggle rows (``competitions submissions --format json``), never our
    own submissions.jsonl — Kaggle is the authority on what it charged us. ``now_utc``
    is INJECTED and must be tz-aware (``datetime(..., tzinfo=timezone.utc)``); this
    function never reads a clock. ⚠ Counting against a LOCAL clock silently miscounts
    near the day boundary — the confident-but-wrong failure this project fails closed
    against everywhere.

    THE FAIL-CLOSED CONTRACT: returns the ``-1`` sentinel for any row that could be TODAY's
    and cannot be accounted for. Cannot count => the caller MUST fail closed — never guess a
    count. Silently SKIPPING a today-dated row whose status the parser does not recognize
    (e.g. a FUTURE Kaggle status literal) would UNDERCOUNT the charged submissions and let
    the user spend past Kaggle's real daily limit.

    ⚠ THE DATE IS PARSED FIRST, AND THE ORDER IS LOAD-BEARING (WR-06). ``--page-size 200``
    returns the whole recent HISTORY, so a status-first parse meant that ONE old row with an
    unrecognized literal (a legacy value, a future enum) returned ``-1`` **permanently** —
    bricking the budget for that competition on every subsequent day, forever, with no
    escape that is not an override. The "skipping would UNDERCOUNT" rationale only ever held
    for rows that COULD be today's: a row whose DATE parses cleanly to a PAST day cannot
    change today's count no matter what its status says. Narrowing the trigger to the rows
    that can actually affect the answer keeps the fail-closed guarantee exactly where it
    protects a slot, and removes the permanent-brick mode.

      * a non-object row → ``-1`` immediately (the payload is not what we think it is)
      * unparseable date → ``-1`` immediately. An unknowable DAY is ALWAYS fatal — it might
        BE today. This is the boundary the narrowing must never cross.
      * a PAST/FUTURE day → skipped without ever consulting the status. It cannot be
        charged against today.
      * unparseable status ON A TODAY-DATED ROW → ``-1``. Still fatal: this row IS one of
        today's and we cannot tell whether Kaggle charged it.
      * ``FAILED``       → skip. D-13: Kaggle does NOT charge a processing-error submission,
        so the arithmetic comes free with no special-casing anywhere else. This is a KNOWN,
        PARSED status — the ONLY legitimate skip of a today-dated row.
      * otherwise        → counted. ``PENDING`` IS counted: the slot was accepted and is
        being scored.

    An empty list is a real, knowable ``0`` — not the sentinel.
    """
    today = now_utc.date()
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            return COUNT_UNAVAILABLE

        # DATE FIRST (WR-06). An unknowable day is always fatal; a knowable PAST day is
        # always irrelevant. Only what is left can affect today's count.
        ts = parse_utc(row.get("date"))
        if ts is None:
            return COUNT_UNAVAILABLE
        if ts.date() != today:
            continue

        status = parse_status(row.get("status"))
        if status is None:
            # An unrecognized literal on one of TODAY's rows: we cannot account for it.
            # FAIL CLOSED — skipping it would undercount the budget.
            return COUNT_UNAVAILABLE
        if status == "FAILED":
            continue  # D-13 — never charged.

        count += 1

    return count


def remaining_slots(daily_limit, charged) -> int | None:
    """Slots left today, or ``None`` when the answer is UNKNOWABLE (=> fail closed).

    ``None`` when ``daily_limit`` is unknown (the D-13 limit-extraction may have failed
    → exit 78) or when ``charged`` is the ``-1`` sentinel. A ``None`` here is never
    silently treated as "plenty left".
    """
    if daily_limit is None or charged is None or charged == COUNT_UNAVAILABLE:
        return None
    return max(0, int(daily_limit) - int(charged))


# --------------------------------------------------------------------------- #
# Kaggle read — through the gateway ONLY (D-16). Never a bare shell-out.
# --------------------------------------------------------------------------- #
def fetch_submissions(slug: str, timeout: int = 60) -> list | None:
    """Kaggle's authoritative submission list for ``slug``, or ``None`` (=> fail closed).

    ``None`` on any non-zero rc (the caller classifies — a 403 goes to
    ``classify_gate`` → exit 77) or on a payload that is not a JSON array. The raw
    buffer is PARSED, never printed: it can carry a token-shaped string (T-05-03-01).
    An EMPTY array is a real, knowable ``[]`` — never ``None`` (a brand-new competition
    the user simply has not submitted to yet must not fail closed).

    ``--page-size 200`` is the CLI maximum and one page always covers today (the sort is
    date-descending and daily limits are ≤ ~10). Pagination is NOT attempted:
    ``--page-token`` is functionally dead (the CLI discards ``next_page_token``).
    """
    rc, out = run_kaggle(
        "competitions", "submissions", slug, "--format", "json", "--page-size", "200",
        timeout=timeout,
    )
    if rc != 0:
        return None
    # The CLI PRETTY-PRINTS the array across many lines, so a last-line parse fails on
    # the closing `]`. The gateway's banner-tolerant whole-payload parse is the ONE
    # parser for this shape.
    rows = _parse_json_array(out)
    if not isinstance(rows, list):
        return None
    return rows


def find_by_exp_id(rows, exp_id: str, since: datetime | None = None) -> dict | None:
    """The NEWEST Kaggle row whose ``description`` announces ``exp_id``, else ``None``.

    Kaggle-returned text is UNTRUSTED (T-05-03-02), so the match is a STRICT ANCHORED
    regex ``^exp-\\d{3}\\b`` — never a substring test. ``\\b`` is what stops ``exp-007``
    matching a prefix-colliding ``exp-0071``. No filesystem path and no executed argv is
    EVER derived from this text.

    ``since`` (tz-aware) additionally requires the row to be at or after that instant,
    so a STALE row from an earlier submission of the SAME experiment cannot be mistaken
    for the read-back of the one just made.
    """
    matcher = _exp_id_re(exp_id)
    best: dict | None = None
    best_ts: datetime | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        description = row.get("description")
        if not isinstance(description, str) or matcher.match(description.strip()) is None:
            continue
        ts = parse_utc(row.get("date"))
        if ts is None:
            continue
        if since is not None and ts < since:
            continue
        if best_ts is None or ts > best_ts:
            best, best_ts = row, ts
    return best


# --------------------------------------------------------------------------- #
# File I/O — control/submissions.jsonl (canonical, git-tracked).
# --------------------------------------------------------------------------- #
def _path(ws: Path) -> Path:
    return Path(ws) / SUBMISSIONS_REL


def _render(rows) -> str:
    """One COMPACT JSON row per line, key order fixed => a byte-stable rewrite.

    A non-empty log is newline-terminated; an empty one is BYTE-EMPTY (never ``"[]"``,
    never a stray newline) — the ``rebuild_ledger`` render contract.
    """
    lines = [
        json.dumps({k: row.get(k) for k in SUBMISSION_ROW_KEYS}, separators=(",", ":"))
        for row in rows
    ]
    return ("\n".join(lines) + "\n") if lines else ""


def _atomic_write(path: Path, text: str) -> None:
    """Crash-safe overwrite: render to a sibling ``.tmp`` then ``os.replace``.

    Copied from ``rebuild_ledger._atomic_write``. The live submissions.jsonl is never
    partial-written; on a crash the previous file survives intact (T-05-03-06).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def read_rows(ws: Path) -> list[dict]:
    """Parse ``control/submissions.jsonl`` into row dicts (missing/empty → ``[]``).

    Fail-clear (``regen_strategy._read_ledger`` posture): a malformed line (e.g. a
    truncated final line from an interrupted write) is SKIPPED with a stderr warning,
    as is a non-object row — never an aborting traceback.
    """
    path = _path(ws)
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"submissions: skipping unparseable line: {exc}.", file=sys.stderr)
            continue
        if not isinstance(row, dict):
            print("submissions: skipping non-object line.", file=sys.stderr)
            continue
        rows.append(row)
    return rows


def write_rows(ws: Path, rows) -> None:
    """Rewrite the WHOLE log atomically (tempfile + ``os.replace``)."""
    _atomic_write(_path(ws), _render(rows))


def append_row(ws: Path, row: dict) -> None:
    """Append ONE row — the earlier lines' bytes are never rewritten."""
    path = _path(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(_render([row]))


def upsert_row(ws: Path, kaggle_ref, **updates) -> bool:
    """Update the row matching ``kaggle_ref`` in place; return whether one was found.

    This is the PENDING → SCORED | FAILED transition (RESEARCH R5 option (a)): load all
    rows, patch the matching one, rewrite the whole file ATOMICALLY. Keeping ONE ROW PER
    SUBMISSION — rather than appending a second event row — is what the D-11 CV↔LB join
    and the D-10 alarm actually want, and the atomic rewrite makes the mutation
    crash-safe. Unknown keys are refused: the schema is closed.
    """
    unknown = [k for k in updates if k not in SUBMISSION_ROW_KEYS]
    if unknown:
        raise KeyError(f"not submissions.jsonl schema keys: {sorted(unknown)}")

    rows = read_rows(ws)
    found = False
    for row in rows:
        if row.get("kaggle_ref") == kaggle_ref:
            row.update(updates)
            found = True
    if found:
        write_rows(ws, rows)
    return found
