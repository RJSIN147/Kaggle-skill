"""Opt-in LIVE CLI-drift canary for the submission read-back shape (SCORE-01, DRIFT).

Marked ``live`` and therefore EXCLUDED from the default run (``pyproject.toml`` sets
``addopts = -m 'not live'``). Run it explicitly, with a real credential:

    uv run pytest -m live tests/test_submission_live.py

⭐ **READ-ONLY. THIS SUITE SPENDS NOTHING.** It issues exactly one command —
``competitions submissions <slug> --format json --page-size 200`` — which lists submissions
that already exist. It CANNOT create one. A submission is IRREVERSIBLE and consumes a scarce
daily slot, so no live test may ever make one; that rule is enforced mechanically by
``tests/test_submit.py::test_no_live_test_ever_submits``, which greps every
``tests/test_*live*.py`` for a submit invocation and fails if it finds one.

What it pins (the shapes 05-RESEARCH.md §R2 captured live against CLI 2.2.3, 2026-07-12):
  * the response is a JSON ARRAY, pretty-printed across many lines;
  * every row carries EXACTLY the seven allow-listed fields — ``ref``, ``fileName``,
    ``date``, ``description``, ``status``, ``publicScore``, ``privateScore``;
  * ``ref`` is an **int**; ``publicScore`` / ``privateScore`` are **strings** (``""`` when
    unscored — never a float, never null);
  * ``date`` is a **NAIVE** ISO-8601 string with no timezone suffix (the trap the UTC budget
    arithmetic is built around — assumption A1);
  * ``status`` is the **fully-qualified** ``SubmissionStatus.{PENDING,COMPLETE,ERROR}``
    literal, not a bare token.

If Kaggle changes any of this out from under us, this canary reddens — mechanically, instead
of someone re-reading a research document.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import kaggle_gateway as gw  # noqa: E402  (self-locating sys.path insert above)

# A public, already-entered competition. Listing its submissions is free and mutates nothing.
LIVE_SLUG = "titanic"

# The complete allow-list, confirmed live by triggering the CLI's own projection error:
#   "Unknown field in projection: 'errorDescription'. Allowed fields: date, description,
#    fileName, privateScore, publicScore, ref, status"
SUBMISSION_FIELDS = {
    "ref",
    "fileName",
    "date",
    "description",
    "status",
    "publicScore",
    "privateScore",
}

STATUS_LITERALS = {
    "SubmissionStatus.PENDING",
    "SubmissionStatus.COMPLETE",
    "SubmissionStatus.ERROR",
}

_OAUTH_PREFIXES = ("kagat_", "kagrt_", "KGAT_")


def _credential_present() -> bool:
    """The accepted-sources guard (existence ONLY — no credential file is ever read)."""
    home = Path(os.environ.get("HOME") or Path.home())
    has_pair = bool(os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"))
    has_token = bool(os.environ.get("KAGGLE_API_TOKEN"))
    has_file = (home / ".kaggle" / "access_token").is_file() or (
        home / ".kaggle" / "kaggle.json"
    ).is_file()
    return has_pair or has_token or has_file


def _require_credential() -> None:
    if not _credential_present():
        pytest.skip(
            "no real Kaggle credential present; provide any one of: "
            "KAGGLE_USERNAME+KAGGLE_KEY, KAGGLE_API_TOKEN, "
            "~/.kaggle/access_token, or ~/.kaggle/kaggle.json"
        )


def _read_back(slug):
    """The ONE read-only call this suite is permitted to make."""
    return gw.run_kaggle(
        "competitions", "submissions", slug, "--format", "json", "--page-size", "200"
    )


@pytest.mark.live
def test_submissions_shape_is_seven_fields():
    """The read-back still yields the 7 allow-listed keys, an int ref, and STRING scores."""
    _require_credential()

    rc, combined = _read_back(LIVE_SLUG)
    assert rc == 0, "`competitions submissions` did not exit 0 (offline / gated?)"

    for pfx in _OAUTH_PREFIXES:
        assert pfx not in combined, f"OAuth token prefix {pfx!r} leaked into the CLI buffer"

    rows = gw._parse_json_array(combined.strip())
    if not rows:
        pytest.skip(
            f"the account has no submissions for '{LIVE_SLUG}' — the shape canary needs at "
            "least one existing row. This suite must NEVER create one (a submission is "
            "irreversible and spends a real daily slot)."
        )
    assert isinstance(rows, list)

    for row in rows:
        assert isinstance(row, dict), f"submission row is not an object: {type(row)}"
        assert set(row) == SUBMISSION_FIELDS, (
            f"CLI DRIFT: the submission field set changed. got={sorted(row)} "
            f"expected={sorted(SUBMISSION_FIELDS)}"
        )
        assert isinstance(row["ref"], int), "`ref` must be an int (the Kaggle submission id)"
        assert isinstance(row["publicScore"], str), (
            "CLI DRIFT: `publicScore` is a STRING (and '' when unscored) — a guarded float() "
            "parse depends on it"
        )
        assert isinstance(row["privateScore"], str)
        assert isinstance(row["date"], str)
        # ⚠ A1: the timestamp is NAIVE — no tz suffix. The whole UTC budget arithmetic
        # (charged_today) is built on treating it as UTC.
        assert not row["date"].endswith("Z")
        assert "+" not in row["date"], "CLI DRIFT: `date` grew a timezone offset"


@pytest.mark.live
def test_status_literal_is_fully_qualified():
    """`status` is still the fully-qualified `SubmissionStatus.<TOKEN>` enum render."""
    _require_credential()

    rc, combined = _read_back(LIVE_SLUG)
    assert rc == 0
    rows = gw._parse_json_array(combined.strip())
    if not rows:
        pytest.skip(f"no existing submissions for '{LIVE_SLUG}' to inspect (creating one is forbidden)")

    for row in rows:
        status = row["status"]
        assert status in STATUS_LITERALS, (
            f"CLI DRIFT: unknown status literal {status!r}. The parse is ANCHORED on "
            f"{sorted(STATUS_LITERALS)} — a new literal must fail closed, never be guessed."
        )
        assert status.startswith("SubmissionStatus."), (
            "CLI DRIFT: the enum is no longer fully-qualified — `row['status'] == 'COMPLETE'` "
            "would now be the correct comparison, inverting the Pitfall-2 trap"
        )


@pytest.mark.live
def test_no_quota_command_for_submissions():
    """`kaggle quota` still reports GPU/TPU hours ONLY — there is no submission-quota API.

    This is why the daily budget must be DERIVED by counting rows (D-04). If Kaggle ever ships
    a real submission quota, this test reddens and the count-rows workaround can be retired.
    """
    _require_credential()

    rc, combined = gw.run_kaggle("quota", "--format", "json")
    if rc != 0:
        pytest.skip("`kaggle quota` did not exit 0 (offline / surface changed)")

    rows = gw._parse_json_array(combined.strip()) or []
    resources = {str(r.get("resource", "")).upper() for r in rows if isinstance(r, dict)}
    assert resources <= {"GPU", "TPU"}, (
        f"CLI CHANGE: `quota` now reports {resources} — if a SUBMISSION quota exists, D-04's "
        "count-the-rows derivation can be replaced by the authoritative number."
    )
