"""set_metric.py — the D-08 metric setter (AI decides enum, tooling writes config).

GREEN target: 03-01 Task 2. RED until scripts/set_metric.py exists.

Contract:
  * A KNOWN metric's direction is LOOKED UP from metric_registry — never free-typed.
  * `custom` REQUIRES an explicit --greater-is-better/--no-greater-is-better (block,
    don't guess); without it the setter exits non-zero and writes NOTHING.
  * A non-enum value is rejected at the argparse `choices` boundary (exit 2, no write).
  * A corrupt config.json is left byte-for-byte intact and the setter returns non-zero.
"""

import json
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
MODULE_PATH = SCRIPTS / "set_metric.py"
TMPL_PATH = SCRIPTS / "templates" / "config.json.tmpl"


def _seed(ws):
    """Write a scaffolded control/config.json with the reserved-null `metric` key."""
    ctrl = ws / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    cfg = {
        "workspace_version": 1,
        "competition_slug": "titanic",
        "execution_target": "local",
        "cv": {"scheme": "StratifiedKFold"},
        "metric": None,
        "submission": {"daily_limit": None, "limit_provenance": None},
        "competition": {"type": None},
        "created": "2026-01-01T00:00:00Z",
    }
    (ctrl / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    return ctrl / "config.json"


def _metric(cfg_path):
    return json.loads(cfg_path.read_text())["metric"]


def test_known_metric_direction_looked_up(tmp_workspace, run_script):
    """rmse is lower-is-better; the direction is looked up, not passed as a flag."""
    ws = tmp_workspace
    cfg = _seed(ws)
    r = run_script("set_metric.py", "--workspace", ws, "--metric", "rmse", cwd=ws)
    assert r.returncode == 0, r.stderr
    assert _metric(cfg) == {"name": "rmse", "greater_is_better": False}


def test_greater_is_better_metric(tmp_workspace, run_script):
    ws = tmp_workspace
    cfg = _seed(ws)
    r = run_script("set_metric.py", "--workspace", ws, "--metric", "roc_auc", cwd=ws)
    assert r.returncode == 0, r.stderr
    assert _metric(cfg) == {"name": "roc_auc", "greater_is_better": True}


def test_custom_without_direction_blocks(tmp_workspace, run_script):
    """custom with no direction flag: exit 2, config.metric unchanged (block, don't guess)."""
    ws = tmp_workspace
    cfg = _seed(ws)
    before = cfg.read_bytes()
    r = run_script("set_metric.py", "--workspace", ws, "--metric", "custom", cwd=ws)
    assert r.returncode == 2, r.stderr
    assert cfg.read_bytes() == before
    assert _metric(cfg) is None


def test_custom_with_explicit_direction(tmp_workspace, run_script):
    ws = tmp_workspace
    cfg = _seed(ws)
    r = run_script(
        "set_metric.py", "--workspace", ws, "--metric", "custom",
        "--greater-is-better", cwd=ws,
    )
    assert r.returncode == 0, r.stderr
    assert _metric(cfg) == {"name": "custom", "greater_is_better": True}


def test_custom_with_no_greater_is_better(tmp_workspace, run_script):
    ws = tmp_workspace
    cfg = _seed(ws)
    r = run_script(
        "set_metric.py", "--workspace", ws, "--metric", "custom",
        "--no-greater-is-better", cwd=ws,
    )
    assert r.returncode == 0, r.stderr
    assert _metric(cfg) == {"name": "custom", "greater_is_better": False}


def test_unknown_metric_rejected_at_choices(tmp_workspace, run_script):
    """A value outside SUPPORTED is rejected by argparse (exit 2), nothing written."""
    ws = tmp_workspace
    cfg = _seed(ws)
    before = cfg.read_bytes()
    r = run_script("set_metric.py", "--workspace", ws, "--metric", "not_a_metric", cwd=ws)
    assert r.returncode == 2
    assert cfg.read_bytes() == before


def test_corrupt_config_left_untouched(tmp_workspace, run_script):
    """MalformedControlJSON posture: corrupt config bytes intact, non-zero exit."""
    ws = tmp_workspace
    ctrl = ws / "control"
    ctrl.mkdir(parents=True)
    corrupt = b'{ "workspace_version": 1,, broken'
    (ctrl / "config.json").write_bytes(corrupt)
    r = run_script("set_metric.py", "--workspace", ws, "--metric", "rmse", cwd=ws)
    assert r.returncode != 0
    assert (ctrl / "config.json").read_bytes() == corrupt


def test_template_reserves_metric_null():
    """config.json.tmpl parses as JSON and reserves the `metric` key as null."""
    tmpl = json.loads(TMPL_PATH.read_text())
    assert "metric" in tmpl
    assert tmpl["metric"] is None


def test_set_metric_is_stdlib_only():
    """No ML import in the setter — it only reads the stdlib registry's name strings."""
    src = MODULE_PATH.read_text()
    assert not re.search(r"^\s*import\s+(sklearn|pandas|numpy)\b", src, re.M), src
    assert not re.search(r"^\s*from\s+(sklearn|pandas|numpy)\b", src, re.M), src
