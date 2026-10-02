"""The bring-your-own `custom` template: selection, the output contract, stages."""

import ast
import json

import pytest
from conftest import FakeAdapter, kx
from test_run_record import make_outputs
from test_templates_local import _raw, _titanic_like, _ws

from kx import experiment

STUB = 'raise NotImplementedError("KX_TODO: write the pipeline for this idea")'

# A tiny stdlib pipeline: majority-class "model" per fold, scored with accuracy.
PIPELINE = '''
    rows = list(csv.DictReader(open(DATA_DIR / "train.csv")))
    test = list(csv.DictReader(open(DATA_DIR / "test.csv")))
    folds = [i % N_FOLDS for i in range(len(rows))]
    scores, oof = [], []
    for k in range(N_FOLDS):
        tr = [r for r, f in zip(rows, folds) if f != k]
        va = [r for r, f in zip(rows, folds) if f == k]
        rate = sum(r["Survived"] == "1" for r in tr) / len(tr)
        guess = "1" if rate >= 0.5 else "0"
        scores.append(sum(r["Survived"] == guess for r in va) / len(va))
        oof += [(r["PassengerId"], k, r["Survived"], rate) for r in va]
    if WRITE_PREDS:
        write_preds(oof, [(r["PassengerId"], 0.4) for r in test])
    if WRITE_OUTPUT:
        with (OUT / EXPECTED_OUTPUT).open("w") as fh:
            fh.write("PassengerId,Survived\\n" + "".join(f"{r['PassengerId']},0\\n" for r in test))
    if STOP:
        stop_incomplete({"fold": 0})
        return
    if REPORT:
        report(scores, note="majority class")
'''


@pytest.fixture
def titanic_custom(tmp_path, token_home):
    raw = _raw("titanic", "Categorization Accuracy",
               ["gender_submission.csv", "train.csv", "test.csv"])
    return _ws(tmp_path, token_home, raw, "accuracy", _titanic_like())


def _custom(ws, fake, *extra, **flags):
    env = kx(ws, fake, "new", "--idea", "majority", "--hypothesis", "h", "--template", "custom",
             "--template-reason", "testing the contract", "--local", "--expect", "same", *extra)
    assert env["status"] == "ok", env
    exp = env["data"]["exp_id"]
    d = ws / "experiments" / exp
    code = (d / "main.py").read_text()
    opts = {"WRITE_PREDS": False, "WRITE_OUTPUT": True, "STOP": False, "REPORT": True} | flags
    body = "".join(f"    {k} = {v}\n" for k, v in opts.items()) + PIPELINE
    (d / "main.py").write_text(code.replace(f"    {STUB}\n", body))
    spec = json.loads((d / "experiment.json").read_text())
    spec["cv"]["reasoning"] = "iid rows"
    (d / "experiment.json").write_text(json.dumps(spec))
    return exp, d


def test_custom_renders_a_stdlib_harness_and_refuses_the_stub(titanic_custom):
    ws, fake = titanic_custom
    env = kx(ws, fake, "new", "--idea", "x", "--hypothesis", "h", "--template", "custom",
             "--template-reason", "r", "--local")
    d = ws / "experiments" / env["data"]["exp_id"]
    code = (d / "main.py").read_text()
    tree = ast.parse(code)
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
            for a in n.names}
    assert mods <= {"csv", "json", "math", "os", "platform", "shutil", "statistics", "sys",
                    "time", "types"}, mods
    assert "import kx" not in code and "from kx" not in code
    spec = json.loads((d / "experiment.json").read_text())
    spec["cv"]["reasoning"] = "x"
    (d / "experiment.json").write_text(json.dumps(spec))
    env = kx(ws, fake, "run", env["data"]["exp_id"])
    assert env["status"] == "invalid"
    assert any(experiment.AI_STUB in e for e in env["errors"])


def test_a_pipeline_that_honours_the_contract_is_recorded(titanic_custom):
    ws, fake = titanic_custom
    exp, d = _custom(ws, fake, WRITE_PREDS=True)
    env = kx(ws, fake, "run", exp)
    assert env["data"]["result"] == "SUCCESS", env
    res = json.loads((d / "output" / "result.json").read_text())
    assert res["note"] == "majority class" and res["n_folds"] == 5
    meta = json.loads((d / "meta.json").read_text())
    assert meta["predictions"]["format"] == "kx-preds/1" and meta["fold_hash"]
    assert json.loads((d / "output" / "kx_manifest.json").read_text())["exp_id"] == exp


@pytest.mark.parametrize("flags,reason", [
    ({"REPORT": False}, "kernel_error"),
    ({"WRITE_OUTPUT": False}, "kernel_error"),
    ({"STOP": True}, "runtime_limit"),
])
def test_contract_breaches_fail_closed(titanic_custom, flags, reason):
    ws, fake = titanic_custom
    exp, d = _custom(ws, fake, **flags)
    env = kx(ws, fake, "run", exp)
    assert env["data"]["result"] == "FAILED" and env["data"]["failure_reason"] == reason, env
    assert env["data"]["cv_mean"] is None
    assert not json.loads((d / "meta.json").read_text()).get("resumable")  # local: no resume


def test_no_template_profiles_fall_back_to_custom(tmp_path, token_home):
    fake = FakeAdapter(comp_slug="arc-prize-2026-arc-agi-2")
    ws = tmp_path / "ws"
    kx(ws, fake, "init", "arc-prize-2026-arc-agi-2")
    kx(ws, fake, "sync")
    env = kx(ws, fake, "confirm", "--note", "t")
    assert env["data"]["template"] == "custom"
    assert env["data"]["type_guides"] == ["references/types/custom.md",
                                          "references/types/code-competition.md"]
    env = kx(ws, fake, "metric", "custom", "--direction", "higher", "--range", "0", "1",
             "--label", "task accuracy")
    assert "task accuracy" in env["summary"] and env["data"]["metric"]["label"] == "task accuracy"
    env = kx(ws, fake, "new", "--idea", "x", "--hypothesis", "h")
    assert env["data"]["template"] == "custom"
    code = (ws / "experiments" / env["data"]["exp_id"] / "main.py").read_text()
    assert "EXPECTED_OUTPUT = 'submission.json'" in code


def test_custom_stages_chain_and_refuse_internet_when_submitted(tmp_path, token_home):
    fake = FakeAdapter(comp_slug="equity-post-hct-survival-predictions")
    ws = tmp_path / "ws"
    kx(ws, fake, "init", "equity-post-hct-survival-predictions")
    kx(ws, fake, "sync")
    kx(ws, fake, "confirm", "--note", "t")
    kx(ws, fake, "metric", "roc_auc")
    env = kx(ws, fake, "new", "--idea", "train", "--hypothesis", "h", "--template", "custom",
             "--template-reason", "survival model")
    up = env["data"]["exp_id"]
    d = ws / "experiments" / up
    (d / "main.py").write_text((d / "main.py").read_text().replace(
        STUB, "report([0.6, 0.7, 0.6, 0.7, 0.6])  # upstream marker"))
    spec = json.loads((d / "experiment.json").read_text())
    spec["cv"]["reasoning"] = "x"
    (d / "experiment.json").write_text(json.dumps(spec))
    fake.outputs = make_outputs()
    res = json.loads(fake.outputs["result.json"])
    res["metric"] = "roc_auc"
    fake.outputs["result.json"] = json.dumps(res).encode()
    fake.statuses = ["COMPLETE"]
    assert kx(ws, fake, "run", up, "--wait", "5")["data"]["result"] == "SUCCESS"
    env = kx(ws, fake, "new", "--idea", "infer", "--hypothesis", "h", "--after", up)
    assert env["status"] == "ok", env
    down = ws / "experiments" / env["data"]["exp_id"]
    spec = json.loads((down / "experiment.json").read_text())
    assert spec["template"] == "custom" and spec["sources"]["kernels"] == [f"@{up}"]
    assert spec["expected_effect"]["direction"] == "same"
    assert spec["cv"]["reasoning"].startswith(f"inherits {up}")
    assert "# upstream marker" in (down / "main.py").read_text()
    spec["runtime"]["internet"] = True
    (down / "experiment.json").write_text(json.dumps(spec))
    pushes = len(fake.pushed())
    env = kx(ws, fake, "run", env["data"]["exp_id"], "--wait", "5")
    assert env["errors"] == ["internet_on_submitted_stage"] and len(fake.pushed()) == pushes
