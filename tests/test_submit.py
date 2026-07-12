"""test_submit.py — RED (Wave 0, 05-01-T3). The SLOT-SAFETY CORE (SCORE-01).
GREEN target: 05-05 Tasks 2/3 (``scripts/submit.py``).

A real submission is IRREVERSIBLE and spends a scarce daily slot. Every test here
monkeypatches the gateway (``run_kaggle``) on the importing module — **no CLI process is
ever spawned and no slot can ever be spent.** Tests assert on the ARGV the fake receives:
that is how the exact command shape is proven WITHOUT executing it.

Pinned contract (05-RESEARCH.md §R1 — read from the installed CLI 2.2.3 source):

  ⚠ ``submit`` is **FAIL-OPEN on its exit code.** A 404 slug and a failed upload both PRINT
  a message and exit **0**. ``rc == 0`` is therefore NOT proof that the submission landed.
  And the CLI DISCARDS the submission id (``.ref``), returning only ``.message`` — so the
  ONLY reliable correlation channel is the ``-m`` message, which round-trips into the
  ``description`` field on read-back. The read-back is simultaneously the success proof, the
  source of the Kaggle ``ref``, and the first poll tick.

  * exit codes (mirroring ``poll_kernel.py``): 0 = SCORED, 2 = submission FAILED (Kaggle
    ERROR), 3 = DETACHED (PENDING — re-run ``fetch_lb.py``), 4 = transient / fail-closed.

This module is the ONE place in ``tests/`` allowed to contain the submit-subcommand literal
(``test_no_live_test_ever_submits`` below greps for it, and the phase verification asserts it
appears nowhere else).
"""

from __future__ import annotations

import hashlib
import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent

SLUG = "titanic"
EXP_ID = "exp-007"

# The D-02 reference file submit.py validates against before it spends a slot. Titanic's
# real sample is `gender_submission.csv` — NOT the conventionally-guessed
# `sample_submission.csv` — and `_resolve_reference`'s rung-2 glob finds it by name.
SAMPLE_NAME = "gender_submission.csv"
DEFAULT_CSV_BODY = "PassengerId,Survived\n892,0\n893,1\n"
SAMPLE_BODY = DEFAULT_CSV_BODY

# The two client-hardcoded fail-open literals, transcribed live (§R1).
FAIL_OPEN_404 = (TESTS_DIR / "fixtures" / "submissions" / "submit_404.txt").read_text()
FAIL_OPEN_UPLOAD = (
    TESTS_DIR / "fixtures" / "submissions" / "submit_upload_failed.txt"
).read_text()

# The submit SUCCESS message is server-authored and was never captured (capturing it would
# cost a real slot). It is deliberately treated as UNKNOWN TEXT and never parsed (A2).
SERVER_SUCCESS = "Successfully submitted to Titanic - Machine Learning from Disaster"


def _submit():
    """Import scripts/submit.py (on sys.path via conftest). Absent at RED."""
    return importlib.import_module("submit")


# --------------------------------------------------------------------------- #
# Workspace seeding + the fake gateway. Shared with test_fetch_lb / the leak suite.
# --------------------------------------------------------------------------- #
def _naive_utc(dt):
    """Render a datetime the way Kaggle does: a NAIVE ISO string, no tz suffix (§R2)."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat()


def _kaggle_row(*, ref, description, date, status="SubmissionStatus.PENDING",
                public_score="", file_name="submission.csv"):
    """A row in the exact 7-key live-verified shape (§R2)."""
    return {
        "ref": ref,
        "fileName": file_name,
        "date": date,
        "description": description,
        "status": status,
        "publicScore": public_score,
        "privateScore": "",
    }


def _seed_ws(ws, *, exp_id=EXP_ID, slug=SLUG, csv_body=None, cv_mean=0.84123,
             comp_type="csv", daily_limit=5, limit_provenance="rules_page",
             seed_data=True, sample_body=None):
    """A scaffolded workspace: config + ledger + data/ + an experiment with a submission.csv.

    ``seed_data`` writes ``data/gender_submission.csv`` — the D-02 reference that submit.py
    validates against before spending a slot. It defaults ON because a workspace WITHOUT a
    reference is now a refusal path, not a happy path. ``test_check_submission`` seeds its
    own ``data/`` and opts out.
    """
    ctrl = ws / "control"
    (ctrl / "raw").mkdir(parents=True, exist_ok=True)
    (ctrl / "config.json").write_text(
        json.dumps(
            {
                "workspace_version": 1,
                "competition_slug": slug,
                "execution_target": "local",
                "cv": {"scheme": "StratifiedKFold"},
                "metric": {"name": "accuracy", "greater_is_better": True},
                "competition": {"type": comp_type},
                "submission": {
                    "daily_limit": daily_limit,
                    "limit_provenance": limit_provenance,
                    "noise_k": 1.0,
                },
                "created": "2026-01-01T00:00:00Z",
            }
        )
    )
    (ctrl / "ledger.jsonl").write_text(
        json.dumps(
            {
                "exp_id": exp_id,
                "status": "SUCCESS",
                "idea": "LightGBM baseline",
                "metric": "accuracy",
                "greater_is_better": True,
                "cv_mean": cv_mean,
                "cv_std": 0.01,
                "git_commit": "abc1234",
                "seed": 42,
                "created": "2026-07-12T10:00:00Z",
                "verdict_path": f"experiments/{exp_id}/VERDICT.md",
            },
            separators=(",", ":"),
        )
        + "\n"
    )
    (ctrl / "submissions.jsonl").write_text("")

    if seed_data:
        data = ws / "data"
        data.mkdir(parents=True, exist_ok=True)
        (data / SAMPLE_NAME).write_text(
            SAMPLE_BODY if sample_body is None else sample_body
        )

    exp_dir = ws / "experiments" / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    body = csv_body if csv_body is not None else DEFAULT_CSV_BODY
    (exp_dir / "submission.csv").write_text(body)
    (exp_dir / "meta.json").write_text(
        json.dumps(
            {
                "exp_id": exp_id,
                "status": "SUCCESS",
                "idea": "LightGBM baseline",
                "cv_mean": cv_mean,
                "cv_std": 0.01,
                "provenance": {
                    "run_id": "run-1",
                    "artifact_hash": "sha256:" + "0" * 64,
                    "git_commit": "abc1234",
                    "seed": 42,
                },
            },
            indent=2,
        )
        + "\n"
    )
    return ws


def _sha256(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _fake_gateway(*, submit_rc=0, submit_out=SERVER_SUCCESS, readback=None,
                  readback_rc=0, raise_on_readback_after=None):
    """A ``run_kaggle`` stand-in that DISPATCHES on the subcommand and records every argv.

    ``readback`` may be a list of Kaggle rows or a zero-arg callable returning one (so a
    test can make the read-back evolve across poll ticks). Nothing is ever executed.
    """
    calls = []
    state = {"readbacks": 0}

    def _fake(*argv, timeout=60):
        calls.append(tuple(str(a) for a in argv))
        sub = argv[1] if len(argv) > 1 else ""
        if sub == "submit":
            return submit_rc, submit_out
        if sub == "submissions":
            state["readbacks"] += 1
            if (
                raise_on_readback_after is not None
                and state["readbacks"] > raise_on_readback_after
            ):
                raise RuntimeError("gateway exploded mid-poll")
            rows = readback() if callable(readback) else (readback or [])
            # The CLI PRETTY-PRINTS --format json across many lines (§R2).
            return readback_rc, json.dumps(rows, indent=2)
        raise AssertionError(f"submit.py issued an unexpected subcommand: {argv!r}")

    return _fake, calls


def _read_sub_rows(ws):
    text = (ws / "control" / "submissions.jsonl").read_text()
    return [json.loads(ln) for ln in text.splitlines() if ln.strip()]


def _run(mod, ws, *extra):
    return mod.main(["--workspace", str(ws), "--exp-id", EXP_ID, *extra])


# --------------------------------------------------------------------------- #
# The exact command shape — proven from the captured argv, never executed.
# --------------------------------------------------------------------------- #
def test_argv_shape(tmp_workspace, monkeypatch):
    mod = _submit()
    ws = _seed_ws(tmp_workspace)
    csv_path = ws / "experiments" / EXP_ID / "submission.csv"

    now = datetime.now(timezone.utc)
    fake, calls = _fake_gateway(
        readback=lambda: [
            _kaggle_row(
                ref=46780678,
                description=f"{EXP_ID} | cv=0.841230",
                date=_naive_utc(now + timedelta(seconds=5)),
                status="SubmissionStatus.COMPLETE",
                public_score="0.77511",
            )
        ]
    )
    monkeypatch.setattr(mod, "run_kaggle", fake)

    assert _run(mod, ws, "--confirm") == 0

    submits = [c for c in calls if len(c) > 1 and c[1] == "submit"]
    assert len(submits) == 1, "exactly ONE slot may be spent per invocation"
    argv = submits[0]

    assert argv[0] == "competitions"
    assert argv[1] == "submit"
    assert argv[2] == SLUG, "the competition is POSITIONAL (never -c), and always explicit"
    assert "-f" in argv and argv[argv.index("-f") + 1] == str(csv_path)
    assert "-m" in argv
    message = argv[argv.index("-m") + 1]
    assert message.startswith(EXP_ID), (
        "-m is the ONLY exp_id<->Kaggle correlation channel (it round-trips into "
        "`description`); it MUST start with the exp_id"
    )

    # Code-competition flags are D-01-refused, and --sandbox is a host/admin flag, NOT a
    # dry run. None may EVER appear.
    for forbidden in ("-k", "--kernel", "-v", "--version", "--sandbox"):
        assert forbidden not in argv, f"{forbidden} must never be passed"


# --------------------------------------------------------------------------- #
# ⚠ THE FAIL-OPEN GUARDS: rc == 0 is NOT proof of success.
# --------------------------------------------------------------------------- #
def test_fail_open_404_is_not_success(tmp_workspace, monkeypatch, capsys):
    """rc == 0 + `Could not find competition` ⇒ FAILURE. The CLI swallows its own 404."""
    mod = _submit()
    ws = _seed_ws(tmp_workspace)

    fake, calls = _fake_gateway(submit_rc=0, submit_out=FAIL_OPEN_404, readback=[])
    monkeypatch.setattr(mod, "run_kaggle", fake)

    rc = _run(mod, ws, "--confirm")
    assert rc != 0, "a fail-open 404 (exit 0!) must NOT be reported as success"

    rows = _read_sub_rows(ws)
    assert not [r for r in rows if r.get("status") == "SCORED"], "no SCORED row may be written"

    out = capsys.readouterr()
    combined = out.out + out.err
    assert "Could not find competition" not in combined, "the raw CLI buffer is never echoed"


def test_fail_open_upload_is_not_success(tmp_workspace, monkeypatch, capsys):
    """rc == 0 + `Could not submit to competition` ⇒ FAILURE, and no token-shaped leak."""
    mod = _submit()
    ws = _seed_ws(tmp_workspace)

    fake, calls = _fake_gateway(submit_rc=0, submit_out=FAIL_OPEN_UPLOAD, readback=[])
    monkeypatch.setattr(mod, "run_kaggle", fake)

    rc = _run(mod, ws, "--confirm")
    assert rc != 0, "a failed upload (exit 0!) must NOT be reported as success"
    assert not [r for r in _read_sub_rows(ws) if r.get("status") == "SCORED"]

    out = capsys.readouterr()
    combined = out.out + out.err
    # T-05-01-02: the raw buffer may carry a secret — it is QUARANTINED, never printed.
    assert "TOKENLEAK_SENTINEL" not in combined
    assert "kagat_" not in combined
    assert FAIL_OPEN_UPLOAD not in combined


def test_unconfirmed_submission_fails_closed(tmp_workspace, monkeypatch):
    """rc == 0, no failure literal — but the read-back proves nothing landed ⇒ fail closed."""
    mod = _submit()
    ws = _seed_ws(tmp_workspace)

    # The read-back carries only OTHER people's/experiments' rows: no confirmation.
    fake, calls = _fake_gateway(
        submit_rc=0,
        submit_out=SERVER_SUCCESS,
        readback=[
            _kaggle_row(
                ref=1,
                description="exp-001 | cv=0.70",
                date=_naive_utc(datetime.now(timezone.utc) - timedelta(days=2)),
                status="SubmissionStatus.COMPLETE",
                public_score="0.70",
            )
        ],
    )
    monkeypatch.setattr(mod, "run_kaggle", fake)

    rc = _run(mod, ws, "--confirm")
    assert rc != 0, (
        "an UNCONFIRMED submission must never claim success — the read-back IS the proof, "
        "and rc == 0 is not"
    )
    assert not [r for r in _read_sub_rows(ws) if r.get("status") == "SCORED"]


# --------------------------------------------------------------------------- #
# Correlation: the description prefix + date >= start, and the recovered Kaggle ref.
# --------------------------------------------------------------------------- #
def test_correlates_by_exp_id(tmp_workspace, monkeypatch):
    mod = _submit()
    ws = _seed_ws(tmp_workspace)
    now = datetime.now(timezone.utc)

    ours = _kaggle_row(
        ref=46780678,
        description=f"{EXP_ID} | cv=0.841230",
        date=_naive_utc(now + timedelta(seconds=5)),
        status="SubmissionStatus.COMPLETE",
        public_score="0.77511",
    )
    # Decoy 1: a PREFIX-COLLIDING exp id. The match must be ANCHORED (^exp-\d{3}\b), so
    # "exp-0071" must NOT satisfy a lookup for "exp-007".
    decoy_prefix = _kaggle_row(
        ref=999001,
        description="exp-0071 | cv=0.999999",
        date=_naive_utc(now + timedelta(seconds=6)),
        status="SubmissionStatus.COMPLETE",
        public_score="0.99",
    )
    # Decoy 2: OUR exp id, but submitted LONG BEFORE this run started — an older attempt
    # can never confirm THIS one (date >= started).
    decoy_old = _kaggle_row(
        ref=999002,
        description=f"{EXP_ID} | cv=0.841230",
        date=_naive_utc(now - timedelta(days=3)),
        status="SubmissionStatus.COMPLETE",
        public_score="0.60",
    )

    fake, calls = _fake_gateway(readback=[decoy_prefix, ours, decoy_old])
    monkeypatch.setattr(mod, "run_kaggle", fake)

    assert _run(mod, ws, "--confirm") == 0

    # The read-back is issued READ-ONLY, in the live-verified shape.
    readbacks = [c for c in calls if len(c) > 1 and c[1] == "submissions"]
    assert readbacks, "the read-back IS the confirmation — it must always be issued"
    rb = readbacks[0]
    assert rb[0] == "competitions" and rb[2] == SLUG
    assert "--format" in rb and rb[rb.index("--format") + 1] == "json"

    rows = _read_sub_rows(ws)
    assert len(rows) == 1
    row = rows[0]
    assert row["exp_id"] == EXP_ID
    assert row["kaggle_ref"] == 46780678, (
        "the Kaggle ref is RECOVERED from the read-back (the submit call discards it) — "
        "and it must be OUR row's ref, not a prefix-colliding or stale decoy's"
    )
    assert row["kaggle_ref"] not in (999001, 999002)
    assert row["status"] == "SCORED"
    assert row["public_score"] == 0.77511
    assert row["competition_slug"] == SLUG
    assert row["file_sha256"] == _sha256(ws / "experiments" / EXP_ID / "submission.csv")


# --------------------------------------------------------------------------- #
# Pitfall 6 — WRITE ORDERING: a crash mid-poll must never orphan a SPENT slot.
# --------------------------------------------------------------------------- #
def test_pending_row_written_before_poll(tmp_workspace, monkeypatch):
    """The PENDING row is persisted BEFORE the poll loop begins.

    The slot is spent the instant Kaggle accepts the upload. If the poll then crashes and
    nothing was written, the submission is invisible locally: its exp_id<->ref provenance is
    gone forever and the CV→LB gap for that experiment can never be computed.
    """
    mod = _submit()
    ws = _seed_ws(tmp_workspace)
    now = datetime.now(timezone.utc)

    # The first read-back CONFIRMS the submission (still PENDING). Every subsequent poll
    # tick explodes — simulating a crash/network death mid-poll.
    fake, calls = _fake_gateway(
        readback=[
            _kaggle_row(
                ref=46780678,
                description=f"{EXP_ID} | cv=0.841230",
                date=_naive_utc(now + timedelta(seconds=5)),
                status="SubmissionStatus.PENDING",
            )
        ],
        raise_on_readback_after=1,
    )
    monkeypatch.setattr(mod, "run_kaggle", fake)

    try:
        rc = _run(mod, ws, "--confirm")
    except Exception:
        rc = None  # a raw crash is tolerated here; LOSING THE ROW is not
    assert rc != 0, "a crashed poll is not a successful submission"

    rows = _read_sub_rows(ws)
    assert rows, (
        "the PENDING row MUST already be on disk before the poll starts — a crash mid-poll "
        "otherwise loses the provenance of a slot that was really spent (Pitfall 6)"
    )
    row = rows[0]
    assert row["exp_id"] == EXP_ID
    assert row["kaggle_ref"] == 46780678
    assert row["status"] == "PENDING"
    assert row["file_sha256"] == _sha256(ws / "experiments" / EXP_ID / "submission.csv")


# --------------------------------------------------------------------------- #
# Pitfall 7 — re-running submit must NOT double-spend.
# --------------------------------------------------------------------------- #
def test_refuses_double_spend(tmp_workspace, monkeypatch, capsys):
    mod = _submit()
    ws = _seed_ws(tmp_workspace)
    csv_path = ws / "experiments" / EXP_ID / "submission.csv"
    now = datetime.now(timezone.utc)

    # An existing, NON-FAILED row for the same exp_id AND the same file hash.
    (ws / "control" / "submissions.jsonl").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "exp_id": EXP_ID,
                "kaggle_ref": 46780678,
                "competition_slug": SLUG,
                "file": f"experiments/{EXP_ID}/submission.csv",
                "file_sha256": _sha256(csv_path),
                "message": f"{EXP_ID} | cv=0.841230",
                "submitted_at": "2026-07-12T14:03:11Z",
                "status": "PENDING",
                "public_score": None,
                "private_score": None,
                "scored_at": None,
                "override_reason": None,
                "error_description": None,
            },
            separators=(",", ":"),
        )
        + "\n"
    )

    fake, calls = _fake_gateway(readback=[])
    monkeypatch.setattr(mod, "run_kaggle", fake)

    rc = _run(mod, ws, "--confirm")
    assert rc != 0, "re-submitting an identical file for the same experiment must be refused"
    assert not [c for c in calls if len(c) > 1 and c[1] == "submit"], (
        "the double-spend refusal must happen BEFORE the slot is spent"
    )
    msg = capsys.readouterr()
    assert "fetch_lb" in (msg.out + msg.err), "point the user at the re-runnable fetch_lb.py"
    assert len(_read_sub_rows(ws)) == 1, "no second row may be appended"

    # --resubmit is the explicit override for a genuine second submission of the same file.
    fake2, calls2 = _fake_gateway(
        readback=lambda: [
            _kaggle_row(
                ref=46780999,
                description=f"{EXP_ID} | cv=0.841230",
                date=_naive_utc(now + timedelta(seconds=5)),
                status="SubmissionStatus.COMPLETE",
                public_score="0.77511",
            )
        ]
    )
    monkeypatch.setattr(mod, "run_kaggle", fake2)
    assert _run(mod, ws, "--confirm", "--resubmit") == 0
    assert [c for c in calls2 if len(c) > 1 and c[1] == "submit"], "--resubmit really submits"
    assert len(_read_sub_rows(ws)) == 2, "a genuine second submission appends a second row"


def test_refuses_double_spend_after_reconcile(tmp_workspace, monkeypatch, capsys):
    """⚠ CR-01 — THE RECOVERY PATH MUST NOT BE THE DOUBLE-SPEND PATH.

    This is the trap the double-spend guard exists for, and the one it used to miss. When
    submit.py's read-back fails, the slot MAY already be spent — and submit.py's own message
    tells the user: *"if the submission is there, run `fetch_lb.py --reconcile` to back-fill
    it."* But a reconciled row carries ``file_sha256: null`` (correctly — Kaggle does not
    return the bytes it was sent), and the guard keyed on ``file_sha256 == digest``. So
    ``None != digest``, the guard did not fire, and a user who followed the framework's OWN
    recovery advice and re-ran ``submit.py --confirm`` spent a SECOND REAL SLOT on the same
    experiment.

    The whole flow is exercised here — reconcile for real, then submit — rather than
    hand-seeding a row, because it is the SEAM BETWEEN the two scripts that was broken.
    """
    mod = _submit()
    fetch_lb = importlib.import_module("fetch_lb")
    ws = _seed_ws(tmp_workspace)
    now = datetime.now(timezone.utc)

    # The submission Kaggle really did accept — the slot IS spent — but which submit.py
    # never recorded, because its read-back came back empty.
    spent = [
        _kaggle_row(
            ref=46780678,
            description=f"{EXP_ID} | cv=0.841230",
            date=_naive_utc(now - timedelta(minutes=5)),
            status="SubmissionStatus.COMPLETE",
            public_score="0.77511",
        )
    ]

    # --- 1. The user does exactly what submit.py told them to do. ----------------------
    fake_fl, _ = _fake_gateway(readback=spent)
    monkeypatch.setattr(fetch_lb, "run_kaggle", fake_fl)
    assert fetch_lb.main(["--workspace", str(ws), "--reconcile"]) == 0

    rows = _read_sub_rows(ws)
    assert len(rows) == 1 and rows[0]["exp_id"] == EXP_ID
    assert rows[0]["file_sha256"] is None, (
        "a reconciled row genuinely CANNOT know the file hash — Kaggle never returns it. "
        "That is CORRECT, and it is exactly why sha-equality cannot be the guard's sole key"
    )
    assert rows[0]["status"] != "FAILED", "a SCORED row is a SPENT slot"

    # --- 2. ...and then re-runs submit, as the SKILL's exit-75 loop makes natural. ------
    fake, calls = _fake_gateway(readback=spent)
    monkeypatch.setattr(mod, "run_kaggle", fake)

    rc = _run(mod, ws, "--confirm")
    assert rc != 0, "the re-submit after a reconcile must be REFUSED, not honoured"
    assert not [c for c in calls if len(c) > 1 and c[1] == "submit"], (
        "NO SECOND SLOT. The recorded row has no hash, so the bytes cannot be PROVEN "
        "different from the ones already submitted — and the cost of being wrong is an "
        "irreversible slot. Fail closed on exp_id alone."
    )
    assert len(_read_sub_rows(ws)) == 1, "no second row may be appended"

    printed = capsys.readouterr()
    combined = printed.out + printed.err
    assert "--resubmit" in combined, (
        "the refusal must name the DELIBERATE escape hatch — a fail-closed guard with no "
        "documented override is a dead end, not a safety feature (D-05)"
    )

    # --- 3. --resubmit remains the explicit, deliberate override. ----------------------
    fake2, calls2 = _fake_gateway(
        readback=lambda: [
            _kaggle_row(
                ref=46780999,
                description=f"{EXP_ID} | cv=0.841230",
                date=_naive_utc(datetime.now(timezone.utc) + timedelta(seconds=5)),
                status="SubmissionStatus.COMPLETE",
                public_score="0.77511",
            )
        ]
    )
    monkeypatch.setattr(mod, "run_kaggle", fake2)
    assert _run(mod, ws, "--confirm", "--resubmit") == 0
    assert [c for c in calls2 if len(c) > 1 and c[1] == "submit"], (
        "--resubmit is the human's conscious 'yes, spend another slot' — it must still work"
    )
    assert len(_read_sub_rows(ws)) == 2


def test_a_recorded_hash_that_differs_does_not_block(tmp_workspace, monkeypatch):
    """The CR-01 guard must not OVER-block: a KNOWN, DIFFERENT hash proves new bytes.

    Only an UNKNOWN hash is treated as an unprovable match. When the recorded row carries a
    real hash and it differs from the file on disk, the bytes are demonstrably not the ones
    already submitted — that is a genuinely new file for the same experiment, and it submits
    without needing --resubmit, exactly as before.
    """
    mod = _submit()
    ws = _seed_ws(tmp_workspace)
    csv_path = ws / "experiments" / EXP_ID / "submission.csv"
    now = datetime.now(timezone.utc)

    # A prior submission of DIFFERENT bytes (a real, recorded hash that is not ours).
    (ws / "control" / "submissions.jsonl").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "exp_id": EXP_ID,
                "kaggle_ref": 46780678,
                "competition_slug": SLUG,
                "file": f"experiments/{EXP_ID}/submission.csv",
                "file_sha256": "sha256:" + "b" * 64,  # a REAL hash — and NOT this file's
                "message": f"{EXP_ID} | cv=0.841230",
                "submitted_at": "2026-07-12T14:03:11Z",
                "status": "SCORED",
                "public_score": 0.70,
                "private_score": None,
                "scored_at": "2026-07-12T14:05:00Z",
                "override_reason": None,
                "error_description": None,
            },
            separators=(",", ":"),
        )
        + "\n"
    )
    assert _sha256(csv_path) != "sha256:" + "b" * 64

    fake, calls = _fake_gateway(
        readback=lambda: [
            _kaggle_row(
                ref=46780999,
                description=f"{EXP_ID} | cv=0.841230",
                date=_naive_utc(now + timedelta(seconds=5)),
                status="SubmissionStatus.COMPLETE",
                public_score="0.78",
            )
        ]
    )
    monkeypatch.setattr(mod, "run_kaggle", fake)

    assert _run(mod, ws, "--confirm") == 0, (
        "a genuinely different file for the same experiment is not a double-spend — the "
        "recorded hash PROVES the bytes differ"
    )
    assert [c for c in calls if len(c) > 1 and c[1] == "submit"]
    assert len(_read_sub_rows(ws)) == 2


# --------------------------------------------------------------------------- #
# CR-02 / D-02 — NEVER SUBMIT AN UNVALIDATED FILE. Mechanically, inside submit.py.
#
# submit.py is the ONLY script that spends the irreversible resource, so it cannot merely
# TRUST that the free gate (check_submission.py) was run first. Its whole file check used
# to be `csv_path.is_file()` — existence — while SKILL.md documented exit 65 (sample
# mismatch) as a submit.py outcome and stated "Never submit an unvalidated file". That
# invariant lived only in prose, i.e. in the agent remembering to run the gate.
#
# The failure is NOT free even though Kaggle does not charge processing errors (D-13): a
# header/id-set mismatch is frequently SCORED, not errored — a wrong-but-parseable file
# burns a real slot and lands a garbage score on the board.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "case,body",
    [
        ("header_mismatch", "PassengerId,Prediction\n892,0\n893,1\n"),
        ("row_count_mismatch", "PassengerId,Survived\n892,0\n"),
        ("id_set_mismatch", "PassengerId,Survived\n892,0\n999,1\n"),
        ("blank_prediction", "PassengerId,Survived\n892,0\n893,\n"),
        ("nan_prediction", "PassengerId,Survived\n892,0\n893,nan\n"),
    ],
)
def test_refuses_an_unvalidated_submission_csv(tmp_workspace, monkeypatch, case, body):
    """A file that does not match the competition's sample never reaches the gateway."""
    mod = _submit()
    gw = importlib.import_module("kaggle_gateway")
    ws = _seed_ws(tmp_workspace / case, csv_body=body)

    fake, calls = _fake_gateway(readback=[])
    monkeypatch.setattr(mod, "run_kaggle", fake)

    rc = _run(mod, ws, "--confirm")
    assert rc == gw.VALIDATION_FAILED == 65, (
        f"{case}: submit.py must run the D-02 validation ITSELF and exit 65 — SKILL.md "
        f"documents exit 65 (sample mismatch) as a submit.py outcome"
    )
    assert calls == [], (
        f"{case}: a structurally invalid file must be caught BEFORE the gateway. Kaggle "
        f"would frequently SCORE it rather than error it — burning a real, irreversible "
        f"slot and landing a garbage score on the board"
    )
    assert _read_sub_rows(ws) == [], "nothing is recorded for a file that was never sent"


def test_refuses_when_there_is_nothing_to_validate_against(tmp_workspace, monkeypatch):
    """No reference file at all => FAIL CLOSED (65). An unvalidated file is never submitted."""
    mod = _submit()
    gw = importlib.import_module("kaggle_gateway")
    ws = _seed_ws(tmp_workspace, seed_data=False)  # no data/ => nothing to validate against

    fake, calls = _fake_gateway(readback=[])
    monkeypatch.setattr(mod, "run_kaggle", fake)

    assert _run(mod, ws, "--confirm") == gw.VALIDATION_FAILED
    assert calls == [], "with nothing to validate against, the slot is never risked"


def test_a_valid_csv_still_submits(tmp_workspace, monkeypatch):
    """The CR-02 guard must not block the happy path: a file matching the sample submits."""
    mod = _submit()
    ws = _seed_ws(tmp_workspace)  # the default csv_body MATCHES the seeded sample
    now = datetime.now(timezone.utc)

    fake, calls = _fake_gateway(
        readback=lambda: [
            _kaggle_row(
                ref=46780678,
                description=f"{EXP_ID} | cv=0.841230",
                date=_naive_utc(now + timedelta(seconds=5)),
                status="SubmissionStatus.COMPLETE",
                public_score="0.77511",
            )
        ]
    )
    monkeypatch.setattr(mod, "run_kaggle", fake)

    assert _run(mod, ws, "--confirm") == 0
    assert [c for c in calls if len(c) > 1 and c[1] == "submit"]


def test_dry_run_refuses_an_unvalidated_file(tmp_workspace, monkeypatch):
    """--dry-run rehearses the REAL pre-flight, so it must surface the validation failure.

    A --dry-run that printed a clean command for a file the real run would refuse would be
    a rehearsal of the wrong thing.
    """
    mod = _submit()
    gw = importlib.import_module("kaggle_gateway")
    ws = _seed_ws(tmp_workspace, csv_body="Wrong,Header\n1,2\n")

    fake, calls = _fake_gateway(readback=[])
    monkeypatch.setattr(mod, "run_kaggle", fake)

    assert _run(mod, ws, "--dry-run") == gw.VALIDATION_FAILED
    assert calls == []


# --------------------------------------------------------------------------- #
# D-11 — the experiment folder is IMMUTABLE. The LB score never lands in meta.json.
# --------------------------------------------------------------------------- #
def test_meta_json_untouched(tmp_workspace, monkeypatch):
    mod = _submit()
    ws = _seed_ws(tmp_workspace)
    meta_path = ws / "experiments" / EXP_ID / "meta.json"
    before = meta_path.read_bytes()
    now = datetime.now(timezone.utc)

    fake, calls = _fake_gateway(
        readback=lambda: [
            _kaggle_row(
                ref=46780678,
                description=f"{EXP_ID} | cv=0.841230",
                date=_naive_utc(now + timedelta(seconds=5)),
                status="SubmissionStatus.COMPLETE",
                public_score="0.77511",
            )
        ]
    )
    monkeypatch.setattr(mod, "run_kaggle", fake)

    assert _run(mod, ws, "--confirm") == 0
    # The submission really was scored — and STILL meta.json did not move a byte.
    assert _read_sub_rows(ws)[0]["public_score"] == 0.77511
    assert meta_path.read_bytes() == before, (
        "D-11: submissions.jsonl is the CANONICAL LB record. The LB score is NEVER written "
        "back into meta.json — the experiment folder is immutable after record."
    )


# --------------------------------------------------------------------------- #
# --dry-run: the inspectable pre-flight that touches nothing.
# --------------------------------------------------------------------------- #
def test_dry_run_never_calls_gateway(tmp_workspace, monkeypatch, capsys):
    mod = _submit()
    ws = _seed_ws(tmp_workspace)
    csv_path = ws / "experiments" / EXP_ID / "submission.csv"

    fake, calls = _fake_gateway(readback=[])
    monkeypatch.setattr(mod, "run_kaggle", fake)

    assert _run(mod, ws, "--dry-run") == 0
    assert calls == [], "--dry-run must NEVER reach the gateway (it is a pre-flight, not a run)"

    printed = capsys.readouterr().out
    # It prints the exact argv it WOULD pass, so a human can inspect it before spending.
    assert "competitions" in printed and "submit" in printed
    assert SLUG in printed
    assert str(csv_path) in printed
    assert EXP_ID in printed
    assert "--sandbox" not in printed, "--sandbox is a host/admin flag, NOT a dry run"

    assert _read_sub_rows(ws) == [], "--dry-run writes nothing"


# --------------------------------------------------------------------------- #
# ⭐ THE IRREVERSIBILITY GUARANTEE (SAFETY). GREEN from the moment it is written.
# --------------------------------------------------------------------------- #
def test_no_live_test_ever_submits():
    """HARD RULE: no ``@pytest.mark.live`` test may invoke the submit subcommand.

    A live test that submits would spend a real, irreversible slot on EVERY run of the opt-in
    live suite. This is a mechanical source guard (mirroring
    ``test_poll_kernel.py::test_source_routes_through_gateway``) so the constraint is
    ENFORCED, not remembered.
    """
    live_files = sorted(TESTS_DIR.glob("test_*live*.py"))
    assert live_files, "the live suite vanished — the guard must have something to guard"

    offenders = []
    for path in live_files:
        src = path.read_text()
        if (
            "competitions submit" in src
            or '"competitions", "submit"' in src
            or "'competitions', 'submit'" in src
        ):
            offenders.append(path.name)
    assert not offenders, (
        f"live test(s) {offenders} contain a submit invocation — a live run would spend a "
        "REAL, IRREVERSIBLE submission slot. Live tests may only READ "
        "(`competitions submissions`)."
    )
