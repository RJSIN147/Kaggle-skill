"""SETUP-03 live credential validation against the real Kaggle API.

Marked `live` (excluded from default runs). Run manually with a real credential:
    uv run pytest tests/test_credentials_live.py -m live

Accepted credential sources (ANY one is sufficient — files are detected by
EXISTENCE ONLY; their contents are NEVER read by this test):
  * env pair            KAGGLE_USERNAME + KAGGLE_KEY
  * env token           KAGGLE_API_TOKEN
  * access_token file   ~/.kaggle/access_token   (CLI 2.2.3 foregrounds this)
  * kaggle.json file    ~/.kaggle/kaggle.json

Rationale for accepting the file sources: references/kaggle-cli-behavior.md
(observed live during 01-04 Task 2) found that kaggle CLI 2.2.3 foregrounds
KAGGLE_API_TOKEN / ~/.kaggle/access_token / OAuth and does not even mention the
legacy KAGGLE_USERNAME+KAGGLE_KEY pair. The original env-only skip guard predates
that finding and silently skipped when only a real credential FILE was present.

GREEN target: 01-04. Confirmed at the 01-04 Task 3 human-verify checkpoint.
"""

import json
import os
import re
from pathlib import Path

import pytest


# The shape of a raw Kaggle key/token: a run of >=32 hex/base64url chars. Used to
# assert — WITHOUT ever reading a real secret file — that no token-shaped string
# leaked into the transcript when the credential came from a file on disk.
_TOKEN_SHAPED = re.compile(r"[A-Za-z0-9_-]{32,}")


@pytest.mark.live
def test_live_validation(seeded_workspace, run_script):
    """With a real credential, check_credentials validates and flips state -> VALIDATED.

    Skips ONLY when no credential source of any accepted form is present: the env
    pair (KAGGLE_USERNAME + KAGGLE_KEY), KAGGLE_API_TOKEN, ~/.kaggle/access_token,
    or ~/.kaggle/kaggle.json. Files are detected by EXISTENCE ONLY — their
    contents are never read here.
    """
    home = Path(os.environ.get("HOME") or Path.home())
    access_token = home / ".kaggle" / "access_token"
    kaggle_json = home / ".kaggle" / "kaggle.json"

    has_pair = bool(os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"))
    has_token = bool(os.environ.get("KAGGLE_API_TOKEN"))
    has_file = access_token.is_file() or kaggle_json.is_file()  # existence only
    if not (has_pair or has_token or has_file):
        pytest.skip(
            "no real Kaggle credential present; provide any one of: "
            "KAGGLE_USERNAME+KAGGLE_KEY, KAGGLE_API_TOKEN, "
            "~/.kaggle/access_token, or ~/.kaggle/kaggle.json"
        )

    ws = seeded_workspace
    # Thread through whichever source exists. Env creds go via their vars; a
    # FILE-based credential requires the subprocess to see the real HOME so both
    # check_credentials.py's source detection and the kaggle CLI can find
    # ~/.kaggle (the conftest base env would otherwise not guarantee it).
    passthrough = {
        k: os.environ[k]
        for k in ("KAGGLE_USERNAME", "KAGGLE_KEY", "KAGGLE_API_TOKEN")
        if k in os.environ
    }
    if has_file:
        passthrough["HOME"] = str(home)

    res = run_script("check_credentials.py", "--workspace", ws, cwd=ws, extra_env=passthrough)
    assert res.returncode == 0, res.stderr

    state = json.loads((Path(ws) / "control" / "state.json").read_text())
    assert state["credentials"] == "VALIDATED"

    # SETUP-04 / T-01-02: even on the success path, no raw credential VALUE may
    # appear in the transcript (masked or env-var-name only). Guards against a
    # regression where a token leaks via the checker's own output.
    transcript = res.stdout + res.stderr

    # (a) Env-based secrets we already hold in-process: assert literal absence.
    for secret in (os.environ.get("KAGGLE_KEY"), os.environ.get("KAGGLE_API_TOKEN")):
        if secret:
            assert secret not in transcript, "credential value leaked to output"

    # (b) File-based secret: we deliberately NEVER read the token file, so we
    # cannot compare against its literal value. Instead assert the transcript
    # carries no token-shaped string — no OAuth prefix (kagat_/kagrt_/KGAT_) and
    # no >=32-char hex/base64url run (the shape of a raw key/token).
    if has_file:
        assert "kagat_" not in transcript, "OAuth access-token prefix leaked to output"
        assert "kagrt_" not in transcript, "OAuth refresh-token prefix leaked to output"
        assert "KGAT_" not in transcript, "legacy scoped-token prefix leaked to output"
        assert _TOKEN_SHAPED.search(transcript) is None, "token-shaped string leaked to output"
