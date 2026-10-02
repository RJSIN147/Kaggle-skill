"""Lineage: parent, pre-registered prediction, paired fold comparison (compare.py)."""

import json

from conftest import kx
from test_run_record import make_outputs, scaffold

from kx import compare


def _oof(path, pairs):
    path.write_text("row_id,fold,target,pred\n" + "".join(f"{r},{f},0,0.5\n" for r, f in pairs))
    return path


def test_fold_hash_ignores_row_order_but_not_fold_assignment(tmp_path):
    a = compare.fold_hash(_oof(tmp_path / "a.csv", [(1, 0), (2, 1), (3, 0)]))
    b = compare.fold_hash(_oof(tmp_path / "b.csv", [(3, 0), (1, 0), (2, 1)]))
    c = compare.fold_hash(_oof(tmp_path / "c.csv", [(1, 1), (2, 1), (3, 0)]))
    assert a == b and a != c and a.startswith("sha256:")
    (tmp_path / "bad.csv").write_text("id,fold\n1,0\n")
    assert compare.fold_hash(tmp_path / "bad.csv") is None
    assert compare.fold_hash(tmp_path / "missing.csv") is None


def test_paired_orientation_and_labels():
    up = compare.paired([0.82, 0.83, 0.81, 0.84, 0.82], [0.80, 0.81, 0.80, 0.82, 0.80], True)
    assert up["label"] == "better" and up["folds_better"] == 5 and up["mean_delta"] > 0
    # lower is better: a smaller RMSE is an improvement (positive delta)
    down = compare.paired([1.0, 1.1, 0.9], [1.2, 1.25, 1.1], False)
    assert down["label"] == "better" and all(d > 0 for d in down["deltas"])
    mixed = compare.paired([0.81, 0.79, 0.82, 0.80], [0.80, 0.80, 0.80, 0.81], True)
    assert mixed["label"] == "inconclusive"
    assert compare.paired([0.8, 0.9], [0.8, 0.9], True)["label"] == "identical"
    assert compare.paired([0.8, 0.9, 0.7], [0.8, 0.9], True)["comparable"] is False


def test_corrected_t_is_more_conservative_than_plain():
    import math
    import statistics

    c, p = [0.812, 0.815, 0.811, 0.816, 0.813], [0.810, 0.811, 0.810, 0.811, 0.811]
    r = compare.paired(c, p, True)
    d = r["deltas"]
    plain = statistics.mean(d) / (statistics.stdev(d) / math.sqrt(len(d)))
    assert r["t"] < plain and r["t_crit"] == compare.t_crit(4) == 2.776


def test_prediction_outcome():
    vs = {"comparable": True, "label": "inconclusive"}
    assert compare.prediction_outcome({"direction": "same"}, vs) == "matched"
    assert compare.prediction_outcome({"direction": "better"}, vs) == "missed"
    assert compare.prediction_outcome({"direction": "better"}, {"comparable": False}) is None
    assert compare.prediction_outcome(None, vs) is None


def _record(ws, fake, idea, scores, *extra, folds_shift=0):
    exp, d = scaffold(ws, fake, idea=idea)
    if extra:  # re-scaffold with explicit lineage flags
        env = kx(ws, fake, "new", "--idea", idea, "--hypothesis", "h", *extra)
        assert env["status"] == "ok", env
        exp, d = env["data"]["exp_id"], ws / "experiments" / env["data"]["exp_id"]
        spec = json.loads((d / "experiment.json").read_text())
        spec["cv"]["reasoning"] = "iid"
        (d / "experiment.json").write_text(json.dumps(spec))
    out = make_outputs(scores=scores)
    if folds_shift:
        out["oof.csv"] = out["oof.csv"].replace(b",0,", b",9,").replace(b",1,", b",0,") \
            .replace(b",9,", b",1,")
    fake.outputs = out
    fake.statuses = ["COMPLETE"]
    env = kx(ws, fake, "run", exp, "--wait", "5")
    assert env["status"] == "ok" and env["data"]["result"] == "SUCCESS", env
    return exp, d, env


def test_default_parent_is_the_best_and_expect_is_required(ready_ws, fake):
    exp1, _, env1 = _record(ready_ws, fake, "base", (0.80, 0.81))
    assert env1["data"]["parent"] is None and env1["data"]["vs_parent"] is None
    env = kx(ready_ws, fake, "new", "--idea", "x", "--hypothesis", "y")
    assert env["status"] == "invalid" and env["errors"] == ["expect_required"]
    env = kx(ready_ws, fake, "new", "--idea", "x", "--hypothesis", "y", "--parent", "none")
    assert env["status"] == "ok" and env["data"]["parent"] is None
    env = kx(ready_ws, fake, "new", "--idea", "x", "--hypothesis", "y", "--parent", "exp-999",
             "--expect", "better")
    assert env["status"] == "invalid"
    env = kx(ready_ws, fake, "new", "--idea", "x", "--hypothesis", "y", "--expect", "better",
             "--expect-delta", "0.01")
    assert env["data"]["parent"] == exp1 and env["data"]["parent_reason"].startswith("default")
    spec = json.loads((ready_ws / "experiments" / env["data"]["exp_id"] / "experiment.json")
                      .read_text())
    assert spec["parent"] == exp1 and spec["expected_effect"] == {"direction": "better",
                                                                  "delta": 0.01}


def test_child_is_compared_with_its_parent_fold_by_fold(ready_ws, fake):
    exp1, _, _ = _record(ready_ws, fake, "base", (0.80, 0.81))
    exp2, d2, env = _record(ready_ws, fake, "better", (0.84, 0.85))  # scaffold: --expect better
    vs = env["data"]["vs_parent"]
    # equal deltas on both folds: sd 0, so the sign decides
    assert vs["comparable"] and vs["parent"] == exp1 and vs["label"] == "better"
    assert env["data"]["prediction"] == "matched"
    assert f"vs {exp1}: better" in env["summary"]
    meta = json.loads((d2 / "meta.json").read_text())
    assert meta["fold_hash"].startswith("sha256:") and meta["parent"] == exp1
    verdict = (d2 / "VERDICT.md").read_text()
    assert f"- parent: {exp1}" in verdict and "prediction matched" in verdict
    assert "$comparison" not in verdict
    row = [json.loads(x) for x in (ready_ws / "control/ledger.jsonl").read_text().splitlines()][-1]
    assert row["parent"] == exp1 and row["vs_parent"] == "better" and row["prediction"] == "matched"


def test_changed_folds_are_not_comparable(ready_ws, fake):
    exp1, _, _ = _record(ready_ws, fake, "base", (0.80, 0.81))
    _, _, env = _record(ready_ws, fake, "new folds", (0.84, 0.85), folds_shift=1)
    vs = env["data"]["vs_parent"]
    assert vs["comparable"] is False and "CV scheme changed" in vs["reason"]
    assert env["data"]["prediction"] is None
    assert vs["parent_cv_mean"] == 0.805


def test_strategy_shows_lineage_and_calibration(ready_ws, fake):
    exp1, d1, _ = _record(ready_ws, fake, "base", (0.80, 0.81))
    _, d2, _ = _record(ready_ws, fake, "worse", (0.70, 0.71))  # predicted better: missed
    for d in (d1, d2):
        (d / "VERDICT.md").write_text("# Verdict\nok\n")
    (ready_ws / "r.md").write_text("next\n")
    env = kx(ready_ws, fake, "strategy", "--reasoning-file", "r.md")
    assert env["status"] == "ok"
    text = (ready_ws / "strategy.md").read_text()
    assert f"(from {exp1})" in text and "vs parent: worse" in text
    assert "Pre-registered predictions: 0 of 1 matched." in text
