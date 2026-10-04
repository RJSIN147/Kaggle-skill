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
        extra = {"folds": [(r["PassengerId"], f) for r, f in zip(rows, folds)]} if FOLDS else {}
        report(scores, note="majority class", **extra)
'''


@pytest.fixture
def titanic_custom(tmp_path, token_home):
    raw = _raw("titanic", "Categorization Accuracy",
               ["gender_submission.csv", "train.csv", "test.csv"])
    return _ws(tmp_path, token_home, raw, "accuracy", _titanic_like())


def _custom(ws, fake, *extra, new_args=None, **flags):
    env = kx(ws, fake, "new", "--idea", "majority", "--hypothesis", "h", *(new_args or (
        "--template", "custom", "--template-reason", "testing the contract", "--expect", "same")),
        "--local", *extra)
    assert env["status"] == "ok", env
    exp = env["data"]["exp_id"]
    d = ws / "experiments" / exp
    code = (d / "main.py").read_text()
    opts = {"WRITE_PREDS": False, "WRITE_OUTPUT": True, "STOP": False, "REPORT": True,
            "FOLDS": False} | flags
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
    exp = env["data"]["exp_id"]
    code = (ws / "experiments" / exp / "main.py").read_text()
    assert "EXPECTED_OUTPUT = 'submission.json'" in code
    # a code-competition proposal for a custom kernel, CV shown under the metric's label
    d = ws / "experiments" / exp
    (d / "main.py").write_text(code.replace(STUB, "report([0.1, 0.2, 0.1, 0.2, 0.1])"))
    spec = json.loads((d / "experiment.json").read_text())
    spec["cv"]["reasoning"] = "x"
    (d / "experiment.json").write_text(json.dumps(spec))
    res = {"exp_id": exp, "metric": "custom", "n_folds": 5, "fold_scores": [0.1, 0.2, 0.1, 0.2, 0.1],
           "cv_mean": 0.14, "cv_std": 0.05, "submission_file": "submission.json"}
    fake.outputs = {"result.json": json.dumps(res).encode(), "submission.json": b"{}",
                    "kx_manifest.json": b"{}"}
    fake.statuses = ["COMPLETE"]
    assert kx(ws, fake, "run", exp, "--wait", "5")["data"]["result"] == "SUCCESS"
    fake.submissions = lambda slug, page_size=50: []
    env = kx(ws, fake, "submit", exp)
    assert env["status"] == "needs_user", env
    assert "CV: task accuracy 0.14" in env["data"]["confirmation"]
    assert any("output submission.json" in line for line in env["data"]["confirmation"])


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
    # a second stage that changes one thing in the first starts from the first's block
    (down / "main.py").write_text((down / "main.py").read_text().replace(
        "# upstream marker", "# stage marker"))
    env = kx(ws, fake, "new", "--idea", "rule", "--hypothesis", "h", "--after", up,
             "--parent", down.name, "--expect", "better")
    assert env["status"] == "ok", env
    assert env["data"]["ai_block_from"] == down.name
    assert "# stage marker" in (ws / "experiments" / env["data"]["exp_id"] / "main.py").read_text()


def test_report_folds_gives_a_fold_hash_and_a_paired_comparison(titanic_custom):
    ws, fake = titanic_custom
    a, da = _custom(ws, fake, FOLDS=True)
    assert kx(ws, fake, "run", a)["data"]["result"] == "SUCCESS"
    assert json.loads((da / "meta.json").read_text())["fold_hash"].startswith("sha256:")
    b, _ = _custom(ws, fake, "--parent", a, FOLDS=True)
    env = kx(ws, fake, "run", b)
    assert env["data"]["vs_parent"]["comparable"] is True, env["data"]["vs_parent"]
    c, dc = _custom(ws, fake, "--parent", a)  # starts from a's block: drop the folds
    (dc / "main.py").write_text((dc / "main.py").read_text().replace(
        "    FOLDS = True\n", "    FOLDS = False\n"))
    env = kx(ws, fake, "run", c)  # no fold assignment: the reason says how to get one
    assert "report(folds=...)" in env["data"]["vs_parent"]["reason"]


def test_a_no_cv_experiment_is_recorded_without_a_score_and_inherited(titanic_custom):
    ws, fake = titanic_custom
    a, da = _custom(ws, fake, new_args=("--no-cv",), REPORT=False)
    spec = json.loads((da / "experiment.json").read_text())
    assert spec["kind"] == "no_cv" and spec["template"] == "custom" and spec["parent"] is None
    assert spec["expected_effect"] is None and "NO_CV = True" in (da / "main.py").read_text()
    env = kx(ws, fake, "run", a)
    assert env["data"]["result"] == "SUCCESS" and env["data"]["cv_mean"] is None, env
    assert "leaderboard only" in env["summary"]
    # a child of a no-CV run is no-CV too, needs no --expect, and never calls report()
    b, db = _custom(ws, fake, "--parent", a, new_args=())
    assert json.loads((db / "experiment.json").read_text())["kind"] == "no_cv"
    code = (db / "main.py").read_text()  # starts from a's block; now break the contract
    (db / "main.py").write_text(code.replace("    REPORT = False\n", "    REPORT = True\n"))
    env = kx(ws, fake, "run", b)
    assert env["data"]["result"] == "FAILED" and env["data"]["failure_reason"] == "kernel_error"
    status = kx(ws, fake, "status")
    assert any("no CV (leaderboard only)" in t for t in status["data"]["tried"])
    assert kx(ws, fake, "new", "--no-cv", "--idea", "x", "--hypothesis", "h", "--template",
              "tabular", "--template-reason", "r")["errors"] == ["bad_no_cv"]
