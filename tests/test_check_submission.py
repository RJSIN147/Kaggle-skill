"""test_check_submission.py — RED (Wave 0, 05-01-T3). The FREE gate (SCORE-01/03, D-02).
GREEN target: 05-04 Task 2 (``scripts/check_submission.py``).

``check_submission.py`` answers *"should I submit?"* — it validates the file (D-02) and
renders the full decision material (D-05/D-06/D-08). **It is FREE: it never spends a slot.**
That freeness is asserted mechanically here, from the captured argv.

Exit codes (05-RESEARCH.md §R6, sysexits-aligned, non-colliding with 77/78/124/126/127/128+):
  * **0**  — clear to submit
  * **65** — ``VALIDATION_FAILED``   (EX_DATAERR)     — D-02 pre-submit validation failed
  * **69** — ``SUBMIT_UNSUPPORTED``  (EX_UNAVAILABLE) — D-01: competition.type in {code, unknown}
  * **75** — ``GATE_BLOCKED``        (EX_TEMPFAIL)    — D-05 block-by-default; the human may override

The gateway is monkeypatched on the importing module in every test — no CLI process is ever
spawned, and the argv assertions prove the submit subcommand is never reached.
"""

from __future__ import annotations

import importlib
import json

import pytest

from test_submit import _fake_gateway, _seed_ws

SLUG = "titanic"
EXP_ID = "exp-007"

# The sample file's real name for titanic is `gender_submission.csv` — NOT the guessed
# `sample_submission.csv`. Phase 2 already captured it; this suite proves it is REUSED.
SAMPLE_NAME = "gender_submission.csv"
SAMPLE_BODY = "PassengerId,Survived\n892,0\n893,1\n894,0\n"
GOOD_BODY = "PassengerId,Survived\n892,1\n893,0\n894,1\n"


def _check():
    """Import scripts/check_submission.py (on sys.path via conftest). Absent at RED."""
    return importlib.import_module("check_submission")


def _seed(ws, *, csv_body=GOOD_BODY, comp_type="csv", sample_body=SAMPLE_BODY,
          sample_name=SAMPLE_NAME, in_manifest=True, test_csv=True, **kw):
    """A scaffolded workspace + the Phase-2 competition-type signals + data/."""
    _seed_ws(ws, csv_body=csv_body, comp_type=comp_type, **kw)

    data = ws / "data"
    data.mkdir(parents=True, exist_ok=True)
    if sample_body is not None:
        (data / sample_name).write_text(sample_body)
    if test_csv:
        (data / "test.csv").write_text("PassengerId,Pclass\n892,3\n893,3\n894,2\n")

    (ws / "control" / "raw" / "competition-type-signals.json").write_text(
        json.dumps(
            {
                "signals": {
                    "submission_csv_in_manifest": sample_name if in_manifest else None,
                    "test_csv_in_manifest": "test.csv",
                }
            },
            indent=2,
        )
    )
    return ws


def _run(mod, ws, *extra):
    return mod.main(["--workspace", str(ws), "--exp-id", EXP_ID, *extra])


# --------------------------------------------------------------------------- #
# D-01: a code / unknown competition is REFUSED — without ever touching Kaggle.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("comp_type", ["code", "unknown", None])
def test_refuses_non_csv_type(tmp_workspace, monkeypatch, comp_type, capsys):
    mod = _check()
    gw = importlib.import_module("kaggle_gateway")
    ws = _seed(tmp_workspace, comp_type=comp_type)

    fake, calls = _fake_gateway(readback=[])
    monkeypatch.setattr(mod, "run_kaggle", fake)

    rc = _run(mod, ws)
    assert rc == gw.SUBMIT_UNSUPPORTED == 69
    assert calls == [], (
        "the D-01 type refusal must short-circuit BEFORE any Kaggle call — it costs nothing "
        "to know a CSV path is unavailable for this competition type"
    )

    captured = capsys.readouterr()
    msg = (captured.out + captured.err).lower()
    assert "kernel" in msg or "code competition" in msg, (
        "the refusal must say WHY (a code competition submits a pushed kernel version, "
        "not a CSV) rather than failing opaquely"
    )


# --------------------------------------------------------------------------- #
# ⭐ check_submission is FREE. It can NEVER spend a slot, on ANY code path.
# --------------------------------------------------------------------------- #
def test_never_submits(tmp_workspace, monkeypatch):
    """Across EVERY path (clear / blocked / validation-failed / unsupported) the captured
    argv never carries the submit subcommand. This is the gate's whole point."""
    mod = _check()

    scenarios = [
        ("clear", dict(csv_body=GOOD_BODY, comp_type="csv")),
        ("validation-failed", dict(csv_body="Wrong,Header\n1,2\n", comp_type="csv")),
        ("unsupported-type", dict(csv_body=GOOD_BODY, comp_type="code")),
        ("no-sample", dict(csv_body=GOOD_BODY, comp_type="csv", sample_body=None,
                           in_manifest=False, test_csv=False)),
    ]

    for name, kwargs in scenarios:
        ws = _seed(tmp_workspace / name, **kwargs)
        # A read-back that would BLOCK on budget (0 remaining) exercises the gate path too.
        fake, calls = _fake_gateway(readback=[])
        monkeypatch.setattr(mod, "run_kaggle", fake)

        _run(mod, ws)  # the exit code is asserted elsewhere; here only FREENESS matters

        for argv in calls:
            assert "submit" not in argv, (
                f"check_submission spent a slot on the {name!r} path — it must be FREE. "
                f"argv={argv!r}"
            )
            # The ONLY Kaggle call it may make is the read-only authoritative count.
            assert argv[:2] == ("competitions", "submissions"), (
                f"the only sanctioned call is the read-only submissions list; got {argv!r}"
            )


# --------------------------------------------------------------------------- #
# D-02: the four validation failures, each with a PRECISE message. Exit 65.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "case,body,needle",
    [
        # 1. exact column headers (order-sensitive — Kaggle is).
        ("header_mismatch", "PassengerId,Prediction\n892,1\n893,0\n894,1\n", "header"),
        # 2. exact row count.
        ("row_count_mismatch", "PassengerId,Survived\n892,1\n893,0\n", "row"),
        # 3. the id SET (order-independent) — 895 is not in the sample; 894 is missing.
        ("id_set_mismatch", "PassengerId,Survived\n892,1\n893,0\n895,1\n", "id"),
        # 4. blank / nan / NA / null / inf in a PREDICTION column.
        ("blank_prediction", "PassengerId,Survived\n892,1\n893,\n894,1\n", "blank"),
        ("nan_prediction", "PassengerId,Survived\n892,1\n893,nan\n894,1\n", "blank"),
        ("na_prediction", "PassengerId,Survived\n892,1\n893,NA\n894,1\n", "blank"),
        ("null_prediction", "PassengerId,Survived\n892,1\n893,null\n894,1\n", "blank"),
        ("inf_prediction", "PassengerId,Survived\n892,1\n893,inf\n894,1\n", "blank"),
    ],
)
def test_validation_matrix(tmp_workspace, monkeypatch, capsys, case, body, needle):
    mod = _check()
    gw = importlib.import_module("kaggle_gateway")
    ws = _seed(tmp_workspace / case, csv_body=body)

    fake, calls = _fake_gateway(readback=[])
    monkeypatch.setattr(mod, "run_kaggle", fake)

    rc = _run(mod, ws)
    assert rc == gw.VALIDATION_FAILED == 65, f"{case} must fail closed with EX_DATAERR"

    out = capsys.readouterr()
    msg = (out.out + out.err).lower()
    assert needle in msg, (
        f"D-02 requires a PRECISE message naming the exact mismatch for {case!r}; "
        f"'{needle}' is absent from the output"
    )
    assert not [c for c in calls if "submit" in c], "a failed file never reaches Kaggle"


def test_validation_happy_path(tmp_workspace, monkeypatch):
    """A well-formed file against the sample validates clean and the gate clears (exit 0)."""
    mod = _check()
    ws = _seed(tmp_workspace, csv_body=GOOD_BODY)

    # An empty read-back = no submissions today = full budget, and the ledger's single
    # experiment is the FIRST submission (best_cv is None) => CLEAR (never a spurious block).
    fake, calls = _fake_gateway(readback=[])
    monkeypatch.setattr(mod, "run_kaggle", fake)

    assert _run(mod, ws) == 0


# --------------------------------------------------------------------------- #
# D-02: the sample-resolution ladder. REUSE Phase 2's signal, don't re-derive it.
# --------------------------------------------------------------------------- #
def test_sample_resolution_ladder(tmp_workspace, monkeypatch, capsys):
    mod = _check()
    gw = importlib.import_module("kaggle_gateway")
    fake, _ = _fake_gateway(readback=[])

    # --- Rung 1: control/raw/competition-type-signals.json -> submission_csv_in_manifest.
    # A DECOY `sample_submission.csv` with a DIFFERENT header sits right next to the real
    # `gender_submission.csv`. A resolver that guesses the conventional name picks the decoy
    # and reports a bogus header mismatch; the signal-driven resolver picks correctly.
    ws = _seed(tmp_workspace / "rung1", csv_body=GOOD_BODY)
    (ws / "data" / "sample_submission.csv").write_text("WrongId,WrongTarget\n1,0\n")
    monkeypatch.setattr(mod, "run_kaggle", fake)

    assert _run(mod, ws) == 0, "the manifest signal must win over a guessed sample_submission.csv"
    printed = capsys.readouterr().out
    assert SAMPLE_NAME in printed, (
        "the CHOSEN sample file must be PRINTED — the heuristic takes the first manifest "
        "match, so a human has to be able to spot a wrong pick"
    )

    # --- Rung 2: no signal -> a case-insensitive data/*submission*.csv glob.
    ws = _seed(tmp_workspace / "rung2", csv_body=GOOD_BODY, in_manifest=False)
    monkeypatch.setattr(mod, "run_kaggle", fake)
    assert _run(mod, ws) == 0
    assert SAMPLE_NAME in capsys.readouterr().out

    # --- Rung 3: no sample anywhere -> derive the expected id SET from data/test.csv's
    # first column (D-02's explicit fallback). The good file's ids match test.csv's.
    ws = _seed(
        tmp_workspace / "rung3", csv_body=GOOD_BODY, sample_body=None, in_manifest=False
    )
    monkeypatch.setattr(mod, "run_kaggle", fake)
    assert _run(mod, ws) == 0
    assert "test.csv" in capsys.readouterr().out

    # ...and the fallback still CATCHES a bad id set (it is a real check, not a rubber stamp).
    ws = _seed(
        tmp_workspace / "rung3bad",
        csv_body="PassengerId,Survived\n892,1\n893,0\n999,1\n",
        sample_body=None,
        in_manifest=False,
    )
    monkeypatch.setattr(mod, "run_kaggle", fake)
    assert _run(mod, ws) == gw.VALIDATION_FAILED

    # --- Rung 4: nothing to validate against at all -> FAIL CLOSED (65). Never submit
    # an unvalidated file.
    ws = _seed(
        tmp_workspace / "rung4",
        csv_body=GOOD_BODY,
        sample_body=None,
        in_manifest=False,
        test_csv=False,
    )
    monkeypatch.setattr(mod, "run_kaggle", fake)
    assert _run(mod, ws) == gw.VALIDATION_FAILED, (
        "with no sample AND no test.csv there is nothing to validate against — fail closed"
    )


# --------------------------------------------------------------------------- #
# CR-03 — a candidate with NO readable CV is never rendered "CLEAR to submit".
# --------------------------------------------------------------------------- #
def test_missing_cv_is_never_clear(tmp_workspace, monkeypatch, capsys):
    """A ledger SUCCESS row with a null ``cv_mean`` must BLOCK, not clear (exit 75).

    This is the FIRST-submission path (an empty submissions.jsonl => ``best_cv is None``),
    which is exactly where the gate used to short-circuit to SUBMIT before it had read the
    candidate at all. The rendered verdict then said ``CV: None +/- None`` and
    ``CLEAR to submit`` — and exited 0, which SKILL.md defines as "go spend the slot".
    """
    mod = _check()
    gw = importlib.import_module("kaggle_gateway")
    ws = _seed(tmp_workspace, csv_body=GOOD_BODY, cv_mean=None)

    fake, calls = _fake_gateway(readback=[])  # empty => full budget, no prior submission
    monkeypatch.setattr(mod, "run_kaggle", fake)

    rc = _run(mod, ws)
    out = capsys.readouterr()
    printed = out.out + out.err

    assert rc == gw.GATE_BLOCKED == 75, (
        "an experiment whose CV the framework cannot read must never exit 0 — exit 0 means "
        "CLEAR and the skill proceeds to spend a real, irreversible slot"
    )
    assert "CLEAR to submit" not in printed
    assert "RECOMMENDATION: BLOCKED" in printed
    assert not [c for c in calls if "submit" in c], "the gate is FREE on this path too"
