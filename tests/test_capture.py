"""capture_competition.py behavior (COMP-01) + the config-write BLOCKER regression.

Covers:
  * capture populates ``competition.md`` (Evaluation-metric section + Rules section
    rendering the provenance-tagged daily limit) via the shared section-safe-merge;
  * the competition.type SIGNALS + a mechanical recommendation are recorded under
    ``control/raw/`` (D-14 tooling-emits-signals step);
  * BLOCKER regression: starting from a config where ``competition.type`` /
    ``submission.daily_limit`` already exist as ``null`` (the exact shape
    ``write_control_json`` cannot fill), ``--set-competition-type code`` LANDS a
    non-null ``"code"`` and full capture LANDS the non-null ``10`` — proving the
    direct ``set_config_field`` setter, not the add-missing-only deep merge;
  * a bogus ``--set-competition-type xyz`` is rejected by argparse ``choices``;
  * re-running capture is idempotent at section granularity (a hand edit survives).

In-process tests mock the gateway (``cap.run_kaggle``); the setter / argparse-reject
tests run as subprocesses (no gateway needed). GREEN target: Task 3.
"""

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

_FILES_JSON = json.dumps(
    [
        {"name": "train.csv", "size": 61194, "creationDate": "2019-12-11T02:17:10Z"},
        {"name": "test.csv", "size": 28629, "creationDate": "2019-12-11T02:17:10Z"},
        {"name": "gender_submission.csv", "size": 3258, "creationDate": "2019-12-11T02:17:10Z"},
    ]
)


def _cap():
    import capture_competition  # noqa: PLC0415 — deferred import (RED-safe)

    return capture_competition


def _read_cfg(ws):
    return json.loads((ws / "control" / "config.json").read_text())


def _mock_gateway(monkeypatch, cap):
    pages = (FIXTURES / "pages_all.json").read_text()

    def _fake(*argv, timeout=60):
        if "pages" in argv:
            return 0, pages
        if "files" in argv:
            return 0, _FILES_JSON
        return 1, "unexpected"

    monkeypatch.setattr(cap, "run_kaggle", _fake)


# --------------------------------------------------------------------------- #
# capture populates competition.md via the section-safe-merge.
# --------------------------------------------------------------------------- #
def test_capture_populates_competition_md(seeded_workspace, monkeypatch):
    cap = _cap()
    ws = seeded_workspace
    _mock_gateway(monkeypatch, cap)

    rc = cap.main(["--workspace", str(ws)])
    assert rc == 0

    md = (ws / "competition.md").read_text()
    assert "## Evaluation metric" in md
    # The Rules section renders the provenance-tagged daily limit.
    assert "10/day" in md
    assert "extracted" in md
    # Verbatim Kaggle prose kept in the doc is fenced with source attribution.
    assert "<untrusted-content" in md

    cfg = _read_cfg(ws)
    assert cfg["submission"]["daily_limit"] == 10
    assert cfg["submission"]["limit_provenance"] == "extracted"


def test_capture_records_type_signals(seeded_workspace, monkeypatch):
    """D-14: the type signals + a mechanical recommendation land under control/raw/."""
    cap = _cap()
    ws = seeded_workspace
    _mock_gateway(monkeypatch, cap)

    cap.main(["--workspace", str(ws)])

    raw_dir = ws / "control" / "raw"
    # Raw provenance payload (tracked, D-03) is written.
    assert (raw_dir / "competition-pages.json").exists()
    # Type signals + recommendation recorded for the AI to reason over.
    sig_files = list(raw_dir.glob("*type*"))
    assert sig_files, "expected a competition-type signals/recommendation file"
    signals = json.loads(sig_files[0].read_text())
    assert "recommendation" in signals


# --------------------------------------------------------------------------- #
# BLOCKER regression — a NON-null value LANDS on a key-exists-as-null config.
# --------------------------------------------------------------------------- #
def test_set_competition_type_lands_nonnull(seeded_workspace, run_script):
    """--set-competition-type code overwrites the reserved-null key (direct setter)."""
    ws = seeded_workspace
    # Precondition: competition.type is present AND null (the merge-skip trap).
    assert _read_cfg(ws)["competition"]["type"] is None

    r = run_script(
        "capture_competition.py", "--workspace", ws, "--set-competition-type", "code", cwd=ws
    )
    assert r.returncode == 0, r.stderr
    assert _read_cfg(ws)["competition"]["type"] == "code"  # non-null LANDED


def test_bogus_competition_type_rejected(seeded_workspace, run_script):
    """A non-enum type is rejected by argparse choices BEFORE any write."""
    ws = seeded_workspace
    r = run_script(
        "capture_competition.py", "--workspace", ws, "--set-competition-type", "xyz", cwd=ws
    )
    assert r.returncode != 0
    assert _read_cfg(ws)["competition"]["type"] is None  # unchanged on bad value


# --------------------------------------------------------------------------- #
# Idempotent at SECTION granularity — a curated / hand edit survives a re-run.
# --------------------------------------------------------------------------- #
def test_capture_idempotent_preserves_edits(seeded_workspace, monkeypatch):
    cap = _cap()
    ws = seeded_workspace
    _mock_gateway(monkeypatch, cap)

    cap.main(["--workspace", str(ws)])
    md_path = ws / "competition.md"

    # A human curates the Evaluation-metric section.
    original = md_path.read_text()
    edited = original.replace(
        "## Evaluation metric",
        "## Evaluation metric\n\nHAND_EDITED: accuracy, per the rules.",
        1,
    )
    md_path.write_text(edited)

    # Re-run capture; the curated line must survive (section no longer _TODO).
    cap.main(["--workspace", str(ws)])
    assert "HAND_EDITED: accuracy, per the rules." in md_path.read_text()
