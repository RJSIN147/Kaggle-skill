#!/usr/bin/env python3
"""analyze_data.py — schema + CV scheme (tooling-writes) + adversarial validation.

The THIRD and last of Phase 2's idempotent entry points (D-09). It completes the
competition "constitution": from the resolved data it commits the cross-validation
scheme (D-05) and produces an adversarial-validation finding (D-06), filling
``competition.md``'s Data-schema, Cross-validation, and Adversarial-validation
sections so success criterion 1 holds end to end.

Two postures make this script distinctive:

  * **Tooling writes, the AI never hand-writes (D-05).** The committed scheme is an
    enum ∈ {GroupKFold, TimeSeriesSplit, StratifiedKFold, KFold}. It reaches
    ``config.json`` ``cv.scheme`` through the direct ``set_config_field`` setter —
    ``write_control_json``'s merge-add-missing CANNOT overwrite the reserved-``null``
    key. The AI's committed choice flows through a choices-validated ``--cv-scheme``
    flag, defaulting to ``cv_evidence.recommend_cv``. The human-readable rationale
    goes to ``competition.md`` via the shared ``competition_doc.replace_section``.

  * **The ONE ML step, behind ``uv run`` (D-06).** Real adversarial validation
    (LogisticRegression on train=0/test=1, ``roc_auc_score``) needs pandas +
    scikit-learn. This script is stdlib PLUMBING that SHELLS to ``uv run`` in the
    workspace ML env for that step — it never imports an ML stack itself, and it
    NEVER runtime-installs packages. If the env is absent it exits 0, emits a stdlib
    marginal-shift report, and records ``adversarial validation: SKIPPED`` — the
    Phase 1 D-07 flag-don't-abort posture. Marginal shift is a weaker artifact than
    joint (adversarial) shift, so it is labeled SKIPPED, never implied to be AV.

D-09 independence: analyze does not need capture. If ``competition.md`` is absent it
is created from the template; if it is still the untouched Phase-1 stub (capture never
ran) the CV scheme + evidence are STILL written and the missing capture is FLAGGED.

Portability: self-locating, ``--workspace`` argparse in / exit-code out,
non-interactive. Provenance is staged by EXPLICIT path (never ``git add -A``).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import cv_evidence as cve  # noqa: E402  (self-locating sys.path insert above)
from competition_doc import replace_section  # noqa: E402
from init_workspace import (  # noqa: E402
    _render_text,
    create_if_absent,
    set_config_field,
)

# The AV strong-shift threshold surfaced next to the number in competition.md
# (RESEARCH §Code Examples / Claude's discretion: ~0.7–0.8 signals meaningful shift).
AV_STRONG_SHIFT_AUC = 0.8
AV_ROW_CAP = 50_000


# --------------------------------------------------------------------------- #
# The adversarial-validation runner — pandas/scikit-learn code that runs ONLY under
# `uv run` in the workspace ML env, NEVER in this stdlib process (D-06). Kept as a
# source string so importing analyze_data.py never pulls an ML stack.
# --------------------------------------------------------------------------- #
_AV_RUNNER_SRC = '''\
"""Adversarial validation runner (workspace ML env only; invoked via `uv run`)."""
import argparse
import json
import sys

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

CAP = 50000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--target", default="")
    ap.add_argument("--id", default="")
    a = ap.parse_args()

    tr = pd.read_csv(a.train)
    te = pd.read_csv(a.test)
    drop = [c for c in (a.target, a.id) if c]
    tr = tr.drop(columns=[c for c in drop if c in tr.columns], errors="ignore")
    te = te.drop(columns=[c for c in drop if c in te.columns], errors="ignore")
    cols = [c for c in tr.columns if c in set(te.columns)]
    if not cols:
        print(json.dumps({"error": "no shared feature columns"}))
        return 1
    tr = tr[cols].copy()
    te = te[cols].copy()
    tr["__is_test__"] = 0
    te["__is_test__"] = 1
    df = pd.concat([tr, te], ignore_index=True)
    if len(df) > CAP:
        df = df.sample(CAP, random_state=0).reset_index(drop=True)
    y = df["__is_test__"].values
    if len(set(y.tolist())) < 2:
        print(json.dumps({"error": "single-class label"}))
        return 1
    X = df.drop(columns=["__is_test__"])
    num = [c for c in X.columns if pd.api.types.is_numeric_dtype(X[c])]
    cat = [c for c in X.columns if c not in num]
    num_pipe = Pipeline([("impute", SimpleImputer(strategy="median")),
                         ("scale", StandardScaler())])
    cat_pipe = Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                         ("oh", OneHotEncoder(handle_unknown="ignore", max_categories=20))])
    pre = ColumnTransformer([("num", num_pipe, num), ("cat", cat_pipe, cat)])
    clf = Pipeline([("pre", pre), ("lr", LogisticRegression(max_iter=1000))])
    proba = cross_val_predict(clf, X, y, cv=5, method="predict_proba")[:, 1]
    auc = float(roc_auc_score(y, proba))
    print(json.dumps({"auc": auc, "n_rows": int(len(df))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


# --------------------------------------------------------------------------- #
# Adversarial validation — shell to `uv run` (the ONLY uv caller in the skill).
# --------------------------------------------------------------------------- #
def run_adversarial_validation(ws: Path, train_path: Path, test_path: Path,
                               target: str | None, id_col: str | None) -> dict:
    """Attempt real AV under the workspace ML env; return a result dict.

    Returns ``{"status": "ok", "auc": ..., "n_rows": ...}`` on success, else
    ``{"status": "skipped", "reason": ...}``. NEVER installs packages: uses
    ``uv run --no-sync`` so a workspace whose ML env is not synced degrades cleanly
    (import error → non-zero) instead of triggering a network install.
    """
    if shutil.which("uv") is None:
        return {"status": "skipped", "reason": "uv not on PATH"}

    fd, tmp = tempfile.mkstemp(suffix="_av_runner.py")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(_AV_RUNNER_SRC)
        cmd = [
            "uv", "run", "--no-sync", "python", tmp,
            "--train", str(train_path), "--test", str(test_path),
            "--target", target or "", "--id", id_col or "",
        ]
        try:
            proc = subprocess.run(
                cmd, cwd=str(ws), capture_output=True, text=True, timeout=600
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return {"status": "skipped", "reason": f"uv run failed: {exc}"}
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    if proc.returncode != 0:
        return {"status": "skipped", "reason": "ML env absent (uv run non-zero)"}
    # Parse the last JSON object emitted on stdout (a uv banner may precede it).
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "auc" in parsed:
            return {"status": "ok", "auc": parsed["auc"],
                    "n_rows": parsed.get("n_rows")}
        break
    return {"status": "skipped", "reason": "could not parse AV output"}


def marginal_shift_report(train_path: Path, test_path: Path,
                          target: str | None, id_col: str | None) -> str:
    """A stdlib per-column marginal-shift summary (the WEAKER fallback for D-06).

    Compares numeric-feature means between train and test. This catches only marginal
    shift — never the joint shift adversarial validation detects — so its caller
    labels the section SKIPPED for real AV.
    """
    _, train_rows = cve._read_csv(train_path)
    test_header, test_rows = cve._read_csv(test_path)
    exclude = {target, id_col}
    feats = [c for c in (train_rows[0].keys() if train_rows else [])
             if c not in exclude and c in set(test_header)]

    def _means(rows, col):
        nums = []
        for r in rows:
            v = str(r.get(col, "")).strip()
            try:
                nums.append(float(v))
            except ValueError:
                return None
        return sum(nums) / len(nums) if nums else None

    lines = []
    for col in feats:
        tm = _means(train_rows, col)
        em = _means(test_rows, col)
        if tm is None or em is None:
            continue
        diff = abs(tm - em)
        denom = max(abs(tm), abs(em), 1e-9)
        lines.append(f"  - {col}: train_mean={tm:.4g}, test_mean={em:.4g}, "
                     f"rel_diff={diff / denom:.2%}")
    if not lines:
        return "  (no numeric feature columns to compare.)"
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# competition.md section bodies.
# --------------------------------------------------------------------------- #
def _cv_driver(evidence: dict) -> str:
    """One-line human rationale for the recommended scheme, from the driving signal."""
    if evidence.get("group_candidates"):
        return (f"repeated-entity group column(s) {evidence['group_candidates']} "
                "→ GroupKFold prevents group leakage across folds")
    if evidence.get("datetime_columns") and evidence.get("datetime_train_precedes_test"):
        return (f"datetime column {evidence['datetime_columns'][0]!r} with train dates "
                "preceding test → TimeSeriesSplit mirrors the temporal holdout")
    cb = evidence.get("class_balance") or {}
    if cb.get("is_classification"):
        imb = " (imbalanced)" if cb.get("imbalanced") else ""
        return (f"classification target{imb} → StratifiedKFold preserves the class "
                "ratio in every fold")
    return "no group/temporal/classification signal → plain KFold"


def _cv_section_body(scheme: str, committed: str, evidence: dict) -> str:
    override = ""
    recommend = evidence.get("recommend")
    if committed and committed != recommend:
        override = (f" Committed **{committed}** — an AI override of the mechanical "
                    f"recommendation ({recommend}).")
    else:
        override = f" Committed **{scheme}** (matches the mechanical recommendation)."
    return (
        f"**Cross-validation scheme:** {scheme}\n\n"
        f"Derivation (mechanical, D-05 tooling-recommends → AI-commits → tooling-writes): "
        f"{_cv_driver(evidence)}.{override} "
        f"Target column: {evidence.get('target', {}).get('column')!r} "
        f"(derived: columns(train) − columns(test) − id)."
    )


def _cv_section_skipped(reason: str) -> str:
    return (
        f"**Cross-validation scheme:** SKIPPED — {reason}. "
        "No scheme was fabricated onto config.json cv.scheme; name the train/test "
        "files or set the scheme manually and re-run."
    )


def _schema_section_body(evidence: dict, train_path: Path, test_path: Path) -> str:
    train_header, train_rows = cve._read_csv(train_path)
    _, test_rows = cve._read_csv(test_path)
    target = evidence.get("target", {}).get("column")
    id_col = evidence.get("target", {}).get("id_column")
    feats = [c for c in train_header if c not in {target, id_col}]
    return (
        f"**Files:** `{train_path.name}` ({len(train_rows)} rows), "
        f"`{test_path.name}` ({len(test_rows)} rows)\n\n"
        f"**Target column:** `{target}` "
        "(mechanically derived: columns(train) − columns(test) − id_column, D-07)\n\n"
        f"**Id column:** `{id_col}`\n\n"
        f"**Feature columns:** {', '.join(f'`{c}`' for c in feats) or '(none)'}"
    )


def _av_section_ok(av: dict) -> str:
    auc = av["auc"]
    verdict = "STRONG train/test shift" if auc >= AV_STRONG_SHIFT_AUC else (
        "no meaningful shift" if auc <= 0.6 else "mild shift"
    )
    return (
        f"**Adversarial validation:** AUC = {auc:.3f} on {av.get('n_rows')} rows "
        f"({verdict}).\n\n"
        "Real AV: LogisticRegression on train=0/test=1, `roc_auc_score` via "
        f"`cross_val_predict` cv=5 (row cap {AV_ROW_CAP}). Interpretation: ~0.5 = no "
        f"shift; ≥ ~{AV_STRONG_SHIFT_AUC} = strong joint distribution shift — a CV→LB "
        "correlation risk (the exact quantity SCORE-02 tracks)."
    )


def _av_section_skipped(reason: str, marginal: str) -> str:
    return (
        "**Adversarial validation:** SKIPPED (ML env absent; run `uv sync`).\n\n"
        f"_Status: adversarial validation: SKIPPED_ — real AV (LogisticRegression "
        "train-vs-test, `roc_auc_score`) did not run ("
        f"{reason}). Skill plumbing never runtime-installs (D-06). When run, the "
        f"strong-shift threshold is ~{AV_STRONG_SHIFT_AUC} AUC.\n\n"
        "The stdlib marginal-shift report below is a WEAKER artifact — per-column "
        "MARGINAL shift only; it does NOT detect the joint shift AV catches:\n\n"
        f"{marginal}"
    )


def _av_section_unresolved() -> str:
    return (
        "**Adversarial validation:** SKIPPED (train/test pair unresolved). "
        "_Status: adversarial validation: SKIPPED_ — no `data/train.csv` + "
        "`data/test.csv` to compare."
    )


# --------------------------------------------------------------------------- #
# competition.md helpers.
# --------------------------------------------------------------------------- #
_TODO = "_TODO (Phase 2)_"


def _section_body(md_text: str, header: str) -> str:
    target = f"## {header}"
    lines = md_text.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.rstrip("\n") == target), None)
    if start is None:
        return ""
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "".join(lines[start + 1:end])


def _capture_has_run(md_text: str) -> bool:
    """True iff capture populated the Evaluation-metric section (no longer the stub)."""
    return _TODO not in _section_body(md_text, "Evaluation metric") and bool(
        _section_body(md_text, "Evaluation metric").strip()
    )


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="analyze_data.py",
        description="Complete the competition constitution: schema + CV scheme "
                    "(set_config_field) + adversarial validation (uv run).",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    ap.add_argument("--cv-scheme", choices=cve.CV_SCHEMES, default=None,
                    help="The AI's committed CV scheme enum. Defaults to the mechanical "
                         "recommend_cv() value. The AI never hand-writes the field — it "
                         "passes this choices-validated flag and tooling writes it (D-05).")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()
    config_path = ws / "control" / "config.json"

    if not config_path.exists():
        print(f"analyze refused: no {config_path} — run init first.", file=sys.stderr)
        return 1
    try:
        cfg = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        print(
            f"analyze refused: {config_path.name} is not valid JSON and was left "
            f"untouched (fail-clear, D-02): {exc}.",
            file=sys.stderr,
        )
        return 1
    slug = cfg.get("competition_slug") or "unknown"

    # Build + persist the structural evidence (tracked; staged by explicit path).
    evidence, _ = cve.write_evidence(ws)

    # competition.md: create from template if absent (D-09 independence), else fill in.
    comp_md = ws / "competition.md"
    create_if_absent(comp_md, _render_text("competition.md.tmpl", {"slug": slug}))
    md_text = comp_md.read_text()

    if not _capture_has_run(md_text):
        print(
            "note: competition.md not yet captured — run capture_competition.py for "
            "metric/rules. Writing cv.scheme + evidence anyway (D-09 independence).",
            file=sys.stderr,
        )

    skipped = evidence.get("status") == "SKIPPED"

    if skipped:
        # Unresolved pair: record SKIPPED, do NOT fabricate a scheme onto the null key.
        reason = evidence.get("reason", "train/test pair unresolved")
        md_text = replace_section(md_text, "Cross-validation scheme",
                                  _cv_section_skipped(reason))
        md_text = replace_section(md_text, "Data schema",
                                  f"_Schema unavailable_ — {reason}.")
        md_text = replace_section(md_text, "Adversarial validation",
                                  _av_section_unresolved())
        comp_md.write_text(md_text)
        print(f"analyze: SKIPPED CV scheme + AV for '{slug}' — {reason} (exit 0).")
        return 0

    # Resolve the pair for schema + AV (evidence is ok → the pair resolves).
    pair = cve.resolve_pair(ws / "data")
    train_path, test_path = pair
    target = evidence.get("target", {}).get("column")
    id_col = evidence.get("target", {}).get("id_column")

    # D-05 tooling-writes: the AI's committed value (or the mechanical default) via the
    # DIRECT setter — write_control_json's merge-add-missing cannot fill the null.
    committed = args.cv_scheme
    scheme = committed or evidence["recommend"]
    rc = set_config_field(config_path, ("cv", "scheme"), scheme)
    if rc != 0:
        return rc

    md_text = replace_section(md_text, "Cross-validation scheme",
                              _cv_section_body(scheme, committed, evidence))
    md_text = replace_section(md_text, "Data schema",
                              _schema_section_body(evidence, train_path, test_path))

    # The ONE ML step, behind uv run — real AV or an honest SKIPPED (never installs).
    av = run_adversarial_validation(ws, train_path, test_path, target, id_col)
    if av["status"] == "ok":
        md_text = replace_section(md_text, "Adversarial validation", _av_section_ok(av))
        av_msg = f"AV AUC={av['auc']:.3f}"
    else:
        marginal = marginal_shift_report(train_path, test_path, target, id_col)
        md_text = replace_section(md_text, "Adversarial validation",
                                  _av_section_skipped(av["reason"], marginal))
        av_msg = f"AV SKIPPED ({av['reason']})"

    comp_md.write_text(md_text)
    print(
        f"analyze '{slug}': cv.scheme={scheme} "
        f"({'AI-committed' if committed else 'mechanical'}); {av_msg}. "
        "competition.md constitution complete."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
