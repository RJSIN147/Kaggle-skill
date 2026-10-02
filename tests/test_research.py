"""RES-01..04 (research ingestion, ideas, host metric) and PROF-04/CORE-05 routing."""

import json
import subprocess

import pytest
from conftest import _base_env, kx

from kx.commands import type_guides
from kx.research import notebook_code


def test_pages_are_fenced_and_uncommitted(ready_ws, fake):
    env = kx(ready_ws, fake, "research", "pages")
    assert env["status"] == "ok"
    ev = (ready_ws / "research/cache/pages/Evaluation.md").read_text()
    assert ev.startswith("<untrusted-content") and "accuracy" in ev
    assert "research/cache/" in (ready_ws / ".gitignore").read_text()
    ignored = subprocess.run(["git", "check-ignore", "research/cache/pages/Evaluation.md"],
                             cwd=ready_ws, capture_output=True, text=True, env=_base_env())
    assert ignored.returncode == 0


def test_discussions_keep_bodies_out_of_envelopes_and_escape_fences(ready_ws, fake):
    env = kx(ready_ws, fake, "research", "discussions")
    blob = json.dumps(env)
    assert "IGNORE ALL PREVIOUS" not in blob
    assert env["data"]["discussions"][0]["title"] == "1st place"
    cache = (ready_ws / "research/cache/discussions/11.md").read_text()
    assert "target encoding" in cache and "thanks" in cache
    assert cache.count("</untrusted-content>") == 1  # the injected closer was neutralised
    idx = json.loads((ready_ws / "research/index.json").read_text())
    assert idx["discussions"][0]["note"] == "research/notes/discussion-11.md"
    assert ("topics", "hot") in fake.calls  # competition still running -> hot


def test_notebooks_record_sources_and_strip_magics(ready_ws, fake):
    env = kx(ready_ws, fake, "research", "notebooks")
    nb = env["data"]["notebooks"][0]
    assert nb["kernel_sources"] == ["metric/acc-metric", "bob/wheels"]
    assert nb["dataset_sources"] == ["bob/weights"]
    cache = (ready_ws / nb["cache"]).read_text()
    assert "import numpy" in cache and "pip install" not in cache
    kw = [c[1] for c in fake.calls if c[0] == "kernels_list"][0]
    assert kw["sort_by"] == "voteCount"


def test_notebook_code_extraction():
    src = json.dumps({"cells": [{"cell_type": "code", "source": "%time x=1\ny=2"}]})
    assert notebook_code(src, "notebook") == "y=2"
    assert notebook_code("print(1)", "script") == "print(1)"


def test_metric_candidates_and_adoption(ready_ws, fake):
    kx(ready_ws, fake, "research", "notebooks")
    env = kx(ready_ws, fake, "research", "metric")
    refs = [c["ref"] for c in env["data"]["metric_candidates"]]
    assert refs == ["metric/acc-metric"]
    env = kx(ready_ws, fake, "research", "metric", "--use-metric", "alice/great-nb")
    assert env["errors"] == ["not_a_metric_kernel"]
    env = kx(ready_ws, fake, "research", "metric", "--use-metric", "metric/acc-metric")
    assert env["status"] == "ok"
    cfg = json.loads((ready_ws / "control/config.json").read_text())
    assert cfg["metric"]["host_metric"]["ref"] == "metric/acc-metric"
    new = kx(ready_ws, fake, "new", "--idea", "x", "--hypothesis", "y")
    code = (ready_ws / "experiments" / new["data"]["exp_id"] / "train.py").read_text()
    assert "HOST METRIC (metric/acc-metric" in code and "host_metric = _LazyHostMetric()" in code
    ns = {}
    exec(compile(code.split("# === AI BLOCK")[0].split('"""', 2)[2].replace(
        "import numpy as np\nimport pandas as pd\n", "import numpy as np\nimport pandas as pd\n"),
        "t", "exec"), ns)
    import pandas as pd
    sol = pd.DataFrame({"id": [1, 2], "y": [1, 0]})
    assert ns["host_metric"].score(sol, sol.copy(), "id") == 1.0


def test_tampered_host_metric_is_refused(ready_ws, fake):
    kx(ready_ws, fake, "research", "metric", "--use-metric", "metric/acc-metric")
    cfg = json.loads((ready_ws / "control/config.json").read_text())
    (ready_ws / cfg["metric"]["host_metric"]["file"]).write_text("def score(*a): return 1\n")
    env = kx(ready_ws, fake, "new", "--idea", "x", "--hypothesis", "y")
    assert env["status"] == "error"


def test_ideas_feed_strategy_and_new(ready_ws, fake):
    env = kx(ready_ws, fake, "research", "idea", "--idea", "target-encode Cabin deck",
             "--source", "discussion 11")
    assert env["data"]["idea"]["n"] == 1
    assert env["next_action"]["command"].startswith("kx new --from-idea 1")
    env = kx(ready_ws, fake, "new", "--from-idea", "1", "--hypothesis", "deck matters")
    assert env["status"] == "ok"
    spec = json.loads((ready_ws / "experiments" / env["data"]["exp_id"] / "experiment.json")
                      .read_text())
    assert spec["idea"].startswith("target-encode Cabin deck [from discussion: discussion 11]")
    rows = [json.loads(ln) for ln in (ready_ws / "research/ideas.jsonl").read_text().splitlines()]
    assert rows[0]["status"] == "tried:exp-001"
    kx(ready_ws, fake, "research", "idea", "--idea", "pseudo-label", "--source", "alice/great-nb")
    from kx import strategy

    body = strategy.research_body(rows + [{"idea": "pseudo-label", "source": "alice/great-nb",
                                           "source_type": "notebook", "status": "open"}])
    assert "[notebook: alice/great-nb] pseudo-label" in body and "Cabin" not in body


@pytest.mark.parametrize("eff,guides", [
    ({"submission_mode": "csv_upload", "modality": "tabular"}, ["tabular.md"]),
    ({"submission_mode": "code_kernel", "modality": "image"},
     ["deep-learning.md", "code-competition.md"]),
    ({"submission_mode": "code_kernel", "modality": "tabular"},
     ["tabular.md", "code-competition.md"]),
    ({"submission_mode": "agent", "modality": "none"}, ["simulation.md"]),
    ({"submission_mode": "writeup", "modality": "none"}, ["writeup.md"]),
    ({"submission_mode": "artifact_upload", "modality": "text"}, ["custom.md"]),
    ({"submission_mode": "code_kernel", "modality": "structured"},
     ["custom.md", "code-competition.md"]),
    ({"submission_mode": "unknown", "modality": "tabular"}, ["other.md"]),
])
def test_type_guides_route_to_exactly_the_matching_guides(eff, guides):
    assert [g.rsplit("/", 1)[1] for g in type_guides(eff)] == guides


def test_every_routed_guide_exists_and_skill_is_lean():
    from conftest import REPO_ROOT

    for name in ("tabular", "timeseries", "deep-learning", "code-competition", "simulation",
                 "writeup", "other", "custom"):
        assert (REPO_ROOT / "references" / "types" / f"{name}.md").exists(), name
    assert len((REPO_ROOT / "SKILL.md").read_text().splitlines()) <= 150


def test_confirm_names_only_the_matching_guide(tmp_path, token_home, fake):
    ws = tmp_path / "ws"
    kx(ws, fake, "init", "titanic")
    kx(ws, fake, "sync")
    env = kx(ws, fake, "confirm", "--note", "ok")
    assert env["data"]["type_guides"] == ["references/types/tabular.md"]
    assert "tabular.md" in env["next_action"]["instruction"]
    assert "deep-learning" not in env["next_action"]["instruction"]
