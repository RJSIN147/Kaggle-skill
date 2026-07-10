"""D-16 Kaggle Gateway pure-function contract (COMP-02).

Unit coverage for the single gateway every Phase 2 entry point routes through
(`scripts/kaggle_gateway.py`):

  - ``preflight_entered()`` — fuzzy ``competitions list --search`` result matched on the
    EXACT slug via ``ref.rsplit('/', 1)[-1]`` (never row[0]); returns True | False | None.
  - ``classify_gate()`` — fails closed on an unclassifiable 403 (D-12): names BOTH the
    rules and phone URLs, states it could not be classified, and NEVER echoes the raw CLI
    buffer (D-11 / T-02-LEAK).
  - the reserved exit-code constants ``UI_GATE == 77`` / ``LIMIT_NEEDS_USER == 78`` (§17).

Mock-backed: each test monkeypatches the gateway's own ``run_kaggle`` (no real Kaggle call).
GREEN target: 02-01 Task 3 (creates scripts/kaggle_gateway.py). RED now (module absent).

The module is imported INSIDE each test (via ``_gateway()``) so collection never crashes
on the missing module — the tests fail cleanly (ModuleNotFoundError) rather than aborting
collection, matching the conftest "never import a not-yet-built script at module top" rule.
"""

import importlib
import json


def _gateway():
    """Import scripts/kaggle_gateway.py (on sys.path via conftest). Absent at RED."""
    return importlib.import_module("kaggle_gateway")


def _fake_run_kaggle(rows):
    """Return a ``run_kaggle`` stand-in yielding ``(0, <json-array line>)``."""
    payload = json.dumps(rows)

    def _fake(*argv, timeout=60):
        return 0, payload + "\n"

    return _fake


# --- preflight_entered: exact-slug match over a FUZZY search result ----------- #
def test_preflight_entered_true(monkeypatch):
    """Exact-slug row with userHasEntered=true → True."""
    gw = _gateway()
    rows = [
        {"ref": "https://www.kaggle.com/competitions/titanic", "userHasEntered": True},
        {"ref": "https://www.kaggle.com/competitions/spaceship-titanic", "userHasEntered": False},
    ]
    monkeypatch.setattr(gw, "run_kaggle", _fake_run_kaggle(rows))
    assert gw.preflight_entered("titanic") is True


def test_preflight_entered_false(monkeypatch):
    """Exact-slug row with userHasEntered=false → False (the rules gate)."""
    gw = _gateway()
    rows = [
        {"ref": "https://www.kaggle.com/competitions/titanic", "userHasEntered": False},
        {"ref": "https://www.kaggle.com/competitions/spaceship-titanic", "userHasEntered": True},
    ]
    monkeypatch.setattr(gw, "run_kaggle", _fake_run_kaggle(rows))
    assert gw.preflight_entered("titanic") is False


def test_preflight_entered_none_when_slug_absent(monkeypatch):
    """Fuzzy search returns only spaceship-titanic → exact 'titanic' absent → None."""
    gw = _gateway()
    rows = [
        {"ref": "https://www.kaggle.com/competitions/spaceship-titanic", "userHasEntered": True},
    ]
    monkeypatch.setattr(gw, "run_kaggle", _fake_run_kaggle(rows))
    assert gw.preflight_entered("titanic") is None


def test_preflight_entered_none_on_nonzero_rc(monkeypatch):
    """Non-zero rc (e.g. blocked egress / bad call) → indeterminate → None."""
    gw = _gateway()

    def _fail(*argv, timeout=60):
        return 1, "boom"

    monkeypatch.setattr(gw, "run_kaggle", _fail)
    assert gw.preflight_entered("titanic") is None


# --- reserved exit-code constants (§17, D-10) -------------------------------- #
def test_exit_code_constants():
    gw = _gateway()
    assert gw.UI_GATE == 77
    assert gw.LIMIT_NEEDS_USER == 78


# --- classify_gate: fail-closed on an unclassifiable 403 (D-12 / D-11) ------- #
# The VERIFIED-LIVE generic download 403 (CLI 2.2.3), with a token-shaped sentinel
# spliced in to prove no raw buffer content reaches the returned message.
GENERIC_403 = (
    "\n403 Client Error: Forbidden for url: "
    "https://api.kaggle.com/v1/competitions.CompetitionApiService/DownloadDataFiles"
    " TOKENLEAK_SENTINEL_kagat_ZZZZ"
)


def test_classify_gate_fails_closed_names_both_urls(monkeypatch):
    """An entered user still hitting a 403 is unclassifiable → name BOTH gates (D-12)."""
    gw = _gateway()
    # userHasEntered=True → the rules gate is NOT the cause → cannot classify.
    rows = [{"ref": "https://www.kaggle.com/competitions/titanic", "userHasEntered": True}]
    monkeypatch.setattr(gw, "run_kaggle", _fake_run_kaggle(rows))

    msg = gw.classify_gate(GENERIC_403, "titanic")
    assert "https://www.kaggle.com/competitions/titanic/rules" in msg
    assert "https://www.kaggle.com/settings" in msg
    # D-12: states plainly it could not be classified.
    assert "could not" in msg.lower() or "not be classified" in msg.lower()


def test_classify_gate_never_echoes_raw_buffer(monkeypatch):
    """D-11 / T-02-LEAK: the raw combined CLI buffer NEVER appears in the returned message."""
    gw = _gateway()
    rows = [{"ref": "https://www.kaggle.com/competitions/titanic", "userHasEntered": True}]
    monkeypatch.setattr(gw, "run_kaggle", _fake_run_kaggle(rows))

    msg = gw.classify_gate(GENERIC_403, "titanic")
    assert "TOKENLEAK_SENTINEL" not in msg
    assert "kagat_" not in msg
    assert GENERIC_403 not in msg
