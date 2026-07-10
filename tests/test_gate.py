"""Never-busy-loop gate flow for scripts/download_data.py (COMP-02 / C3, D-10/D-12).

The download gate must NEVER busy-loop an authenticated endpoint: a single cheap
preflight probe classifies the rules gate, prints the exact rules URL, and exits
the reserved ``UI_GATE`` (77) — the probe runs EXACTLY once, nothing sleeps,
nothing reads stdin. The re-invocation's preflight IS the verification (D-10). An
unclassified 403 fails closed naming BOTH the rules and phone URLs (D-12), and the
raw CLI buffer is quarantined to a file, never echoed (D-11 / T-02-LEAK). Data
download refuses unless credentials are VALIDATED (Phase 1 D-07).

``kaggle_gateway`` exists (Wave 1) so it is imported at module top; ``download_data``
is imported INSIDE each test (via ``_dd()``) so collection never crashes while the
module is absent (RED) — matching the conftest "never import a not-yet-built
script at module top" rule. Every gateway call the script makes is stubbed on the
shared ``kaggle_gateway`` module, so NO real Kaggle CLI call is ever made — the
real ``classify_gate`` runs against a stubbed ``preflight_entered`` (no network).
"""

import importlib
import json
import time
import zipfile
from pathlib import Path

import kaggle_gateway as gw

RULES_URL = "https://www.kaggle.com/competitions/titanic/rules"
PHONE_URL = "https://www.kaggle.com/settings"


def _dd():
    """Import scripts/download_data.py (on sys.path via conftest). Absent at RED."""
    return importlib.import_module("download_data")


def _set_credentials(ws: Path, status: str) -> None:
    p = ws / "control" / "state.json"
    data = json.loads(p.read_text())
    data["credentials"] = status
    p.write_text(json.dumps(data))


# --------------------------------------------------------------------------- #
# C3: gated preflight → exit 77 + exact rules URL, probe ONCE, NO sleep, NO poll.
# --------------------------------------------------------------------------- #
def test_gate_false_exits_ui_gate_without_busy_loop(seeded_workspace, monkeypatch, capsys):
    dd = _dd()
    _set_credentials(seeded_workspace, "VALIDATED")

    calls = {"preflight": 0}

    def fake_preflight(slug):
        calls["preflight"] += 1
        return False  # positively-classified rules gate

    monkeypatch.setattr(gw, "preflight_entered", fake_preflight)

    slept = {"n": 0}
    monkeypatch.setattr(time, "sleep", lambda *a, **k: slept.__setitem__("n", slept["n"] + 1))

    def boom_run(*a, **k):
        raise AssertionError("download attempted despite a closed rules gate")

    monkeypatch.setattr(gw, "run_kaggle", boom_run)

    rc = dd.main(["--workspace", str(seeded_workspace)])
    out = capsys.readouterr().out

    assert rc == gw.UI_GATE == 77
    assert RULES_URL in out
    assert calls["preflight"] == 1        # exactly one probe, no retry
    assert slept["n"] == 0                 # nothing ever slept (no busy-loop)


# --------------------------------------------------------------------------- #
# D-10: the re-invocation's preflight (now True) proceeds to download + extract.
# --------------------------------------------------------------------------- #
def test_gate_true_proceeds_to_download_and_extract(seeded_workspace, monkeypatch):
    dd = _dd()
    _set_credentials(seeded_workspace, "VALIDATED")
    monkeypatch.setattr(gw, "preflight_entered", lambda slug: True)

    def fake_download(*argv, timeout=60):
        argv = list(argv)
        pdir = Path(argv[argv.index("-p") + 1])
        pdir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(pdir / "titanic.zip", "w") as zf:
            zf.writestr("train.csv", "a,b\n1,2\n")
            zf.writestr("test.csv", "a\n1\n")
        return 0, "Downloading titanic.zip to " + str(pdir)

    monkeypatch.setattr(gw, "run_kaggle", fake_download)

    rc = dd.main(["--workspace", str(seeded_workspace)])

    assert rc == 0
    data_dir = seeded_workspace / "data"
    assert (data_dir / "train.csv").is_file()
    assert (data_dir / "test.csv").is_file()


# --------------------------------------------------------------------------- #
# D-12: an unclassified 403 (entered/indeterminate) fails closed — BOTH URLs,
# exit UI_GATE, raw buffer quarantined to a file and NEVER echoed.
# --------------------------------------------------------------------------- #
def test_unclassified_403_fails_closed_naming_both_urls(seeded_workspace, monkeypatch, capsys):
    dd = _dd()
    _set_credentials(seeded_workspace, "VALIDATED")
    # preflight indeterminate (None) → download proceeds → generic 403 → classify_gate.
    monkeypatch.setattr(gw, "preflight_entered", lambda slug: None)

    def fake_403(*argv, timeout=60):
        return 1, (
            "\n403 Client Error: Forbidden for url: "
            "https://api.kaggle.com/v1/competitions.CompetitionApiService/DownloadDataFiles"
            " TOKENLEAK_SENTINEL_kagat_ZZZZ"
        )

    monkeypatch.setattr(gw, "run_kaggle", fake_403)

    rc = dd.main(["--workspace", str(seeded_workspace)])
    out = capsys.readouterr().out

    assert rc == gw.UI_GATE == 77
    assert RULES_URL in out
    assert PHONE_URL in out
    assert ("could not" in out.lower()) or ("not be classified" in out.lower())
    # T-02-LEAK: the raw buffer is quarantined, never echoed.
    assert "TOKENLEAK_SENTINEL" not in out
    assert "kagat_" not in out
    dump = seeded_workspace / "control" / "raw" / "last-error.txt"
    assert dump.is_file()
    assert "TOKENLEAK_SENTINEL" in dump.read_text()


# --------------------------------------------------------------------------- #
# WR-01 Gap 2: rc==127 (kaggle CLI missing) gets the install-CLI remediation and
# returns 127 — NOT the exit-77 UI-gate "accept the rules" misreport. Mirrors
# capture_competition._gateway_failure. No sleep/poll — never-busy-loop holds.
# --------------------------------------------------------------------------- #
def test_missing_cli_rc127_reports_install_not_ui_gate(seeded_workspace, monkeypatch, capsys):
    dd = _dd()
    _set_credentials(seeded_workspace, "VALIDATED")
    # preflight indeterminate (None) → falls through to the download call.
    monkeypatch.setattr(gw, "preflight_entered", lambda slug: None)

    slept = {"n": 0}
    monkeypatch.setattr(time, "sleep", lambda *a, **k: slept.__setitem__("n", slept["n"] + 1))

    monkeypatch.setattr(gw, "run_kaggle", lambda *a, **k: (127, "kaggle CLI not found on PATH"))

    # The 127/124 markers are fixed + secret-free — they are NOT quarantined, so
    # dump_last_error / classify_gate must not run for these codes.
    def boom_dump(*a, **k):
        raise AssertionError("127 must not be quarantined/echoed via dump_last_error")

    def boom_classify(*a, **k):
        raise AssertionError("127 must not hit the UI-gate classify_gate branch")

    monkeypatch.setattr(gw, "dump_last_error", boom_dump)
    monkeypatch.setattr(gw, "classify_gate", boom_classify)

    rc = dd.main(["--workspace", str(seeded_workspace)])
    cap = capsys.readouterr()
    combined = (cap.out + cap.err).lower()

    assert rc == 127
    assert rc != gw.UI_GATE
    assert "not found on path" in combined
    assert "install" in combined
    # NOT the rules-acceptance / UI-gate misreport.
    assert RULES_URL not in (cap.out + cap.err)
    assert "accept the rules" not in combined
    assert "[ui_gate]" not in combined
    assert slept["n"] == 0                 # nothing ever slept (no busy-loop)


# --------------------------------------------------------------------------- #
# WR-01 Gap 2: rc==124 (timeout / stalled egress) gets the timeout/egress
# remediation and returns 124 — NOT exit 77. No sleep/poll.
# --------------------------------------------------------------------------- #
def test_timeout_rc124_reports_egress_not_ui_gate(seeded_workspace, monkeypatch, capsys):
    dd = _dd()
    _set_credentials(seeded_workspace, "VALIDATED")
    monkeypatch.setattr(gw, "preflight_entered", lambda slug: None)

    slept = {"n": 0}
    monkeypatch.setattr(time, "sleep", lambda *a, **k: slept.__setitem__("n", slept["n"] + 1))

    monkeypatch.setattr(gw, "run_kaggle", lambda *a, **k: (124, "kaggle timed out"))

    def boom_dump(*a, **k):
        raise AssertionError("124 must not be quarantined/echoed via dump_last_error")

    def boom_classify(*a, **k):
        raise AssertionError("124 must not hit the UI-gate classify_gate branch")

    monkeypatch.setattr(gw, "dump_last_error", boom_dump)
    monkeypatch.setattr(gw, "classify_gate", boom_classify)

    rc = dd.main(["--workspace", str(seeded_workspace)])
    cap = capsys.readouterr()
    combined = (cap.out + cap.err).lower()

    assert rc == 124
    assert rc != gw.UI_GATE
    assert "timed out" in combined
    assert "egress" in combined
    assert RULES_URL not in (cap.out + cap.err)
    assert "accept the rules" not in combined
    assert "[ui_gate]" not in combined
    assert slept["n"] == 0


# --------------------------------------------------------------------------- #
# Phase 1 D-07: download refuses unless credentials == VALIDATED, BEFORE any probe.
# --------------------------------------------------------------------------- #
def test_refuses_without_validated_credentials(seeded_workspace, monkeypatch, capsys):
    dd = _dd()
    # seeded_workspace ships credentials == UNVALIDATED (unchanged).
    called = {"preflight": 0}
    monkeypatch.setattr(
        gw, "preflight_entered",
        lambda slug: called.__setitem__("preflight", called["preflight"] + 1),
    )

    rc = dd.main(["--workspace", str(seeded_workspace)])
    cap = capsys.readouterr()

    assert rc == 1                          # refused, not a UI gate
    assert rc != gw.UI_GATE
    assert called["preflight"] == 0         # credential gate short-circuits before any probe
    assert "VALIDATED" in (cap.out + cap.err)


# --------------------------------------------------------------------------- #
# Fail-clear (WR-02): a corrupt state.json is not silently rewritten; no probe.
# --------------------------------------------------------------------------- #
def test_malformed_state_fails_clear(seeded_workspace, monkeypatch):
    dd = _dd()
    (seeded_workspace / "control" / "state.json").write_text("{ not valid json")
    called = {"preflight": 0}
    monkeypatch.setattr(
        gw, "preflight_entered",
        lambda slug: called.__setitem__("preflight", called["preflight"] + 1),
    )

    rc = dd.main(["--workspace", str(seeded_workspace)])

    assert rc == 1
    assert called["preflight"] == 0
