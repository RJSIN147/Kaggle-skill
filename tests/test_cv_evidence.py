"""CV-evidence + analyze behavior (COMP-01 / D-05 / D-06 / D-07 / D-09).

Pins, for plan 02-04:

  * ``recommend_cv`` decision order group > temporal > stratified > plain (imported
    directly), and the fixture-driven decision table (grouped→GroupKFold,
    temporal→TimeSeriesSplit, imbalanced→StratifiedKFold) via ``cv_evidence.py``;
  * the mechanical target derivation (``columns(train) − columns(test) − id``, D-07)
    recorded in ``control/raw/cv-evidence.json``;
  * ``analyze_data.py`` lands a NON-null ``cv.scheme`` enum starting from the
    reserved-null config (proves ``set_config_field``, not the no-op merge) AND
    writes the scheme name + a non-empty rationale into ``competition.md``'s
    ``## Cross-validation scheme`` section (D-05's two-part deliverable);
  * D-09 independence: with ``competition.md`` absent/stub (no capture), analyze
    still writes ``cv.scheme`` + evidence, flags the missing capture, exits 0;
  * the train/test unresolved degrade (exit 0 + ``SKIPPED (could not resolve …)``)
    and the ML-absent AV degrade (exit 0 + ``adversarial validation: SKIPPED``).

Scripts are exercised as subprocesses (``run_script``) or imported INSIDE a test
(``_mod``) so collection never crashes while the modules are absent (RED). These
tests pass with NO pandas / NO scikit-learn installed (D-06): the AV path degrades
to SKIPPED rather than importing an ML stack in the test process. GREEN: Tasks 2-3.
"""

from __future__ import annotations

import importlib
import json

from cv_fixtures import build_pair


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def _recommend_cv():
    """Import cv_evidence.recommend_cv (absent at RED → ModuleNotFoundError)."""
    return importlib.import_module("cv_evidence").recommend_cv


def _read_evidence(ws):
    return json.loads((ws / "control" / "raw" / "cv-evidence.json").read_text())


def _read_cfg(ws):
    return json.loads((ws / "control" / "config.json").read_text())


# --------------------------------------------------------------------------- #
# recommend_cv — decision order, imported directly (D-05 / RESEARCH §Code Examples).
# --------------------------------------------------------------------------- #
def test_recommend_cv_decision_order():
    recommend_cv = _recommend_cv()

    assert recommend_cv({"group_candidates": ["group_id"]}) == "GroupKFold"
    assert (
        recommend_cv(
            {
                "group_candidates": [],
                "datetime_columns": ["date"],
                "datetime_train_precedes_test": True,
            }
        )
        == "TimeSeriesSplit"
    )
    assert (
        recommend_cv(
            {"group_candidates": [], "datetime_columns": [],
             "class_balance": {"is_classification": True}}
        )
        == "StratifiedKFold"
    )
    assert (
        recommend_cv(
            {"group_candidates": [], "datetime_columns": [],
             "class_balance": {"is_classification": False}}
        )
        == "KFold"
    )


def test_recommend_cv_priority_group_beats_temporal_beats_stratified():
    recommend_cv = _recommend_cv()
    # All signals present at once → group wins.
    ev = {
        "group_candidates": ["group_id"],
        "datetime_columns": ["date"],
        "datetime_train_precedes_test": True,
        "class_balance": {"is_classification": True},
    }
    assert recommend_cv(ev) == "GroupKFold"
    # Drop the group → temporal wins over stratified.
    ev["group_candidates"] = []
    assert recommend_cv(ev) == "TimeSeriesSplit"


# --------------------------------------------------------------------------- #
# cv_evidence.py — fixture-driven decision table + target derivation.
# --------------------------------------------------------------------------- #
def test_grouped_pair_recommends_groupkfold(seeded_workspace, run_script):
    ws = seeded_workspace
    meta = build_pair(ws / "data", "grouped")

    r = run_script("cv_evidence.py", "--workspace", ws, cwd=ws)
    assert r.returncode == 0, r.stderr

    ev = _read_evidence(ws)
    assert ev["recommend"] == "GroupKFold"
    assert meta["group_col"] in ev["group_candidates"]
    assert ev["target"]["column"] == "target"


def test_temporal_pair_recommends_timeseries(seeded_workspace, run_script):
    ws = seeded_workspace
    meta = build_pair(ws / "data", "temporal")

    r = run_script("cv_evidence.py", "--workspace", ws, cwd=ws)
    assert r.returncode == 0, r.stderr

    ev = _read_evidence(ws)
    assert ev["recommend"] == "TimeSeriesSplit"
    assert meta["datetime_col"] in ev["datetime_columns"]


def test_imbalanced_pair_recommends_stratified(seeded_workspace, run_script):
    ws = seeded_workspace
    build_pair(ws / "data", "imbalanced")

    r = run_script("cv_evidence.py", "--workspace", ws, cwd=ws)
    assert r.returncode == 0, r.stderr

    ev = _read_evidence(ws)
    assert ev["recommend"] == "StratifiedKFold"
    assert ev["class_balance"]["is_classification"] is True
    assert ev["class_balance"]["imbalanced"] is True


def test_target_derivation_is_recorded(seeded_workspace, run_script):
    ws = seeded_workspace
    build_pair(ws / "data", "grouped")

    run_script("cv_evidence.py", "--workspace", ws, cwd=ws)

    ev = _read_evidence(ws)
    tgt = ev["target"]
    assert tgt["column"] == "target"
    assert tgt["id_column"] == "id"
    # The auditable derivation: columns(train) − columns(test) − id (D-07).
    assert "columns(train)" in tgt["derivation"]


def test_cv_evidence_does_not_write_cv_scheme(seeded_workspace, run_script):
    """cv_evidence emits evidence only; it never commits config.json cv.scheme."""
    ws = seeded_workspace
    build_pair(ws / "data", "grouped")
    assert _read_cfg(ws)["cv"]["scheme"] is None

    run_script("cv_evidence.py", "--workspace", ws, cwd=ws)

    # cv_evidence is read-only w.r.t. config.json cv.scheme (that is analyze's job).
    assert _read_cfg(ws)["cv"]["scheme"] is None


def test_unresolved_pair_degrades_to_skipped(seeded_workspace, run_script):
    """data/ lacking train.csv/test.csv → exit 0 + a SKIPPED record, never a crash."""
    ws = seeded_workspace
    (ws / "data").mkdir(parents=True, exist_ok=True)
    (ws / "data" / "something_else.csv").write_text("a,b\n1,2\n")

    r = run_script("cv_evidence.py", "--workspace", ws, cwd=ws)
    assert r.returncode == 0, r.stderr

    ev = _read_evidence(ws)
    assert ev["status"] == "SKIPPED"
    assert "could not resolve" in ev["reason"].lower()


# --------------------------------------------------------------------------- #
# analyze_data.py — set_config_field cv.scheme + competition.md rationale (D-05).
# --------------------------------------------------------------------------- #
def test_analyze_lands_nonnull_cv_scheme_and_rationale(seeded_workspace, run_script):
    ws = seeded_workspace
    build_pair(ws / "data", "grouped")
    # Precondition: cv.scheme present AND null (the write_control_json merge-skip trap).
    assert _read_cfg(ws)["cv"]["scheme"] is None

    r = run_script("analyze_data.py", "--workspace", ws, cwd=ws)
    assert r.returncode == 0, r.stderr

    # NON-null enum LANDED → proves set_config_field, not the add-missing-only merge.
    assert _read_cfg(ws)["cv"]["scheme"] == "GroupKFold"

    md = (ws / "competition.md").read_text()
    # The ## Cross-validation scheme section holds the scheme name + a rationale,
    # and no longer the template default.
    cv_section = md.split("## Cross-validation scheme", 1)[1].split("\n## ", 1)[0]
    assert "GroupKFold" in cv_section
    assert "_TODO (Phase 2)_" not in cv_section
    assert len(cv_section.strip()) > len("GroupKFold") + 5  # a non-empty rationale too


def test_analyze_cv_scheme_flag_overrides_recommendation(seeded_workspace, run_script):
    """The AI's committed value (--cv-scheme) is written; mechanical is only the default."""
    ws = seeded_workspace
    build_pair(ws / "data", "grouped")  # mechanical would be GroupKFold

    r = run_script(
        "analyze_data.py", "--workspace", ws, "--cv-scheme", "KFold", cwd=ws
    )
    assert r.returncode == 0, r.stderr
    assert _read_cfg(ws)["cv"]["scheme"] == "KFold"


def test_analyze_rejects_bogus_cv_scheme(seeded_workspace, run_script):
    """A non-enum --cv-scheme is rejected by argparse choices BEFORE any write."""
    ws = seeded_workspace
    build_pair(ws / "data", "grouped")

    r = run_script(
        "analyze_data.py", "--workspace", ws, "--cv-scheme", "BogusFold", cwd=ws
    )
    assert r.returncode != 0
    assert _read_cfg(ws)["cv"]["scheme"] is None  # unchanged on a bad value


def test_analyze_independent_of_capture(seeded_workspace, run_script):
    """D-09: competition.md absent/stub (no capture) → still writes cv.scheme + evidence,
    flags the missing capture, exits 0 (flag-don't-abort)."""
    ws = seeded_workspace
    build_pair(ws / "data", "temporal")
    assert not (ws / "competition.md").exists()  # capture never ran

    r = run_script("analyze_data.py", "--workspace", ws, cwd=ws)
    assert r.returncode == 0, r.stderr

    # cv.scheme + evidence still land despite no capture.
    assert _read_cfg(ws)["cv"]["scheme"] == "TimeSeriesSplit"
    assert (ws / "control" / "raw" / "cv-evidence.json").exists()
    # The missing capture is FLAGGED (not silently ignored, not aborted).
    combined = (r.stdout + r.stderr).lower()
    assert "not yet captured" in combined


def test_analyze_av_skipped_without_ml_env(seeded_workspace, run_script):
    """D-06: with the workspace ML env absent, analyze exits 0 and records AV SKIPPED
    (never runtime pip-installs)."""
    ws = seeded_workspace
    build_pair(ws / "data", "imbalanced")

    r = run_script("analyze_data.py", "--workspace", ws, cwd=ws)
    assert r.returncode == 0, r.stderr

    md = (ws / "competition.md").read_text()
    assert "adversarial validation: SKIPPED" in md


def test_analyze_unresolved_pair_does_not_fabricate_scheme(seeded_workspace, run_script):
    """If the train/test pair is unresolved, analyze records CV scheme SKIPPED and
    does NOT fabricate a scheme (exit 0)."""
    ws = seeded_workspace
    (ws / "data").mkdir(parents=True, exist_ok=True)
    (ws / "data" / "arbitrary.csv").write_text("a,b\n1,2\n")

    r = run_script("analyze_data.py", "--workspace", ws, cwd=ws)
    assert r.returncode == 0, r.stderr

    # No scheme fabricated onto the reserved-null key.
    assert _read_cfg(ws)["cv"]["scheme"] is None
    md = (ws / "competition.md").read_text()
    cv_section = md.split("## Cross-validation scheme", 1)[1].split("\n## ", 1)[0]
    assert "SKIPPED" in cv_section
