"""Opt-in LIVE verification of the recorded Phase 2 Kaggle CLI shapes (COMP-01/02/03).

Marked ``live`` and therefore EXCLUDED from the default run (``pyproject.toml``
sets ``addopts = -m 'not live'``). Run it explicitly, with a real credential:

    uv run pytest -m live tests/test_competition_live.py

Accepted credential sources — the SAME accepted-sources guard as
``tests/test_credentials_live.py`` (files are detected by EXISTENCE ONLY; their
contents are NEVER read here):
  * env pair            KAGGLE_USERNAME + KAGGLE_KEY
  * env token           KAGGLE_API_TOKEN
  * access_token file   ~/.kaggle/access_token   (CLI 2.2.3 foregrounds this)
  * kaggle.json file    ~/.kaggle/kaggle.json

What it pins (all against the read-only, quota-free public ``titanic`` slug so no
submission budget is spent and nothing is mutated), routing every call through the
D-16 gateway / the entry points — NEVER a raw shell string built from page content:
  * ``competitions pages <slug> --content --format json`` → ``[{name, content:HTML}]``
  * ``competitions files <slug> --format json --page-size 200`` → ``[{name, size:int, creationDate}]``
  * ``competitions list --search <slug> --format json`` exposes ``userHasEntered``
  * a real download of an ENTERED slug yields a single ``<slug>.zip`` (CLI 2.2.3 has
    no ``--unzip``; the on-disk artifact is one zip)
  * an UN-ENTERED slug download produces the generic 403 (exit 1), the
    positively-classifiable rules gate
  * the FRAMEWORK-authored transcript of an entry point never leaks a token-shaped
    string (reuses ``_TOKEN_SHAPED`` from ``test_credentials_live.py``)

The phone-verification 403 is a documented ``pytest.skip`` placeholder: it cannot be
produced from a verified account and the download 403 is generic (never names the
phone gate), so the signature is UNVERIFIABLE by design (T-02-A1 / D-12 fail-closed).

Provenance is honest: these shapes were recorded VERIFIED-LIVE in
``references/kaggle-cli-behavior.md`` (CLI 2.2.3, 2026-07-10); this suite re-pins them
without ever reading, printing, or recording a credential value.
"""

import json
import os
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
# Let this module import the gateway directly (its calls ARE the "through the
# gateway" contract the plan requires — no raw shell strings from page content).
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import kaggle_gateway as gw  # noqa: E402  (self-locating sys.path insert above)


# The shape of a raw Kaggle key/token: a run of >=32 hex/base64url chars. REUSED
# verbatim from test_credentials_live.py to assert — WITHOUT ever reading a real
# secret file — that no token-shaped string leaked into a framework transcript.
_TOKEN_SHAPED = re.compile(r"[A-Za-z0-9_-]{32,}")
# OAuth / legacy scoped-token prefixes; specific enough to assert absent even in a
# raw CLI buffer (they never occur in legitimate competition prose).
_OAUTH_PREFIXES = ("kagat_", "kagrt_", "KGAT_")

# A read-only, quota-free public competition. Probing its pages / files / list
# shapes and downloading its (tiny) data costs NO submission budget and mutates
# nothing on the account.
LIVE_SLUG = "titanic"

# Candidate un-entered public slugs for the generic-403 assertion. Each is PROBED
# with the cheap preflight; the first that reports userHasEntered == False is used.
# If none do (the account entered them, or the probe is indeterminate), the 403
# test skips honestly — this suite must NEVER accept rules itself (D-10).
_UNENTERED_CANDIDATES = ("spaceship-titanic", "gemini-3", "playground-series-s4e1")


# --------------------------------------------------------------------------- #
# Shared guards / helpers.
# --------------------------------------------------------------------------- #
def _credential_present() -> bool:
    """Reuse test_credentials_live.py's accepted-sources guard (existence only)."""
    home = Path(os.environ.get("HOME") or Path.home())
    has_pair = bool(os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"))
    has_token = bool(os.environ.get("KAGGLE_API_TOKEN"))
    has_file = (
        (home / ".kaggle" / "access_token").is_file()
        or (home / ".kaggle" / "kaggle.json").is_file()
    )
    return has_pair or has_token or has_file


def _require_credential() -> None:
    """Skip cleanly when no real credential of any accepted form is present."""
    if not _credential_present():
        pytest.skip(
            "no real Kaggle credential present; provide any one of: "
            "KAGGLE_USERNAME+KAGGLE_KEY, KAGGLE_API_TOKEN, "
            "~/.kaggle/access_token, or ~/.kaggle/kaggle.json"
        )


def _assert_no_token_shaped(text: str, where: str) -> None:
    """Assert a FRAMEWORK-authored transcript carries no token-shaped string.

    Applied ONLY to framework-authored transcripts (short, secret-free by design) —
    never to a raw JSON page payload, whose HTML content legitimately contains long
    alphanumeric runs. The OAuth-prefix checks below are additionally applied to raw
    buffers because those prefixes never occur in legitimate competition prose.
    """
    for pfx in _OAUTH_PREFIXES:
        assert pfx not in text, f"OAuth token prefix {pfx!r} leaked to {where}"
    assert _TOKEN_SHAPED.search(text) is None, f"token-shaped string leaked to {where}"


def _assert_no_oauth_prefix(text: str, where: str) -> None:
    """Assert no OAuth/legacy token prefix rides on a raw CLI buffer (safe on HTML)."""
    for pfx in _OAUTH_PREFIXES:
        assert pfx not in text, f"OAuth token prefix {pfx!r} leaked to {where}"


def _parse_json_array(combined: str):
    """Parse a JSON array from gateway output, tolerating a leading banner line."""
    stripped = combined.strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, list) else None
    except json.JSONDecodeError:
        pass
    # The array may sit on the last non-empty line (banner-prefixed) or after a
    # leading banner — try both, most-specific first.
    for line in reversed(stripped.splitlines()):
        line = line.strip()
        if line.startswith("["):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list):
                return parsed
    start = stripped.find("[")
    if start != -1:
        try:
            parsed = json.loads(stripped[start:])
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return None


# --------------------------------------------------------------------------- #
# CLI-shape assertions (VERIFIED-LIVE shapes from references/kaggle-cli-behavior.md).
# --------------------------------------------------------------------------- #
@pytest.mark.live
def test_pages_shape_is_name_content_html():
    """`competitions pages <slug> --content --format json` → [{name, content:HTML}]."""
    _require_credential()
    rc, combined = gw.run_kaggle(
        "competitions", "pages", LIVE_SLUG, "--content", "--format", "json"
    )
    assert rc == 0, "`competitions pages` did not exit 0 (offline / gated?)"
    pages = _parse_json_array(combined)
    assert isinstance(pages, list) and pages, "pages did not return a non-empty JSON array"
    for page in pages:
        assert isinstance(page, dict), f"page row is not an object: {type(page)}"
        assert "name" in page, "page row missing 'name'"
        assert "content" in page, "page row missing 'content'"
    # VERIFIED-LIVE: page content is HTML (RESEARCH §Pitfall 5), not markdown.
    assert any("<" in (p.get("content") or "") for p in pages), "no HTML content found"
    _assert_no_oauth_prefix(combined, "pages buffer")


@pytest.mark.live
def test_files_shape_is_name_size_creationdate():
    """`competitions files <slug> --format json --page-size 200` → [{name, size:int, creationDate}]."""
    _require_credential()
    rc, combined = gw.run_kaggle(
        "competitions", "files", LIVE_SLUG, "--format", "json", "--page-size", "200"
    )
    assert rc == 0, "`competitions files` did not exit 0"
    files = _parse_json_array(combined)
    assert isinstance(files, list) and files, "files did not return a non-empty JSON array"
    for f in files:
        assert isinstance(f, dict), f"file row is not an object: {type(f)}"
        assert "name" in f, "file row missing 'name'"
        assert "size" in f, "file row missing 'size'"
        assert isinstance(f["size"], int), f"'size' is not an int: {type(f['size'])}"
        assert "creationDate" in f, "file row missing 'creationDate'"
    _assert_no_oauth_prefix(combined, "files buffer")


@pytest.mark.live
def test_list_search_exposes_user_has_entered():
    """`competitions list --search <slug> --format json` exposes userHasEntered (exact slug)."""
    _require_credential()
    rc, combined = gw.run_kaggle(
        "competitions", "list", "--search", LIVE_SLUG, "--format", "json"
    )
    assert rc == 0, "`competitions list --search` did not exit 0"
    rows = _parse_json_array(combined)
    assert isinstance(rows, list) and rows, "list --search returned no rows"
    # --search is FUZZY ("titanic" also returns "spaceship-titanic"): match the
    # EXACT slug via ref.rsplit('/', 1)[-1], never rows[0] (mirrors the gateway).
    exact = [
        r
        for r in rows
        if isinstance(r, dict)
        and str(r.get("ref", "")).rsplit("/", 1)[-1] == LIVE_SLUG
    ]
    assert exact, f"exact slug {LIVE_SLUG!r} absent from fuzzy search rows"
    assert "userHasEntered" in exact[0], "userHasEntered field absent from the row"
    # The gateway's own preflight must resolve a DEFINITE bool for the exact slug.
    entered = gw.preflight_entered(LIVE_SLUG)
    assert entered in (True, False), f"preflight_entered should resolve a bool, got {entered!r}"
    _assert_no_oauth_prefix(combined, "list buffer")


@pytest.mark.live
def test_download_yields_single_slug_zip(tmp_path):
    """A real download of an ENTERED slug yields a single `<slug>.zip` (CLI 2.2.3 has no --unzip)."""
    _require_credential()
    entered = gw.preflight_entered(LIVE_SLUG)
    if entered is not True:
        pytest.skip(
            f"account has not entered '{LIVE_SLUG}' (userHasEntered={entered!r}); the "
            "download-shape assertion needs an entered competition, and this suite "
            "must NOT accept rules itself (D-10 human-only gate)"
        )
    dest = tmp_path / "data"
    dest.mkdir()
    rc, combined = gw.run_kaggle("competitions", "download", LIVE_SLUG, "-p", str(dest))
    assert rc == 0, "download of an entered competition did not exit 0"
    zips = sorted(dest.glob("*.zip"))
    assert zips == [dest / f"{LIVE_SLUG}.zip"], f"expected exactly one {LIVE_SLUG}.zip, got {zips}"
    _assert_no_oauth_prefix(combined, "download buffer")


@pytest.mark.live
def test_unentered_download_is_generic_403(tmp_path):
    """An un-entered slug download → generic 403 (exit 1), no files pulled (rules gate)."""
    _require_credential()
    target = None
    for cand in _UNENTERED_CANDIDATES:
        if gw.preflight_entered(cand) is False:
            target = cand
            break
    if target is None:
        pytest.skip(
            "could not find an un-entered public slug among "
            f"{_UNENTERED_CANDIDATES} (all entered or indeterminate); cannot exercise "
            "the generic-403 rules gate without one"
        )
    dest = tmp_path / "data"
    dest.mkdir()
    rc, combined = gw.run_kaggle("competitions", "download", target, "-p", str(dest))
    assert rc != 0, "un-entered download unexpectedly succeeded"
    assert ("403" in combined) or ("Forbidden" in combined), "expected a generic 403 signature"
    assert not list(dest.glob("*.zip")), "no archive should be pulled on a 403"
    _assert_no_oauth_prefix(combined, "un-entered 403 buffer")


@pytest.mark.live
def test_entrypoint_transcript_never_leaks_a_secret(seeded_workspace, run_script):
    """The FRAMEWORK-authored transcript of an entry point carries no token-shaped string.

    Runs ``capture_competition.py`` (whose stdout/stderr are framework-authored — the
    raw CLI payload is quarantined to ``control/raw/``, NEVER echoed) against the
    read-only ``titanic`` slug and asserts its transcript has no OAuth prefix and no
    >=32-char token-shaped run. This is the operator-facing leak guard (T-02-LEAK-02):
    whatever reaches the terminal must be secret-free. HOME is threaded through so the
    subprocess CLI can find a FILE-based credential (~/.kaggle/access_token).
    """
    _require_credential()
    ws = seeded_workspace  # control/config.json already carries competition_slug=titanic
    home = Path(os.environ.get("HOME") or Path.home())
    res = run_script(
        "capture_competition.py",
        "--workspace",
        ws,
        "--assume-default-limit",  # never block on the D-13 limit prompt in a test
        cwd=ws,
        extra_env={"HOME": str(home)},
    )
    transcript = res.stdout + res.stderr
    _assert_no_token_shaped(transcript, "capture_competition transcript")


@pytest.mark.live
def test_phone_verification_403_placeholder():
    """Documented placeholder: the phone-verification 403 cannot be produced here (T-02-A1).

    A verified account cannot trigger the phone-verification gate, and the download
    403 is GENERIC — it never names the phone gate (VERIFIED-LIVE). So this signature
    is UNVERIFIABLE from a verified account by design; the framework fails closed
    regardless (D-12 names BOTH gates). Recorded as an explicit skip so the gap is
    visible in the suite rather than silently absent.
    """
    _require_credential()
    pytest.skip(
        "cannot trigger the phone-verification 403 from a verified account "
        "(T-02-A1 / D-12 fail-closed); the download 403 is generic and never names "
        "the phone gate — see references/kaggle-cli-behavior.md"
    )
