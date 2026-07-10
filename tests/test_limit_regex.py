"""Daily-submission-limit extraction (COMP-01, D-13) — regex → provenance.

Grounded on the LIVE titanic rules page (real limit = 10/day):
  * ``(\\d+)\\s+(?:entries|submissions)\\s+per\\s+day`` extracts ``10``  → provenance ``extracted``
  * the trap ``up to (\\d+) final`` (final-selection count = 5) is NOT the daily limit
  * extraction failure → the capture path signals ``LIMIT_NEEDS_USER`` (exit 78) so the
    SKILL asks the user (D-13 step 2); scripts never block on stdin.

Modules imported inside each test (RED-safe). GREEN target: Task 3 (capture_competition.py).
"""

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

_FILES_JSON = json.dumps(
    [
        {"name": "train.csv", "size": 61194, "creationDate": "2019-12-11T02:17:10Z"},
        {"name": "test.csv", "size": 28629, "creationDate": "2019-12-11T02:17:10Z"},
        {"name": "gender_submission.csv", "size": 3258, "creationDate": "2019-12-11T02:17:10Z"},
    ]
)


def _cap():
    import capture_competition  # noqa: PLC0415 — deferred import (RED-safe)

    return capture_competition


def _read_cfg(ws):
    return json.loads((ws / "control" / "config.json").read_text())


def _gateway_returning(pages_payload):
    """A fake run_kaggle: pages → ``pages_payload``, files → titanic manifest."""

    def _fake(*argv, timeout=60):
        if "pages" in argv:
            return 0, pages_payload
        if "files" in argv:
            return 0, _FILES_JSON
        return 1, "unexpected"

    return _fake


# --------------------------------------------------------------------------- #
# The mechanical extractor.
# --------------------------------------------------------------------------- #
def test_limit_extracted_from_titanic_rules():
    """The anchored ``per day`` regex extracts 10 from the (HTML) titanic rules."""
    cap = _cap()
    rules_html = (
        "<h2>Submissions</h2><p>You may submit a maximum of 10 entries per day.</p>"
    )
    assert cap.extract_daily_limit(rules_html) == 10


def test_final_selection_trap_not_matched():
    """``up to 5 final submissions for judging`` is NOT the daily limit (no 'per day')."""
    cap = _cap()
    trap = "<p>You may select up to 5 final submissions for judging.</p>"
    assert cap.extract_daily_limit(trap) is None


def test_boilerplate_without_digit_not_matched():
    """'…Submissions per day as specified on the Competition Website' has no digit → None."""
    cap = _cap()
    boiler = "<p>Submissions per day as specified on the Competition Website.</p>"
    assert cap.extract_daily_limit(boiler) is None


# --------------------------------------------------------------------------- #
# End-to-end provenance: extracted value LANDS with limit_provenance == extracted.
# --------------------------------------------------------------------------- #
def test_extracted_limit_lands_with_provenance(seeded_workspace, monkeypatch):
    """Full capture on the titanic fixture writes daily_limit=10, provenance=extracted."""
    cap = _cap()
    ws = seeded_workspace
    pages = (FIXTURES / "pages_all.json").read_text()
    monkeypatch.setattr(cap, "run_kaggle", _gateway_returning(pages))

    rc = cap.main(["--workspace", str(ws)])
    assert rc == 0, "extraction succeeds → clean exit (limit resolved)"

    cfg = _read_cfg(ws)
    assert cfg["submission"]["daily_limit"] == 10
    assert cfg["submission"]["limit_provenance"] == "extracted"


# --------------------------------------------------------------------------- #
# Extraction failure → LIMIT_NEEDS_USER (exit 78).
# --------------------------------------------------------------------------- #
def test_missing_limit_signals_needs_user(seeded_workspace, monkeypatch):
    """No 'per day' line anywhere → capture exits LIMIT_NEEDS_USER (78) to ask the user."""
    cap = _cap()
    ws = seeded_workspace
    no_limit_pages = json.dumps(
        [
            {"name": "Evaluation", "content": "<p>Accuracy is the metric.</p>"},
            {
                "name": "rules",
                "content": "<p>You may select up to 5 final submissions for judging.</p>",
            },
            {"name": "data-description", "content": "<p>train.csv and test.csv.</p>"},
        ]
    )
    monkeypatch.setattr(cap, "run_kaggle", _gateway_returning(no_limit_pages))

    rc = cap.main(["--workspace", str(ws)])
    assert rc == cap.LIMIT_NEEDS_USER == 78


def test_user_supplied_limit_overrides(seeded_workspace, monkeypatch):
    """--daily-limit N lands with provenance user-supplied (D-13 step 2)."""
    cap = _cap()
    ws = seeded_workspace
    no_limit_pages = json.dumps(
        [
            {"name": "Evaluation", "content": "<p>Accuracy is the metric.</p>"},
            {"name": "rules", "content": "<p>No machine-readable limit here.</p>"},
            {"name": "data-description", "content": "<p>train.csv and test.csv.</p>"},
        ]
    )
    monkeypatch.setattr(cap, "run_kaggle", _gateway_returning(no_limit_pages))

    rc = cap.main(["--workspace", str(ws), "--daily-limit", "7"])
    assert rc == 0
    cfg = _read_cfg(ws)
    assert cfg["submission"]["daily_limit"] == 7
    assert cfg["submission"]["limit_provenance"] == "user-supplied"


def test_assumed_default_limit(seeded_workspace, monkeypatch):
    """--assume-default-limit falls back to 5/day tagged assumed_default (D-13 step 3)."""
    cap = _cap()
    ws = seeded_workspace
    no_limit_pages = json.dumps(
        [
            {"name": "Evaluation", "content": "<p>Accuracy is the metric.</p>"},
            {"name": "rules", "content": "<p>No machine-readable limit here.</p>"},
            {"name": "data-description", "content": "<p>train.csv and test.csv.</p>"},
        ]
    )
    monkeypatch.setattr(cap, "run_kaggle", _gateway_returning(no_limit_pages))

    rc = cap.main(["--workspace", str(ws), "--assume-default-limit"])
    assert rc == 0
    cfg = _read_cfg(ws)
    assert cfg["submission"]["daily_limit"] == 5
    assert cfg["submission"]["limit_provenance"] == "assumed_default"
