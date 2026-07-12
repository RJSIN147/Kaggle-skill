"""test_budget.py — RED (Wave 0, 05-01-T2). Pins the D-04 / D-13 charged-submission count
(SCORE-03). GREEN target: 05-03 Task 2 (``scripts/submissions_log.py``).

There is **NO submission-quota command** in the Kaggle CLI (live-verified: ``kaggle quota``
reports GPU/TPU hours only). The daily budget must therefore be DERIVED by counting rows
from Kaggle's own authoritative ``competitions submissions`` list (05-RESEARCH.md §R2).

Pinned contract:

  * ``charged_today(rows, now_utc) -> int`` — counts TODAY's charged submissions.
      - ``FAILED`` (Kaggle ``ERROR``) rows are NOT charged (D-13 — Kaggle never billed them).
      - ``PENDING`` rows ARE charged (the slot was accepted and is being scored).
      - Returns the ``-1`` SENTINEL on any row it cannot account for => the caller FAILS
        CLOSED. It must NEVER silently skip an unrecognized status: that would UNDERCOUNT
        (e.g. against a future Kaggle status literal) and let the user submit past the real
        daily limit. ``FAILED`` is the ONLY legitimate skip.
  * ``parse_utc(raw)`` — Kaggle's ``date`` is a NAIVE ISO string with no tz suffix. It is
    treated as UTC (assumption A1). ⚠ THE TRAP: comparing it against ``datetime.now()``
    (LOCAL) silently miscounts the budget near the day boundary — the exact
    confident-but-wrong failure this project fails closed against.
  * ``fetch_lb.read_submissions(slug, runner=…) -> list | None`` — ``None`` on any rc != 0
    or a non-array payload. The caller must NEVER guess a count. ⚠ The gateway is an
    ARGUMENT (WR-01): the module-global-resolving ``submissions_log.fetch_submissions`` it
    replaced could silently bypass a monkeypatched gateway and shell out for real.

``now_utc`` is ALWAYS injected — no test here reads the real clock. No CLI process is ever
spawned: the gateway is INJECTED into the reader.
"""

from __future__ import annotations

import importlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "submissions"

# The fixed "now" the fixtures were authored around: 2026-07-12 is "today",
# 2026-07-11 is "yesterday". Injected everywhere — never the real clock.
NOW_UTC = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)

# mixed_today.json holds, on 2026-07-12 (UTC): one COMPLETE at 23:15 (within 2h of the
# NEXT UTC midnight), one PENDING at 14:03, one ERROR at 09:41, one COMPLETE at 00:47
# (within 2h of the PREVIOUS UTC midnight). The ERROR is free (D-13) => 3 charged.
EXPECTED_CHARGED_TODAY = 3


def _log():
    """Import scripts/submissions_log.py (on sys.path via conftest). Absent at RED."""
    return importlib.import_module("submissions_log")


def _fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _fake_gateway(payload, rc=0):
    """A ``run_kaggle`` stand-in returning ``(rc, payload)``. No CLI process is spawned."""

    def _fake(*argv, timeout=60):
        return rc, payload

    return _fake


# --------------------------------------------------------------------------- #
# D-04 + D-13: count today, exclude ERROR, include PENDING.
# --------------------------------------------------------------------------- #
def test_charged_today():
    log = _log()
    rows = _fixture("mixed_today")

    assert log.charged_today(rows, NOW_UTC) == EXPECTED_CHARGED_TODAY

    # D-13: an ERROR row dated TODAY is recorded but NOT charged.
    err_today = [r for r in rows if "ERROR" in r["status"] and r["date"].startswith("2026-07-12")]
    assert err_today, "fixture must carry a today-dated ERROR row"
    assert log.charged_today(err_today, NOW_UTC) == 0

    # A PENDING row dated TODAY IS charged — the slot was accepted and is being scored.
    pending_today = [
        r for r in rows if "PENDING" in r["status"] and r["date"].startswith("2026-07-12")
    ]
    assert pending_today, "fixture must carry a today-dated PENDING row"
    assert log.charged_today(pending_today, NOW_UTC) == 1

    # Yesterday's rows never count against today.
    yesterday = [r for r in rows if r["date"].startswith("2026-07-11")]
    assert yesterday
    assert log.charged_today(yesterday, NOW_UTC) == 0

    # An empty list is a real, knowable ZERO — not the -1 sentinel.
    assert log.charged_today([], NOW_UTC) == 0
    assert log.charged_today(_fixture("empty"), NOW_UTC) == 0


# --------------------------------------------------------------------------- #
# THE UTC TRAP (Pitfall 4): the count must not move with the developer's TZ.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tz", ["Pacific/Kiritimati", "Pacific/Midway", "UTC"])
def test_utc_day_boundary(monkeypatch, tz):
    """Identical count under UTC+14 and UTC-11.

    This is the test that proves ``datetime.now()`` / a local-time conversion was NOT used.
    mixed_today.json deliberately carries rows within 2h of BOTH UTC midnight edges
    (00:47 and 23:15), so any local-time rendering shifts them across the day boundary and
    changes the count.
    """
    log = _log()
    monkeypatch.setenv("TZ", tz)
    time.tzset()

    rows = _fixture("mixed_today")
    assert log.charged_today(rows, NOW_UTC) == EXPECTED_CHARGED_TODAY, (
        f"the charged count changed under TZ={tz} — the day boundary is being computed "
        "in LOCAL time. Kaggle's `date` is a naive ISO string and MUST be read as UTC."
    )

    # parse_utc yields a tz-AWARE UTC datetime regardless of the ambient TZ.
    ts = log.parse_utc("2026-07-12T23:15:42.123000")
    assert ts is not None
    assert ts.tzinfo is not None and ts.utcoffset().total_seconds() == 0
    assert (ts.year, ts.month, ts.day, ts.hour) == (2026, 7, 12, 23)
    assert ts.date() == NOW_UTC.date()


# --------------------------------------------------------------------------- #
# WR-06 — the fail-closed trigger is NARROWED to rows that could actually be TODAY's,
# without ever failing OPEN.
#
# The status parse used to run BEFORE the date parse, so ONE historical row carrying an
# unrecognized status literal (a future Kaggle enum, a legacy value) returned -1 —
# PERMANENTLY. `--page-size 200` returns the whole recent history, so that single row
# would brick the budget count for the competition on EVERY subsequent day, forever, with
# no escape that is not an override.
#
# The stated rationale ("skipping would UNDERCOUNT") only ever held for rows that COULD be
# today's. A row whose DATE parses cleanly to a past day cannot change today's count no
# matter what its status says.
#
# ⚠ The fail-closed guarantee is UNCHANGED where it is load-bearing: an unparseable DATE is
# still fatal (an unknowable DAY could be today), and an unparseable status on a row dated
# TODAY is still fatal.
# --------------------------------------------------------------------------- #
def _unknown_status_row(date, *, ref=46780799):
    """A row Kaggle sent us whose status literal this framework cannot classify."""
    return {
        "ref": ref,
        "fileName": "submission.csv",
        "date": date,
        "description": "exp-099",
        "status": "SubmissionStatus.QUARANTINED",
        "publicScore": "",
        "privateScore": "",
    }


def test_a_past_row_with_an_unknown_status_does_not_brick_the_count():
    """A YESTERDAY-dated unknown status must NOT return the sentinel — it cannot be today's.

    RED before WR-06: the status parse ran first, so this returned -1 and every subsequent
    day's budget was permanently unknowable for this competition.
    """
    log = _log()
    rows = _fixture("mixed_today")

    # Dated YESTERDAY (and even a year ago): it cannot possibly be charged against today.
    for stale_date in ("2026-07-11T09:41:02.000000", "2025-01-02T03:04:05.000000"):
        polluted = rows + [_unknown_status_row(stale_date)]
        assert log.charged_today(polluted, NOW_UTC) == EXPECTED_CHARGED_TODAY, (
            f"a row dated {stale_date} cannot change TODAY's count whatever its status "
            "says — failing closed on it permanently bricks the budget for this "
            "competition, with no non-override escape"
        )


def test_the_unknown_status_of_a_today_row_still_fails_closed():
    """⚠ The narrowing must NOT fail OPEN. A TODAY-dated unknown status is STILL fatal."""
    log = _log()
    rows = _fixture("mixed_today")

    today = rows + [_unknown_status_row("2026-07-12T18:00:00.000000")]
    assert log.charged_today(today, NOW_UTC) == -1, (
        "an unrecognized status on a row that IS today's must still FAIL CLOSED — skipping "
        "it would UNDERCOUNT and let the user spend past Kaggle's real daily limit"
    )

    # ...and an unparseable DATE remains fatal regardless of the status, because an
    # unknowable DAY might BE today. This is the boundary the narrowing must not cross.
    assert log.charged_today(rows + [_unknown_status_row("not-a-timestamp")], NOW_UTC) == -1
    assert log.charged_today(
        rows + [_unknown_status_row(None)], NOW_UTC
    ) == -1, "a MISSING date is an unknowable day — fail closed"


# --------------------------------------------------------------------------- #
# D-04: FAIL CLOSED. Never guess a count.
# --------------------------------------------------------------------------- #
def test_fails_closed_when_count_unavailable():
    log = _log()
    rows = _fixture("mixed_today")

    # (1) An UNPARSEABLE STATUS returns the -1 sentinel — it is NOT silently skipped.
    #     Silently skipping an unrecognized literal (e.g. a FUTURE Kaggle status) would
    #     UNDERCOUNT the charged submissions and let the user submit past the real limit.
    unknown_status = rows + [
        {
            "ref": 46780799,
            "fileName": "submission.csv",
            "date": "2026-07-12T18:00:00.000000",
            "description": "exp-099",
            "status": "SubmissionStatus.QUARANTINED",
            "publicScore": "",
            "privateScore": "",
        }
    ]
    assert log.charged_today(unknown_status, NOW_UTC) == -1, (
        "an unrecognized status must FAIL CLOSED (-1), never be skipped — skipping "
        "undercounts the budget and permits a submission past Kaggle's real daily limit"
    )

    # (2) An UNPARSEABLE DATE returns the -1 sentinel.
    bad_date = rows + [
        {
            "ref": 46780800,
            "fileName": "submission.csv",
            "date": "not-a-timestamp",
            "description": "exp-100",
            "status": "SubmissionStatus.COMPLETE",
            "publicScore": "0.7",
            "privateScore": "",
        }
    ]
    assert log.charged_today(bad_date, NOW_UTC) == -1
    assert log.parse_utc("not-a-timestamp") is None
    assert log.parse_utc(None) is None

    # (3) FAILED is the ONLY legitimate skip — an all-ERROR list still counts cleanly to 0.
    assert log.charged_today(_fixture("error"), NOW_UTC) == 0

    # (4) The READER returns None (=> fail closed) on a non-zero rc...
    #
    # ⚠ WR-01: this is `fetch_lb.read_submissions(..., runner=…)` — the INJECTABLE reader,
    # which takes the gateway as an ARGUMENT. It replaced `submissions_log.fetch_submissions`,
    # which resolved `run_kaggle` from its OWN module globals: patching the gateway anywhere
    # but inside that module was silently bypassed and the REAL Kaggle CLI shelled out from
    # inside a supposedly-mocked test. Passing `runner=` cannot be bypassed.
    read = importlib.import_module("fetch_lb").read_submissions

    assert read("titanic", runner=_fake_gateway("403 Client Error: Forbidden", rc=1)) is None

    # ...and on a payload that is not a JSON array.
    assert read("titanic", runner=_fake_gateway('{"error":"nope"}', rc=0)) is None
    assert read("titanic", runner=_fake_gateway("this is not json at all", rc=0)) is None

    # The happy path: a pretty-printed JSON array (CLI 2.2.3 spans many lines) parses.
    payload = json.dumps(_fixture("mixed_today"), indent=2)
    assert "\n" in payload, "the CLI pretty-prints --format json across many lines"
    fetched = read("titanic", runner=_fake_gateway(payload, rc=0))
    assert isinstance(fetched, list) and len(fetched) == len(rows)
    assert log.charged_today(fetched, NOW_UTC) == EXPECTED_CHARGED_TODAY

    # An empty array is a real, knowable EMPTY list — never None (that would fail closed
    # on a brand-new competition the user has simply not submitted to yet).
    assert read("titanic", runner=_fake_gateway("[]", rc=0)) == []
