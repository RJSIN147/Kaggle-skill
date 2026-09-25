"""TMPL-01/03, RUN-03/06, ENS-01: rendered templates really run (locally, on
synthetic data) and write outputs the recorder accepts."""

import json

import numpy as np
import pandas as pd
import pytest
from conftest import FakeAdapter, kx

pytest.importorskip("lightgbm")


def _raw(slug, metric, files, tags=()):
    return {
        "slug": slug,
        "competition": {"ref": f"https://www.kaggle.com/competitions/{slug}", "title": slug,
                        "category": "Playground", "evaluation_metric": metric,
                        "max_daily_submissions": 5, "is_kernels_submissions_only": False,
                        "submissions_disabled": False, "deadline": "2030-01-01T00:00:00",
                        "max_team_size": 5, "host_name": "", "user_has_entered": True,
                        "tags": [{"name": t} for t in tags]},
        "files_summary": {"file_summary_info": {"total_file_count": len(files),
                                                "file_types": [{"extension": ".csv",
                                                                "file_count": len(files),
                                                                "total_size": 1000}]}},
        "tree_root": {"files": [{"name": f, "total_bytes": 100} for f in files],
                      "directories": []},
        "tree_depth1": {},
    }


def _ws(tmp_path, token_home, raw, metric_key, frames: dict):
    fake = FakeAdapter()
    fake.raw = raw
    ws = tmp_path / "ws"
    assert kx(ws, fake, "init", raw["slug"])["status"] == "ok"
    assert kx(ws, fake, "sync")["status"] == "ok"
    assert kx(ws, fake, "confirm", "--note", "t")["status"] == "ok"
    assert kx(ws, fake, "metric", metric_key)["status"] == "ok"
    d = ws / "data" / raw["slug"]
    d.mkdir(parents=True)
    for name, df in frames.items():
        df.to_csv(d / name, index=False)
    return ws, fake


def _fill(ws, exp, reasoning="synthetic iid rows"):
    p = ws / "experiments" / exp / "experiment.json"
    spec = json.loads(p.read_text())
    spec["cv"]["reasoning"] = reasoning
    p.write_text(json.dumps(spec))


def _titanic_like(n=240, m=60, seed=0):
    rng = np.random.default_rng(seed)

    def frame(k, start):
        return pd.DataFrame({"PassengerId": range(start, start + k),
                             "Pclass": rng.integers(1, 4, k), "Sex": rng.choice(["m", "f"], k),
                             "Age": rng.normal(30, 10, k).round(1), "Fare": rng.gamma(2, 10, k)})
    tr = frame(n, 1)
    tr.insert(1, "Survived", ((tr.Sex == "f") ^ (rng.random(n) < 0.2)).astype(int))
    te = frame(m, n + 1)
    sub = pd.DataFrame({"PassengerId": te.PassengerId, "Survived": 0})
    return {"train.csv": tr, "test.csv": te, "gender_submission.csv": sub}


@pytest.fixture
def titanic_local(tmp_path, token_home):
    raw = _raw("titanic", "Categorization Accuracy",
               ["gender_submission.csv", "train.csv", "test.csv"])
    return _ws(tmp_path, token_home, raw, "accuracy", _titanic_like())


def test_tabular_local_run_records_success(titanic_local):
    ws, fake = titanic_local
    env = kx(ws, fake, "new", "--idea", "lgbm", "--hypothesis", "h", "--local")
    exp = env["data"]["exp_id"]
    _fill(ws, exp)
    env = kx(ws, fake, "run", exp)
    assert env["status"] == "ok", env
    assert env["data"]["result"] == "SUCCESS", env["data"]
    assert 0.5 < env["data"]["cv_mean"] <= 1.0
    out = ws / "experiments" / exp / "output"
    sub = pd.read_csv(out / "submission.csv")
    assert list(sub.columns) == ["PassengerId", "Survived"] and set(sub.Survived) <= {0, 1}
    assert fake.pushed() == []
    meta = json.loads((ws / "experiments" / exp / "meta.json").read_text())
    assert meta["backend"] == "local" and meta["subsample"] is None
    assert meta["environment"]["libraries"]["lightgbm"]


def test_subsample_is_marked_everywhere(titanic_local):
    ws, fake = titanic_local
    env = kx(ws, fake, "new", "--idea", "sub", "--hypothesis", "h", "--local", "--subsample", "0.5")
    exp = env["data"]["exp_id"]
    _fill(ws, exp)
    env = kx(ws, fake, "run", exp)
    assert env["data"]["result"] == "SUCCESS" and env["data"]["subsample"] == 0.5
    assert any("subsample" in w for w in env["warnings"])
    row = json.loads((ws / "control/ledger.jsonl").read_text().splitlines()[-1])
    assert row["subsample"] == 0.5
    oof = pd.read_csv(ws / "experiments" / exp / "output" / "oof.csv")
    assert len(oof) == 120


def test_local_throw_is_failed_with_traceback(titanic_local):
    ws, fake = titanic_local
    env = kx(ws, fake, "new", "--idea", "boom", "--hypothesis", "h", "--local")
    exp = env["data"]["exp_id"]
    _fill(ws, exp)
    p = ws / "experiments" / exp / "train.py"
    p.write_text(p.read_text().replace('    X = train.drop(', '    raise ValueError("boom")\n    X = train.drop(', 1))
    env = kx(ws, fake, "run", exp)
    assert env["data"]["result"] == "FAILED" and env["data"]["failure_reason"] == "kernel_error"
    assert env["data"]["failure_detail"]["error_line"] == "ValueError: boom"


def test_local_run_needs_data(tmp_path, token_home):
    raw = _raw("titanic", "Categorization Accuracy", ["gender_submission.csv", "train.csv", "test.csv"])
    fake = FakeAdapter()
    fake.raw = raw
    ws = tmp_path / "ws"
    kx(ws, fake, "init", "titanic")
    kx(ws, fake, "sync")
    kx(ws, fake, "confirm", "--note", "t")
    kx(ws, fake, "metric", "accuracy")
    exp = kx(ws, fake, "new", "--idea", "x", "--hypothesis", "h", "--local")["data"]["exp_id"]
    _fill(ws, exp)
    env = kx(ws, fake, "run", exp)
    assert env["errors"] == ["no_local_data"]
    assert env["next_action"]["command"] == "kx sync titanic --download"


def test_multiclass_and_regression_templates(tmp_path, token_home):
    rng = np.random.default_rng(1)
    n, m = 300, 50
    tr = pd.DataFrame({"id": range(n), "a": rng.normal(size=n), "b": rng.normal(size=n)})
    tr["label"] = np.where(tr.a > 0.5, "x", np.where(tr.b > 0, "y", "z"))
    te = pd.DataFrame({"id": range(n, n + m), "a": rng.normal(size=m), "b": rng.normal(size=m)})
    frames = {"train.csv": tr, "test.csv": te,
              "sample_submission.csv": pd.DataFrame({"id": te.id, "label": "x"})}
    raw = _raw("multi", "Multiclass Loss", ["sample_submission.csv", "train.csv", "test.csv"])
    ws, fake = _ws(tmp_path, token_home, raw, "logloss", frames)
    exp = kx(ws, fake, "new", "--idea", "mc", "--hypothesis", "h", "--local")["data"]["exp_id"]
    _fill(ws, exp)
    env = kx(ws, fake, "run", exp)
    assert env["data"]["result"] == "SUCCESS", env
    res = json.loads((ws / "experiments" / exp / "output/result.json").read_text())
    assert res["predictions"]["pred_columns"] == ["pred_0", "pred_1", "pred_2"]
    assert res["predictions"]["classes"] == ["x", "y", "z"]


def _store_like(seed=2):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=200, freq="D")
    rows = [(d, s, rng.poisson(20 + 5 * s + 3 * d.dayofweek)) for d in dates for s in range(3)]
    tr = pd.DataFrame(rows, columns=["date", "store", "sales"])
    tr.insert(0, "id", range(len(tr)))
    tdates = pd.date_range(dates[-1] + pd.Timedelta(days=1), periods=14, freq="D")
    te = pd.DataFrame([(d, s) for d in tdates for s in range(3)], columns=["date", "store"])
    te.insert(0, "id", range(len(tr), len(tr) + len(te)))
    tr["date"] = tr["date"].dt.strftime("%Y-%m-%d")
    te["date"] = te["date"].dt.strftime("%Y-%m-%d")
    return {"train.csv": tr, "test.csv": te,
            "sample_submission.csv": pd.DataFrame({"id": te.id, "sales": 0.0})}


def test_timeseries_template_is_walk_forward(tmp_path, token_home):
    raw = _raw("store", "Root Mean Squared Logarithmic Error",
               ["sample_submission.csv", "train.csv", "test.csv"], tags=("time series analysis",))
    ws, fake = _ws(tmp_path, token_home, raw, "rmsle", _store_like())
    env = kx(ws, fake, "new", "--idea", "wf", "--hypothesis", "h", "--local", "--template",
             "timeseries")
    assert env["errors"] == ["template_reason_required"]
    env = kx(ws, fake, "new", "--idea", "wf", "--hypothesis", "h", "--local", "--folds", "3",
             "--template", "timeseries", "--template-reason", "sales are time-ordered")
    exp = env["data"]["exp_id"]
    assert "AI override of 'tabular'" in env["data"]["template_reason"]
    _fill(ws, exp, "test is the next 14 days, so validate on the last 3 14-day windows")
    env = kx(ws, fake, "run", exp)
    assert env["data"]["result"] == "SUCCESS", env
    out = ws / "experiments" / exp / "output"
    res = json.loads((out / "result.json").read_text())
    assert res["cv_scheme"] == "walk-forward (expanding window)"
    oof = pd.read_csv(out / "oof.csv")
    assert (oof.fold == -1).sum() > 0 and sorted(oof.fold[oof.fold >= 0].unique()) == [0, 1, 2]
    meta = json.loads((ws / "experiments" / exp / "meta.json").read_text())
    assert meta["template"] == "timeseries"
    assert "sales are time-ordered" in json.loads(
        (ws / "experiments" / exp / "experiment.json").read_text())["template_reason"]
