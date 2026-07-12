"""test_submissions_log.py — RED (Wave 0, 05-01-T2). Pins the ONE submissions.jsonl
schema module (SCORE-01/02). GREEN target: 05-03 Task 2 (`scripts/submissions_log.py`).

``submissions_log.py`` is the direct analogue of ``experiment_meta.py``: it owns the row
schema, the PENDING/SCORED/FAILED vocabulary, the Kaggle status-literal parse, and the
read / atomic-rewrite helpers — so all three entry points (``check_submission`` /
``submit`` / ``fetch_lb``) plus ``regen_strategy`` import ONE module and the schema lives
in exactly one place.

Pinned contract (05-RESEARCH.md §R2 / Pattern 2, live-verified against CLI 2.2.3):

  * ``parse_status(raw) -> "PENDING"|"SCORED"|"FAILED"|None`` — the CLI serializes the enum
    FULLY-QUALIFIED (``"SubmissionStatus.COMPLETE"``), so the parse is an ANCHORED regex,
    never a substring grep. An unparseable value is ``None`` (=> the caller treats it as
    TRANSIENT and fails closed) — NEVER a false terminal.
  * ``parse_score(raw) -> float | None`` — Kaggle gives ``publicScore`` as a **STRING**, and
    ``""`` for every not-yet-scored row. ``""`` MUST become ``None``, never ``0.0`` (a
    defensive ``float(x or 0)`` would poison the CV→LB gap with a fabricated zero).
  * ``SUBMISSION_ROW_KEYS`` — a fixed-ORDER 14-key tuple, so an atomic rewrite is byte-stable.
  * ``validate_row(row) -> list[str]`` — [] when well-formed; non-empty error strings otherwise.
  * ``write_rows`` / ``read_rows`` round-trip through ``control/submissions.jsonl``: one
    COMPACT (``separators=(",",":")``) row per line, newline-terminated, byte-empty when
    empty, and no ``.tmp`` residue (tempfile + ``os.replace``, per ``rebuild_ledger.py``).

The module does NOT exist yet — it is imported INSIDE each test body so collection never
crashes at RED (the conftest "never import a not-yet-built script at module top" rule).
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "submissions"


def _log():
    """Import scripts/submissions_log.py (on sys.path via conftest). Absent at RED."""
    return importlib.import_module("submissions_log")


def _fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _row(**over):
    """A well-formed submissions.jsonl row (all 14 keys)."""
    row = {
        "schema_version": 1,
        "exp_id": "exp-007",
        "kaggle_ref": 46780678,
        "competition_slug": "titanic",
        "file": "experiments/exp-007/submission.csv",
        "file_sha256": "sha256:9f2b" + "0" * 60,
        "message": "exp-007 | cv=0.841230",
        "submitted_at": "2026-07-12T14:03:11Z",
        "status": "PENDING",
        "public_score": None,
        "private_score": None,
        "scored_at": None,
        "override_reason": None,
        "error_description": None,
    }
    row.update(over)
    return row


# --------------------------------------------------------------------------- #
# parse_status — anchored, tolerant of BOTH renders, never a false terminal.
# --------------------------------------------------------------------------- #
def test_parse_status():
    log = _log()

    # The live literal is FULLY-QUALIFIED (VERIFIED against CLI 2.2.3).
    assert log.parse_status("SubmissionStatus.COMPLETE") == "SCORED"
    assert log.parse_status("SubmissionStatus.PENDING") == "PENDING"
    assert log.parse_status("SubmissionStatus.ERROR") == "FAILED"

    # The bare token is tolerated too (mirrors poll_kernel._STATUS_RE's posture).
    assert log.parse_status("COMPLETE") == "SCORED"
    assert log.parse_status("PENDING") == "PENDING"
    assert log.parse_status("ERROR") == "FAILED"

    # Unparseable => None (TRANSIENT), NEVER a false terminal.
    assert log.parse_status("connection reset by peer") is None
    assert log.parse_status("SubmissionStatus.SOMETHING_NEW") is None
    assert log.parse_status("") is None
    assert log.parse_status(None) is None
    assert log.parse_status(42) is None

    # The parse is ANCHORED, not a substring grep: an ERROR row whose DESCRIPTION merely
    # carries the word COMPLETE must still classify from its `status` field alone.
    err = _fixture("error")[0]
    assert "COMPLETE" in err["description"], "fixture must carry the substring trap"
    assert log.parse_status(err["status"]) == "FAILED"

    # The live-captured fixtures parse to the terminal vocabulary.
    assert log.parse_status(_fixture("complete")[0]["status"]) == "SCORED"
    assert log.parse_status(_fixture("pending")[0]["status"]) == "PENDING"

    assert set(log.SUB_STATUSES) == {"PENDING", "SCORED", "FAILED"}


# --------------------------------------------------------------------------- #
# parse_score — a STRING, and "" is NOT zero.
# --------------------------------------------------------------------------- #
def test_parse_score():
    log = _log()

    assert log.parse_score("0.77511") == 0.77511
    assert log.parse_score(_fixture("complete")[0]["publicScore"]) == 0.77511

    # THE trap: "" must be None, NEVER 0.0 (guards against a defensive `float(x or 0)`).
    unscored = _fixture("unscored")[0]["publicScore"]
    assert unscored == ""
    got = log.parse_score(unscored)
    assert got is None
    assert got != 0.0
    assert not isinstance(got, float)

    assert log.parse_score("") is None
    assert log.parse_score("   ") is None
    assert log.parse_score("abc") is None
    assert log.parse_score(None) is None


# --------------------------------------------------------------------------- #
# The row schema: a fixed-ORDER 14-key tuple; validate_row reports precise errors.
# --------------------------------------------------------------------------- #
def test_row_schema():
    log = _log()

    keys = log.SUBMISSION_ROW_KEYS
    assert isinstance(keys, tuple), "must be a TUPLE (fixed order => byte-stable rewrite)"
    assert keys == (
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
    assert len(keys) == 14

    # A well-formed row validates clean.
    assert log.validate_row(_row()) == []
    assert log.validate_row(_row(status="SCORED", public_score=0.77511)) == []
    assert log.validate_row(_row(status="FAILED")) == []

    # A missing required key is reported by NAME.
    missing = _row()
    del missing["exp_id"]
    errs = log.validate_row(missing)
    assert errs and any("exp_id" in e for e in errs)

    # An unknown status is refused (the vocabulary is PENDING/SCORED/FAILED — never
    # Kaggle's raw literal, which parse_status has already mapped).
    errs = log.validate_row(_row(status="SubmissionStatus.COMPLETE"))
    assert errs and any("status" in e.lower() for e in errs)
    errs = log.validate_row(_row(status="COMPLETE"))
    assert errs, "'COMPLETE' is Kaggle's word, not ours — the row vocabulary is SCORED"


# --------------------------------------------------------------------------- #
# Atomic, byte-stable rewrite through control/submissions.jsonl.
# --------------------------------------------------------------------------- #
def test_atomic_rewrite(tmp_workspace):
    log = _log()
    ws = tmp_workspace

    # An empty log is byte-EMPTY (never "[]", never a stray newline).
    log.write_rows(ws, [])
    path = ws / "control" / "submissions.jsonl"
    assert path.exists()
    assert path.read_bytes() == b""
    assert log.read_rows(ws) == []

    rows = [_row(exp_id="exp-001", kaggle_ref=1), _row(exp_id="exp-002", kaggle_ref=2)]
    log.write_rows(ws, rows)

    # Round-trips.
    assert log.read_rows(ws) == rows

    text = path.read_text()
    assert text.endswith("\n"), "JSONL must be newline-terminated"
    lines = text.splitlines()
    assert len(lines) == 2, "one row per line"
    for line, row in zip(lines, rows):
        # COMPACT separators + fixed key ORDER => a byte-stable rewrite.
        assert line == json.dumps(row, separators=(",", ":"))
        assert list(json.loads(line)) == list(log.SUBMISSION_ROW_KEYS)
        # Compact: no ", " / ": " pretty-print separators anywhere in the STRUCTURE.
        assert '", "' not in line and '": ' not in line

    # append_row extends without rewriting the earlier lines' bytes.
    before = path.read_text()
    log.append_row(ws, _row(exp_id="exp-003", kaggle_ref=3))
    after = path.read_text()
    assert after.startswith(before)
    assert len(log.read_rows(ws)) == 3

    # An in-place status transition (PENDING -> SCORED) rewrites atomically.
    kept = log.read_rows(ws)
    kept[0]["status"] = "SCORED"
    kept[0]["public_score"] = 0.77511
    kept[0]["scored_at"] = "2026-07-12T14:09:00Z"
    log.write_rows(ws, kept)
    assert log.read_rows(ws)[0]["status"] == "SCORED"

    # No .tmp residue survives any of it (tempfile + os.replace).
    assert list((ws / "control").glob("*.tmp")) == []
    assert list((ws / "control").glob("submissions.jsonl*")) == [path]
