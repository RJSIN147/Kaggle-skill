"""TMPL-02 / RUN-05: the deep template trains (AMP, checkpoints), stops at its time
budget, resumes from its checkpoints, and an inference stage reads an upstream's
fold models. Runs only where torch is installed (e.g. `uv run --with torch pytest`)."""

import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest
from conftest import FakeAdapter, kx

torch = pytest.importorskip("torch")


def _digits(n=240, m=40, seed=0):
    rng = np.random.default_rng(seed)
    y = rng.integers(0, 3, n)
    img = rng.integers(0, 40, (n, 784))
    for c in range(3):  # class c lights up a band of rows
        img[y == c, c * 200:c * 200 + 150] += 180
    tr = pd.DataFrame(img, columns=[f"pixel{i}" for i in range(784)])
    tr.insert(0, "label", y)
    te = pd.DataFrame(rng.integers(0, 255, (m, 784)), columns=[f"pixel{i}" for i in range(784)])
    sub = pd.DataFrame({"ImageId": range(1, m + 1), "Label": 0})
    return tr, te, sub


@pytest.fixture
def digits_ws(tmp_path, token_home):
    fake = FakeAdapter(comp_slug="digit-recognizer")
    ws = tmp_path / "ws"
    kx(ws, fake, "init", "digit-recognizer")
    kx(ws, fake, "sync")
    assert kx(ws, fake, "confirm", "--note", "t")["data"]["template"] == "deep"
    kx(ws, fake, "metric", "accuracy")
    d = ws / "data" / "digit-recognizer"
    d.mkdir(parents=True)
    tr, te, sub = _digits()
    tr.to_csv(d / "train.csv", index=False)
    te.to_csv(d / "test.csv", index=False)
    sub.to_csv(d / "sample_submission.csv", index=False)
    return ws, fake


def _run_script(exp_dir, data_dir, out_dir, extra_env=None):
    env = dict(os.environ, KX_DATA_DIR=str(data_dir), KX_OUTPUT_DIR=str(out_dir),
               PYTHON_COLORS="0")
    env.update(extra_env or {})
    return subprocess.run([sys.executable, "train.py"], cwd=exp_dir, env=env,
                          capture_output=True, text=True, timeout=600)


def _fill(ws, exp, **overrides):
    p = ws / "experiments" / exp / "experiment.json"
    spec = json.loads(p.read_text())
    spec["cv"]["reasoning"] = "iid digits"
    p.write_text(json.dumps(spec))
    code = ws / "experiments" / exp / "train.py"
    text = code.read_text()
    for k, v in overrides.items():
        text = text.replace(f"\n{k} = ", f"\n{k} = {v!r}  # was: ", 1)
    code.write_text(text)


def test_deep_train_budget_resume_and_infer(digits_ws, tmp_path):
    ws, fake = digits_ws
    env = kx(ws, fake, "new", "--idea", "small cnn", "--hypothesis", "h", "--folds", "2")
    assert env["data"]["template"] == "deep"
    exp = env["data"]["exp_id"]
    _fill(ws, exp, EPOCHS=2, BATCH_SIZE=32, NUM_WORKERS=0)
    exp_dir = ws / "experiments" / exp
    data_dir = ws / "data" / "digit-recognizer"

    # 1) a tiny budget: stops cleanly before finishing, checkpoints saved
    out1 = tmp_path / "run1"
    code = (exp_dir / "train.py").read_text()
    (exp_dir / "train.py").write_text(code.replace("TIME_BUDGET_S = ", "TIME_BUDGET_S = 0 or ", 1)
                                      .replace("if elapsed + (epoch_s or 0) > TIME_BUDGET_S:",
                                               "if epoch == 1 and not resumed:", 1))
    r = _run_script(exp_dir, data_dir, out1)
    assert r.returncode == 0, r.stderr[-2000:]
    res = json.loads((out1 / "result.json").read_text())
    assert res["incomplete"] is True and res["stopped_at"] == {"fold": 0, "epoch": 1}
    assert (out1 / "checkpoints/fold0/last.pt").exists()

    # 2) resume: the previous output mounted as /kaggle/input/<slug>/ is simulated by
    #    seeding the new output's checkpoints (what _restore_checkpoints copies)
    out2 = tmp_path / "run2"
    import shutil
    shutil.copytree(out1 / "checkpoints", out2 / "checkpoints")
    r = _run_script(exp_dir, data_dir, out2)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "KX_RESUMED fold 0 at epoch 1" in r.stdout
    res = json.loads((out2 / "result.json").read_text())
    assert res["stage"] == "train" and len(res["fold_scores"]) == 2
    assert res["predictions"]["pred_columns"] == ["pred_0", "pred_1", "pred_2"]
    from kx import preds
    assert preds.validate(out2, res["predictions"], 2) == []
    assert (out2 / "checkpoints/fold1/model.pt").exists()
    man = json.loads((out2 / "kx_manifest.json").read_text())
    assert man["run_nonce"] and "torch" in man["libraries"]

    # 3) inference stage reading the upstream output (mounted like kernel_sources)
    env = kx(ws, fake, "new", "--idea", "infer", "--hypothesis", "h", "--after", exp)
    assert env["data"]["template"] == "deep-infer"
    inf = env["data"]["exp_id"]
    spec = json.loads((ws / "experiments" / inf / "experiment.json").read_text())
    assert spec["sources"]["kernels"] == [f"@{exp}"] and spec["cv"]["n_folds"] == 2
    code = (ws / "experiments" / inf / "train.py").read_text()
    code = code.replace('Path("/kaggle/input/notebooks") / owner / slug', f'Path({str(out2)!r})')
    code = code.replace("NUM_WORKERS = 2", "NUM_WORKERS = 0")
    (ws / "experiments" / inf / "train.py").write_text(code)
    out3 = tmp_path / "run3"
    r = _run_script(ws / "experiments" / inf, data_dir, out3)
    assert r.returncode == 0, r.stderr[-2000:]
    res3 = json.loads((out3 / "result.json").read_text())
    assert res3["stage"] == "infer" and res3["fold_scores"] == res["fold_scores"]
    up = json.loads((out3 / "upstream_manifest.json").read_text())
    assert up["run_nonce"] == man["run_nonce"]
    assert preds.validate(out3, res3["predictions"], 2) == []
