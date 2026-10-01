"""kx-preds/1: the one prediction format every predictive template writes.

  oof.csv         row_id, fold, target, <pred columns>   one row per train row
  test_preds.csv  row_id, <pred columns>                 one row per test row

Pred columns are ``pred`` (binary probability or regression value) or
``pred_0 .. pred_{K-1}`` (multiclass probabilities, class order in
result.json predictions.classes). ``fold`` is in [0, n_folds) or -1 for rows
never validated (walk-forward). Scores are continuous (probabilities), never
hard labels, so any set of experiments can be blended.

Validated with stdlib csv only, streaming, so the recorder needs no pandas.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

FORMAT = "kx-preds/1"


def _plain_name(name) -> bool:
    return isinstance(name, str) and name and "/" not in name and "\\" not in name \
        and name not in (".", "..") and "\x00" not in name


def _finite(v: str) -> bool:
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def validate(output_dir: Path, block, n_folds: int) -> list[str]:
    """Errors for result.json's ``predictions`` block and the files it names."""
    if not isinstance(block, dict):
        return ["result.json has no predictions block"]
    errs: list[str] = []
    if block.get("format") != FORMAT:
        errs.append(f"predictions.format must be {FORMAT}")
    cols = block.get("pred_columns")
    if not (isinstance(cols, list) and cols and all(isinstance(c, str) and c for c in cols)):
        return errs + ["predictions.pred_columns must be a non-empty list of names"]
    if len(cols) > 1 and cols != [f"pred_{i}" for i in range(len(cols))]:
        errs.append("multiclass pred columns must be pred_0..pred_{K-1}")
    if len(cols) == 1 and cols != ["pred"]:
        errs.append("a single pred column must be named pred")
    classes = block.get("classes")
    if len(cols) > 1 and (not isinstance(classes, list) or len(classes) != len(cols)):
        errs.append("predictions.classes must list one class per pred column")
    for key in ("oof", "test"):
        if not _plain_name(block.get(key)):
            errs.append(f"predictions.{key} must be a plain file name in output/")
    if errs:
        return errs

    oof_ids, oof_cols = _check_file(output_dir / block["oof"], ["row_id", "fold", "target", *cols],
                                    block.get("n_oof"), n_folds, errs, "oof")
    _check_file(output_dir / block["test"], ["row_id", *cols], block.get("n_test"), None, errs,
                "test")
    if oof_cols is not None and oof_cols != set(range(n_folds)):
        errs.append(f"oof folds used {sorted(oof_cols)} != range({n_folds})")
    return errs


def _check_file(path: Path, header: list[str], n_expected, n_folds, errs: list[str], label: str):
    if not path.is_file():
        errs.append(f"{label}: {path.name} is missing")
        return None, None
    seen: set[str] = set()
    folds: set[int] = set()
    n = 0
    try:
        with path.open(newline="") as fh:
            reader = csv.reader(fh)
            got = next(reader, None)
            if got != header:
                errs.append(f"{label}: header must be {header}")
                return None, None
            pred_start = 3 if n_folds is not None else 1
            for row in reader:
                n += 1
                if len(row) != len(header):
                    errs.append(f"{label}: row {n} has {len(row)} fields, expected {len(header)}")
                    return None, None
                rid = row[0]
                if rid in seen:
                    errs.append(f"{label}: duplicate row_id {rid!r}")
                    return None, None
                seen.add(rid)
                validated = True
                if n_folds is not None:
                    try:
                        f = int(row[1])
                    except ValueError:
                        errs.append(f"{label}: row {n} fold is not an int")
                        return None, None
                    if not (f == -1 or 0 <= f < n_folds):
                        errs.append(f"{label}: row {n} fold {f} outside [-1, {n_folds})")
                        return None, None
                    if f >= 0:
                        folds.add(f)
                    validated = f >= 0
                if validated and not all(_finite(v) for v in row[pred_start:]):
                    errs.append(f"{label}: row {n} has a non-finite prediction")
                    return None, None
    except (OSError, UnicodeDecodeError, csv.Error):
        errs.append(f"{label}: {path.name} is unreadable")
        return None, None
    if n == 0:
        errs.append(f"{label}: {path.name} has no rows")
    if not (isinstance(n_expected, int) and not isinstance(n_expected, bool)) or n != n_expected:
        errs.append(f"{label}: {n} rows, but result.json declares {n_expected}")
    return seen, folds
