"""SETUP-03 live credential validation against the real Kaggle API.

Marked `live` (excluded from default runs). Run manually with a real token:
    uv run pytest tests/test_credentials_live.py -m live

GREEN target: 01-04. RED now (check_credentials.py does not exist yet).
"""

import json
import os
from pathlib import Path

import pytest


@pytest.mark.live
def test_live_validation(seeded_workspace, run_script):
    """With a real token, check_credentials validates and flips state.json -> VALIDATED."""
    has_pair = os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY")
    has_token = os.environ.get("KAGGLE_API_TOKEN")
    if not (has_pair or has_token):
        pytest.skip("no real Kaggle token in env; set KAGGLE_USERNAME/KAGGLE_KEY to run the live check")

    ws = seeded_workspace
    passthrough = {
        k: os.environ[k]
        for k in ("KAGGLE_USERNAME", "KAGGLE_KEY", "KAGGLE_API_TOKEN")
        if k in os.environ
    }
    res = run_script("check_credentials.py", "--workspace", ws, cwd=ws, extra_env=passthrough)
    assert res.returncode == 0, res.stderr

    state = json.loads((Path(ws) / "control" / "state.json").read_text())
    assert state["credentials"] == "VALIDATED"
