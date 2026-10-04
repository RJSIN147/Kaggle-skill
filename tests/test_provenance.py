"""Ported third-party code: marked at kx new, confirmed by the user before the first push."""

import json

from conftest import kx
from test_run_record import make_outputs
from test_submit_ensemble import _propose

from kx import provenance
from kx.util import KxError

URL = "https://www.kaggle.com/code/someuser/top-engine-v29"


def _new(ws, fake, idea, *extra):
    env = kx(ws, fake, "new", "--idea", idea, "--hypothesis", "h", *extra)
    assert env["status"] == "ok", env
    d = ws / "experiments" / env["data"]["exp_id"]
    spec = json.loads((d / "experiment.json").read_text())
    spec["cv"]["reasoning"] = "iid"
    (d / "experiment.json").write_text(json.dumps(spec))
    return env, d


def test_a_cited_notebook_needs_the_users_yes_before_the_first_push(ready_ws, fake):
    env, d = _new(ready_ws, fake, f"port of {URL}")
    exp = d.name
    assert env["data"]["third_party"]["sources"] == ["someuser/top-engine-v29"]
    assert any("ported" in w for w in env["warnings"])
    env = kx(ready_ws, fake, "run", exp)
    assert env["status"] == "needs_user" and env["errors"] == ["third_party_unconfirmed"]
    assert env["next_action"]["kind"] == "ask_user" and "--third-party-ok" in \
        env["next_action"]["then"]
    assert not fake.pushed()
    assert kx(ready_ws, fake, "run", exp, "--third-party-ok", " ")["errors"] == ["note_required"]
    fake.outputs = make_outputs()
    env = kx(ready_ws, fake, "run", exp, "--third-party-ok", "yes, Apache-2.0, credit in writeup",
             "--wait", "5")
    assert env["data"]["result"] == "SUCCESS" and len(fake.pushed()) == 1
    conf = json.loads((d / "experiment.json").read_text())["third_party"]["confirmed"]
    assert conf["note"] == "yes, Apache-2.0, credit in writeup"
    assert any("[ported]" in t for t in kx(ready_ws, fake, "status")["data"]["tried"])
    # a child of confirmed code is not asked again ...
    env, dc = _new(ready_ws, fake, "tune the ported engine", "--expect", "better")
    assert env["data"]["third_party"]["confirmed"] and not any("ported" in w
                                                               for w in env["warnings"])
    # ... unless its code cites another notebook
    code = dc / "train.py"
    code.write_text(code.read_text().replace(
        "def make_model(seed: int):",
        "# adapted from https://www.kaggle.com/code/other/blend-trick\ndef make_model(seed: int):"))
    env = kx(ready_ws, fake, "run", dc.name)
    assert env["errors"] == ["third_party_unconfirmed"]
    assert env["data"]["third_party"]["sources"] == ["someuser/top-engine-v29", "other/blend-trick"]


def test_bare_handles_count_only_when_kaggle_says_public_notebook(ready_ws, fake):
    def get_kernel(owner, slug):
        if (owner, slug) == ("someuser", "top-engine"):
            return {"is_private": False}
        raise KxError("needs_user", "403", errors=["http_403:get_kernel"])

    fake.get_kernel = get_kernel
    found = provenance.cited_notebooks(
        ["port someuser/top-engine; train/test split; uses owner/some-dataset; "
         f"{fake.username}/my-own-notebook"], fake, fake.username)
    assert found == ["someuser/top-engine"]


def test_submit_shows_the_ported_code_line(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    env, d = _new(ready_ws, fake, f"port of {URL}")
    fake.outputs = make_outputs()
    res = json.loads(fake.outputs["result.json"])
    res.update({"sample_columns": ["id", "y"], "sample_rows": 1, "submission_file": "submission.csv"})
    fake.outputs["result.json"] = json.dumps(res).encode()
    kx(ready_ws, fake, "run", d.name, "--third-party-ok", "checked", "--wait", "5")
    env, _ = _propose(ready_ws, fake, d.name)
    assert any(line.startswith("contains code ported from someuser/top-engine-v29 (the user "
                               "confirmed") for line in env["data"]["confirmation"])


def test_a_blend_is_confirmed_only_if_every_ported_member_was():
    ok = provenance.confirm({"sources": ["a/x"], "confirmed": None}, "fine")
    raw = {"sources": ["b/y"], "confirmed": None}
    assert provenance.combine([ok, None])["confirmed"]["sources"] == ["a/x"]
    assert provenance.combine([ok, raw])["confirmed"] is None
    assert provenance.combine([None, None]) is None
