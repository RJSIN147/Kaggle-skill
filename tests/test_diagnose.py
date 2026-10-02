"""kx diagnose: facts.json validation, findings, real local runs, evidence references."""

import json

import numpy as np
import pandas as pd
import pytest
from conftest import kx
from test_templates_local import _raw, _store_like, _ws

from kx import diagnose

pytest.importorskip("lightgbm")


def _facts(**over):
    base = {"format": "kx-facts/1", "n_train": 10, "n_test": 5, "columns": {}, "time": [],
            "entities": [], "single_feature": [], "duplicates": {},
            "adversarial": {"status": "ok", "fold_aucs": [0.5, 0.52], "auc_mean": 0.51,
                            "top_features": [{"column": "a", "gain_share": 0.9}]}}
    base.update(over)
    return base


def _write(tmp_path, facts):
    (tmp_path / "facts.json").write_text(json.dumps(facts))
    return diagnose.read_facts(tmp_path)


# --------------------------------------------------------------------------- #
# facts.json validation (fail closed) and findings
# --------------------------------------------------------------------------- #
def test_read_facts_fails_closed(tmp_path):
    assert diagnose.read_facts(tmp_path)[1] == "missing_result"
    facts, reason, result = _write(tmp_path, _facts())
    assert reason is None and result["n_folds"] == 2 and result["cv_mean"] == pytest.approx(0.51)
    assert _write(tmp_path, _facts(format="x"))[1] == "schema_invalid"
    bad_mean = _facts(adversarial={"status": "ok", "fold_aucs": [0.5, 0.6], "auc_mean": 0.9})
    assert _write(tmp_path, bad_mean)[1] == "schema_invalid"
    out = _facts(adversarial={"status": "ok", "fold_aucs": [0.5, 1.5], "auc_mean": 1.0})
    assert _write(tmp_path, out)[1] == "out_of_range"
    skipped = _facts(adversarial={"status": "skipped", "reason": "tiny test"})
    _, reason, result = _write(tmp_path, skipped)
    assert reason is None and result["cv_mean"] is None and result["fold_scores"] == []
    assert _write(tmp_path, _facts(n_train="10"))[1] == "schema_invalid"


def test_findings_thresholds():
    def codes(**over):
        return [(f["severity"], f["code"]) for f in diagnose.findings(_facts(**over))]

    assert codes() == []
    adv = {"status": "ok", "fold_aucs": [0.65, 0.65], "auc_mean": 0.65, "top_features": []}
    assert codes(adversarial=adv) == [("medium", "adversarial_shift")]
    adv = dict(adv, fold_aucs=[0.8, 0.8], auc_mean=0.8)
    assert codes(adversarial=adv) == [("high", "adversarial_shift")]
    assert codes(time=[{"column": "date", "relation": "test_after_train"}]) == \
        [("high", "test_after_train")]
    assert codes(entities=[{"column": "pid", "rows_per_value": 5, "test_overlap": 0.1}]) == \
        [("high", "unseen_entities")]
    assert codes(entities=[{"column": "pid", "rows_per_value": 5, "test_overlap": 0.9}]) == \
        [("info", "shared_entities")]
    assert codes(single_feature=[{"column": "x", "kind": "auc", "score": 0.99}]) == \
        [("high", "single_feature_leak")]
    assert codes(duplicates={"test_in_train": 0.02, "train_internal": 0.0}) == \
        [("medium", "test_rows_in_train")]
    mixed = codes(duplicates={"test_in_train": 0.5},
                  time=[{"column": "d", "relation": "test_after_train"}])
    assert [s for s, _ in mixed] == ["high", "medium"]  # most severe first


# --------------------------------------------------------------------------- #
# real local runs of the diagnose template
# --------------------------------------------------------------------------- #
def _tabular(n=3000, m=1500, shift=0.0, leak=False, groups=False, seed=0):
    rng = np.random.default_rng(seed)

    def frame(k, start, s):
        # "cabin": mostly missing, nearly unique when present (Titanic's Cabin): not an entity
        cabin = [f"C{start + i}" if rng.random() < 0.2 else None for i in range(k)]
        df = pd.DataFrame({"id": range(start, start + k), "a": rng.normal(s, 1, k),
                           "b": rng.normal(0, 1, k), "c": rng.choice(list("pqrstuvwxy"), k),
                           "cabin": cabin})
        if groups:
            df["patient_id"] = rng.integers(start, start + k // 10, k)
        return df
    tr = frame(n, 0, 0.0)
    tr.insert(1, "y", (tr.b + rng.normal(0, 1, n) > 0).astype(int))
    if leak:
        tr["leak"] = tr.y + rng.normal(0, 0.01, n)
    te = frame(m, n, shift)
    if leak:
        te["leak"] = rng.normal(0.5, 0.5, m)
    return {"train.csv": tr, "test.csv": te,
            "sample_submission.csv": pd.DataFrame({"id": te.id, "y": 0})}


def _diagnose_ws(tmp_path, token_home, frames, slug="synth", metric=("Roc Auc Score", "roc_auc")):
    raw = _raw(slug, metric[0], ["sample_submission.csv", "train.csv", "test.csv"])
    ws, fake = _ws(tmp_path, token_home, raw, metric[1], frames)
    return ws, fake


def _run_diagnose(ws, fake):
    env = kx(ws, fake, "diagnose", "--local")
    assert env["status"] == "ok", env
    exp = env["data"]["exp_id"]
    env = kx(ws, fake, "run", exp)
    assert env["status"] == "ok" and env["data"]["result"] == "SUCCESS", env
    return exp, env


def test_iid_data_is_clean_and_facts_are_published(tmp_path, token_home):
    ws, fake = _diagnose_ws(tmp_path, token_home, _tabular())
    exp, env = _run_diagnose(ws, fake)
    assert env["data"]["cv_mean"] < diagnose.ADV_MEDIUM
    assert not [f for f in env["data"]["findings"] if f["severity"] == "high"]
    assert env["data"]["validation"] == "ok"
    facts = json.loads((ws / "control" / "facts.json").read_text())
    assert facts["from"] == exp and facts["n_train"] == 3000 and facts["target"]["column"] == "y"
    assert facts["adversarial"]["status"] == "ok" and "id" not in facts["columns"]
    assert "cabin" not in [e["column"] for e in facts["entities"]]
    meta = json.loads((ws / "experiments" / exp / "meta.json").read_text())
    assert meta["kind"] == "diagnostic" and meta["metric"] == "adv_auc"
    row = json.loads((ws / "control" / "ledger.jsonl").read_text().splitlines()[-1])
    assert row["kind"] == "diagnostic"
    # never a submission candidate, a blend member or a default parent
    assert kx(ws, fake, "submit", exp)["errors"] == ["not_a_candidate"]
    env = kx(ws, fake, "new", "--idea", "x", "--hypothesis", "h", "--local")
    assert env["status"] == "ok" and env["data"]["parent"] is None
    assert any("[diagnostic]" in t for t in env["data"]["tried"])


def test_shift_leak_and_unseen_entities_are_found(tmp_path, token_home):
    ws, fake = _diagnose_ws(tmp_path, token_home,
                            _tabular(shift=2.0, leak=True, groups=True))
    _, env = _run_diagnose(ws, fake)
    codes = {f["code"] for f in env["data"]["findings"] if f["severity"] == "high"}
    assert {"adversarial_shift", "single_feature_leak", "unseen_entities"} <= codes
    assert env["data"]["validation"] == "suspect"
    assert any("SUSPECT" in w for w in env["warnings"])
    env = kx(ws, fake, "new", "--idea", "x", "--hypothesis", "h", "--local")
    assert env["status"] == "ok" and any("SUSPECT" in w for w in env["warnings"])
    facts = json.loads((ws / "control" / "facts.json").read_text())
    assert facts["adversarial"]["top_features"][0]["column"] == "a"
    assert facts["single_feature"][0]["column"] == "leak"


def test_time_ordered_data_and_a_tiny_test_set(tmp_path, token_home):
    ws, fake = _diagnose_ws(tmp_path, token_home, _store_like(), slug="store",
                            metric=("Root Mean Squared Logarithmic Error", "rmsle"))
    _, env = _run_diagnose(ws, fake)
    codes = [(f["severity"], f["code"]) for f in env["data"]["findings"]]
    assert ("high", "test_after_train") in codes and ("info", "adversarial_skipped") in codes
    assert env["data"]["cv_mean"] is None


def test_metric_points_at_diagnose_and_new_refuses_the_template(tmp_path, token_home):
    raw = _raw("synth", "Roc Auc Score", ["sample_submission.csv", "train.csv", "test.csv"])
    ws, fake = _ws(tmp_path, token_home, raw, "roc_auc", _tabular(n=50, m=20))
    env = kx(ws, fake, "metric", "roc_auc")
    assert env["next_action"]["command"] == "kx diagnose"
    env = kx(ws, fake, "new", "--idea", "x", "--hypothesis", "h", "--template", "diagnose",
             "--template-reason", "r")
    assert env["errors"] == ["use_kx_diagnose"]


def test_not_diagnosable_without_a_train_test_pair(tmp_path, token_home):
    raw = _raw("synth", "Roc Auc Score", ["sample_submission.csv", "data.json"])
    ws, fake = _ws(tmp_path, token_home, raw, "roc_auc", {})
    assert kx(ws, fake, "diagnose")["errors"] == ["not_diagnosable"]


def test_evidence_references_are_resolved_by_kx(tmp_path, token_home):
    ws, fake = _diagnose_ws(tmp_path, token_home, _tabular())
    exp, _ = _run_diagnose(ws, fake)
    env = kx(ws, fake, "new", "--idea", "x", "--hypothesis", "h", "--local",
             "--evidence", "facts:n_train", "--evidence", f"{exp}:cv_mean",
             "--evidence", "facts:columns.c.test_unseen_share")
    assert env["status"] == "ok", env
    ev = env["data"]["evidence"]
    assert ev[0] == {"ref": "facts:n_train", "value": 3000}
    assert isinstance(ev[1]["value"], float) and ev[2]["value"] == 0.0
    spec = json.loads((ws / "experiments" / env["data"]["exp_id"] / "experiment.json")
                      .read_text())
    assert spec["evidence"] == ev
    for bad in ("facts:nope", "exp-999:cv_mean", "free text", "facts:"):
        env = kx(ws, fake, "new", "--idea", "x", "--hypothesis", "h", "--evidence", bad)
        assert env["status"] == "invalid", bad
