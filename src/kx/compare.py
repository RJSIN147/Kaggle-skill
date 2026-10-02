"""Lineage comparison: a recorded run against its parent, fold by fold.

Two runs whose ``oof.csv`` assign every row to the same fold (same ``fold_hash``)
can be compared per fold: the fold-to-fold variation they share cancels out, so a
paired comparison sees a real difference that mean ± std hides. kx computes it;
the AI never types it.

The test is a paired t on the per-fold differences with the Nadeau-Bengio
correction (k-fold training sets overlap, so the plain paired t is over-confident):
se = sd * sqrt(1/k + 1/(k-1)), against the two-sided 95 % t critical value.
The label is informational (``better`` / ``worse`` / ``inconclusive``); it never
gates a submission.

stdlib only, no I/O beyond reading the ``oof.csv`` it hashes.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

# Two-sided 95 % critical values of Student's t (df 1-30); larger df use 1.96.
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
        9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074,
        23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045,
        30: 2.042}
TEST_NAME = "paired t, Nadeau-Bengio corrected, 95% two-sided"
TIE = 1e-12


def t_crit(df: int) -> float:
    return T975.get(df, 1.96)


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def fold_hash(oof_path: Path) -> str | None:
    """sha256 of the sorted (row_id, fold) pairs of a kx-preds/1 oof.csv, or None."""
    try:
        with oof_path.open(newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            if not header or header[:2] != ["row_id", "fold"]:
                return None
            pairs = sorted((row[0], row[1]) for row in reader if len(row) >= 2)
    except (OSError, UnicodeDecodeError, csv.Error):
        return None
    if not pairs:
        return None
    h = hashlib.sha256()
    for rid, fold in pairs:
        h.update(f"{rid}\t{fold}\n".encode())
    return "sha256:" + h.hexdigest()


def paired(child_scores, parent_scores, greater_is_better: bool) -> dict:
    """Per-fold comparison; positive deltas mean the child is better."""
    if len(child_scores) != len(parent_scores) or len(child_scores) < 2:
        return {"comparable": False, "reason": "the two runs have different fold counts"}
    if not all(_is_number(s) for s in [*child_scores, *parent_scores]):
        return {"comparable": False, "reason": "a fold score is not a finite number"}
    n = len(child_scores)
    deltas = [(c - p) if greater_is_better else (p - c)
              for c, p in zip(child_scores, parent_scores)]
    mean = statistics.mean(deltas)
    sd = statistics.stdev(deltas)
    crit = t_crit(n - 1)
    t = None
    if sd <= TIE:
        label = "identical" if abs(mean) <= TIE else ("better" if mean > 0 else "worse")
    else:
        t = mean / (sd * math.sqrt(1 / n + 1 / (n - 1)))
        label = "better" if t >= crit else "worse" if t <= -crit else "inconclusive"
    return {"comparable": True, "label": label, "n_folds": n, "deltas": deltas,
            "mean_delta": mean, "sd_delta": sd,
            "folds_better": sum(1 for d in deltas if d > TIE),
            "folds_worse": sum(1 for d in deltas if d < -TIE),
            "t": t, "t_crit": crit, "test": TEST_NAME}


def _not(reason: str, **extra) -> dict:
    return {"comparable": False, "reason": reason, **extra}


def parent_fold_hash(parent_dir: Path, parent_meta: dict) -> str | None:
    """The parent's recorded fold_hash; for runs recorded before it existed, hash its oof."""
    if parent_meta.get("fold_hash"):
        return parent_meta["fold_hash"]
    oof = (parent_meta.get("predictions") or {}).get("oof")
    return fold_hash(parent_dir / "output" / oof) if oof else None


def versus_parent(ws: Path, meta: dict) -> dict | None:
    """The child's comparison with ``meta['parent']`` (None when it has no parent)."""
    parent = meta.get("parent")
    if not parent:
        return None
    base = {"parent": parent}
    if meta.get("status") != "SUCCESS":
        return base | _not(f"this run is {meta.get('status')}")
    ups = [u.get("exp_id") for u in (meta.get("kernel") or {}).get("upstream") or []]
    if parent in ups:
        return base | _not(f"an inference stage: it carries {parent}'s CV")
    pdir = ws / "experiments" / parent
    try:
        pmeta = json.loads((pdir / "meta.json").read_text())
    except (OSError, json.JSONDecodeError):
        return base | _not(f"{parent} is not recorded")
    base |= {"parent_cv_mean": pmeta.get("cv_mean"), "parent_cv_std": pmeta.get("cv_std")}
    if pmeta.get("status") != "SUCCESS":
        return base | _not(f"{parent} is {pmeta.get('status')}")
    if pmeta.get("metric") != meta.get("metric"):
        return base | _not(f"{parent} used another metric ({pmeta.get('metric')})")
    if (pmeta.get("subsample") or None) != (meta.get("subsample") or None):
        return base | _not("the two runs used different subsamples")
    mine, theirs = meta.get("fold_hash"), parent_fold_hash(pdir, pmeta)
    if not mine or not theirs:
        return base | _not("no out-of-fold predictions to check that the folds match")
    if mine != theirs:
        return base | _not("CV scheme changed: the folds differ")
    gib = meta.get("greater_is_better")
    return base | paired(meta.get("fold_scores") or [], pmeta.get("fold_scores") or [],
                         True if gib is None else bool(gib))


def prediction_outcome(expected: dict | None, vs: dict | None) -> str | None:
    """The pre-registered direction against the paired comparison:
    matched     the comparison shows the predicted direction (or no change, for "same");
    missed      it shows a change the prediction ruled out;
    unresolved  a change was predicted but the comparison is inconclusive;
    None        nothing to judge (no prediction, or not comparable)."""
    if not expected or not vs or not vs.get("comparable"):
        return None
    want, label = expected.get("direction"), vs["label"]
    if label in ("inconclusive", "identical"):
        return "matched" if want == "same" else "unresolved"
    return "matched" if want == label else "missed"


def _fmt(v) -> str:
    return f"{v:+.4g}" if _is_number(v) else "—"


def summary(vs: dict | None) -> str | None:
    """One line for envelopes and the tried list."""
    if not vs:
        return None
    if not vs.get("comparable"):
        return f"vs {vs['parent']}: not comparable ({vs['reason']})"
    t = f", corrected t {vs['t']:.2f} vs ±{vs['t_crit']:.2f}" if vs.get("t") is not None else ""
    return (f"vs {vs['parent']}: {vs['label']} ({vs['folds_better']}/{vs['n_folds']} folds "
            f"better, mean Δ {_fmt(vs['mean_delta'])} with + = better{t})")


def verdict_block(meta: dict) -> str:
    """The kx-written facts at the top of a VERDICT.md stub."""
    lines = []
    vs, exp = meta.get("vs_parent"), meta.get("expected_effect")
    if meta.get("parent"):
        lines.append(f"- parent: {meta['parent']}")
    else:
        lines.append("- parent: none (a baseline)")
    if exp:
        delta = f" (Δ {_fmt(exp.get('delta'))})" if _is_number(exp.get("delta")) else ""
        lines.append(f"- pre-registered prediction: {exp.get('direction')}{delta}")
    if vs:
        lines.append(f"- {summary(vs)}")
    outcome = meta.get("prediction")
    if outcome:
        lines.append(f"- prediction {outcome}")
    return "\n".join(lines)
