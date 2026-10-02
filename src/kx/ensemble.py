"""kx ensemble: blend experiments' saved OOF predictions into a new recorded experiment.

Every predictive template writes kx-preds/1 (oof.csv + test_preds.csv with row ids and
probabilities), so any set of SUCCESS experiments on the same rows can be blended:
  hill     greedy forward selection with replacement (Caruana), from the best single model
  weights  non-negative weights summing to 1, optimized on the OOF metric (scipy)
The blend's CV is scored per fold on the OOF rows and recorded through the same
fail-closed recorder as any run (anti-lie mean, range, prediction-file checks).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from kx import envelope as E
from kx import record, workspace
from kx.metrics import REGISTRY
from kx.util import KxError, read_json, utc_now, write_json

HILL_ITERS = 40


def _load(exp_dir: Path):
    import numpy as np

    res = read_json(exp_dir / "output" / "result.json")
    block = res.get("predictions") or {}
    cols = block.get("pred_columns") or []
    with (exp_dir / "output" / block["oof"]).open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    ids = [r["row_id"] for r in rows]
    folds = np.array([int(r["fold"]) for r in rows])
    target = [r["target"] for r in rows]
    oof = np.array([[float(r[c]) if r[c] != "" else np.nan for c in cols] for r in rows])
    with (exp_dir / "output" / block["test"]).open(newline="") as fh:
        trows = list(csv.DictReader(fh))
    test_ids = [r["row_id"] for r in trows]
    test = np.array([[float(r[c]) for c in cols] for r in trows])
    return {"res": res, "cols": cols, "ids": ids, "folds": folds, "target": target, "oof": oof,
            "test_ids": test_ids, "test": test}


def _scorer(metric_cfg: dict, classes):
    import numpy as np
    import sklearn.metrics as skm

    name = metric_cfg["name"]
    info = REGISTRY.get(name)
    if info is None or info["sklearn_callable"] is None:
        raise KxError("invalid", f"kx ensemble scores registry metrics only (not {name!r})",
                      errors=["unsupported_metric"])
    ptype = metric_cfg.get("prediction_type") or info["prediction_type"]

    def score(y, p):
        if ptype == "raw":
            yt = np.asarray(y, dtype=float)
            yp = p[:, 0]
            if name == "rmse":
                return float(np.sqrt(np.mean((yt - yp) ** 2)))
            if name == "rmsle":
                return float(np.sqrt(np.mean((np.log1p(np.clip(yp, 0, None)) - np.log1p(yt)) ** 2)))
            return float(getattr(skm, info["sklearn_callable"])(yt, yp))
        if p.shape[1] == 1:
            yb = np.array([str(v) for v in y])
            pos = sorted(set(yb))[-1]
            yi = (yb == pos).astype(int)
            if ptype == "proba":
                if name == "roc_auc":
                    return float(skm.roc_auc_score(yi, p[:, 0]))
                return float(skm.log_loss(yi, np.column_stack([1 - p[:, 0], p[:, 0]]), labels=[0, 1]))
            return float(getattr(skm, info["sklearn_callable"])(yi, (p[:, 0] >= 0.5).astype(int)))
        yl = [str(v) for v in y]
        if ptype == "proba":
            if name == "roc_auc":
                return float(skm.roc_auc_score(yl, p, multi_class="ovr", labels=classes))
            return float(skm.log_loss(yl, p, labels=classes))
        lab = np.asarray(classes)[p.argmax(1)]
        kw = {"average": "macro"} if name in ("f1_macro", "f1", "precision", "recall") else {}
        if name == "qwk":
            kw = {"weights": "quadratic"}
        return float(getattr(skm, info["sklearn_callable"])(yl, lab, **kw))
    return score


def cmd_ensemble(ws: Path, args, adapter) -> dict:
    import numpy as np

    workspace.require_workspace(ws)
    profile = workspace.load_profile(ws)
    metric_cfg = (workspace.load_config(ws).get("metric") or {})
    if not metric_cfg.get("name"):
        raise KxError("invalid", "set the metric first", errors=["metric_unset"])
    if len(args.exp_ids) < 2:
        raise KxError("invalid", "blend at least two experiments", errors=["too_few"])
    try:
        import sklearn  # noqa: F401
    except ImportError as exc:
        raise KxError("invalid", "blending scores locally: install the local extra",
                      errors=["local_deps_missing"],
                      next_action=E.ask_user("Ask the user to run: uv sync --project <skill dir> "
                                             "--extra local")) from exc
    members, member_cv = [], {}
    for e in args.exp_ids:
        d = workspace.exp_dir(ws, e)
        meta = read_json(d / "meta.json") if (d / "meta.json").exists() else {}
        if meta.get("status") != "SUCCESS" or not meta.get("predictions") or meta.get("subsample") \
                or meta.get("kind") == "diagnostic":
            raise KxError("invalid", f"{e} is not a full-data SUCCESS with saved predictions",
                          errors=["bad_member"], data={"exp_id": e})
        members.append(_load(d))
        member_cv[e] = meta["cv_mean"]
    base = members[0]
    for e, m in zip(args.exp_ids[1:], members[1:]):
        if m["ids"] != base["ids"] or m["test_ids"] != base["test_ids"] or m["cols"] != base["cols"]:
            raise KxError("invalid", f"{e}'s predictions are not row-aligned with {args.exp_ids[0]}",
                          errors=["misaligned"])
    gib = bool(metric_cfg.get("greater_is_better", True))
    classes = base["res"]["predictions"].get("classes")
    score = _scorer(metric_cfg, classes)
    mask = base["folds"] >= 0
    y = [t for t, k in zip(base["target"], mask) if k]
    oofs = [m["oof"][mask] for m in members]
    better = (lambda a, b: a > b) if gib else (lambda a, b: a < b)

    if args.method == "hill":
        singles = [score(y, o) for o in oofs]
        best_i = max(range(len(oofs)), key=lambda i: singles[i] if gib else -singles[i])
        counts = np.zeros(len(oofs))
        counts[best_i] = 1
        cur = singles[best_i]
        for _ in range(HILL_ITERS):
            trial = []
            for i in range(len(oofs)):
                c = counts.copy()
                c[i] += 1
                blend = sum(w * o for w, o in zip(c / c.sum(), oofs))
                trial.append(score(y, blend))
            j = max(range(len(trial)), key=lambda i: trial[i] if gib else -trial[i])
            if not better(trial[j], cur):
                break
            counts[j] += 1
            cur = trial[j]
        weights = counts / counts.sum()
    else:
        from scipy.optimize import minimize

        def loss(w):
            w = np.abs(w) / np.abs(w).sum()
            s = score(y, sum(wi * o for wi, o in zip(w, oofs)))
            return -s if gib else s
        r = minimize(loss, np.full(len(oofs), 1 / len(oofs)), method="Nelder-Mead",
                     options={"maxiter": 400})
        weights = np.abs(r.x) / np.abs(r.x).sum()

    oof = sum(w * m["oof"] for w, m in zip(weights, members))
    test = sum(w * m["test"] for w, m in zip(weights, members))
    fold_scores = []
    for k in sorted(set(base["folds"][mask].tolist())):
        sel = base["folds"] == k
        fold_scores.append(score([t for t, s in zip(base["target"], sel) if s], oof[sel]))

    exp_id = workspace.mint_exp_id(ws)
    d = ws / "experiments" / exp_id
    (d / "output").mkdir(parents=True)
    cols = base["cols"]
    with (d / "output" / "oof.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["row_id", "fold", "target", *cols])
        for i, rid in enumerate(base["ids"]):
            w.writerow([rid, int(base["folds"][i]), base["target"][i],
                        *["" if np.isnan(v) else repr(float(v)) for v in oof[i]]])
    with (d / "output" / "test_preds.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["row_id", *cols])
        for i, rid in enumerate(base["test_ids"]):
            w.writerow([rid, *[repr(float(v)) for v in test[i]]])
    sub_src = ws / "experiments" / args.exp_ids[0] / "output" / \
        (base["res"].get("submission_file") or "submission.csv")
    if sub_src.suffix == ".csv" and sub_src.exists():
        with sub_src.open(newline="") as fh:
            src = list(csv.reader(fh))
        header, body = src[0], src[1:]
        ptype = metric_cfg.get("prediction_type") or REGISTRY[metric_cfg["name"]]["prediction_type"]
        if len(body) == len(base["test_ids"]) and len(header) == 2:
            labels = sorted({r[1] for r in body})
            with (d / "output" / sub_src.name).open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(header)
                for r, p in zip(body, test):
                    if ptype == "label" and len(p) == 1:
                        val = labels[-1] if p[0] >= 0.5 else labels[0]
                    elif ptype == "label":
                        val = classes[int(np.argmax(p))]
                    else:
                        val = repr(float(p[0]))
                    w.writerow([r[0], val])
    blend = {"method": args.method, "members": dict(zip(args.exp_ids, map(float, weights)))}
    (d / "blend.json").write_text(json.dumps(blend, indent=2) + "\n")
    result = {"exp_id": exp_id, "metric": metric_cfg["name"], "n_folds": len(fold_scores),
              "fold_scores": fold_scores, "cv_mean": float(np.mean(fold_scores)),
              "cv_std": float(np.std(fold_scores)), "seed": 42, "greater_is_better": gib,
              "predictions": dict(base["res"]["predictions"], oof="oof.csv", test="test_preds.csv",
                                  n_oof=len(base["ids"]), n_test=len(base["test_ids"])),
              "blend": blend,
              "sample_columns": base["res"].get("sample_columns"),
              "sample_rows": base["res"].get("sample_rows")}
    (d / "output" / "result.json").write_text(json.dumps(result, indent=2))
    idea = args.idea or f"{args.method} blend of {', '.join(args.exp_ids)}"
    best_member = (max if gib else min)(member_cv, key=member_cv.get)
    spec = {"schema_version": 1, "exp_id": exp_id, "created": utc_now(), "kind": "experiment",
            "parent": best_member, "idea": idea,
            "hypothesis": "a blend of diverse experiments beats its best member on CV",
            "expected_effect": {"direction": "better", "delta": None},
            "template": "ensemble", "template_reason": "kx ensemble",
            "runtime": {"target": "local", "accelerator": "cpu", "limit_s": 60, "internet": False},
            "sources": {"competition": profile["slug"], "datasets": [], "kernels": [], "models": []},
            "cv": {"n_folds": len(fold_scores), "reasoning": f"inherits {args.exp_ids[0]}'s folds"},
            "code_file": "blend.json"}
    write_json(d / "experiment.json", spec)
    verdict = workspace.render("VERDICT.md.tmpl", exp_id=exp_id)
    meta, warns = record.record(ws, d, spec, {"backend": "local", "exit_code": 0,
                                               "status": "COMPLETE", "git_commit": "uncommitted"},
                                metric_cfg, None, verdict)
    return E.make("ensemble", "ok",
                  f"{exp_id} recorded {meta['status']}: blend {metric_cfg['name']} "
                  f"{meta['cv_mean'] if meta['cv_mean'] is None else round(meta['cv_mean'], 6)}",
                  data={"exp_id": exp_id, "result": meta["status"], "cv_mean": meta["cv_mean"],
                        "weights": blend["members"], "fold_scores": meta["fold_scores"],
                        "vs_parent": meta.get("vs_parent"), "prediction": meta.get("prediction")},
                  warnings=warns,
                  next_action=E.edit(f"Write experiments/{exp_id}/VERDICT.md (kx compared the "
                                     f"blend with its best member {best_member} fold by fold: "
                                     "read data.vs_parent) and a reasoning.md.",
                                     then=f"kx strategy --reasoning-file experiments/{exp_id}/"
                                          "reasoning.md"))
