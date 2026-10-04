"""Validation status (warn-only), CV-scheme checks and scheme-aware comparisons."""

import json

from conftest import kx
from test_compare import _record
from test_submit_ensemble import _confirmed, _now, _propose, _recorded

from kx import strategy, validation
from kx.ledger import read_ledger


def test_suspect_validation_warns_but_never_refuses(ready_ws, fake):
    assert validation.get(ready_ws)["status"] == "unchecked"
    assert validation.open_suspect(ready_ws, "test", ["train and test differ"], "sig-1")
    env = kx(ready_ws, fake, "new", "--idea", "x", "--hypothesis", "h")
    assert env["status"] == "ok"
    assert any("SUSPECT" in w and "train and test differ" in w for w in env["warnings"])
    status = kx(ready_ws, fake, "status")
    assert status["next_action"]["kind"] == "edit"  # finish the scaffolded experiment first
    env = kx(ready_ws, fake, "validation")
    assert env["data"]["validation"]["status"] == "suspect"
    assert env["next_action"]["command"] == "kx diagnose"


def test_validation_ok_needs_a_note_and_acknowledges_the_event(ready_ws, fake):
    validation.open_suspect(ready_ws, "test", ["r"], "sig-1")
    assert kx(ready_ws, fake, "validation", "ok")["errors"] == ["note_required"]
    env = kx(ready_ws, fake, "validation", "ok", "--note", "the shift is in an unused column")
    assert env["status"] == "ok" and env["data"]["validation"]["status"] == "ok"
    assert not validation.open_suspect(ready_ws, "test", ["r"], "sig-1")  # acknowledged
    assert validation.open_suspect(ready_ws, "test", ["new"], "sig-2")
    assert "the shift is in an unused column" in validation.body(ready_ws)


def test_lb_rank_inversion_makes_validation_suspect_once(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    a, _ = _recorded(ready_ws, fake, idea="a", scores=(0.80, 0.82))
    ma = _confirmed(ready_ws, fake, a)
    b, _ = _recorded(ready_ws, fake, idea="b", scores=(0.84, 0.86))
    mb = _confirmed(ready_ws, fake, b)

    def lb(score_a, score_b):
        fake.submissions = lambda slug, page_size=50: [
            {"ref": 1, "date": _now(), "description": f"{ma} a", "status": "COMPLETE",
             "public_score": score_a, "private_score": "", "team_name": "t"},
            {"ref": 2, "date": _now(), "description": f"{mb} b", "status": "COMPLETE",
             "public_score": score_b, "private_score": "", "team_name": "t"}]
        return kx(ready_ws, fake, "lb", "--wait", "0")

    env = lb("0.80", "0.75")  # b has the better CV, a the better LB
    assert env["data"]["validation"] == "suspect" and "suspect" in env["summary"]
    assert env["next_action"]["command"] == "kx diagnose"
    kx(ready_ws, fake, "validation", "ok", "--note", "public LB is 300 rows: noise")
    env = lb("0.80", "0.75")
    assert env["data"]["validation"] == "ok" and not env["warnings"]


def test_cv_check_copies_the_parent_model_and_is_not_compared(ready_ws, fake):
    exp1, d1, _ = _record(ready_ws, fake, "base", (0.80, 0.81))
    code1 = (d1 / "train.py").read_text().replace(
        "def make_model(seed: int):", "# parent model marker\ndef make_model(seed: int):")
    (d1 / "train.py").write_text(code1)
    env = kx(ready_ws, fake, "new", "--cv-check", "--idea", "group folds", "--hypothesis", "h")
    assert env["status"] == "ok", env
    exp2 = env["data"]["exp_id"]
    d2 = ready_ws / "experiments" / exp2
    spec = json.loads((d2 / "experiment.json").read_text())
    assert spec["kind"] == "cv_check" and spec["parent"] == exp1
    assert spec["expected_effect"] is None and spec["template"] == "tabular"
    assert "# parent model marker" in (d2 / "train.py").read_text()
    assert "assign_folds" in env["next_action"]["instruction"]
    assert kx(ready_ws, fake, "new", "--cv-check", "--idea", "x", "--hypothesis", "h",
              "--template", "deep", "--template-reason", "r")["errors"] == ["bad_cv_check"]
    # the documented way to resolve a small effect: the parent's model on more folds
    env = kx(ready_ws, fake, "new", "--cv-check", "--parent", exp1, "--folds", "10",
             "--idea", "more folds", "--hypothesis", "h")
    d3 = ready_ws / "experiments" / env["data"]["exp_id"]
    assert json.loads((d3 / "experiment.json").read_text())["cv"]["n_folds"] == 10
    assert "# parent model marker" in (d3 / "train.py").read_text()


def test_reference_scheme_ranks_best_within_it(ready_ws, fake):
    exp1, _, _ = _record(ready_ws, fake, "random folds", (0.90, 0.91))
    exp2, _, env = _record(ready_ws, fake, "group folds", (0.80, 0.81), folds_shift=1)
    assert env["data"]["vs_parent"]["reason"] == "CV scheme changed: the folds differ"
    rows = read_ledger(ready_ws)
    assert strategy.best_row(rows, True)["exp_id"] == exp1
    assert kx(ready_ws, fake, "validation", "ok", "--note", "n", "--scheme",
              "exp-999")["status"] == "invalid"
    env = kx(ready_ws, fake, "validation", "ok", "--note", "group folds mirror test",
             "--scheme", exp2)
    assert env["data"]["validation"]["reference"]["exp_id"] == exp2
    ref = validation.reference_hash(ready_ws)
    assert strategy.best_row(rows, True, ref)["exp_id"] == exp2
    env = kx(ready_ws, fake, "new", "--idea", "next", "--hypothesis", "h", "--expect", "better")
    assert env["data"]["parent"] == exp2
    assert any("other CV scheme" in t for t in env["data"]["tried"])


def test_submit_cv_bar_only_compares_the_same_scheme(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    a, _ = _recorded(ready_ws, fake, idea="random folds", scores=(0.90, 0.91))
    _confirmed(ready_ws, fake, a)
    b, d = _recorded(ready_ws, fake, idea="group folds", scores=(0.80, 0.81))
    meta = json.loads((d / "meta.json").read_text())
    meta["fold_hash"] = "sha256:other"
    (d / "meta.json").write_text(json.dumps(meta))
    from kx.ledger import rebuild_ledger_file
    rebuild_ledger_file(ready_ws)
    env, _ = _propose(ready_ws, fake, b)
    assert any("CV bar skipped" in line for line in env["data"]["confirmation"])
    validation.open_suspect(ready_ws, "test", ["drift"], "sig")
    env, _ = _propose(ready_ws, fake, b)
    assert any(line.startswith("WARNING: validation is SUSPECT")
               for line in env["data"]["confirmation"])


def _without_folds(d):
    """Make a recorded run look like one with no fold assignment (no oof.csv)."""
    from kx.ledger import rebuild_ledger_file

    meta = json.loads((d / "meta.json").read_text())
    meta.update({"fold_hash": None, "predictions": None})
    (d / "meta.json").write_text(json.dumps(meta))
    (d / "output" / "oof.csv").unlink()
    rebuild_ledger_file(d.parent.parent)


def test_a_run_without_folds_never_sets_the_bar_or_inverts(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    leaky, d = _recorded(ready_ws, fake, idea="smoke CV", scores=(0.96, 0.96))
    _without_folds(d)
    ml = _confirmed(ready_ws, fake, leaky)
    honest, _ = _recorded(ready_ws, fake, idea="honest CV", scores=(0.50, 0.52))
    env, _ = _propose(ready_ws, fake, honest)  # no --force-cv needed
    assert any("CV bar skipped" in line for line in env["data"]["confirmation"])
    mh = _confirmed(ready_ws, fake, honest)
    fake.submissions = lambda slug, page_size=50: [
        {"ref": 1, "date": _now(), "description": f"{ml} a", "status": "COMPLETE",
         "public_score": "0.30", "private_score": "", "team_name": "t"},
        {"ref": 2, "date": _now(), "description": f"{mh} b", "status": "COMPLETE",
         "public_score": "0.40", "private_score": "", "team_name": "t"}]
    env = kx(ready_ws, fake, "lb", "--wait", "0")
    assert env["data"]["validation"] != "suspect"


def test_an_acknowledged_pair_never_reopens_only_a_new_pair_does(ready_ws, fake):
    fake.submissions = lambda slug, page_size=50: []
    runs = [_recorded(ready_ws, fake, idea=i, scores=s)[0]
            for i, s in (("a", (0.80, 0.82)), ("b", (0.84, 0.86)), ("c", (0.88, 0.90)))]
    marks = [_confirmed(ready_ws, fake, e) for e in runs]

    def lb(*scores):
        fake.submissions = lambda slug, page_size=50: [
            {"ref": i, "date": _now(), "description": f"{m} x", "status": "COMPLETE",
             "public_score": s, "private_score": "", "team_name": "t"}
            for i, (m, s) in enumerate(zip(marks, scores))]
        return kx(ready_ws, fake, "lb", "--wait", "0")["data"]["validation"]

    assert lb("0.80", "0.75", "0.70") == "suspect"  # every pair inverted
    kx(ready_ws, fake, "validation", "ok", "--note", "noise")
    # a smaller set of already-acknowledged pairs (c now agrees) does not re-open it
    assert lb("0.80", "0.75", "0.90") == "ok"
    assert lb("0.80", "0.75", "0.70") == "ok"
    kx(ready_ws, fake, "validation", "ok", "--note", "n2")
    d = _recorded(ready_ws, fake, idea="d", scores=(0.92, 0.94))[0]
    marks.append(_confirmed(ready_ws, fake, d))
    assert lb("0.80", "0.75", "0.70", "0.60") == "suspect"  # d inverts: a new pair
