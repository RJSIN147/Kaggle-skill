"""cv_fixtures.py — ONE builder helper generating train/test CSV pairs on demand.

Mirrors the "small malicious/benign zip builder" idea from test_extract.py: instead
of tracking six discrete CSV fixtures in git, a single helper synthesizes a
``train.csv`` + ``test.csv`` pair (named to exercise the 02-03 resolution contract)
for each of three structural shapes that drive ``recommend_cv``:

  * ``grouped``    — a repeated-entity ``group_id`` column shared across rows
                     (many groups, each with several rows)  → GroupKFold
  * ``temporal``   — a parseable ISO ``date`` column with test dates strictly after
                     the train dates                        → TimeSeriesSplit
  * ``imbalanced`` — a skewed binary classification ``target``          → StratifiedKFold

Each built ``train.csv`` carries exactly ONE non-id column absent from its
``test.csv`` — the target — so ``columns(train) − columns(test) − id`` (D-07) resolves
to a single target. Deterministic (seeded ``random.Random``); stdlib-only (``csv``),
so it imports with NO pandas / NO scikit-learn installed.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SHAPES = ("grouped", "temporal", "imbalanced")


def _write_csv(path: Path, header, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def _build_grouped(data_dir: Path, rng: random.Random) -> dict:
    """20 groups × 3 rows = 60 train rows; ``group_id`` repeats (avg group size 3)."""
    n_groups, per_group = 20, 3
    train_rows = []
    rid = 1
    for g in range(1, n_groups + 1):
        for _ in range(per_group):
            feat = round(rng.uniform(0, 1000) + rid * 1e-3, 6)  # distinct → not a group
            target = rng.randint(0, 1)
            train_rows.append([rid, g, feat, target])
            rid += 1
    # test: distinct (new) groups, target column absent.
    test_rows = []
    for g in range(n_groups + 1, n_groups + 21):
        feat = round(rng.uniform(0, 1000) + rid * 1e-3, 6)
        test_rows.append([rid, g, feat])
        rid += 1

    _write_csv(data_dir / "train.csv", ["id", "group_id", "feat1", "target"], train_rows)
    _write_csv(data_dir / "test.csv", ["id", "group_id", "feat1"], test_rows)
    return {"target": "target", "id": "id", "expected_recommend": "GroupKFold",
            "group_col": "group_id"}


def _build_temporal(data_dir: Path, rng: random.Random) -> dict:
    """40 train rows on increasing ISO dates; 20 test rows strictly AFTER them."""
    start = date(2020, 1, 1)
    train_rows = []
    rid = 1
    for i in range(40):
        d = (start + timedelta(days=i)).isoformat()
        feat = round(rng.uniform(0, 1000) + rid * 1e-3, 6)
        target = rng.randint(0, 1)
        train_rows.append([rid, d, feat, target])
        rid += 1
    test_start = start + timedelta(days=90)  # strictly after the last train date
    test_rows = []
    for i in range(20):
        d = (test_start + timedelta(days=i)).isoformat()
        feat = round(rng.uniform(0, 1000) + rid * 1e-3, 6)
        test_rows.append([rid, d, feat])
        rid += 1

    _write_csv(data_dir / "train.csv", ["id", "date", "feat1", "target"], train_rows)
    _write_csv(data_dir / "test.csv", ["id", "date", "feat1"], test_rows)
    return {"target": "target", "id": "id", "expected_recommend": "TimeSeriesSplit",
            "datetime_col": "date"}


def _build_imbalanced(data_dir: Path, rng: random.Random) -> dict:
    """100 train rows, ~10% positive binary target; continuous features (no group)."""
    n = 100
    n_pos = 10
    labels = [1] * n_pos + [0] * (n - n_pos)
    rng.shuffle(labels)
    train_rows = []
    for rid in range(1, n + 1):
        f1 = round(rng.uniform(0, 1000) + rid * 1e-3, 6)
        f2 = round(rng.uniform(0, 1000) + rid * 1e-3, 6)
        train_rows.append([rid, f1, f2, labels[rid - 1]])
    test_rows = []
    for rid in range(n + 1, n + 41):
        f1 = round(rng.uniform(0, 1000) + rid * 1e-3, 6)
        f2 = round(rng.uniform(0, 1000) + rid * 1e-3, 6)
        test_rows.append([rid, f1, f2])

    _write_csv(data_dir / "train.csv", ["id", "feat1", "feat2", "target"], train_rows)
    _write_csv(data_dir / "test.csv", ["id", "feat1", "feat2"], test_rows)
    return {"target": "target", "id": "id", "expected_recommend": "StratifiedKFold"}


_BUILDERS = {
    "grouped": _build_grouped,
    "temporal": _build_temporal,
    "imbalanced": _build_imbalanced,
}


def build_pair(data_dir, shape: str, seed: int = 0) -> dict:
    """Write ``train.csv`` + ``test.csv`` for ``shape`` into ``data_dir``.

    Returns metadata: ``{"target", "id", "expected_recommend", ...}``. ``shape`` must
    be one of :data:`SHAPES`. The target column is present in ``train.csv`` only, and
    is the single non-id column absent from ``test.csv`` (D-07 target derivation).
    """
    if shape not in _BUILDERS:
        raise ValueError(f"unknown shape {shape!r}; expected one of {SHAPES}")
    data_dir = Path(data_dir)
    return _BUILDERS[shape](data_dir, random.Random(seed))
