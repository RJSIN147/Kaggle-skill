"""test_fetch_lb.py — RED (Wave 0, 05-01-T3). The D-03 detach/resume fallback (SCORE-01).
GREEN target: 05-05 Task 3 (``scripts/fetch_lb.py``).

D-03: bounded poll, then **DETACH** — never an unbounded wait, and never a lost slot. On
budget expiry the ``submissions.jsonl`` row simply STAYS ``PENDING`` (with its Kaggle
``ref``), and this discrete, re-runnable entry point records the score later.

Pinned contract (05-RESEARCH.md §R5 — reuse the PROVEN Phase 4 poller shape; import
``poll_kernel.compute_delay`` rather than forking the backoff math):

  * ``poll_lb(status_fn, *, now, sleep, rng, budget_s, max_consecutive_errors) -> dict``
    — the injected ``now``/``sleep``/``rng`` seam is what makes the loop deterministically
    testable with NO REAL WAITING (``_FakeClock`` + ``_sequence``, reused verbatim from
    ``tests/test_poll_kernel.py``).
  * LB-local constants (LB scoring is seconds-to-minutes, not the hours a kernel takes):
    ``LB_BASE_DELAY`` / ``LB_MAX_DELAY`` / ``LB_BUDGET_S``.
  * exit codes: 0 = SCORED, 2 = FAILED (Kaggle ERROR), 3 = DETACHED (still PENDING),
    4 = transient / fail-closed.

Every test monkeypatches the gateway. No CLI process is ever spawned, and this module is
structurally incapable of spending a slot: it only ever READS.
"""

from __future__ import annotations

import importlib
import json
import random
from datetime import datetime, timedelta, timezone

from test_poll_kernel import _FakeClock, _sequence
from test_submit import (
    EXP_ID,
    SLUG,
    _fake_gateway,
    _kaggle_row,
    _naive_utc,
    _read_sub_rows,
    _seed_ws,
    _sha256,
)

KAGGLE_REF = 46780678


def _fetch():
    """Import scripts/fetch_lb.py (on sys.path via conftest). Absent at RED."""
    return importlib.import_module("fetch_lb")


def _pending_row(ws, *, exp_id=EXP_ID, ref=KAGGLE_REF):
    """The row a DETACHED submit left behind: PENDING, carrying its Kaggle ref."""
    return {
        "schema_version": 1,
        "exp_id": exp_id,
        "kaggle_ref": ref,
        "competition_slug": SLUG,
        "file": f"experiments/{exp_id}/submission.csv",
        "file_sha256": _sha256(ws / "experiments" / exp_id / "submission.csv"),
        "message": f"{exp_id} | cv=0.841230",
        "submitted_at": "2026-07-12T14:03:11Z",
        "status": "PENDING",
        "public_score": None,
        "private_score": None,
        "scored_at": None,
        "override_reason": None,
        "error_description": None,
    }


def _seed_pending(ws, **kw):
    _seed_ws(ws)
    (ws / "control" / "submissions.jsonl").write_text(
        json.dumps(_pending_row(ws, **kw), separators=(",", ":")) + "\n"
    )
    return ws


def _run(mod, ws, *extra):
    return mod.main(["--workspace", str(ws), *extra])


# --------------------------------------------------------------------------- #
# D-03: the bounded poll DETACHES. It never cancels, and never loses the slot.
# --------------------------------------------------------------------------- #
def test_detach_preserves_pending(tmp_workspace, monkeypatch):
    mod = _fetch()

    # --- the loop itself, on an injected clock: no real waiting ----------------------
    clock = _FakeClock()
    pending_out = (0, json.dumps([_kaggle_row(
        ref=KAGGLE_REF,
        description=f"{EXP_ID} | cv=0.841230",
        date=_naive_utc(datetime.now(timezone.utc)),
        status="SubmissionStatus.PENDING",
    )]))
    result = mod.poll_lb(
        _sequence([pending_out]),  # never leaves PENDING
        now=clock.now,
        sleep=clock.sleep,
        rng=random.Random(0),
        budget_s=100,
        max_consecutive_errors=5,
    )
    assert result["terminal"] is False, "PENDING past the budget is a DETACH, not a terminal"
    assert result["status"] in ("DETACHED", "PENDING")
    assert clock.now() >= 100, "the loop must run until the wall-clock budget"
    assert clock.sleeps, "the loop must actually back off between ticks"
    assert all(s <= mod.LB_MAX_DELAY for s in clock.sleeps), (
        "FULL jitter: a sleep can never exceed the cap, so the budget is provably safe"
    )
    assert mod.LB_MAX_DELAY < 120.0 and mod.LB_BUDGET_S < 7200, (
        "LB scoring is seconds-to-minutes — the kernel constants are a starting point, "
        "not a mandate (§R5)"
    )

    # --- the entry point: exit 3, the row stays PENDING with its ref -----------------
    ws = _seed_pending(tmp_workspace)
    fake, calls = _fake_gateway(
        readback=[
            _kaggle_row(
                ref=KAGGLE_REF,
                description=f"{EXP_ID} | cv=0.841230",
                date=_naive_utc(datetime.now(timezone.utc)),
                status="SubmissionStatus.PENDING",
            )
        ]
    )
    monkeypatch.setattr(mod, "run_kaggle", fake)

    assert _run(mod, ws, "--budget-s", "0") == 3, "DETACHED is exit 3 (re-run fetch_lb later)"

    rows = _read_sub_rows(ws)
    assert len(rows) == 1
    assert rows[0]["status"] == "PENDING", "the spent slot is NEVER lost on a detach"
    assert rows[0]["kaggle_ref"] == KAGGLE_REF
    assert rows[0]["public_score"] is None

    # It only ever READS. No cancel-style / mutating argv is ever issued.
    for argv in calls:
        assert argv[:2] == ("competitions", "submissions"), f"unexpected call: {argv!r}"
        assert "cancel" not in argv and "submit" not in argv


# --------------------------------------------------------------------------- #
# Re-runnable and IDEMPOTENT: PENDING -> SCORED once, then a byte-stable no-op.
# --------------------------------------------------------------------------- #
def test_idempotent_resume(tmp_workspace, monkeypatch):
    mod = _fetch()
    ws = _seed_pending(tmp_workspace)

    scored = [
        _kaggle_row(
            ref=KAGGLE_REF,
            description=f"{EXP_ID} | cv=0.841230",
            date=_naive_utc(datetime.now(timezone.utc)),
            status="SubmissionStatus.COMPLETE",
            public_score="0.77511",
        )
    ]
    fake, calls = _fake_gateway(readback=scored)
    monkeypatch.setattr(mod, "run_kaggle", fake)

    assert _run(mod, ws) == 0, "a scored submission is exit 0"

    rows = _read_sub_rows(ws)
    assert len(rows) == 1, "the row transitions IN PLACE — never a duplicate"
    row = rows[0]
    assert row["status"] == "SCORED"
    assert row["public_score"] == 0.77511
    assert isinstance(row["public_score"], float), "the score is PARSED by tooling, never a string"
    assert row["scored_at"]
    assert row["kaggle_ref"] == KAGGLE_REF

    # A SECOND run is a byte-identical no-op — and never re-submits.
    before = (ws / "control" / "submissions.jsonl").read_bytes()
    assert _run(mod, ws) == 0
    assert (ws / "control" / "submissions.jsonl").read_bytes() == before
    assert not [c for c in calls if "submit" in c], "fetch_lb can only ever READ"


# --------------------------------------------------------------------------- #
# D-13: a Kaggle ERROR is RECORDED (not counted) — and its reason is NOT fabricated.
# --------------------------------------------------------------------------- #
def test_error_row_becomes_failed(tmp_workspace, monkeypatch, capsys):
    mod = _fetch()
    ws = _seed_pending(tmp_workspace)

    fake, _ = _fake_gateway(
        readback=[
            _kaggle_row(
                ref=KAGGLE_REF,
                description=f"{EXP_ID} | cv=0.841230",
                date=_naive_utc(datetime.now(timezone.utc)),
                status="SubmissionStatus.ERROR",
            )
        ]
    )
    monkeypatch.setattr(mod, "run_kaggle", fake)

    assert _run(mod, ws) == 2, "a Kaggle-side submission FAILURE is exit 2"

    row = _read_sub_rows(ws)[0]
    assert row["status"] == "FAILED"
    assert row["public_score"] is None
    assert row["error_description"] is None, (
        "the CLI does NOT expose the error reason (`errorDescription` is not in the 7-field "
        "allow-list) — record null, never a fabricated cause"
    )

    out = capsys.readouterr()
    msg = out.out + out.err
    assert "kaggle.com" in msg.lower(), (
        "point the user at their Kaggle submissions page for the real reason"
    )


# --------------------------------------------------------------------------- #
# --reconcile: make the canonical file SELF-HEALING against the one source that outranks it.
# --------------------------------------------------------------------------- #
def test_reconcile_backfills_out_of_band(tmp_workspace, monkeypatch):
    mod = _fetch()
    ws = _seed_pending(tmp_workspace)
    now = datetime.now(timezone.utc)

    fake, _ = _fake_gateway(
        readback=[
            # our known row, now scored
            _kaggle_row(
                ref=KAGGLE_REF,
                description=f"{EXP_ID} | cv=0.841230",
                date=_naive_utc(now),
                status="SubmissionStatus.COMPLETE",
                public_score="0.77511",
            ),
            # an OUT-OF-BAND submission made from the Kaggle website, absent locally.
            _kaggle_row(
                ref=46781000,
                description="exp-012 | cv=0.850000",
                date=_naive_utc(now - timedelta(hours=1)),
                status="SubmissionStatus.COMPLETE",
                public_score="0.78900",
            ),
            # ...and one with NO exp-NNN prefix at all (a hand-made upload).
            _kaggle_row(
                ref=46781001,
                description="quick manual try",
                date=_naive_utc(now - timedelta(hours=2)),
                status="SubmissionStatus.COMPLETE",
                public_score="0.75000",
            ),
        ]
    )
    monkeypatch.setattr(mod, "run_kaggle", fake)

    assert _run(mod, ws, "--reconcile") == 0

    rows = _read_sub_rows(ws)
    by_ref = {r["kaggle_ref"]: r for r in rows}
    assert set(by_ref) == {KAGGLE_REF, 46781000, 46781001}, (
        "--reconcile back-fills every row present on Kaggle but absent locally"
    )

    assert by_ref[KAGGLE_REF]["status"] == "SCORED"
    assert by_ref[KAGGLE_REF]["exp_id"] == EXP_ID

    # exp_id is recovered from the description prefix...
    assert by_ref[46781000]["exp_id"] == "exp-012"
    assert by_ref[46781000]["public_score"] == 0.78900

    # ...and is NULL when the description carries no exp-NNN prefix (never invented).
    assert by_ref[46781001]["exp_id"] is None
    assert by_ref[46781001]["public_score"] == 0.75000

    # Re-reconciling is idempotent — no duplicate rows.
    before = (ws / "control" / "submissions.jsonl").read_bytes()
    assert _run(mod, ws, "--reconcile") == 0
    assert (ws / "control" / "submissions.jsonl").read_bytes() == before
