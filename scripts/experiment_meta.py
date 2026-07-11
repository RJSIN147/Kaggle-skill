#!/usr/bin/env python3
"""experiment_meta.py — the ONE source of the meta.json ⇄ ledger.jsonl schema.

``meta.json`` is the canonical per-experiment record (MEM-01 / D-10); ``ledger.jsonl``
is a DERIVED one-line-per-experiment index that the AI reasons over. Both
``record_experiment.py`` (writes a row) and ``rebuild_ledger.py`` (rebuilds all rows
from the folders) import THIS module, so the derived-row schema lives in exactly one
place — the same single-source-of-truth rationale ``competition_doc.replace_section``
embodies for section merging.

Two pure functions:

  * ``to_ledger_row(meta) -> dict`` — the exact 11-key derived subset
    (03-RESEARCH.md §Ledger line 486), sourcing ``git_commit`` + ``seed`` from
    ``meta["provenance"]`` (never top-level, so a decoy top-level value cannot
    poison provenance — T-03-02-01). Key order is fixed so a full rebuild is
    byte-stable.
  * ``validate_meta(meta) -> list[str]`` — human-readable error strings (``[]``
    == valid). A meta that fails validation must NOT be fabricated into a row
    (T-03-02-02); the rebuilder skips-and-warns instead.

Portability (CLAUDE.md §Stack Patterns): stdlib-only, importable, NO side effects on
import, NO ``main()`` — mirrors ``competition_doc.py``. Importing it pulls no ML stack
(the D-06 stdlib-plumbing split): the recorder can import it without dragging in
sklearn/pandas/numpy.
"""

from __future__ import annotations

# Canonical status enum for a recorded experiment (D-06): a validated run is
# SUCCESS; any failure of the validation ladder is FAILED (recorded WITH a
# verdict, never dropped). No other value is a valid meta status.
STATUSES = ("SUCCESS", "FAILED")

# Required top-level keys every meta.json must carry to derive a ledger row.
REQUIRED_TOP_KEYS = ("exp_id", "status")

# Provenance sub-keys that make a row auditable (EXP-04): what run, what code
# (artifact hash), what commit, what seed. All four must be present before a row
# is emitted (T-03-02-01).
REQUIRED_PROVENANCE_KEYS = ("run_id", "artifact_hash", "git_commit", "seed")

# The exact, ordered key set of a derived ledger.jsonl row (03-RESEARCH.md line 486).
LEDGER_ROW_KEYS = (
    "exp_id",
    "status",
    "idea",
    "metric",
    "greater_is_better",
    "cv_mean",
    "cv_std",
    "git_commit",
    "seed",
    "created",
    "verdict_path",
)


def to_ledger_row(meta: dict) -> dict:
    """Derive the one-line ledger.jsonl row from a canonical ``meta.json`` dict.

    Returns EXACTLY the 11 keys in ``LEDGER_ROW_KEYS`` (fixed order → byte-stable
    rebuild). ``git_commit`` and ``seed`` are read from ``meta["provenance"]``, NOT
    from any top-level key, so a tampered top-level ``git_commit``/``seed`` can never
    override the recorded provenance (T-03-02-01). A FAILED meta with a null
    ``cv_mean`` still produces a valid row (the status is carried; the null tolerated).

    This is a pure projection — it does not validate. Call ``validate_meta`` first
    when the source is untrusted (the rebuilder does).
    """
    provenance = meta.get("provenance") or {}
    return {
        "exp_id": meta.get("exp_id"),
        "status": meta.get("status"),
        "idea": meta.get("idea"),
        "metric": meta.get("metric"),
        "greater_is_better": meta.get("greater_is_better"),
        "cv_mean": meta.get("cv_mean"),
        "cv_std": meta.get("cv_std"),
        "git_commit": provenance.get("git_commit"),
        "seed": provenance.get("seed"),
        "created": meta.get("created"),
        "verdict_path": meta.get("verdict_path"),
    }


def validate_meta(meta: dict) -> list[str]:
    """Return a list of human-readable error strings; ``[]`` means well-formed.

    Checks (D-06 fail-closed posture, so a corrupt/partial meta is never fabricated
    into a plausible row — T-03-02-02):
      * ``meta`` is a JSON object;
      * required top-level keys (``exp_id``, ``status``) are present and non-empty;
      * ``status`` ∈ {SUCCESS, FAILED};
      * ``provenance`` is an object carrying all four of
        run_id / artifact_hash / git_commit / seed (present and non-empty).

    Numeric result fields (``cv_mean``/``cv_std``/``fold_scores``) are deliberately
    NOT required here: a FAILED meta legitimately carries a null ``cv_mean`` and must
    still validate (its status + provenance are what make the row auditable).
    """
    if not isinstance(meta, dict):
        return [f"meta must be a JSON object, got {type(meta).__name__}"]

    errors: list[str] = []

    for key in REQUIRED_TOP_KEYS:
        if key not in meta or meta[key] in (None, ""):
            errors.append(f"missing required key: {key}")

    status = meta.get("status")
    if status is not None and status not in STATUSES:
        errors.append(
            f"status must be one of {STATUSES}, got {status!r}"
        )

    provenance = meta.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("missing required key: provenance (must be an object)")
    else:
        for key in REQUIRED_PROVENANCE_KEYS:
            if key not in provenance or provenance[key] in (None, ""):
                errors.append(f"missing required provenance key: provenance.{key}")

    return errors
