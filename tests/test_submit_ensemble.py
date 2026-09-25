"""SUB-01..07 (prepare, hand over, read back; never submit), ENS-02 (blending)."""

import json
from datetime import datetime, timezone

import pytest
from conftest import kx
from test_run_record import make_outputs, scaffold

from kx import subs


def _now():
    return datetime.now(timezone.utc).isoformat()


def _recorded(ws, fake, idea="base", scores=(0.8, 0.9)):
    exp, d = scaffold(ws, fake, idea=idea)
    fake.outputs = make_outputs(scores=scores)
    res = json.loads(fake.outputs["result.json"])
    res.update({"sample_columns": ["id", "y"], "sample_rows": 1, "submission_file": "submission.csv"})
    fake.outputs["result.json"] = json.dumps(res).encode()
    fake.statuses = ["COMPLETE"]
    assert kx(ws, fake, "run", exp, "--wait", "5")["data"]["result"] == "SUCCESS"
    return exp, d


def test_kx_has_no_code_path_that_submits():
    from conftest import KX_DIR
    for p in KX_DIR.rglob("*.py"):
        text = p.read_text()
        for api in ("competition_submit", "competition_submit_code", "create_submission",
                    "CreateSubmission", "create_code_submission", "submit_cli"):
            assert api not in text, (p.name, api)


def test_submit_hands_over_the_command(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    exp, d = _recorded(ready_ws, fake)
    env = kx(ready_ws, fake, "submit", exp)
    assert env["status"] == "needs_user", env
    cmd = env["data"]["command"]
    assert " competitions submit titanic -f " in cmd and "kx:exp-001:" in cmd
    assert env["next_action"]["kind"] == "ask_user" and "! " in env["next_action"]["instruction"]
    (row,) = subs.read(ready_ws)
    assert row["status"] == "HANDED_OVER" and row["file_sha256"].startswith("sha256:")


def test_submit_refusals(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: [
        {"date": _now(), "status": "COMPLETE"} for _ in range(10)]
    exp, _ = _recorded(ready_ws, fake)
    env = kx(ready_ws, fake, "submit", exp)
    assert env["status"] == "invalid" and "no submission slots" in env["errors"][0]
    fake.submissions = lambda slug, page_size=50: []
    bad, bd = scaffold(ready_ws, fake, idea="bad")
    fake.statuses = ["ERROR"]
    kx(ready_ws, fake, "run", bad, "--wait", "5")
    assert "only a SUCCESS" in kx(ready_ws, fake, "submit", bad)["errors"][0]


def test_cv_gate_and_lb_read_back(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    exp, _ = _recorded(ready_ws, fake, scores=(0.8, 0.9))
    env = kx(ready_ws, fake, "submit", exp)
    marker = env["data"]["marker"]
    fake.submissions = lambda slug, page_size=50: [
        {"ref": 555, "date": _now(), "description": f"{marker} base", "status": "COMPLETE",
         "public_score": "0.77", "private_score": "", "team_name": "tester"}]
    env = kx(ready_ws, fake, "lb", "--wait", "0")
    assert env["status"] == "ok"
    (s,) = env["data"]["submissions"]
    assert s["status"] == "SCORED" and s["public_score"] == 0.77 and s["private_score"] is None
    assert env["data"]["table"][0].startswith("exp-001: CV 0.85 | LB 0.77")
    worse, _ = _recorded(ready_ws, fake, idea="worse", scores=(0.7, 0.8))
    env = kx(ready_ws, fake, "submit", worse)
    assert any("not better than the best submitted CV" in e for e in env["errors"])
    assert kx(ready_ws, fake, "submit", worse, "--force-cv")["status"] == "needs_user"


def test_lb_pending_is_running(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    exp, _ = _recorded(ready_ws, fake)
    marker = kx(ready_ws, fake, "submit", exp)["data"]["marker"]
    fake.submissions = lambda slug, page_size=50: [
        {"ref": 1, "date": _now(), "description": marker, "status": "PENDING"}]
    env = kx(ready_ws, fake, "lb", "--wait", "0")
    assert env["status"] == "running" and env["next_action"]["command"] == "kx lb"


def test_code_kernel_command_and_internet_check(tmp_path, token_home):
    from conftest import FakeAdapter
    fake = FakeAdapter(comp_slug="equity-post-hct-survival-predictions")
    ws = tmp_path / "ws"
    kx(ws, fake, "init", "equity-post-hct-survival-predictions")
    kx(ws, fake, "sync")
    kx(ws, fake, "confirm", "--note", "t")
    kx(ws, fake, "metric", "roc_auc")
    fake.submissions = lambda slug, page_size=50: []
    exp, _ = scaffold(ws, fake)
    fake.outputs = make_outputs()
    res = json.loads(fake.outputs["result.json"])
    res["metric"] = "roc_auc"
    fake.outputs["result.json"] = json.dumps(res).encode()
    fake.statuses = ["COMPLETE"]
    assert kx(ws, fake, "run", exp, "--wait", "5")["data"]["result"] == "SUCCESS"
    env = kx(ws, fake, "submit", exp)
    cmd = env["data"]["command"]
    assert "competitions submit equity-post-HCT-survival-predictions -k tester/" in cmd
    assert " -v 1 -f submission.csv " in cmd
    fake.kernel_meta["enable_internet"] = True
    assert any("internet ON" in e for e in kx(ws, fake, "submit", exp)["errors"])


def test_agent_outcome_from_replay():
    rep = {"info": {"TeamNames": ["me", "them"]}, "rewards": [1, -1]}
    assert subs.outcome(rep, "me") == ("W", [0])
    assert subs.outcome({"info": {"TeamNames": ["them", "me"]}, "rewards": [1, -1]}, "me")[0] == "L"
    assert subs.outcome({"info": {"TeamNames": ["me", "them"]}, "rewards": [0, 0]}, "me")[0] == "D"
    assert subs.outcome({"info": {"TeamNames": ["me", "me"]}, "rewards": [1, -1]}, "me")[0] == "self"
    assert subs.outcome({"info": {"TeamNames": ["a", "b"]}, "rewards": [1, -1]}, "me") is None


def test_writeup_checklist(tmp_path, token_home):
    from conftest import FakeAdapter
    fake = FakeAdapter(comp_slug="gemma-4-good-hackathon")
    ws = tmp_path / "ws"
    kx(ws, fake, "init", "gemma-4-good-hackathon")
    kx(ws, fake, "sync")
    env = kx(ws, fake, "confirm", "--note", "writeup")
    assert env["next_action"]["command"] == "kx submit --writeup"
    env = kx(ws, fake, "submit", "--writeup")
    assert env["status"] == "needs_user"
    text = (ws / "writeup/CHECKLIST.md").read_text()
    assert "submits it by hand" in text and "Evaluation.md" in text


def test_ensemble_blends_into_a_recorded_experiment(tmp_path, token_home):
    pytest.importorskip("lightgbm")
    from test_templates_local import _fill, _raw, _titanic_like, _ws
    raw = _raw("titanic", "Categorization Accuracy",
               ["gender_submission.csv", "train.csv", "test.csv"])
    ws, fake = _ws(tmp_path, token_home, raw, "accuracy", _titanic_like())
    exps = []
    for i in range(2):
        exp = kx(ws, fake, "new", "--idea", f"m{i}", "--hypothesis", "h", "--local")["data"]["exp_id"]
        _fill(ws, exp)
        p = ws / "experiments" / exp / "train.py"
        p.write_text(p.read_text().replace("n_estimators=400", f"n_estimators={50 + 300 * i}"))
        assert kx(ws, fake, "run", exp)["data"]["result"] == "SUCCESS"
        exps.append(exp)
    env = kx(ws, fake, "ensemble", *exps, "--method", "hill")
    assert env["status"] == "ok" and env["data"]["result"] == "SUCCESS", env
    assert abs(sum(env["data"]["weights"].values()) - 1) < 1e-9
    d = ws / "experiments" / env["data"]["exp_id"]
    assert (d / "output/submission.csv").exists() and (d / "blend.json").exists()
    env2 = kx(ws, fake, "ensemble", *exps, "--method", "weights")
    assert env2["data"]["result"] == "SUCCESS"
    row = json.loads((ws / "control/ledger.jsonl").read_text().splitlines()[-1])
    assert row["idea"].startswith("weights blend of")
