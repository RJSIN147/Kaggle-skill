"""test_gate_policy.py — RED (Wave 0, 05-01-T2). Pins the D-05 / D-06 / D-08 submission
gate (SCORE-03). GREEN target: 05-04 Task 1 (``scripts/submission_gate.py``).

A PURE-FUNCTION matrix, no I/O (mirrors ``tests/test_metric_registry.py``). The gate is the
control that protects a scarce, IRREVERSIBLE resource, so its policy is pinned exhaustively:

  * **D-06 — "meaningful" means beating the best ALREADY-SUBMITTED CV by MORE THAN
    fold-noise**: ``margin > k * cand_std``. STRICTLY greater — a margin exactly equal to the
    noise bound is NOT meaningful. Direction-aware via ``greater_is_better``. ``k`` is
    configurable (``config.json -> submission.noise_k``; default 1.0).
  * **The FIRST submission is CLEAR.** With no prior submitted experiment there is no
    ``best_cv`` — an empty comparison set must NEVER produce a spurious block.
  * **D-05 — BLOCK BY DEFAULT with an informed human override.** Within noise =>
    ``recommendation == "BLOCKED"`` and ``requires_confirmation is True``. The framework
    never auto-submits and never silently hard-refuses; the HUMAN always makes the call.
  * **D-08 — an ASSUMED daily limit warns EVERY time**, and the LAST assumed slot is gated
    behind an explicit confirmation even when the CV recommendation is SUBMIT.

``decide()`` returns
``{"recommendation": "SUBMIT"|"BLOCKED", "reasons": [...], "warnings": [...],
   "requires_confirmation": bool}``.
"""

from __future__ import annotations

import importlib

import pytest


def _gate():
    """Import scripts/submission_gate.py (on sys.path via conftest). Absent at RED."""
    return importlib.import_module("submission_gate")


def _decide(gate, **over):
    """decide() with a CLEAR baseline: a meaningful gain, slots left, a CONFIRMED limit."""
    kwargs = {
        "cand_cv": 0.82,
        "cand_std": 0.01,
        "best_cv": 0.80,
        "greater_is_better": True,
        "remaining": 4,
        "limit_provenance": "rules_page",
    }
    kwargs.update(over)
    return gate.decide(**kwargs)


# --------------------------------------------------------------------------- #
# D-06: the noise gate, both metric directions, k configurable.
# --------------------------------------------------------------------------- #
def test_noise_gate_matrix():
    gate = _gate()
    assert gate.NOISE_K_DEFAULT == 1.0

    # --- greater_is_better=True (e.g. roc_auc): best 0.80, fold-std 0.01, k=1.0 ------
    m = gate.is_meaningful
    assert m(0.82, 0.01, 0.80, True) is True, "gain 0.020 > 1*0.01 -> meaningful"
    assert m(0.81, 0.01, 0.80, True) is False, "gain 0.010 == 1*0.01 -> STRICTLY greater required"
    assert m(0.805, 0.01, 0.80, True) is False, "gain 0.005 < 1*0.01 -> within noise"
    assert m(0.78, 0.01, 0.80, True) is False, "a gain in the WRONG direction is never meaningful"
    assert m(0.80, 0.01, 0.80, True) is False, "a tie is not an improvement"

    # --- greater_is_better=False (e.g. rmse): LOWER is better. best 0.20, std 0.01 ----
    assert m(0.18, 0.01, 0.20, False) is True, "improvement 0.020 > 0.01 -> meaningful"
    assert m(0.19, 0.01, 0.20, False) is False, "improvement 0.010 == bound -> not meaningful"
    assert m(0.195, 0.01, 0.20, False) is False, "within noise"
    assert m(0.22, 0.01, 0.20, False) is False, "WORSE (higher error) is never meaningful"

    # --- k is configurable: it flips a borderline case in both directions -------------
    assert m(0.805, 0.01, 0.80, True, k=0.0) is True, "k=0 -> any strict gain is meaningful"
    assert m(0.805, 0.01, 0.80, True, k=1.0) is False
    assert m(0.82, 0.01, 0.80, True, k=3.0) is False, "a stricter k blocks a 2-sigma gain"
    assert m(0.195, 0.01, 0.20, False, k=0.0) is True
    assert m(0.195, 0.01, 0.20, False, k=1.0) is False

    # A zero fold-std collapses the bound to 0 => any strict gain clears.
    assert m(0.8001, 0.0, 0.80, True) is True
    assert m(0.80, 0.0, 0.80, True) is False


# --------------------------------------------------------------------------- #
# The baseline case: the FIRST submission is CLEAR, never a spurious block.
# --------------------------------------------------------------------------- #
def test_first_submission_is_clear():
    gate = _gate()

    # No prior SUBMITTED experiment => best_cv is None => the comparison set is empty.
    assert gate.is_meaningful(0.55, 0.30, None, True) is True
    assert gate.is_meaningful(0.55, 0.30, None, False) is True
    # Even a huge fold-std cannot block the first submission — there is nothing to beat.
    assert gate.is_meaningful(0.10, 99.0, None, True) is True

    out = _decide(gate, best_cv=None, cand_cv=0.55, cand_std=0.30)
    assert out["recommendation"] == "SUBMIT"
    assert out["requires_confirmation"] is False
    assert isinstance(out["reasons"], list) and out["reasons"]
    assert isinstance(out["warnings"], list)


# --------------------------------------------------------------------------- #
# D-05: BLOCK BY DEFAULT when the gain is within fold-noise.
# --------------------------------------------------------------------------- #
def test_blocked_by_default_when_within_noise():
    gate = _gate()

    out = _decide(gate, cand_cv=0.805)  # gain 0.005 <= 1 * 0.01 -> within noise
    assert out["recommendation"] == "BLOCKED"
    # D-05: not a hard refusal — the human may consciously confirm and proceed.
    assert out["requires_confirmation"] is True
    assert out["reasons"], "a BLOCKED decision must say WHY"

    # A meaningful gain against the same baseline clears without confirmation.
    clear = _decide(gate, cand_cv=0.82)
    assert clear["recommendation"] == "SUBMIT"
    assert clear["requires_confirmation"] is False

    # The recommendation vocabulary is exactly two values.
    assert out["recommendation"] in ("SUBMIT", "BLOCKED")
    assert clear["recommendation"] in ("SUBMIT", "BLOCKED")


# --------------------------------------------------------------------------- #
# D-08: an ASSUMED limit warns EVERY time; the LAST assumed slot needs confirmation.
# --------------------------------------------------------------------------- #
def test_assumed_limit_last_slot():
    gate = _gate()

    def _warns(out):
        return " ".join(out["warnings"]).upper()

    # The warning rides on EVERY decision under an assumed limit — cleared or blocked.
    for remaining in (5, 4, 3, 2, 1):
        out = _decide(gate, remaining=remaining, limit_provenance="assumed_default")
        assert "ASSUMED" in _warns(out), (
            f"D-08: the assumed-budget warning must appear on EVERY decision "
            f"(remaining={remaining}), not only on the last slot"
        )
    blocked = _decide(gate, cand_cv=0.805, remaining=3, limit_provenance="assumed_default")
    assert "ASSUMED" in _warns(blocked)

    # A CONFIRMED limit never carries the assumed warning.
    confirmed = _decide(gate, remaining=1, limit_provenance="rules_page")
    assert "ASSUMED" not in _warns(confirmed)

    # THE LAST ASSUMED SLOT: requires_confirmation even though the CV says SUBMIT.
    last = _decide(gate, remaining=1, limit_provenance="assumed_default")
    assert last["recommendation"] == "SUBMIT", "the CV signal is unchanged — it is still a clear gain"
    assert last["requires_confirmation"] is True, (
        "D-08: never spend the FINAL ASSUMED slot without explicit human confirmation"
    )
    assert "ASSUMED" in _warns(last)

    # With slots to spare under an assumed limit, a clear gain does NOT need confirmation
    # (D-08 gates the LAST slot only — it is not a refuse-until-confirmed regime).
    spare = _decide(gate, remaining=2, limit_provenance="assumed_default")
    assert spare["recommendation"] == "SUBMIT"
    assert spare["requires_confirmation"] is False

    # The same last slot under a CONFIRMED limit needs no confirmation.
    assert confirmed["recommendation"] == "SUBMIT"
    assert confirmed["requires_confirmation"] is False


# --------------------------------------------------------------------------- #
# No slots left (or an uncountable budget) => BLOCKED regardless of the CV signal.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("remaining", [0, -1, -3])
def test_zero_remaining_blocks(remaining):
    gate = _gate()

    # A spectacular CV gain cannot buy a slot that does not exist.
    out = _decide(gate, cand_cv=0.99, cand_std=0.001, remaining=remaining)
    assert out["recommendation"] == "BLOCKED"
    assert out["reasons"], "the block must say why (no remaining budget)"

    # And it blocks for the first submission too (nothing special-cases the baseline here).
    first = _decide(gate, best_cv=None, remaining=remaining)
    assert first["recommendation"] == "BLOCKED"
