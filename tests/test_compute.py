"""RUN-02..07: resume, pipelines, env provenance, partial downloads, error mapping."""

import json

import pytest
from conftest import kx
from test_run_record import make_outputs, scaffold

from kx.adapter import KaggleAdapter, _is_network_error
from kx.util import KxError


def test_pipeline_waits_for_upstream_and_records_consumed_version(ready_ws, fake):
    up, up_dir = scaffold(ready_ws, fake, idea="upstream")
    env = kx(ready_ws, fake, "new", "--idea", "down", "--hypothesis", "h", "--after", up)
    down = env["data"]["exp_id"]
    spec = json.loads((ready_ws / "experiments" / down / "experiment.json").read_text())
    spec["cv"]["reasoning"] = "same"
    (ready_ws / "experiments" / down / "experiment.json").write_text(json.dumps(spec))
    env = kx(ready_ws, fake, "run", down)
    assert env["status"] == "invalid" and env["errors"] == ["upstream_not_ready"]
    assert env["next_action"]["command"] == f"kx run {up}"
    assert fake.pushed() == []

    fake.outputs = make_outputs()
    nonce = "abc123"
    fake.outputs["kx_manifest.json"] = json.dumps({"run_nonce": nonce, "created": "t1"}).encode()
    assert kx(ready_ws, fake, "run", up, "--wait", "5")["data"]["result"] == "SUCCESS"
    fake.statuses = ["COMPLETE"]
    fake.outputs["upstream_manifest.json"] = json.dumps({"run_nonce": nonce}).encode()
    env = kx(ready_ws, fake, "run", down, "--wait", "5")
    assert env["data"]["result"] == "SUCCESS"
    (_, meta, _), = [c for c in fake.pushed() if "exp-002" in c[1]["id"]]
    assert meta["kernel_sources"] == [f"tester/{fake.pushed()[0][1]['id'].split('/')[1]}"]
    m = json.loads((ready_ws / "experiments" / down / "meta.json").read_text())
    (u,) = m["kernel"]["upstream"]
    assert u["consumed"] == "v1" and u["consumed_version"] == 1


def test_consumed_mismatch_is_reported(ready_ws, fake):
    up, _ = scaffold(ready_ws, fake, idea="upstream")
    fake.outputs = make_outputs()
    fake.outputs["kx_manifest.json"] = json.dumps({"run_nonce": "n1"}).encode()
    kx(ready_ws, fake, "run", up, "--wait", "5")
    env = kx(ready_ws, fake, "new", "--idea", "down", "--hypothesis", "h", "--after", up)
    down = env["data"]["exp_id"]
    p = ready_ws / "experiments" / down / "experiment.json"
    spec = json.loads(p.read_text())
    spec["cv"]["reasoning"] = "same"
    p.write_text(json.dumps(spec))
    fake.statuses = ["COMPLETE"]
    fake.outputs["upstream_manifest.json"] = json.dumps({"run_nonce": "OTHER", "created": "x"}).encode()
    kx(ready_ws, fake, "run", down, "--wait", "5")
    m = json.loads((ready_ws / "experiments" / down / "meta.json").read_text())
    assert m["kernel"]["upstream"][0]["consumed"].startswith("a different upstream run")


def test_budget_stop_is_resumable_and_resume_mounts_itself(ready_ws, fake):
    exp, d = scaffold(ready_ws, fake)
    fake.outputs = {"result.json": json.dumps({"incomplete": True,
                                               "stopped_at": {"fold": 0, "epoch": 3}}).encode(),
                    "checkpoints/fold0/last.pt": b"x"}
    env = kx(ready_ws, fake, "run", exp, "--wait", "5")
    assert env["data"]["result"] == "FAILED" and env["data"]["failure_reason"] == "runtime_limit"
    assert env["data"]["resumable"] is True
    assert env["next_action"]["command"] == f"kx run {exp} --resume"
    m = json.loads((d / "meta.json").read_text())
    assert m["resumable"] is True and m["stopped_at"] == {"fold": 0, "epoch": 3}
    assert (d / "output/checkpoints/fold0/last.pt").exists()

    fake.outputs = make_outputs()
    fake.kernel_meta["current_version_number"] = 2
    fake.push_response = {"version_number": 2}
    env = kx(ready_ws, fake, "run", exp, "--resume", "--wait", "5")
    assert env["data"]["result"] == "SUCCESS"
    last_push = fake.pushed()[-1][1]
    assert last_push["kernel_sources"] == [last_push["id"]]
    assert json.loads((d / "meta.json").read_text())["kernel"]["resumed_from_version"] == 1


def test_resume_refuses_a_hard_stop(ready_ws, fake):
    exp, _ = scaffold(ready_ws, fake)
    fake.statuses = ["CANCEL_ACKNOWLEDGED"]
    kx(ready_ws, fake, "run", exp, "--wait", "5")
    env = kx(ready_ws, fake, "run", exp, "--resume")
    assert env["errors"] == ["not_resumable"]


def test_rules_not_accepted_is_needs_user(ready_ws, fake):
    exp, _ = scaffold(ready_ws, fake)
    fake.push_response = {"error": "You must accept this competition's rules before you'll be "
                                   "able to add it as a datasource: titanic"}
    env = kx(ready_ws, fake, "run", exp)
    assert env["status"] == "needs_user" and env["errors"] == ["rules_not_accepted"]
    assert "competitions/titanic/rules" in env["next_action"]["instruction"]


def test_env_compares_runs_with_local(ready_ws, fake):
    exp, _ = scaffold(ready_ws, fake)
    fake.outputs = make_outputs()
    kx(ready_ws, fake, "run", exp, "--wait", "5")
    env = kx(ready_ws, fake, "env")
    (row,) = env["data"]["runs"]
    assert row["docker_image"].startswith("gcr.io/kaggle-images/python@sha256")
    assert row["libraries"] == {"pandas": "2.3.3"}
    assert env["data"]["local"]["python"]
    assert any(t.startswith("GPU quota: 29.0 h left of 30 h") for t in env["data"]["table"])


def test_partial_file_download_is_bounded_and_listed(ready_ws, fake, tmp_path):
    env = kx(ready_ws, fake, "sync", "--files", "nope.csv")
    assert env["errors"] == ["unknown_file"]
    env = kx(ready_ws, fake, "sync", "--files", *[f"f{i}.csv" for i in range(11)])
    assert env["errors"] == ["too_many_files"]

    def download_file(slug, name, dest, timeout):
        dest.mkdir(parents=True, exist_ok=True)
        p = dest / name
        p.write_text("a,b\n1,2\n")
        return p

    fake.download_file = download_file
    env = kx(ready_ws, fake, "sync", "--files", "train.csv")
    assert env["status"] == "ok" and env["data"]["download"]["partial"] is True
    assert (ready_ws / "data/titanic/train.csv").exists()


def test_network_errors_are_not_credential_errors():
    import requests

    try:
        try:
            raise OSError("dns")
        except OSError as inner:
            raise requests.ConnectionError("down") from inner
    except requests.ConnectionError as exc:
        assert _is_network_error(exc)
    assert not _is_network_error(ValueError("bad token"))


def test_push_is_never_retried_but_reads_are(monkeypatch):
    a = KaggleAdapter()
    calls = {"n": 0}

    def once(op, fn, timeout):
        calls["n"] += 1
        raise KxError("error", "x", errors=[f"ConnectionError:{op}"])

    monkeypatch.setattr(a, "_call_once", once)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(KxError):
        a._call("get_kernel", lambda api: None)
    assert calls["n"] == 3
    calls["n"] = 0
    with pytest.raises(KxError):
        a._call("save_kernel", lambda api: None, retries=0)
    assert calls["n"] == 1


def test_new_attaches_models_and_datasets(ready_ws, fake):
    handle = "timm/tf-mobilenet-v3/pyTorch/tf-mobilenetv3-small-100/1"
    env = kx(ready_ws, fake, "new", "--idea", "i", "--hypothesis", "h", "--model", handle,
             "--dataset", "cdeotte/pip-install-lifelines")
    spec = json.loads((ready_ws / "experiments" / env["data"]["exp_id"] /
                       "experiment.json").read_text())
    assert spec["sources"]["models"] == [handle]
    assert spec["sources"]["datasets"] == ["cdeotte/pip-install-lifelines"]
    env = kx(ready_ws, fake, "new", "--idea", "j", "--hypothesis", "h", "--model", "timm/x")
    assert env["status"] == "invalid" and env["errors"] == ["bad_model_handle"]


def _dataset_fake(fake, versions):
    """dataset_state answers from `versions` (None = HTTP 404); pushes are recorded."""
    from kx.util import KxError

    def state(ref):
        v = versions[0]
        if v is None:
            raise KxError("invalid", "404", errors=["http_404:dataset_status"])
        return {"status": "ready", "current_version_number": v}

    def push(folder, *, new, notes):
        fake.calls.append(("dataset_push", folder, new))
        versions[0] = (versions[0] or 0) + 1
        return {"ref": "x", "status": "ok", "error": ""}

    fake.dataset_state, fake.dataset_push = state, push
    fake.public = False
    fake.my_datasets = lambda search: [] if versions[0] is None else [
        {"ref": f"{fake.username}/{search}", "is_private": not fake.public}]


def test_dataset_push_creates_a_private_dataset_and_refuses_credentials(ready_ws, fake, tmp_path):
    folder = tmp_path / "wheels"
    folder.mkdir()
    (folder / "rdkit-2026.1-cp312.whl").write_bytes(b"PK\x03\x04")
    _dataset_fake(fake, [None])
    env = kx(ready_ws, fake, "dataset", "push", str(folder), "--slug", "rdkit-wheels")
    assert env["status"] == "ok" and env["data"]["created"] and env["data"]["version"] == 1
    meta = json.loads((folder / "dataset-metadata.json").read_text())
    assert meta["id"] == f"{fake.username}/rdkit-wheels"
    assert env["next_action"]["command"].startswith(f"kx new --dataset {fake.username}/rdkit-wheels")
    env = kx(ready_ws, fake, "dataset", "push", str(folder), "--slug", "rdkit-wheels")
    assert env["data"]["version"] == 2 and not env["data"]["created"]
    fake.public = True  # never add a version (and these files) to a public dataset
    pushes = len([c for c in fake.calls if c[0] == "dataset_push"])
    env = kx(ready_ws, fake, "dataset", "push", str(folder), "--slug", "rdkit-wheels")
    assert env["errors"] == ["dataset_not_private"]
    assert len([c for c in fake.calls if c[0] == "dataset_push"]) == pushes
    (folder / "kaggle.json").write_text("{}")
    env = kx(ready_ws, fake, "dataset", "push", str(folder), "--slug", "rdkit-wheels")
    assert env["errors"] == ["credential_in_folder"]


def test_an_interrupted_dataset_push_is_read_back(ready_ws, fake, tmp_path):
    folder = tmp_path / "w"
    folder.mkdir()
    (folder / "a.bin").write_bytes(b"x")
    versions = [None]
    _dataset_fake(fake, versions)

    def interrupted(folder, *, new, notes):
        versions[0] = 1  # Kaggle got it; kx died mid-call
        raise KeyboardInterrupt

    fake.dataset_push = interrupted
    with pytest.raises(KeyboardInterrupt):
        kx(ready_ws, fake, "dataset", "push", str(folder), "--slug", "probe-set")
    _dataset_fake(fake, versions)
    env = kx(ready_ws, fake, "dataset", "push", str(folder), "--slug", "probe-set")
    assert "did not upload again" in env["summary"]
    assert not [c for c in fake.calls if c[0] == "dataset_push"]
