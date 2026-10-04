"""CORE-03 (experiment.json), RUN-01 (kernel run), CORE-04 (recorder/ledger/strategy),
TMPL-01 (template render), ENS-01 (kx-preds/1)."""

import ast
import json
import random
from pathlib import Path

import pytest
from conftest import FIXTURES, kx

from kx import kernel, preds, record
from kx.adapter import safe_join
from kx.experiment import PLACEHOLDER


def make_outputs(n_oof=6, n_test=3, n_folds=2, scores=(0.8, 0.9), mean=None, bad_preds=False):
    oof = "row_id,fold,target,pred\n" + "".join(
        f"{i},{i % n_folds},{i % 2},{0.1 * (i % 9)}\n" for i in range(n_oof))
    test = "row_id,pred\n" + "".join(f"{100 + i},0.5\n" for i in range(n_test))
    if bad_preds:
        test = "row_id,pred\n100,nan\n"
    result = {"exp_id": "exp-001", "metric": "accuracy", "n_folds": n_folds,
              "fold_scores": list(scores), "cv_mean": mean if mean is not None else
              sum(scores) / len(scores), "cv_std": 0.05, "seed": 42,
              "predictions": {"format": "kx-preds/1", "oof": "oof.csv", "test": "test_preds.csv",
                              "pred_columns": ["pred"], "classes": None, "n_oof": n_oof,
                              "n_test": n_test}}
    return {"result.json": json.dumps(result).encode(), "oof.csv": oof.encode(),
            "test_preds.csv": test.encode(), "submission.csv": b"id,y\n100,1\n",
            "kx_manifest.json": json.dumps({"python": "3.12.13",
                                            "libraries": {"pandas": "2.3.3"}}).encode()}


def scaffold(ws, fake, idea="baseline"):
    env = kx(ws, fake, "new", "--idea", idea, "--hypothesis", "h", "--expect", "better")
    assert env["status"] == "ok", env
    exp = env["data"]["exp_id"]
    d = ws / "experiments" / exp
    spec = json.loads((d / "experiment.json").read_text())
    spec["cv"]["reasoning"] = "iid rows, stratified"
    (d / "experiment.json").write_text(json.dumps(spec))
    return exp, d


# --------------------------------------------------------------------------- #
# new + template
# --------------------------------------------------------------------------- #
def test_new_requires_confirmed_profile(tmp_path, token_home, fake):
    ws = tmp_path / "ws"
    kx(ws, fake, "init", "titanic")
    kx(ws, fake, "sync")
    env = kx(ws, fake, "new", "--idea", "x", "--hypothesis", "y")
    assert env["status"] == "invalid" and env["errors"] == ["profile_unconfirmed"]


def test_new_scaffolds_a_safe_template(ready_ws, fake):
    env = kx(ready_ws, fake, "new", "--idea", 'quote " and """ and \\n', "--hypothesis", "h")
    assert env["status"] == "ok"
    d = ready_ws / "experiments" / "exp-001"
    code = (d / "train.py").read_text()
    ast.parse(code)
    assert "import kx" not in code and "from kx" not in code
    assert "# === AI BLOCK" in code and "# === KX HARNESS" in code
    assert "SAMPLE_SUBMISSION = 'gender_submission.csv'" in code
    assert "os.environ[" not in code  # never dumps env values (KAGGLE_USER_SECRETS_TOKEN)
    spec = json.loads((d / "experiment.json").read_text())
    assert spec["cv"]["reasoning"] == PLACEHOLDER
    assert spec["runtime"] == {"target": "kernel", "accelerator": "cpu", "limit_s": 1800,
                               "internet": False}
    assert spec["harness_sha256"]
    assert env["next_action"]["then"] == "kx run exp-001"


def test_template_override_needs_a_reason(ready_ws, fake):
    env = kx(ready_ws, fake, "new", "--idea", "x", "--hypothesis", "y", "--template", "nope")
    assert env["status"] == "invalid" and env["errors"] == ["template_reason_required"]


# --------------------------------------------------------------------------- #
# experiment.json validation: refused before any push
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mutate,needle", [
    (lambda s: s["cv"].update(reasoning=PLACEHOLDER), "placeholder"),
    (lambda s: s.update(acclerator="cpu"), "unknown key: acclerator"),
    (lambda s: s["runtime"].update(accelerator="NvidiaTeslaP100"), "runtime.accelerator"),
    (lambda s: s["runtime"].update(limit_s=10), "runtime.limit_s"),
    (lambda s: s["runtime"].update(target="cloud"), "runtime.target"),
    (lambda s: s["sources"].update(competition="spaceship-titanic"), "sources.competition"),
    (lambda s: s["sources"].update(datasets=["not a ref"]), "sources.datasets"),
    (lambda s: s["cv"].update(n_folds=1), "cv.n_folds"),
    (lambda s: s.update(idea=""), "idea"),
    (lambda s: s.update(exp_id="exp-999"), "does not match"),
])
def test_invalid_spec_is_refused_before_push(ready_ws, fake, mutate, needle):
    exp, d = scaffold(ready_ws, fake)
    spec = json.loads((d / "experiment.json").read_text())
    mutate(spec)
    (d / "experiment.json").write_text(json.dumps(spec))
    env = kx(ready_ws, fake, "run", exp)
    assert env["status"] == "invalid"
    assert any(needle in e for e in env["errors"]), env["errors"]
    assert fake.pushed() == []


def test_modified_harness_or_syntax_error_is_refused(ready_ws, fake):
    exp, d = scaffold(ready_ws, fake)
    code = (d / "train.py").read_text()
    (d / "train.py").write_text(code.replace("fold_scores.append(", "fold_scores.append(1 or "))
    env = kx(ready_ws, fake, "run", exp)
    assert env["status"] == "invalid" and any("HARNESS" in e for e in env["errors"])
    (d / "train.py").write_text(code + "\ndef broken(:\n")
    env = kx(ready_ws, fake, "run", exp)
    assert any("syntax error" in e for e in env["errors"])
    assert fake.pushed() == []


# --------------------------------------------------------------------------- #
# run: push -> poll -> pull -> record
# --------------------------------------------------------------------------- #
def test_happy_path_records_success(ready_ws, fake):
    exp, d = scaffold(ready_ws, fake)
    fake.outputs = make_outputs()
    env = kx(ready_ws, fake, "run", exp, "--wait", "5")
    assert env["status"] == "ok", env
    assert env["data"]["result"] == "SUCCESS"
    assert env["data"]["cv_mean"] == pytest.approx(0.85)
    (_, meta, timeout), = fake.pushed()
    assert meta["kernel_type"] == "script" and meta["is_private"] is True
    assert meta["enable_internet"] is False and meta["competition_sources"] == ["titanic"]
    assert len(meta["title"]) <= 50 and timeout == 1800
    m = json.loads((d / "meta.json").read_text())
    assert m["status"] == "SUCCESS" and m["cv_reasoning"] == "iid rows, stratified"
    assert m["environment"]["docker_image"].startswith("gcr.io/kaggle-images/python@sha256")
    assert m["environment"]["libraries"] == {"pandas": "2.3.3"}
    assert m["provenance"]["git_commit"] != "uncommitted"
    ledger = (ready_ws / "control/ledger.jsonl").read_text().splitlines()
    assert len(ledger) == 1 and json.loads(ledger[0])["exp_id"] == exp
    assert (d / "output" / "oof.csv").exists() and (d / "VERDICT.md").exists()
    assert env["next_action"]["then"].startswith("kx strategy")
    again = kx(ready_ws, fake, "run", exp)
    assert "already recorded" in again["summary"] and len(fake.pushed()) == 1


def test_budget_expiry_returns_running_and_resume_never_repushes(ready_ws, fake):
    exp, d = scaffold(ready_ws, fake)
    fake.statuses = ["RUNNING"]
    env = kx(ready_ws, fake, "run", exp, "--wait", "0")
    assert env["status"] == "running"
    assert env["next_action"]["command"] == f"kx run {exp}"
    assert json.loads((d / "kernel_run.json").read_text())["recorded"] is False
    fake.statuses = ["COMPLETE"]
    fake.outputs = make_outputs()
    env = kx(ready_ws, fake, "run", exp, "--wait", "0")
    assert env["data"]["result"] == "SUCCESS"
    assert len(fake.pushed()) == 1
    assert kx(ready_ws, fake, "status")["next_action"]["kind"] == "edit"


@pytest.mark.parametrize("setup,reason", [
    (lambda f: f.statuses.__setitem__(slice(None), ["ERROR"]), "kernel_error"),
    (lambda f: f.statuses.__setitem__(slice(None), ["CANCEL_ACKNOWLEDGED"]), "runtime_limit"),
    (lambda f: (setattr(f, "log", (FIXTURES / "kernel_logs/titanic_error.json").read_text()),
                f.outputs.pop("result.json")), "kernel_error"),
    (lambda f: setattr(f, "log", None), "kernel_error"),
    (lambda f: f.outputs.pop("result.json"), "missing_result"),
    (lambda f: f.outputs.update(make_outputs(mean=0.99)), "schema_invalid"),
    (lambda f: f.outputs.update(make_outputs(scores=(0.8, float("nan")))), "non_finite"),
    (lambda f: f.outputs.update(make_outputs(scores=(1.5, 1.7))), "out_of_range"),
    (lambda f: f.outputs.update(make_outputs(bad_preds=True)), "predictions_invalid"),
])
def test_fail_closed_ladder(ready_ws, fake, setup, reason):
    exp, d = scaffold(ready_ws, fake)
    fake.outputs = make_outputs()
    setup(fake)
    env = kx(ready_ws, fake, "run", exp, "--wait", "5")
    assert env["status"] == "ok"
    assert env["data"]["result"] == "FAILED"
    assert env["data"]["failure_reason"] == reason
    m = json.loads((d / "meta.json").read_text())
    assert m["cv_mean"] is None and m["idea"] == "baseline"
    row = json.loads((ready_ws / "control/ledger.jsonl").read_text().splitlines()[0])
    assert row["status"] == "FAILED" and row["cv_mean"] is None


def test_failed_run_keeps_traceback_and_partials(ready_ws, fake):
    exp, d = scaffold(ready_ws, fake)
    fake.statuses = ["ERROR"]
    fake.outputs = {"partial.txt": b"half"}
    fake.log = (FIXTURES / "kernel_logs/titanic_error.json").read_text()
    env = kx(ready_ws, fake, "run", exp, "--wait", "5")
    det = env["data"]["failure_detail"]
    assert det["error_line"] == "RuntimeError: deliberate failure: fail-closed live check"
    assert "partial.txt" in det["partial_outputs"]
    assert (d / "output" / "traceback.txt").read_text().startswith("Traceback")


def test_push_errors_fail_closed_and_quarantine(ready_ws, fake):
    exp, _ = scaffold(ready_ws, fake)
    fake.push_response = {"error": "server said https://signed.example/secret", "version_number": None}
    env = kx(ready_ws, fake, "run", exp)
    assert env["status"] == "error" and env["errors"] == ["push_error"]
    assert "signed.example" not in json.dumps(env)
    assert "signed.example" in (ready_ws / "control/raw/last-error.txt").read_text()
    fake.push_response = {"version_number": 2, "invalid_competition_sources": ["titanic"]}
    assert kx(ready_ws, fake, "run", exp)["errors"] == ["invalid_sources"]


def test_server_flag_mismatch_and_version_readback(ready_ws, fake):
    exp, _ = scaffold(ready_ws, fake)
    fake.kernel_meta["enable_internet"] = True
    assert kx(ready_ws, fake, "run", exp)["errors"] == ["server_flags_mismatch"]
    fake.kernel_meta["enable_internet"] = False
    fake.push_response = {"version_number": None}
    fake.kernel_meta["current_version_number"] = 7
    fake.outputs = make_outputs()
    env = kx(ready_ws, fake, "run", exp, "--rerun", "--wait", "5")
    assert env["data"]["kernel_version"] == 7


def test_newer_kernel_version_is_never_recorded(ready_ws, fake):
    exp, d = scaffold(ready_ws, fake)
    fake.statuses = ["RUNNING"]
    kx(ready_ws, fake, "run", exp, "--wait", "0")
    fake.statuses = ["COMPLETE"]
    fake.kernel_meta["current_version_number"] = 2
    env = kx(ready_ws, fake, "run", exp, "--wait", "0")
    assert env["errors"] == ["version_mismatch"]
    assert not (d / "meta.json").exists()


# --------------------------------------------------------------------------- #
# strategy
# --------------------------------------------------------------------------- #
def test_strategy_requires_verdict_and_renders_digest(ready_ws, fake):
    exp, d = scaffold(ready_ws, fake)
    fake.outputs = make_outputs()
    kx(ready_ws, fake, "run", exp, "--wait", "5")
    (ready_ws / "r.md").write_text("### Queue\n1. next\n")
    env = kx(ready_ws, fake, "strategy", "--reasoning-file", "r.md")
    assert env["status"] == "invalid" and env["errors"] == ["verdict_pending"]
    (d / "VERDICT.md").write_text("# Verdict\nworked\n")
    env = kx(ready_ws, fake, "strategy", "--reasoning-file", "r.md")
    assert env["status"] == "ok" and env["data"]["commit"]
    text = (ready_ws / "strategy.md").read_text()
    assert "**exp-001**" in text and "- exp-001 | baseline | SUCCESS" in text
    assert "1. next" in text
    exp2, d2 = scaffold(ready_ws, fake, idea="second")
    fake.statuses = ["ERROR"]
    kx(ready_ws, fake, "run", exp2, "--wait", "5")
    (d2 / "VERDICT.md").write_text("# Verdict\nfailed\n")
    kx(ready_ws, fake, "strategy", "--reasoning-file", "r.md")
    text = (ready_ws / "strategy.md").read_text()
    assert "- exp-002 (from exp-001) | second | FAILED | — | vs parent: not comparable" in text
    new = kx(ready_ws, fake, "new", "--idea", "third", "--hypothesis", "h", "--expect", "better")
    assert len(new["data"]["tried"]) == 2


# --------------------------------------------------------------------------- #
# units
# --------------------------------------------------------------------------- #
def test_safe_join_refuses_escapes(tmp_path):
    for bad in ("../x", "/etc/passwd", "a/../../x", "a\\b", "", "x\x00y"):
        with pytest.raises(ValueError):
            safe_join(tmp_path, bad)
    assert safe_join(tmp_path, "sub/ok.csv") == (tmp_path / "sub/ok.csv").resolve()


def test_poll_never_overruns_its_budget():
    clock = {"t": 0.0}
    slept = []

    def sleep(s):
        slept.append(s)
        clock["t"] += s

    out = kernel.poll(lambda: ("RUNNING", None), budget_s=25, now=lambda: clock["t"],
                      sleep=sleep, rng=random.Random(0))
    assert out["outcome"] == "budget" and clock["t"] <= 25.0001
    out = kernel.poll(lambda: ("CANCEL_REQUESTED", None), budget_s=0, now=lambda: 0, sleep=sleep)
    assert out["outcome"] == "budget"  # CANCEL_REQUESTED is still in flight
    calls = iter([None, None, ("COMPLETE", None)])

    def flaky():
        v = next(calls)
        if v is None:
            from kx.util import KxError
            raise KxError("error", "blip")
        return v

    out = kernel.poll(flaky, budget_s=100, now=lambda: 0, sleep=lambda s: None)
    assert out == {"outcome": "terminal", "status": "COMPLETE", "failure_message": None}


def test_kernel_slug_is_bounded():
    s = kernel.kernel_slug("equity-post-hct-survival-predictions", "a1b2", "exp-123")
    assert len(s) <= 50 and s.endswith("-a1b2-exp-123") and s == s.lower()


def test_benign_kaggle_warnings_are_not_failures():
    assert not record.scan_log((FIXTURES / "kernel_logs/titanic_ok.json").read_text())
    assert record.scan_log((FIXTURES / "kernel_logs/titanic_error.json").read_text())
    assert not record.scan_log((FIXTURES / "kernel_logs/benign_warnings.json").read_text())


def _write(tmp_path: Path, files: dict):
    for k, v in files.items():
        (tmp_path / k).write_bytes(v)


@pytest.mark.parametrize("edit,needle", [
    (lambda f: f.update({"oof.csv": b"row_id,fold,pred\n1,0,0.1\n"}), "header"),
    (lambda f: f.update({"oof.csv": b"row_id,fold,target,pred\n1,0,1,0.1\n1,1,0,0.2\n"}),
     "duplicate"),
    (lambda f: f.update({"oof.csv": b"row_id,fold,target,pred\n1,0,1,0.1\n2,5,0,0.2\n"}),
     "fold 5"),
    (lambda f: f.update({"oof.csv": b"row_id,fold,target,pred\n1,0,1,inf\n2,1,0,0.2\n"}),
     "non-finite"),
    (lambda f: f.pop("test_preds.csv"), "missing"),
])
def test_preds_validator(tmp_path, edit, needle):
    files = make_outputs(n_oof=2, n_test=3)
    edit(files)
    _write(tmp_path, files)
    block = json.loads(files["result.json"])["predictions"]
    errs = preds.validate(tmp_path, block, 2)
    assert any(needle in e for e in errs), errs


def test_preds_validator_accepts_walk_forward_and_multiclass(tmp_path):
    (tmp_path / "oof.csv").write_text("row_id,fold,target,pred_0,pred_1,pred_2\n"
                                      "a,-1,x,,,\nb,0,y,0.2,0.3,0.5\nc,1,z,0.1,0.1,0.8\n")
    (tmp_path / "test_preds.csv").write_text("row_id,pred_0,pred_1,pred_2\nt,0.3,0.3,0.4\n")
    block = {"format": "kx-preds/1", "oof": "oof.csv", "test": "test_preds.csv",
             "pred_columns": ["pred_0", "pred_1", "pred_2"], "classes": ["x", "y", "z"],
             "n_oof": 3, "n_test": 1}
    assert preds.validate(tmp_path, block, 2) == []
    block["oof"] = "../oof.csv"
    assert preds.validate(tmp_path, block, 2)


def test_handled_traceback_in_a_complete_run_is_a_warning_and_re_record_needs_no_push(ready_ws,
                                                                                      fake):
    exp, d = scaffold(ready_ws, fake)
    fake.outputs = make_outputs()
    fake.log = (FIXTURES / "kernel_logs/titanic_error.json").read_text()
    env = kx(ready_ws, fake, "run", exp, "--wait", "5")
    assert env["data"]["result"] == "SUCCESS" and env["data"]["cv_mean"] == pytest.approx(0.85)
    assert any("handled" in w and "traceback.txt" in w for w in env["warnings"])
    assert json.loads((d / "meta.json").read_text())["log_markers"] is True
    assert (d / "output" / "traceback.txt").exists()
    # a run recorded under older rules is classified again from its pulled output
    meta = json.loads((d / "meta.json").read_text())
    meta.update({"status": "FAILED", "failure_reason": "kernel_error", "cv_mean": None})
    (d / "meta.json").write_text(json.dumps(meta))
    calls = len(fake.calls)
    env = kx(ready_ws, fake, "run", exp, "--re-record")
    assert env["data"]["result"] == "SUCCESS" and env["data"]["re_recorded"] is True
    assert len(fake.calls) == calls  # no Kaggle call at all
    assert kx(ready_ws, fake, "run", "exp-999", "--re-record")["status"] == "invalid"


def test_interrupted_push_is_read_back_never_pushed_twice(ready_ws, fake):
    exp, d = scaffold(ready_ws, fake)

    def interrupted(meta, code_text, timeout_s=None):  # Kaggle got it; kx died mid-call
        fake.calls.append(("push", meta, timeout_s))
        raise KeyboardInterrupt

    fake.push = interrupted
    with pytest.raises(KeyboardInterrupt):
        kx(ready_ws, fake, "run", exp, "--wait", "0")
    intent = json.loads((d / "kernel_run.json").read_text())
    assert intent["status"] == "PUSHING" and intent["prev_version"] is None
    assert "resume" in kx(ready_ws, fake, "status")["summary"]
    del fake.push
    fake.kernel_meta["current_version_number"] = 1  # the push landed as v1
    fake.outputs = make_outputs()
    env = kx(ready_ws, fake, "run", exp, "--wait", "5")
    assert env["data"]["result"] == "SUCCESS" and env["data"]["kernel_version"] == 1
    assert len(fake.pushed()) == 1
    assert any("did not push again" in w for w in env["warnings"])


def test_interrupted_push_that_never_landed_is_pushed_once(ready_ws, fake):
    exp, d = scaffold(ready_ws, fake)
    from kx import kernel as K

    K.save_run(d, {"backend": "kernel", "kernel_ref": "kxuser/never-landed", "status": "PUSHING",
                   "prev_version": None, "recorded": False})
    from kx.util import KxError

    def missing(owner, slug):
        fake.calls.append(("get_kernel", owner, slug))
        if not fake.pushed():  # Kaggle answers 403 for a kernel that does not exist
            raise KxError("needs_user", "403", errors=["http_403:get_kernel"])
        return dict(fake.kernel_meta)

    fake.get_kernel = missing
    fake.outputs = make_outputs()
    env = kx(ready_ws, fake, "run", exp, "--wait", "5")
    assert env["data"]["result"] == "SUCCESS" and len(fake.pushed()) == 1


def test_gpu_push_shows_the_quota_and_warns_before_kaggle_refuses(ready_ws, fake):
    exp, d = scaffold(ready_ws, fake)
    spec = json.loads((d / "experiment.json").read_text())
    spec["runtime"].update({"accelerator": "NvidiaTeslaT4", "limit_s": 7200})
    (d / "experiment.json").write_text(json.dumps(spec))
    fake.quota = {"refresh": "2026-10-10T00:00:00",
                  "gpu": {"used_s": 100000.0, "reserved_s": 3600.0, "allowed_s": 108000.0}}
    for other in ("exp-090", "exp-091"):  # two GPU kernels still running in this workspace
        od = ready_ws / "experiments" / other
        od.mkdir()
        (od / "kernel_run.json").write_text(json.dumps(
            {"accelerator": "NvidiaTeslaT4", "status": "RUNNING", "recorded": False}))
    fake.statuses = ["RUNNING"]
    env = kx(ready_ws, fake, "run", exp, "--wait", "0")
    assert env["data"]["gpu_quota"]["gpu_hours_left"] == 1.2
    assert env["data"]["gpu_quota"]["running_gpu_kernels"] == ["exp-090", "exp-091"]
    assert any("GPU quota: 1.2 h left" in w for w in env["warnings"])
    assert any("at most 2 GPU sessions" in w for w in env["warnings"])


def test_the_gpu_session_cap_is_a_clear_refusal_and_leaves_no_push_record(ready_ws, fake):
    exp, d = scaffold(ready_ws, fake)
    fake.push_response = {"error": "Maximum batch GPU session count of 2 reached.",
                          "version_number": None}
    env = kx(ready_ws, fake, "run", exp)
    assert env["status"] == "needs_user" and env["errors"] == ["gpu_session_limit"]
    assert not (d / "kernel_run.json").exists()


IMG = "gcr.io/kaggle-images/python@sha256:" + "d" * 64


def test_a_pinned_docker_image_is_pushed_inherited_and_verified(ready_ws, fake):
    env = kx(ready_ws, fake, "new", "--idea", "x", "--hypothesis", "h", "--docker-image",
             "docker.io/evil/image:latest")
    assert env["errors"] == ["bad_docker_image"]
    fake.get_kernel = lambda owner, slug: {"docker_image": IMG}  # a public notebook's image
    env = kx(ready_ws, fake, "new", "--idea", "x", "--hypothesis", "h",
             "--image-from", "someone/top-notebook")
    assert env["data"]["docker_image"] == IMG
    del fake.get_kernel
    exp, d = env["data"]["exp_id"], ready_ws / "experiments" / env["data"]["exp_id"]
    spec = json.loads((d / "experiment.json").read_text())
    assert spec["runtime"]["docker_image"] == IMG
    spec["cv"]["reasoning"] = "iid"
    (d / "experiment.json").write_text(json.dumps(spec))
    fake.kernel_meta["docker_image"] = "gcr.io/kaggle-images/python@sha256:" + "0" * 64
    assert kx(ready_ws, fake, "run", exp)["errors"] == ["server_flags_mismatch"]  # not pinned
    fake.kernel_meta["docker_image"] = IMG
    fake.outputs = make_outputs()
    env = kx(ready_ws, fake, "run", exp, "--wait", "5")
    assert env["data"]["result"] == "SUCCESS" and fake.pushed()[-1][1]["docker_image"] == IMG
    child = kx(ready_ws, fake, "new", "--idea", "y", "--hypothesis", "h", "--expect", "better")
    assert child["data"]["docker_image"] == IMG  # a child keeps its parent's environment


def test_a_cpu_image_is_refused_on_a_gpu(ready_ws, fake):
    env = kx(ready_ws, fake, "new", "--idea", "x", "--hypothesis", "h", "--docker-image", IMG,
             "--accelerator", "NvidiaTeslaT4")
    assert any("no NVIDIA driver" in w for w in env["warnings"])
    d = ready_ws / "experiments" / env["data"]["exp_id"]
    spec = json.loads((d / "experiment.json").read_text())
    spec["cv"]["reasoning"] = "iid"
    (d / "experiment.json").write_text(json.dumps(spec))
    env = kx(ready_ws, fake, "run", env["data"]["exp_id"])
    assert env["status"] == "invalid" and any("no NVIDIA driver" in e for e in env["errors"])
    assert not fake.pushed()


def test_strategy_defaults_to_the_newest_reasoning_file(ready_ws, fake):
    exp, d = scaffold(ready_ws, fake)
    fake.outputs = make_outputs()
    kx(ready_ws, fake, "run", exp, "--wait", "5")
    assert kx(ready_ws, fake, "strategy")["errors"] == ["reasoning_missing"]
    v = d / "VERDICT.md"
    v.write_text(v.read_text().replace("_TODO", "done"))
    (d / "reasoning.md").write_text("next: more features\n")
    env = kx(ready_ws, fake, "strategy")
    assert env["status"] == "ok", env
