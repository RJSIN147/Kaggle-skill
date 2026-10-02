"""SUB-01..07 (propose, submit on confirmation, read back), ENS-02 (blending)."""

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


def test_only_the_adapter_calls_the_submit_api():
    from conftest import KX_DIR
    for p in KX_DIR.rglob("*.py"):
        text = p.read_text()
        for api in ("competition_submit", "create_submission", "create_code_submission",
                    "submit_cli"):
            if api in text:
                assert p.name == "adapter.py", (p.name, api)
    src = (KX_DIR / "submit.py").read_text()
    # the one call site is the confirmed path
    assert src.count("adapter.submit(") == 2 and src.index("adapter.submit(") > \
        src.index("def _submit_confirmed")


def _propose(ws, fake, *extra):
    env = kx(ws, fake, "submit", *extra)
    assert env["status"] == "needs_user", env
    return env, env["next_action"]["then"].split("--confirm ")[1].split()[0]


def test_submit_proposes_then_submits_only_on_confirm(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    exp, d = _recorded(ready_ws, fake)
    env, token = _propose(ready_ws, fake, exp)
    assert not fake.submitted()
    lines = env["data"]["confirmation"]
    assert any(line.startswith("competition: titanic") for line in lines)
    assert any("submits: file " in line and "sha256:" in line for line in lines)
    assert any(line.startswith("CV: ") for line in lines)
    assert env["next_action"]["kind"] == "ask_user"
    assert env["next_action"]["then"] == f"kx submit {exp} --confirm {token}"
    assert "manual_command" not in env["data"]
    (row,) = subs.read(ready_ws)
    assert row["status"] == "PROPOSED" and row["file_sha256"].startswith("sha256:")
    assert kx(ready_ws, fake, "lb", "--wait", "0")["summary"] == "no submissions yet"

    env = kx(ready_ws, fake, "submit", exp, "--confirm", token)
    assert env["status"] == "ok" and env["data"]["kaggle_ref"] == 9001, env
    (call,) = fake.submitted()
    assert call[1] == "titanic" and call[2] == row["message"] and call[3] == row["file"]
    (row,) = subs.read(ready_ws)
    assert row["status"] == "SUBMITTED" and "confirm_token" not in row
    # single use: the same token cannot submit twice
    env = kx(ready_ws, fake, "submit", exp, "--confirm", token, "--force-cv")
    assert env["status"] == "invalid" and env["errors"] == ["no_proposal"]
    assert len(fake.submitted()) == 1


def test_confirm_refusals(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    exp, d = _recorded(ready_ws, fake)
    _, token = _propose(ready_ws, fake, exp)
    assert kx(ready_ws, fake, "submit", exp, "--confirm", "deadbeef")["errors"] == ["no_proposal"]
    sub = d / "output" / "submission.csv"
    original = sub.read_text()
    lines = original.splitlines()  # same shape, last value changed
    sub.write_text("\n".join(lines[:-1] + [lines[-1][:-1] + "9"]) + "\n")
    env = kx(ready_ws, fake, "submit", exp, "--confirm", token)
    assert env["errors"] == ["candidate_changed"], env
    sub.write_text(original)
    rows = subs.read(ready_ws)
    rows[0]["proposed_at"] = "2020-01-01T00:00:00Z"
    subs.write(ready_ws, rows)
    assert kx(ready_ws, fake, "submit", exp, "--confirm", token)["errors"] == ["proposal_expired"]
    assert not fake.submitted()


def test_confirm_reruns_the_checks(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    exp, _ = _recorded(ready_ws, fake)
    _, token = _propose(ready_ws, fake, exp)
    fake.submissions = lambda slug, page_size=50: [
        {"date": _now(), "status": "COMPLETE"} for _ in range(10)]
    env = kx(ready_ws, fake, "submit", exp, "--confirm", token)
    assert env["status"] == "invalid" and "no submission slots" in env["errors"][0]
    assert not fake.submitted()


def test_confirm_never_submits_twice_and_maps_errors(ready_ws, fake):
    from kx.util import KxError
    fake.submissions = lambda slug, page_size=50: []
    exp, _ = _recorded(ready_ws, fake)
    _, token = _propose(ready_ws, fake, exp)
    marker = subs.read(ready_ws)[0]["marker"]
    fake.submissions = lambda slug, page_size=50: [
        {"ref": 7, "date": _now(), "description": marker, "status": "PENDING"}]
    env = kx(ready_ws, fake, "submit", exp, "--confirm", token)
    assert env["status"] == "ok" and "already on Kaggle" in env["summary"]
    assert not fake.submitted()

    fake.submissions = lambda slug, page_size=50: []
    _, token = _propose(ready_ws, fake, exp, "--force-cv")
    fake.submit_response = KxError("error", "Kaggle call timed out (create_submission)",
                                   errors=["kaggle_timeout:create_submission"])
    env = kx(ready_ws, fake, "submit", exp, "--confirm", token, "--force-cv")
    assert env["status"] == "error" and env["next_action"]["command"] == "kx lb"
    assert subs.read(ready_ws)[-1]["status"] == "SUBMIT_ERROR"
    assert len(fake.submitted()) == 1


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


def _confirmed(ws, fake, exp, *extra):
    """Propose, confirm, and return the submitted row's marker."""
    _, token = _propose(ws, fake, exp, *extra)
    env = kx(ws, fake, "submit", exp, "--confirm", token, *extra)
    assert env["status"] == "ok", env
    return env["data"]["marker"]


def test_cv_gate_and_lb_read_back(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    exp, _ = _recorded(ready_ws, fake, scores=(0.8, 0.9))
    marker = _confirmed(ready_ws, fake, exp)
    assert kx(ready_ws, fake, "status")["data"]["submissions"]["awaiting_read_back"] == [exp]
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
    marker = _confirmed(ready_ws, fake, exp)
    fake.submissions = lambda slug, page_size=50: [
        {"ref": 1, "date": _now(), "description": marker, "status": "PENDING"}]
    env = kx(ready_ws, fake, "lb", "--wait", "0")
    assert env["status"] == "running" and env["next_action"]["command"] == "kx lb"


def test_message_flag_and_status_shows_an_unanswered_proposal(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    exp, d = _recorded(ready_ws, fake)
    (d / "VERDICT.md").write_text("verdict")
    (d / "reasoning.md").write_text("why")
    kx(ready_ws, fake, "strategy", "--reasoning-file", f"experiments/{exp}/reasoning.md")
    env, _ = _propose(ready_ws, fake, exp, "--message", "seed blend v2")
    assert env["data"]["marker"] + " seed blend v2" in env["data"]["confirmation"][-1]
    st = kx(ready_ws, fake, "status")
    assert st["data"]["submissions"]["proposed"] == [exp]
    assert st["next_action"]["command"] == f"kx submit {exp}"


def test_a_confirmed_submit_kaggle_never_lists_becomes_not_submitted(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    exp, _ = _recorded(ready_ws, fake)
    _, token = _propose(ready_ws, fake, exp)
    from kx.util import KxError
    fake.submit_response = KxError("error", "Kaggle call failed (create_submission: http_500)",
                                   errors=["http_500:create_submission"])
    assert kx(ready_ws, fake, "submit", exp, "--confirm", token)["status"] == "error"
    env = kx(ready_ws, fake, "lb", "--wait", "0")
    assert env["data"]["not_found_yet"] == [exp]
    rows = subs.read(ready_ws)
    rows[0]["confirmed_at"] = "2020-01-01T00:00:00Z"
    subs.write(ready_ws, rows)
    env = kx(ready_ws, fake, "lb", "--wait", "0")
    assert env["data"]["not_found_yet"] == [] and env["status"] == "ok"
    assert subs.read(ready_ws)[0]["status"] == "NOT_SUBMITTED"
    # it never landed, so it does not set the CV bar for the next candidate
    fake.submit_response = {"ref": 9002, "message": "ok"}
    _confirmed(ready_ws, fake, exp)


def test_a_crash_mid_submit_is_recovered_by_marker(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    exp, _ = _recorded(ready_ws, fake)
    _propose(ready_ws, fake, exp)
    rows = subs.read(ready_ws)
    rows[0].update({"status": "SUBMITTING", "confirmed_at": _now()})
    rows[0].pop("confirm_token")
    subs.write(ready_ws, rows)
    marker = rows[0]["marker"]
    fake.submissions = lambda slug, page_size=50: [
        {"ref": 3, "date": _now(), "description": marker, "status": "PENDING"}]
    assert kx(ready_ws, fake, "lb", "--wait", "0")["status"] == "running"
    assert subs.read(ready_ws)[0]["status"] == "PENDING"


def test_legacy_handed_over_rows_still_set_the_cv_bar(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    exp, _ = _recorded(ready_ws, fake)
    subs.write(ready_ws, [{"marker": "kx:exp-001:aaaaaa", "exp_id": exp, "mode": "csv_upload",
                           "status": "HANDED_OVER", "message": "kx:exp-001:aaaaaa x"}])
    env = kx(ready_ws, fake, "submit", exp)
    assert any("not better than the best submitted CV" in e for e in env["errors"])


def test_agent_upload_is_confirmed_by_file_hash(tmp_path, token_home):
    from conftest import FakeAdapter
    fake = FakeAdapter(comp_slug="connectx")
    ws = tmp_path / "ws"
    kx(ws, fake, "init", "connectx")
    kx(ws, fake, "sync")
    kx(ws, fake, "confirm", "--note", "t")
    fake.submissions = lambda slug, page_size=50: []
    exp = kx(ws, fake, "new", "--idea", "centre", "--hypothesis", "h")["data"]["exp_id"]
    d = ws / "experiments" / exp
    (d / "meta.json").write_text(json.dumps({
        "exp_id": exp, "status": "SUCCESS", "cv_mean": 0.9, "greater_is_better": True,
        "agent_eval": {"validation": {"ok": True}}}))
    env, token = _propose(ws, fake, exp)
    assert any(line.startswith("submits: agent ") and "main.py" in line
               for line in env["data"]["confirmation"])
    (d / "main.py").write_text((d / "main.py").read_text() + "\n# changed\n")
    assert kx(ws, fake, "submit", exp, "--confirm", token)["errors"] == ["candidate_changed"]
    env, token = _propose(ws, fake, exp)
    assert kx(ws, fake, "submit", exp, "--confirm", token)["status"] == "ok"
    (call,) = fake.submitted()
    assert call[3].endswith("main.py") and call[4] is None


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
    assert "manual_command" not in env["data"]
    assert any("version 1 (internet off), output submission.csv" in line
               for line in env["data"]["confirmation"])
    token = env["next_action"]["then"].split("--confirm ")[1]
    fake.kernel_meta["enable_internet"] = True  # the confirm re-checks the kernel
    assert any("internet ON" in e for e in kx(ws, fake, "submit", exp, "--confirm", token)["errors"])
    fake.kernel_meta["enable_internet"] = False
    assert kx(ws, fake, "submit", exp, "--confirm", token)["status"] == "ok"
    (call,) = fake.submitted()
    assert call[1] == "equity-post-HCT-survival-predictions" and call[4].startswith("tester/")
    assert call[5] == 1 and call[6] == "submission.csv"
    fake.kernel_meta["enable_internet"] = True
    assert any("internet ON" in e for e in kx(ws, fake, "submit", exp)["errors"])


def test_code_comp_inference_stage_refuses_internet_before_pushing(tmp_path, token_home):
    from conftest import FakeAdapter
    fake = FakeAdapter(comp_slug="equity-post-hct-survival-predictions")
    ws = tmp_path / "ws"
    kx(ws, fake, "init", "equity-post-hct-survival-predictions")
    kx(ws, fake, "sync")
    kx(ws, fake, "confirm", "--note", "t")
    kx(ws, fake, "metric", "roc_auc")
    up, _ = scaffold(ws, fake)
    up_spec = json.loads((ws / "experiments" / up / "experiment.json").read_text())
    up_spec["runtime"]["internet"] = True  # a training stage may download weights
    (ws / "experiments" / up / "experiment.json").write_text(json.dumps(up_spec))
    fake.outputs = make_outputs()
    res = json.loads(fake.outputs["result.json"])
    res["metric"] = "roc_auc"
    fake.outputs["result.json"] = json.dumps(res).encode()
    fake.statuses = ["COMPLETE"]
    fake.kernel_meta["enable_internet"] = True
    env = kx(ws, fake, "run", up, "--wait", "5")
    assert env["data"]["result"] == "SUCCESS" and any("internet is ON" in w
                                                      for w in env["warnings"])
    env = kx(ws, fake, "new", "--idea", "infer", "--hypothesis", "h", "--after", up)
    down = env["data"]["exp_id"]
    p = ws / "experiments" / down / "experiment.json"
    spec = json.loads(p.read_text())
    assert spec["template"] == "inference" and spec["runtime"]["internet"] is False
    spec["cv"]["reasoning"] = "inherited"
    spec["runtime"]["internet"] = True
    p.write_text(json.dumps(spec))
    pushes = len(fake.pushed())
    env = kx(ws, fake, "run", down, "--wait", "5")
    assert env["status"] == "invalid" and env["errors"] == ["internet_on_submitted_stage"]
    assert len(fake.pushed()) == pushes


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
        exp = kx(ws, fake, "new", "--idea", f"m{i}", "--hypothesis", "h", "--local",
                 "--expect", "better")["data"]["exp_id"]
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
