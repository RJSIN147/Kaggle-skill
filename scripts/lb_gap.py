#!/usr/bin/env python3
"""lb_gap.py — the CV→LB gap trend and the D-10 rank-inversion divergence alarm (SCORE-02).

A PURE, DERIVED view (D-11). `control/submissions.jsonl` (the canonical leaderboard record,
owned by `submissions_log`) is joined against `control/ledger.jsonl` (the canonical CV record,
owned by `experiment_meta`) on `exp_id`. The leaderboard score is NEVER written back into the
experiment folder's recorded metadata — that folder is IMMUTABLE after record, and a copy of the
LB score there would be a second source of truth to keep in sync. Deriving the view instead also
handles MANY SUBMISSIONS PER EXPERIMENT for free, which a single per-experiment field cannot.

CV REMAINS THE DECISION METRIC (SCORE-02). Nothing here selects, ranks or endorses an experiment:
the gap is OBSERVED and TRENDED, and the alarm tells the user when CV has stopped being
trustworthy. No LB number is ever allowed to override a CV-based decision.

WHY RANK INVERSION AND NOT AN |CV − LB| THRESHOLD (D-10):
    A large but STABLE offset between CV and LB is usually benign — different data, different
    split. What actually breaks a competition run is CV ORDERING ceasing to predict LB ordering:
    experiment B has the better CV, yet scores WORSE on the leaderboard. That is the moment CV
    stops being a trustworthy decision metric. Rank inversion detects exactly that, and it is
    SCALE-FREE: identical logic for AUC, RMSE and LogLoss with no per-competition tuning, no
    magic threshold to pick, and no units to get wrong.

HONESTY BELOW TWO POINTS:
    An inversion needs a PAIR. With 0 or 1 scored submissions there is no signal, so the renderer
    says exactly that ("needs >=2 scored submissions (have N)") rather than printing a
    reassuring, fabricated all-clear.

NO FABRICATED ZEROS:
    Only SCORED submissions carrying a NON-None `public_score` enter the view.
    `submissions_log.parse_score` maps Kaggle's `""` to None (never 0.0), so an unscored row can
    never sneak in as a catastrophic 0.0 and fire a bogus alarm.

Portability (CLAUDE.md §Stack Patterns): stdlib-only, importable, NO side effects on import, no
`main()`, and NO I/O of any kind — every function takes ALREADY-LOADED row lists. The caller
(`regen_strategy.py`) owns the reading; this module owns the arithmetic. That is what lets the
whole contract be tested without a filesystem and without touching Kaggle.
"""

from __future__ import annotations

import itertools

# The exact honesty line the renderer emits below two scored points. Pinned as a constant so the
# alarm's "I have no signal" wording can never drift into something that reads like an all-clear.
NOT_ENOUGH_DATA = "Divergence alarm: needs >=2 scored submissions (have {n})."


def _is_number(value) -> bool:
    """True for a real int/float (bools are NOT numbers here)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _better(x: float, y: float, greater_is_better: bool) -> bool:
    """Is `x` a BETTER score than `y` under the metric's direction? (strict; ties are neither).

    The SAME direction governs both sides of the comparison: Kaggle reports `publicScore` in the
    competition's OWN metric, so a higher AUC is better on the leaderboard exactly as it is in CV,
    and a lower RMSE is better on both.
    """
    return x > y if greater_is_better else x < y


def _fmt(value) -> str:
    """Render a score compactly (0.77, not 0.7700000000000001)."""
    return f"{value:g}" if _is_number(value) else "—"


def join_cv_lb(sub_rows, ledger_rows) -> list[dict]:
    """The DERIVED CV↔LB view: one dict per SCORED submission that has a matching CV (D-11).

    Emits `{exp_id, cv_mean, cv_std, lb_score, gap, kaggle_ref, scored_at}` with
    `gap = lb_score - cv_mean`, ordered by `scored_at` (falling back to `submitted_at`) ASCENDING
    — that ordering IS the trend criterion 2 asks for.

    EXCLUDED, deliberately and without coercion:
      * PENDING rows — accepted but not yet scored; there is no number to compare.
      * FAILED rows — Kaggle rejected them; there is no number at all.
      * SCORED rows whose `public_score` is None (Kaggle's `""`) — a defensive `float(x or 0)`
        here would invent an LB score of 0.0, which is indistinguishable from a genuinely
        catastrophic result and would fire a false alarm. We never invent a number.
      * rows whose `exp_id` is null (an out-of-band submission back-filled by
        `fetch_lb --reconcile`) or absent from the ledger — with no CV there is nothing to
        compare against.
      * ledger rows that are not `SUCCESS`, or that carry no numeric `cv_mean`.

    MANY SUBMISSIONS PER EXPERIMENT are handled naturally: each scored submission is its own row.
    """
    by_exp: dict[str, dict] = {}
    for row in ledger_rows:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "SUCCESS":
            continue
        if not _is_number(row.get("cv_mean")):
            continue
        exp_id = row.get("exp_id")
        if isinstance(exp_id, str) and exp_id:
            by_exp[exp_id] = row

    joined: list[dict] = []
    for row in sub_rows:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "SCORED":
            continue
        lb_score = row.get("public_score")
        if not _is_number(lb_score):
            continue  # unscored (None) — never coerced to 0.0.
        exp_id = row.get("exp_id")
        if not isinstance(exp_id, str) or exp_id not in by_exp:
            continue  # no CV to compare against.

        led = by_exp[exp_id]
        cv_mean = float(led["cv_mean"])
        joined.append(
            {
                "exp_id": exp_id,
                "cv_mean": cv_mean,
                "cv_std": led.get("cv_std"),
                "lb_score": float(lb_score),
                "gap": float(lb_score) - cv_mean,
                "kaggle_ref": row.get("kaggle_ref"),
                "scored_at": row.get("scored_at") or row.get("submitted_at"),
            }
        )

    joined.sort(key=lambda r: (r["scored_at"] or "", str(r["kaggle_ref"])))
    return joined


def to_pairs(joined) -> list[tuple]:
    """`join_cv_lb` output → the `[(exp_id, cv_mean, lb_score)]` shape the alarm consumes."""
    return [(r["exp_id"], r["cv_mean"], r["lb_score"]) for r in joined]


def rank_inversions(pairs, greater_is_better: bool) -> list[tuple]:
    """Every (CV-better, LB-worse) pair — the D-10 alarm. `[]` means CV still predicts LB.

    `pairs` is `[(exp_id, cv_mean, lb_score)]`, SCORED submissions only. For each unordered pair
    an INVERSION exists when CV says one experiment wins and the LEADERBOARD says the other does.
    Returns `(better_cv_id, better_lb_id, cv_delta, lb_delta)` so the renderer can name the actual
    numbers rather than assert a conclusion.

    SCALE-FREE and DIRECTION-AWARE: no threshold, no per-competition tuning; flipping
    `greater_is_better` flips the verdict. Requires >= 2 points to fire — with 0 or 1 the pair
    loop is empty by construction and this returns `[]`. Do NOT read that `[]` as an all-clear:
    ask :func:`alarm_state` whether the alarm CAN fire at all.
    """
    clean = [
        (i, cv, lb)
        for i, cv, lb in pairs
        if _is_number(cv) and _is_number(lb)
    ]
    inversions: list[tuple] = []
    for (a_id, a_cv, a_lb), (b_id, b_cv, b_lb) in itertools.combinations(clean, 2):
        # CV says B wins, the leaderboard says A wins.
        if _better(b_cv, a_cv, greater_is_better) and _better(a_lb, b_lb, greater_is_better):
            inversions.append((b_id, a_id, abs(b_cv - a_cv), abs(a_lb - b_lb)))
        # ...or the mirror image: CV says A wins, the leaderboard says B wins.
        elif _better(a_cv, b_cv, greater_is_better) and _better(b_lb, a_lb, greater_is_better):
            inversions.append((a_id, b_id, abs(a_cv - b_cv), abs(b_lb - a_lb)))
    return inversions


def alarm_state(pairs, greater_is_better: bool) -> dict:
    """`{"n_scored", "can_fire", "inversions"}` — the alarm plus whether it is even ENTITLED to
    speak.

    `can_fire` is False below 2 scored points. That distinction is the whole point: it is what
    lets the renderer print the honest "needs >=2 scored submissions (have N)" line instead of a
    silent, fabricated all-clear that a user would reasonably read as "CV and LB agree".
    """
    scored = [(i, cv, lb) for i, cv, lb in pairs if _is_number(cv) and _is_number(lb)]
    n_scored = len(scored)
    can_fire = n_scored >= 2
    return {
        "n_scored": n_scored,
        "can_fire": can_fire,
        "inversions": rank_inversions(scored, greater_is_better) if can_fire else [],
    }


def alarm_body(pairs, greater_is_better: bool) -> str:
    """The markdown the strategy doc splices (via `regen_strategy._lb_gap_body`).

    Three honest states, never a fourth invented one:
      * fewer than 2 scored points → the shortfall, naming HOW MANY points there actually are;
      * >= 2 points, no inversion  → CV ordering still predicts LB ordering;
      * >= 2 points, an inversion  → the alarm, naming BOTH experiments and BOTH their numbers.
    """
    state = alarm_state(pairs, greater_is_better)
    if not state["can_fire"]:
        return NOT_ENOUGH_DATA.format(n=state["n_scored"])

    n = state["n_scored"]
    inversions = state["inversions"]
    if not inversions:
        return (
            f"Divergence alarm: clear — no rank inversion across the {n} scored submissions. "
            "CV ordering still predicts leaderboard ordering."
        )

    lookup = {i: (cv, lb) for i, cv, lb in pairs}
    lines = [
        f"**Divergence alarm: RANK INVERSION across {n} scored submissions.** "
        "CV ordering has stopped predicting leaderboard ordering, so CV is no longer a "
        "trustworthy decision metric for this competition. Suspect the CV split "
        "(leakage, or a distribution the split does not reproduce) before trusting the next "
        "CV-based comparison.",
        "",
    ]
    for better_cv_id, better_lb_id, cv_delta, lb_delta in inversions:
        cv_a, lb_a = lookup.get(better_cv_id, (None, None))
        cv_b, lb_b = lookup.get(better_lb_id, (None, None))
        lines.append(
            f"- **{better_cv_id}** has the better CV ({_fmt(cv_a)} vs {_fmt(cv_b)}, "
            f"Δcv {_fmt(cv_delta)}) but the WORSE leaderboard score "
            f"({_fmt(lb_a)} vs {_fmt(lb_b)}, Δlb {_fmt(lb_delta)}) — "
            f"**{better_lb_id}** wins on the leaderboard."
        )
    return "\n".join(lines)
