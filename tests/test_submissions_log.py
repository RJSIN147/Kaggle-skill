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
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "submissions"
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


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
# WR-04 — the schema contract must AGREE with the rows the schema's own sibling writes,
# and it must actually be ENFORCED.
#
# `validate_row` was defined, documented as the `experiment_meta.validate_meta` contract,
# and never invoked anywhere in scripts/. It was not merely dead — it DISAGREED with the
# code that writes rows: `REQUIRED_NONEMPTY_KEYS` demanded `exp_id` and `file`, but
# `fetch_lb._row_from_kaggle` legitimately writes BOTH as None for an out-of-band
# submission (Kaggle never returns the bytes it was sent, and a website submission carries
# no exp-NNN). So the validator, had it ever been wired up as written, would have REJECTED
# rows the schema owner's own sibling module deliberately produces.
#
# An unenforced, WRONG contract in the module that claims to own the schema is the worst of
# the three options. Fixed by doing both halves: relax the required set to the keys that
# are genuinely always knowable, and CALL it on the write path.
# --------------------------------------------------------------------------- #
def _reconciled_row():
    """The row `fetch_lb --reconcile` back-fills for a submission made out-of-band.

    exp_id is None (no `exp-NNN` in the description — it was made on the website), and
    file / file_sha256 are None because the local bytes are genuinely UNKNOWN. All three
    are CORRECT: a value we were never given is never invented.
    """
    return _row(exp_id=None, file=None, file_sha256=None, message="my website submission")


def test_the_schema_accepts_the_rows_reconcile_writes():
    """A reconciled row is WELL-FORMED. It was the CONTRACT that was wrong, not the row."""
    log = _log()

    assert log.validate_row(_reconciled_row()) == [], (
        "validate_row rejected a row fetch_lb._row_from_kaggle legitimately writes. An "
        "out-of-band submission has no exp_id and no local file: those are UNKNOWABLE, not "
        "malformed — and a schema that disagrees with its own writer is worse than none"
    )

    # The keys that are genuinely ALWAYS knowable are still demanded — this is a relaxation,
    # not a surrender. Kaggle always tells us which submission, for which competition, when,
    # and in what state.
    assert set(log.REQUIRED_NONEMPTY_KEYS) == {
        "kaggle_ref",
        "competition_slug",
        "submitted_at",
        "status",
    }
    for key in log.REQUIRED_NONEMPTY_KEYS:
        errs = log.validate_row(_reconciled_row() | {key: None})
        assert errs and any(key in e for e in errs), f"a null {key} must still be reported"


def test_the_write_path_actually_validates(tmp_workspace, capsys):
    """⚠ The contract is CALLED — but it WARNS, it never refuses. Both halves matter.

    A refusal here would be actively dangerous: `append_row` is called by submit.py AFTER
    the slot is irreversibly spent. Raising at that point would destroy the provenance of a
    submission that really happened — the exact "a crash mid-poll must never orphan a spent
    slot" failure the whole write-ordering design exists to prevent. So a malformed row is
    written AND loudly reported; the row is never silently swallowed, and never silently
    blessed either.
    """
    log = _log()
    ws = tmp_workspace

    # A well-formed row (and a legitimately reconciled one) says nothing at all.
    log.write_rows(ws, [_row(), _reconciled_row()])
    assert capsys.readouterr().err == "", "a valid row must not produce noise"

    # A row with NO kaggle_ref cannot be matched against Kaggle and would be invisible to
    # upsert_row's PENDING -> SCORED transition. It is REPORTED...
    log.append_row(ws, _row(exp_id="exp-009", kaggle_ref=None))
    err = capsys.readouterr().err
    assert "kaggle_ref" in err, (
        "validate_row must actually be CALLED on the write path — an unenforced schema "
        "contract is decoration"
    )

    # ...and STILL WRITTEN. Never lose the record of a slot that may have been spent.
    rows = log.read_rows(ws)
    assert [r["exp_id"] for r in rows] == ["exp-007", None, "exp-009"], (
        "a malformed row is reported, NOT dropped: submit.py appends AFTER the slot is "
        "spent, and a dropped row is a spent slot with no provenance at all"
    )


# --------------------------------------------------------------------------- #
# WR-01 — the `competitions submissions` argv has EXACTLY ONE HOME, and the
# namespace-binding footgun is GONE.
#
# This module's own docstring calls itself "the ONE source ... never re-derived per caller",
# yet the argv had been re-derived in FOUR places across three modules — and the copy that
# lived HERE (`fetch_submissions`) had ZERO callers and resolved `run_kaggle` from its OWN
# module globals. A caller who monkeypatched `run_kaggle` on the IMPORTING module would have
# been silently bypassed and the REAL Kaggle CLI would have shelled out from inside a
# supposedly-mocked test. Two independent plans hit that rake and each routed around it.
#
# A trap with no callers is not harmless: it is a loaded gun waiting for its first caller.
# It is deleted, and the argv it carried now lives in exactly one function that everyone
# calls.
# --------------------------------------------------------------------------- #
# The argv literal, in the exact live-verified shape (§R2), tolerant of formatting/quoting.
_SUBMISSIONS_ARGV_RE = re.compile(r"""["']competitions["']\s*,\s*["']submissions["']""")


def test_the_mis_binding_fetch_submissions_is_gone():
    """``submissions_log.fetch_submissions`` must NOT exist — it was the footgun.

    The injectable ``fetch_lb.read_submissions(..., runner=…)`` is the ONE reader. It takes
    the gateway as an ARGUMENT, so a caller's monkeypatched gateway is honoured rather than
    silently bypassed.
    """
    log = _log()
    assert not hasattr(log, "fetch_submissions"), (
        "submissions_log.fetch_submissions resolves run_kaggle from its OWN module globals: "
        "a caller who patches the gateway in THEIR namespace is bypassed and a REAL Kaggle "
        "call escapes from inside a mocked test. Use fetch_lb.read_submissions(runner=…)."
    )

    # It shells out for nothing now — the module imports no gateway at all.
    assert not hasattr(log, "run_kaggle"), (
        "the schema module must not hold a process-spawning reference: it OWNS the argv, it "
        "does not EXECUTE it"
    )


def test_the_submissions_argv_has_exactly_one_home():
    """The argv is CONSTRUCTED once, in the module that owns the schema, and imported.

    Four independent copies of ``("competitions", "submissions", slug, "--format", "json",
    "--page-size", "200")`` are four things to keep in sync — and the page-size / format
    flags are exactly the sort of detail that silently drifts in one copy and poisons a
    budget count.
    """
    log = _log()

    assert log.submissions_argv("titanic") == (
        "competitions", "submissions", "titanic",
        "--format", "json", "--page-size", "200",
    ), "the argv shape is live-verified (§R2): --page-size 200 is the CLI maximum"

    offenders = sorted(
        path.name
        for path in SCRIPTS.glob("*.py")
        if path.name != "submissions_log.py"
        and _SUBMISSIONS_ARGV_RE.search(path.read_text())
    )
    assert offenders == [], (
        f"{offenders} re-derive the `competitions submissions` argv. submissions_log.py is "
        "the ONE source of this command — import submissions_argv(slug) instead of building "
        "a second copy that can drift"
    )


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


def test_upsert_refuses_a_null_key(tmp_workspace):
    """⚠ WR-05 — ``upsert_row(ws, None)`` would transition EVERY None-keyed row at once.

    The match is ``row.get("kaggle_ref") == kaggle_ref``, so a ``None`` key matches every
    row that carries no ref — a MASS mis-transition that would stamp one submission's score
    across unrelated rows. There is no legitimate caller for it: a row with no ref cannot be
    matched against Kaggle at all. Refuse loudly rather than corrupt the canonical file.
    """
    log = _log()
    ws = tmp_workspace
    log.write_rows(ws, [_row(exp_id="exp-001", kaggle_ref=None),
                        _row(exp_id="exp-002", kaggle_ref=None)])

    before = (ws / "control" / "submissions.jsonl").read_bytes()
    with pytest.raises(ValueError, match="kaggle_ref"):
        log.upsert_row(ws, None, status="SCORED", public_score=0.9)

    assert (ws / "control" / "submissions.jsonl").read_bytes() == before, (
        "the canonical file must not be touched by a refused upsert"
    )
