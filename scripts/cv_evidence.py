#!/usr/bin/env python3
"""cv_evidence.py — stdlib structural CV evidence + mechanical recommendation (D-05/D-07).

The evidence half of Phase 2's analysis slice. From the downloaded CSVs it resolves
the train/test pair, derives the target column mechanically, computes the structural
signals that decide a cross-validation scheme, and writes them — plus a mechanical
``recommend`` — to ``control/raw/cv-evidence.json`` (TRACKED provenance, D-03). It
NEVER commits ``config.json`` ``cv.scheme``: that is ``analyze_data.py``'s tooling
call AFTER the AI reasons over this evidence (D-05: tooling recommends → AI reasons
→ tooling writes).

Design (D-06): this is skill PLUMBING, so it is **stdlib-only** — the CSVs are read
with the ``csv`` module, never pandas. Real adversarial validation (the one ML step)
lives in ``analyze_data.py`` behind ``uv run``; nothing here imports an ML stack.

Resolution contract (cross-plan with 02-03): the canonical pair is the
case-insensitive ``data/train.csv`` / ``data/test.csv``. If BOTH are not present the
script degrades (Phase 1 D-07 flag-don't-abort): it records a ``SKIPPED`` reason and
exits 0 — it NEVER guesses a pair from arbitrary CSVs.

Portability: self-locating (``Path(__file__)``), ``--workspace`` argparse in /
exit-code out, non-interactive. Provenance is staged by EXPLICIT path (never
``git add -A`` — that would sweep the gitignored ``control/raw/last-error.txt``).
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

CV_SCHEMES = ("GroupKFold", "TimeSeriesSplit", "StratifiedKFold", "KFold")

CV_EVIDENCE_REL = "control/raw/cv-evidence.json"

SKIP_REASON = (
    "could not resolve train.csv/test.csv under data/; name the files or set "
    "config.json cv.scheme manually"
)

# The recommendation is a NON-authoritative advisory hint (D-05). It is emitted so the
# AI has structural evidence to reason over; it is NEVER auto-committed. The AI decides
# the scheme and persists it via ``analyze_data.py --cv-scheme <enum>``.
RECOMMEND_ADVISORY_NOTE = (
    "advisory hint only — a NON-AUTHORITATIVE mechanical suggestion. The AI decides the "
    "cross-validation scheme and commits it via `analyze_data.py --cv-scheme <enum>`; the "
    "framework never auto-picks or auto-commits this value."
)

# Emitted (with ``recommend = None``) when the resolved pair has no analyzable tabular
# structure — no shared train/test columns, or an empty frame. No scheme is asserted.
NON_TABULAR_NOTE = (
    "no tabular structure detected (no shared train/test feature columns or an empty "
    "frame) — nothing recommended; the AI decides the CV scheme."
)

# A classification target is assumed to have few distinct labels; above this it is
# treated as regression (→ plain KFold). Discretionary cap (D-05 / Claude's discretion).
_MAX_CLASS_LABELS = 20
# A minority class below this fraction of rows is flagged "imbalanced" → StratifiedKFold
# earns its keep (a stratified split preserves the rare-class ratio per fold).
_IMBALANCE_FRACTION = 0.35


# --------------------------------------------------------------------------- #
# CSV loading (stdlib only — plumbing stays stdlib, D-06).
# --------------------------------------------------------------------------- #
def _read_csv(path: Path) -> tuple[list[str], list[dict]]:
    """Return ``(header, rows)`` where each row is a ``{column: value}`` dict."""
    with path.open(newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            return [], []
        rows = [dict(zip(header, r)) for r in reader if r]
    return header, rows


def resolve_pair(data_dir: Path) -> tuple[Path, Path] | None:
    """Resolve the ``train.csv`` / ``test.csv`` pair (case-insensitive) under ``data_dir``.

    Returns ``(train_path, test_path)`` when BOTH are present, else ``None`` — never
    guesses a pair from arbitrary CSVs (the cross-plan 02-03 convention is the only
    contract; anything else degrades to SKIPPED).
    """
    if not data_dir.is_dir():
        return None
    found: dict[str, Path] = {}
    for p in data_dir.iterdir():
        if p.is_file() and p.name.lower() in ("train.csv", "test.csv"):
            found[p.name.lower()] = p
    if "train.csv" in found and "test.csv" in found:
        return found["train.csv"], found["test.csv"]
    return None


# --------------------------------------------------------------------------- #
# Mechanical structural detectors.
# --------------------------------------------------------------------------- #
def _try_parse_date(value: str):
    """Parse an ISO-ish date/datetime; return a datetime or ``None``.

    Deliberately conservative: plain integers/floats (ids, numeric features) do NOT
    parse — ``fromisoformat`` and the explicit formats all reject them — so a numeric
    column is never mistaken for a datetime column.
    """
    s = (value or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _column_values(rows: list[dict], col: str) -> list[str]:
    return [r.get(col, "") for r in rows]


def detect_datetime_columns(header: list[str], rows: list[dict]) -> list[str]:
    """Columns where a strong majority of non-empty values parse as dates."""
    out = []
    for col in header:
        vals = [v for v in _column_values(rows, col) if str(v).strip() != ""]
        if len(vals) < 2:
            continue
        parsed = sum(1 for v in vals if _try_parse_date(str(v)) is not None)
        if parsed >= 2 and parsed / len(vals) >= 0.9:
            out.append(col)
    return out


def detect_id_column(train_header, test_header, train_rows) -> tuple[str | None, str]:
    """Identify the id column mechanically; return ``(id_column, method)``.

    Preference order over columns present in BOTH train and test:
      1. an exact ``id`` name (case-insensitive);
      2. an ``*id`` / ``*_id`` name whose train values are all unique;
      3. any both-columns column whose train values are all unique.
    Returns ``(None, "none")`` when nothing qualifies.
    """
    common = [c for c in train_header if c in set(test_header)]

    for c in common:
        if c.lower() == "id":
            return c, "exact-name 'id'"

    def _all_unique(col):
        vals = _column_values(train_rows, col)
        return len(vals) > 0 and len(set(vals)) == len(vals)

    for c in common:
        if (c.lower().endswith("id") or c.lower().endswith("_id")) and _all_unique(c):
            return c, "name endswith 'id' + unique"

    for c in common:
        if _all_unique(c):
            return c, "unique-valued shared column"

    return None, "none"


def _looks_continuous_numeric(vals: list[str]) -> bool:
    """True iff a column is a continuous numeric FEATURE, not a repeated-entity id.

    A genuine group id is an integer/categorical LABEL that repeats. A continuous
    numeric measure (``Age``, ``Fare``) carries fractional values — that is the signal
    the old detector missed, letting Titanic's Age/Fare (n_unique >= 10, avg group >= 2)
    masquerade as group ids. Predicate: EVERY non-empty value parses as a float AND a
    meaningful fraction carry a real decimal part. Kept conservative (fractional-only,
    not raw value-density) so a pure-integer group id is NEVER excluded here.
    """
    parsed = []
    for v in vals:
        s = str(v).strip()
        if s == "":
            continue
        try:
            parsed.append(float(s))
        except ValueError:
            return False  # any non-numeric token → not a continuous-numeric column
    if not parsed:
        return False
    n_noninteger = sum(1 for f in parsed if not float(f).is_integer())
    return n_noninteger / len(parsed) >= 0.05


def detect_group_candidates(
    header, rows, id_column, target, datetime_columns
) -> list[str]:
    """Repeated-entity (group) column candidates from the TRAIN frame.

    A group-leakage column is a *high-cardinality repeated identifier*: values repeat
    (avg group size >= 2) AND there are MANY distinct entities. Three guards keep a
    continuous numeric feature or a mostly-empty column from masquerading as a group id
    (the Gap-1 Titanic false positive on Age/Fare/Cabin):

      * a mostly-EMPTY column (> 50% missing) is not a reliable repeated-entity id;
      * a continuous-numeric feature (fractional values — ``Age``/``Fare``) is a
        measurement, not a group label (see :func:`_looks_continuous_numeric`);
      * the many-entities guard (``n_unique >= 10`` or ``>= 10% of rows``) still
        separates a genuine group id from a low-cardinality categorical FEATURE.

    The fixture's integer ``group_id`` (no fractional values, no missing) stays flagged.
    """
    n_rows = len(rows)
    excluded = {id_column, target, *datetime_columns}
    out = []
    for col in header:
        if col in excluded:
            continue
        raw_vals = _column_values(rows, col)
        vals = [v for v in raw_vals if str(v).strip() != ""]
        n_nonempty = len(vals)
        if n_nonempty == 0:
            continue
        # A mostly-empty column is not a dependable repeated-entity identifier.
        if n_rows > 0 and (n_rows - n_nonempty) / n_rows > 0.5:
            continue
        # A continuous numeric feature (fractional) is a measurement, not a group id.
        if _looks_continuous_numeric(vals):
            continue
        n_unique = len(set(vals))
        if n_unique <= 1 or n_unique >= n_nonempty:
            continue  # constant, or all-unique (no repetition) → not a group
        avg_group = n_nonempty / n_unique
        many_entities = n_unique >= 10 or n_unique >= 0.1 * n_nonempty
        if avg_group >= 2 and many_entities:
            out.append(col)
    return out


def analyze_class_balance(train_rows, target: str | None) -> dict:
    """Classify the target as classification/regression and measure imbalance."""
    if not target:
        return {"is_classification": False, "n_classes": 0, "counts": {},
                "minority_fraction": None, "imbalanced": False}
    vals = [v for v in _column_values(train_rows, target) if str(v).strip() != ""]
    if not vals:
        return {"is_classification": False, "n_classes": 0, "counts": {},
                "minority_fraction": None, "imbalanced": False}
    counts = Counter(vals)
    n_unique = len(counts)
    looks_continuous = any("." in str(v) for v in vals)
    is_classification = n_unique <= _MAX_CLASS_LABELS and not (
        looks_continuous and n_unique > 2
    )
    minority_fraction = min(counts.values()) / len(vals) if is_classification else None
    imbalanced = bool(
        is_classification and n_unique >= 2 and minority_fraction is not None
        and minority_fraction < _IMBALANCE_FRACTION
    )
    return {
        "is_classification": is_classification,
        "n_classes": n_unique if is_classification else 0,
        "counts": dict(counts) if is_classification else {},
        "minority_fraction": minority_fraction,
        "imbalanced": imbalanced,
    }


def datetime_train_precedes_test(train_rows, test_rows, datetime_columns) -> bool:
    """True iff the (first) datetime column's train dates all precede the test dates."""
    if not datetime_columns:
        return False
    col = datetime_columns[0]
    tr = [d for d in (_try_parse_date(str(v)) for v in _column_values(train_rows, col)) if d]
    te = [d for d in (_try_parse_date(str(v)) for v in _column_values(test_rows, col)) if d]
    if not tr or not te:
        return False
    return max(tr) <= min(te)


def id_overlap(train_rows, test_rows, id_column) -> dict:
    """Fraction of test ids also present in train (a proper split → ~0)."""
    if not id_column:
        return {"id_column": None, "test_ids_in_train": 0, "fraction": None}
    train_ids = set(_column_values(train_rows, id_column))
    test_ids = _column_values(test_rows, id_column)
    if not test_ids:
        return {"id_column": id_column, "test_ids_in_train": 0, "fraction": None}
    overlap = sum(1 for i in test_ids if i in train_ids)
    return {
        "id_column": id_column,
        "test_ids_in_train": overlap,
        "fraction": overlap / len(test_ids),
    }


# --------------------------------------------------------------------------- #
# recommend_cv — the mechanical decision order (D-05 / RESEARCH §Code Examples).
# --------------------------------------------------------------------------- #
def recommend_cv(evidence: dict) -> str:
    """group > temporal > stratified > plain (in that priority order).

    * group_candidates present            → "GroupKFold"
    * datetime column + train precedes test → "TimeSeriesSplit"
    * classification target (esp imbalanced) → "StratifiedKFold"
    * else                                 → "KFold"
    """
    if evidence.get("group_candidates"):
        return "GroupKFold"
    if evidence.get("datetime_columns") and evidence.get("datetime_train_precedes_test"):
        return "TimeSeriesSplit"
    cb = evidence.get("class_balance") or {}
    if cb.get("is_classification"):
        return "StratifiedKFold"
    return "KFold"


# --------------------------------------------------------------------------- #
# Evidence assembly.
# --------------------------------------------------------------------------- #
def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_evidence(ws: Path) -> dict:
    """Resolve the pair and assemble the full evidence dict (or a SKIPPED record)."""
    data_dir = ws / "data"
    pair = resolve_pair(data_dir)
    if pair is None:
        return {
            "status": "SKIPPED",
            "reason": SKIP_REASON,
            "recommend": None,
            "generated": _iso_now(),
        }

    train_path, test_path = pair
    train_header, train_rows = _read_csv(train_path)
    test_header, test_rows = _read_csv(test_path)

    # No analyzable tabular structure (no shared columns, or an empty frame) → degrade
    # to a "no tabular structure" sentinel: recommend None, never assert a scheme.
    shared = [c for c in train_header if c in set(test_header)]
    if not shared or not train_rows or not test_rows:
        return {
            "status": "ok",
            "train_file": train_path.name,
            "test_file": test_path.name,
            "n_train_rows": len(train_rows),
            "n_test_rows": len(test_rows),
            "non_tabular": True,
            "recommend": None,
            "recommend_is_hint": True,
            "recommend_note": NON_TABULAR_NOTE,
            "generated": _iso_now(),
        }

    id_column, id_method = detect_id_column(train_header, test_header, train_rows)

    # D-07 target derivation: columns(train) − columns(test) − id_column.
    extra = [c for c in train_header if c not in set(test_header)]
    target_candidates = [c for c in extra if c != id_column]
    target = target_candidates[0] if len(target_candidates) == 1 else (
        target_candidates[0] if target_candidates else None
    )

    datetime_columns = detect_datetime_columns(train_header, train_rows)
    group_candidates = detect_group_candidates(
        train_header, train_rows, id_column, target, datetime_columns
    )
    class_balance = analyze_class_balance(train_rows, target)
    precedes = datetime_train_precedes_test(train_rows, test_rows, datetime_columns)
    overlap = id_overlap(train_rows, test_rows, id_column)

    evidence = {
        "status": "ok",
        "train_file": train_path.name,
        "test_file": test_path.name,
        "n_train_rows": len(train_rows),
        "n_test_rows": len(test_rows),
        "target": {
            "column": target,
            "id_column": id_column,
            "id_method": id_method,
            "train_only_columns": extra,
            "derivation": (
                "columns(train) - columns(test) - id_column = "
                f"{target_candidates}"
            ),
        },
        "group_candidates": group_candidates,
        "datetime_columns": datetime_columns,
        "datetime_train_precedes_test": precedes,
        "class_balance": class_balance,
        "id_overlap": overlap,
        "generated": _iso_now(),
    }
    evidence["recommend"] = recommend_cv(evidence)
    # Label the recommendation a NON-authoritative advisory hint (D-05): the AI decides
    # and commits the scheme via analyze_data.py --cv-scheme; this is never auto-committed.
    evidence["recommend_is_hint"] = True
    evidence["recommend_note"] = RECOMMEND_ADVISORY_NOTE
    return evidence


def _stage_provenance(ws: Path, rel: str) -> None:
    """``git add --`` ONLY the named provenance path (never a blanket ``git add``)."""
    if not (ws / ".git").exists():
        return
    if not (ws / rel).exists():
        return
    subprocess.run(
        ["git", "add", "--", rel],
        cwd=str(ws),
        capture_output=True,
        text=True,
        check=False,
    )


def write_evidence(ws: Path) -> tuple[dict, Path]:
    """Build + persist ``control/raw/cv-evidence.json`` (tracked). Returns ``(evidence, path)``."""
    evidence = build_evidence(ws)
    out = ws / CV_EVIDENCE_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2) + "\n")
    _stage_provenance(ws, CV_EVIDENCE_REL)
    return evidence, out


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="cv_evidence.py",
        description="Emit structural CV evidence + a mechanical recommendation to "
                    "control/raw/cv-evidence.json (never writes config.json cv.scheme).",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()

    evidence, out = write_evidence(ws)
    if evidence.get("status") == "SKIPPED":
        print(
            f"cv_evidence: SKIPPED — {evidence['reason']} "
            f"(recorded in {out.relative_to(ws)}).",
            file=sys.stderr,
        )
        return 0  # flag-don't-abort (Phase 1 D-07): a recorded status, not a crash.

    if evidence.get("non_tabular"):
        print(
            f"cv_evidence: no tabular structure detected — nothing recommended "
            f"(evidence → {out.relative_to(ws)}; the AI decides cv.scheme via analyze_data.py)."
        )
        return 0

    print(
        f"cv_evidence: target={evidence['target']['column']!r} "
        f"recommend={evidence['recommend']} (advisory HINT — the AI commits cv.scheme "
        f"via analyze_data.py --cv-scheme; evidence → {out.relative_to(ws)})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
