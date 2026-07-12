#!/usr/bin/env python3
"""submission_gate.py — the PURE D-05 / D-06 / D-08 submission policy (SCORE-03).

This module decides ONE thing: given a candidate experiment's CV, the best CV that has
ALREADY been submitted, and today's remaining budget — should the framework recommend
spending a scarce, IRREVERSIBLE daily submission slot?

It is deliberately I/O-FREE: no filesystem, no network, no clock, no argparse entry
point, no side effects on import. Every function is pure, so ``tests/test_gate_policy.py``
is an exhaustive decision matrix rather than a fixture-heavy integration test. The caller
(``check_submission.py``) does all the reading and all the printing; this module only
computes. That separation is what makes the policy — the part that protects the
irreversible resource — cheap to reason about and impossible to get wrong by accident.

────────────────────────────────────────────────────────────────────────────────────────
D-05 is the load-bearing decision and is held EXACTLY:

    The framework NEVER auto-submits and NEVER silently hard-refuses.

It computes the material, TAKES A POSITION (``BLOCKED`` by default when the gain is
within fold-noise), and hands the human an informed override. A recommendation is not a
verdict. ``requires_confirmation`` is the mechanism: it says "a human must consciously
say yes", never "the answer is no".

D-07: the override reason is OPTIONAL. Nothing here demands one, and no returned state
requires one.

────────────────────────────────────────────────────────────────────────────────────────
WHY ``NOISE_K_DEFAULT = 1.0`` (D-06)

``cv_std`` as emitted by ``run_cv`` is the **population standard deviation of the fold
scores** — NOT the standard error of the mean (which at 5 folds is ~2.2x smaller). So
requiring a gain to exceed one FULL fold-std is a deliberately **CONSERVATIVE** bar: it
is roughly a 2-sigma test in standard-error terms.

That conservatism is correct here, and the asymmetry is the whole argument:

  * a false "SUBMIT" wastes a slot — scarce, irreversible, capped per UTC day;
  * a false "BLOCKED" costs ONE KEYSTROKE, because D-05 guarantees the human can
    override immediately with full knowledge of the numbers.

The two error costs are not remotely symmetric, so the bar leans toward the cheap
mistake. A genuinely high-variance competition can lower it via
``config.json -> submission.noise_k``; readers MUST tolerate that key being ABSENT (an
already-scaffolded workspace predates it) and fall back to ``NOISE_K_DEFAULT``.
"""

from __future__ import annotations

import math

# ⚠ FLOATING-POINT SAFETY AT THE BOUND. The comparison `margin > k * cv_std` is a
# STRICT inequality evaluated on IEEE-754 doubles, where the interesting case sits
# EXACTLY on the boundary — and lands on the wrong side of it:
#
#     0.81 - 0.80  ==  0.010000000000000009   >   1.0 * 0.01   ->   True (!!)
#
# A gain of exactly one fold-std would therefore be scored "meaningful" purely from
# representation error, spending an irreversible slot on a difference the policy
# explicitly rules out. So a margin within this tolerance of the bound is treated as ON
# the bound (and thus NOT strictly greater). The tolerance is far below any CV gain that
# could matter and far above double-rounding noise.
_REL_TOL = 1e-9
_ABS_TOL = 1e-12

# The fold-noise multiplier. See the module docstring for why one full population
# fold-std — and not the (~2.2x smaller) standard error of the mean — is the default bar.
NOISE_K_DEFAULT = 1.0

# The complete recommendation vocabulary. Exactly two values: the gate never invents a
# third, softer state to hide behind.
RECOMMENDATIONS = ("SUBMIT", "BLOCKED")

# The config value that marks the daily limit as GUESSED rather than read from the
# competition's rules page (D-08).
ASSUMED_PROVENANCE = "assumed_default"


def _as_number(value) -> float | None:
    """``value`` as a float, or ``None`` when it is not a real number.

    ``bool`` is excluded on purpose: ``True`` is an ``int`` in Python, and silently
    scoring ``1.0`` off a stray boolean is exactly the confident-but-wrong arithmetic
    this project fails closed against.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _readable_cv(value) -> float | None:
    """``value`` as a FINITE float, or ``None`` — a CV we cannot READ is not a CV.

    Stricter than :func:`_as_number` on purpose: ``nan`` and ``inf`` are floats, but they
    are not scores. A ``nan`` candidate silently loses every comparison it enters (all
    ``nan`` comparisons are ``False``), so it would slip through a bare numeric check and
    then be reasoned about as though it were a real number.
    """
    number = _as_number(value)
    if number is None or not math.isfinite(number):
        return None
    return number


def is_meaningful(cand_cv, cand_std, best_cv, greater_is_better, k=NOISE_K_DEFAULT) -> bool:
    """Does ``cand_cv`` beat ``best_cv`` by MORE THAN fold-noise? (D-06)

    ``margin > k * cand_std`` — **STRICTLY** greater. A gain exactly equal to the noise
    bound is NOT meaningful: at the bound, the "improvement" is indistinguishable from
    fold-to-fold jitter, and a slot is too expensive to spend on a coin-flip.

    Direction-aware via ``greater_is_better`` (rmse improves DOWNWARD). A gain in the
    wrong direction produces a negative margin and can therefore never pass — no special
    case is needed for "worse".

    **The CANDIDATE IS READ FIRST.** ⚠ ORDER IS LOAD-BEARING (CR-03). A candidate whose
    ``cand_cv`` is absent / null / a string / ``nan`` carries NO decision metric, and CV is
    THE decision metric (SCORE-02) — so it is rejected BEFORE any other rule is consulted.
    Checking the empty-comparison-set shortcut first would declare such a candidate
    "meaningful" on the very first submission (there is no baseline it must fail against),
    and a scarce, irreversible slot would be spent on a number the framework could not
    read. Garbage input is rejected before a shortcut can bless it.

    **The FIRST submission is CLEAR** — once the candidate is known to be readable.
    ``best_cv is None`` means no prior experiment has been submitted, so the comparison set
    is EMPTY. An empty comparison set must NEVER manufacture a block: there is nothing to
    beat, and refusing to make the very first submission because it cannot out-perform a
    baseline that does not exist would be an absurd, self-inflicted deadlock.

    Fail-closed on garbage: a non-numeric ``cand_cv`` / ``best_cv`` / ``cand_std`` / ``k``
    returns ``False``. A numeric ``0.0`` std is NOT garbage — it collapses the bound to
    zero, so any strictly-positive margin clears (a perfectly stable CV genuinely has no
    fold-noise to clear). But an ABSENT std (``None``) is unknowable noise, and claiming
    a gain exceeds a bound we could not compute would be a fabricated confidence.
    """
    # ⚠ CR-03: the candidate is validated BEFORE the baseline shortcut. No readable CV =>
    # nothing to reason about => fail closed. This MUST stay above the `best_cv is None`
    # return, or a CV-less experiment clears on its first submission.
    candidate = _readable_cv(cand_cv)
    if candidate is None:
        return False

    # The baseline case: an empty comparison set is always clear.
    if best_cv is None:
        return True

    baseline = _as_number(best_cv)
    std = _as_number(cand_std)
    multiplier = _as_number(k)
    if baseline is None or std is None or multiplier is None:
        return False
    if std < 0 or multiplier < 0:
        return False  # a negative noise bound is nonsense input — fail closed.

    margin = (candidate - baseline) if greater_is_better else (baseline - candidate)
    bound = multiplier * std
    # STRICTLY greater — and a margin that merely LOOKS greater because of IEEE-754
    # representation error (see _REL_TOL) is on the bound, not past it.
    if math.isclose(margin, bound, rel_tol=_REL_TOL, abs_tol=_ABS_TOL):
        return False
    return margin > bound


def decide(
    *,
    cand_cv,
    cand_std,
    best_cv,
    greater_is_better,
    remaining,
    limit_provenance,
    k=NOISE_K_DEFAULT,
) -> dict:
    """The whole D-05 + D-06 + D-08 policy, as one pure function.

    Returns::

        {"recommendation": "SUBMIT" | "BLOCKED",
         "reasons":              [str, ...],   # WHY, naming the actual numbers
         "warnings":             [str, ...],   # caveats that ride along regardless
         "requires_confirmation": bool}        # a human must consciously say yes

    Rules, in order:

    1. ``remaining is None`` — the budget could NOT be established (Kaggle's authoritative
       list was unfetchable, or a row's status/date was unparseable → the ``-1``
       ``COUNT_UNAVAILABLE`` sentinel). BLOCK. We never guess a count (D-04): guessing high
       spends a slot that may not exist. ``requires_confirmation`` is ``False`` — there is
       nothing coherent to confirm, because we do not know what we would be confirming.
    2. ``remaining <= 0`` — the budget is exhausted. BLOCK regardless of how spectacular
       the CV signal is: a gain cannot buy a slot that does not exist.
    3. ``cand_cv`` is UNREADABLE (absent / null / a string / ``nan``) — the candidate has
       no decision metric at all. BLOCK, with ``requires_confirmation`` ``False``: there
       is nothing coherent to confirm about a number we could not read. ⚠ This rule sits
       ABOVE the empty-comparison-set shortcut on purpose (CR-03) — a first submission
       has no baseline to fail against, so a CV-less candidate would otherwise sail
       straight through to SUBMIT.
    4. ``limit_provenance == "assumed_default"`` — the daily limit was GUESSED, not read
       from the rules page. Warn on EVERY decision (D-08), and gate the LAST assumed slot
       behind explicit confirmation even when the CV says SUBMIT: if the real limit is
       lower than assumed, that "last" slot may never have existed.
    5. The CV signal (D-06 via :func:`is_meaningful`). Meaningful → SUBMIT. Within noise →
       BLOCKED **with** ``requires_confirmation`` — D-05's block-by-default plus an
       informed human override, never a silent hard refusal.

    Every reason and warning is a plain human-readable sentence that names the REAL
    numbers. This module does not print them; ``check_submission.py`` renders them and
    ``SKILL.md`` holds the human loop.
    """
    reasons: list[str] = []
    warnings: list[str] = []

    # D-08 — the assumed-budget caveat rides on EVERY decision, cleared or blocked. A
    # warning that only appears on the last slot is a warning the user has never been
    # trained to read.
    assumed = limit_provenance == ASSUMED_PROVENANCE
    if assumed:
        warnings.append(
            "the daily submission limit is ASSUMED (5/day) — it was NOT confirmed "
            "against this competition's rules page. The real limit may be lower."
        )

    # Rule 1 — the budget is UNKNOWABLE. Fail closed; never guess a count (D-04).
    if remaining is None:
        reasons.append(
            "BLOCKED: today's remaining submission budget could not be established "
            "(Kaggle's authoritative submission list was unfetchable, or a row carried "
            "an unparseable status/date). The count is never guessed — a guess that "
            "runs high spends a slot that may not exist."
        )
        return {
            "recommendation": "BLOCKED",
            "reasons": reasons,
            "warnings": warnings,
            "requires_confirmation": False,
        }

    # Rule 2 — no slots left. The CV signal is irrelevant: there is nothing to spend.
    left = _as_number(remaining)
    if left is None:
        reasons.append(
            f"BLOCKED: the remaining budget is not a number ({remaining!r}) — fail closed."
        )
        return {
            "recommendation": "BLOCKED",
            "reasons": reasons,
            "warnings": warnings,
            "requires_confirmation": False,
        }
    if left <= 0:
        reasons.append(
            f"BLOCKED: no submission slots remain today (remaining={int(left)}, UTC day). "
            "Even a large CV gain cannot buy a slot that does not exist — wait for the "
            "UTC day to roll over."
        )
        return {
            "recommendation": "BLOCKED",
            "reasons": reasons,
            "warnings": warnings,
            "requires_confirmation": False,
        }

    # Rule 3 — the candidate has NO READABLE CV (CR-03). Checked before the baseline
    # shortcut below, which would otherwise declare the very first submission clear
    # without ever looking at the number. CV is the decision metric; there is no
    # decision to make without one, and no fold-noise verdict worth rendering.
    # requires_confirmation is False: this is garbage input, not a judgment call — there
    # is nothing coherent for a human to confirm.
    if _readable_cv(cand_cv) is None:
        reasons.append(
            f"BLOCKED: this experiment has no readable CV score (cv_mean={cand_cv!r}). "
            "CV is the decision metric (SCORE-02) — a scarce, irreversible slot is never "
            "spent on a number the framework could not read. Re-run the experiment and "
            "record it (record_experiment.py) so it carries a real cv_mean."
        )
        return {
            "recommendation": "BLOCKED",
            "reasons": reasons,
            "warnings": warnings,
            "requires_confirmation": False,
        }

    # Rules 4 + 5 — the CV signal, and the last-assumed-slot gate.
    meaningful = is_meaningful(cand_cv, cand_std, best_cv, greater_is_better, k=k)

    std = _as_number(cand_std)
    multiplier = _as_number(k)
    bound = (multiplier * std) if (std is not None and multiplier is not None) else None

    if best_cv is None:
        reasons.append(
            f"SUBMIT: this is the FIRST submission — no experiment has been submitted "
            f"yet, so there is no CV to beat (candidate cv={cand_cv}). An empty "
            f"comparison set is never a block."
        )
    else:
        candidate = _as_number(cand_cv)
        baseline = _as_number(best_cv)
        if candidate is None or baseline is None:
            margin_text = "unavailable (a CV value was missing or non-numeric)"
        else:
            margin = (candidate - baseline) if greater_is_better else (baseline - candidate)
            margin_text = f"{margin:+.6f}"
        bound_text = "unavailable (cv_std is missing)" if bound is None else f"{bound:.6f}"
        direction = "higher is better" if greater_is_better else "lower is better"

        if meaningful:
            reasons.append(
                f"SUBMIT: the gain over the best already-submitted CV is {margin_text} "
                f"({direction}), which EXCEEDS the fold-noise bound k={multiplier} * "
                f"cv_std={cand_std} = {bound_text}. The improvement is bigger than the "
                f"fold-to-fold jitter, so it is worth a slot."
            )
        else:
            reasons.append(
                f"BLOCKED: the gain over the best already-submitted CV is {margin_text} "
                f"({direction}), which does NOT exceed the fold-noise bound k="
                f"{multiplier} * cv_std={cand_std} = {bound_text}. The apparent "
                f"improvement is within fold-to-fold jitter and may be nothing at all. "
                f"D-05: this is a RECOMMENDATION, not a refusal — you may confirm and "
                f"submit anyway."
            )

    if not meaningful:
        # D-05 — block by default, with an INFORMED human override. Never a hard refusal.
        return {
            "recommendation": "BLOCKED",
            "reasons": reasons,
            "warnings": warnings,
            "requires_confirmation": True,
        }

    # D-08 — the LAST ASSUMED slot is never spent without an explicit human yes, even
    # though the CV signal itself is a clear go. If the true limit is below the assumed
    # 5/day, this slot may not exist; a wasted "last" slot is not recoverable.
    if assumed and int(left) == 1:
        warnings.append(
            "this is the LAST slot under an ASSUMED limit — if the real limit is lower "
            "than assumed, it may not exist at all. Explicit confirmation is required."
        )
        return {
            "recommendation": "SUBMIT",
            "reasons": reasons,
            "warnings": warnings,
            "requires_confirmation": True,
        }

    return {
        "recommendation": "SUBMIT",
        "reasons": reasons,
        "warnings": warnings,
        "requires_confirmation": False,
    }
