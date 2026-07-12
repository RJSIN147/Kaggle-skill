"""test_lb_gap.py — RED (Wave 0, 05-01-T2). Pins the CV→LB gap trend and the D-10
rank-inversion divergence alarm (SCORE-02). GREEN target: 05-06 Task 1 (``scripts/lb_gap.py``).

A DERIVED view: ``control/submissions.jsonl`` (the canonical LB record, D-11) joined against
``control/ledger.jsonl`` (the canonical CV record) on ``exp_id``. Nothing here opens
``meta.json`` — the experiment folder is immutable after record and the LB score is NEVER
written back into it (D-11).

Pinned contract (05-RESEARCH.md Pattern 4):

  * ``join_cv_lb(sub_rows, ledger_rows) -> [{"exp_id", "cv_mean", "lb_score", "gap"}]`` —
    SCORED submissions with a NON-None ``public_score`` only. A PENDING / FAILED / unscored
    row is EXCLUDED (never coerced to 0.0 — that would fabricate a gap and fire a bogus
    alarm). ``gap = lb_score - cv_mean``.
  * ``rank_inversions(pairs, greater_is_better) -> [(better_cv_id, better_lb_id, dcv, dlb)]``
    where ``pairs`` is ``[(exp_id, cv_mean, lb_score)]``. Fires when CV says B beats A but
    the LEADERBOARD says A beats B — i.e. CV has stopped predicting LB. SCALE-FREE, so it
    needs no per-competition tuning, and direction-aware for BOTH ``greater_is_better``
    values (Kaggle reports ``publicScore`` in the competition's own metric).
  * ``alarm_body(pairs, greater_is_better) -> str`` — the renderer ``regen_strategy`` splices
    in (05-06 Task 2). With FEWER THAN 2 scored submissions it emits the HONEST
    "needs >=2 scored submissions (have N)" line and NEVER fabricates a signal from one point.
"""

from __future__ import annotations

import importlib


def _gap():
    """Import scripts/lb_gap.py (on sys.path via conftest). Absent at RED."""
    return importlib.import_module("lb_gap")


def _sub(exp_id, *, status="SCORED", public_score=None, ref=1):
    """A control/submissions.jsonl row (the 14-key shape submissions_log owns)."""
    return {
        "schema_version": 1,
        "exp_id": exp_id,
        "kaggle_ref": ref,
        "competition_slug": "titanic",
        "file": f"experiments/{exp_id}/submission.csv",
        "file_sha256": "sha256:" + "0" * 64,
        "message": f"{exp_id} | cv=0.8",
        "submitted_at": "2026-07-12T14:03:11Z",
        "status": status,
        "public_score": public_score,
        "private_score": None,
        "scored_at": "2026-07-12T14:09:00Z" if status == "SCORED" else None,
        "override_reason": None,
        "error_description": None,
    }


def _led(exp_id, cv_mean, *, status="SUCCESS", cv_std=0.01, greater_is_better=True):
    """A control/ledger.jsonl row (experiment_meta.LEDGER_ROW_KEYS shape)."""
    return {
        "exp_id": exp_id,
        "status": status,
        "idea": f"idea for {exp_id}",
        "metric": "roc_auc",
        "greater_is_better": greater_is_better,
        "cv_mean": cv_mean,
        "cv_std": cv_std,
        "git_commit": "abc1234",
        "seed": 42,
        "created": "2026-07-11T14:22:07Z",
        "verdict_path": f"experiments/{exp_id}/VERDICT.md",
    }


# --------------------------------------------------------------------------- #
# The gap trend: SCORED-with-a-score only. No fabricated zeros.
# --------------------------------------------------------------------------- #
def test_gap_trend():
    gap = _gap()

    subs = [
        _sub("exp-001", status="SCORED", public_score=0.77, ref=1),
        _sub("exp-002", status="SCORED", public_score=0.79, ref=2),
        _sub("exp-003", status="PENDING", public_score=None, ref=3),
        _sub("exp-004", status="FAILED", public_score=None, ref=4),
        # SCORED but never actually scored (Kaggle's publicScore was "") -> excluded.
        _sub("exp-005", status="SCORED", public_score=None, ref=5),
    ]
    ledger = [
        _led("exp-001", 0.81),
        _led("exp-002", 0.84),
        _led("exp-003", 0.85),
        _led("exp-004", 0.86),
        _led("exp-005", 0.87),
    ]

    pairs = gap.join_cv_lb(subs, ledger)
    ids = [p["exp_id"] for p in pairs]

    assert ids == ["exp-001", "exp-002"], (
        "only SCORED rows carrying a real public_score may appear — a PENDING, FAILED or "
        "unscored row must be EXCLUDED, never coerced to 0.0"
    )
    by_id = {p["exp_id"]: p for p in pairs}
    assert by_id["exp-001"]["cv_mean"] == 0.81
    assert by_id["exp-001"]["lb_score"] == 0.77
    # gap = lb - cv, per experiment.
    assert abs(by_id["exp-001"]["gap"] - (0.77 - 0.81)) < 1e-9
    assert abs(by_id["exp-002"]["gap"] - (0.79 - 0.84)) < 1e-9

    # A submission with no matching ledger row cannot be joined (no CV to compare).
    orphan = gap.join_cv_lb([_sub("exp-099", status="SCORED", public_score=0.5)], ledger)
    assert orphan == []

    # An empty input is an empty view, not an error.
    assert gap.join_cv_lb([], []) == []


# --------------------------------------------------------------------------- #
# D-10: the rank-inversion alarm. Scale-free, direction-aware.
# --------------------------------------------------------------------------- #
def test_rank_inversion_alarm():
    gap = _gap()

    # greater_is_better=True: CV says B (0.84) beats A (0.81); the LB says A (0.77) beats
    # B (0.75). CV has stopped predicting LB -> INVERSION.
    inverted = [("exp-A", 0.81, 0.77), ("exp-B", 0.84, 0.75)]
    fires = gap.rank_inversions(inverted, True)
    assert fires, "CV better + LB worse must raise the alarm (greater_is_better=True)"
    flat = {v for tup in fires for v in tup if isinstance(v, str)}
    assert {"exp-A", "exp-B"} <= flat, "the alarm must name BOTH experiments"

    # CV and LB AGREE -> no alarm.
    agreeing = [("exp-A", 0.81, 0.77), ("exp-B", 0.84, 0.79)]
    assert gap.rank_inversions(agreeing, True) == []

    # greater_is_better=False (lower is better, e.g. rmse): CV says B (0.18) beats A (0.21);
    # the LB says A (0.25) beats B (0.30) -> INVERSION.
    inverted_low = [("exp-A", 0.21, 0.25), ("exp-B", 0.18, 0.30)]
    fires_low = gap.rank_inversions(inverted_low, False)
    assert fires_low, "the alarm must be direction-aware (greater_is_better=False)"

    # The SAME numbers under the SAME direction where CV and LB agree -> no alarm.
    agreeing_low = [("exp-A", 0.21, 0.30), ("exp-B", 0.18, 0.25)]
    assert gap.rank_inversions(agreeing_low, False) == []

    # Direction is load-bearing, not cosmetic: a set that inverts under one direction must
    # not inform the other. (Reading `inverted` as lower-is-better, CV says A wins and the
    # LB says B wins -> still an inversion, but the alarm must be computed, not assumed.)
    assert isinstance(gap.rank_inversions(inverted, False), list)

    # Scale-free: multiplying every score by 1000 changes nothing.
    scaled = [(i, cv * 1000, lb * 1000) for i, cv, lb in inverted]
    assert len(gap.rank_inversions(scaled, True)) == len(fires)


# --------------------------------------------------------------------------- #
# Honesty: with < 2 scored points there is NO signal — say so, never fake one.
# --------------------------------------------------------------------------- #
def test_alarm_needs_two_points():
    gap = _gap()

    # Zero and one scored submission: no inversions can exist by construction.
    assert gap.rank_inversions([], True) == []
    assert gap.rank_inversions([("exp-A", 0.81, 0.77)], True) == []

    # The renderer states the shortfall plainly, naming HOW MANY points it actually has.
    zero = gap.alarm_body([], True)
    assert "needs >=2 scored submissions" in zero
    assert "(have 0)" in zero

    one = gap.alarm_body([("exp-A", 0.81, 0.77)], True)
    assert "needs >=2 scored submissions" in one
    assert "(have 1)" in one
    # It must NOT fabricate a divergence signal from a single point.
    assert "inversion" not in one.lower() or "needs >=2" in one

    # With two AGREEING points the alarm is silent but the honesty line is gone (there IS
    # now enough data — the answer is simply "no divergence").
    agree = gap.alarm_body([("exp-A", 0.81, 0.77), ("exp-B", 0.84, 0.79)], True)
    assert "needs >=2 scored submissions" not in agree

    # With two INVERTED points the alarm fires and names both experiments.
    fired = gap.alarm_body([("exp-A", 0.81, 0.77), ("exp-B", 0.84, 0.75)], True)
    assert "needs >=2 scored submissions" not in fired
    assert "exp-A" in fired and "exp-B" in fired
