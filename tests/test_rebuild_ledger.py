"""rebuild_ledger full-rebuild semantics (MEM-01 / D-10), plan 03-02 Task 2.

``ledger.jsonl`` is a PURE FUNCTION of the ``experiments/*/meta.json`` folders, so a
hand-corrupted ledger self-heals on a rebuild. This suite pins:

  * two synthetic meta folders → a two-line, exp_id-sorted ledger, each line ==
    ``to_ledger_row(meta)`` (RESEARCH §rebuild_ledger lines 501-504);
  * delete-then-rebuild is byte-identical (idempotent pure function);
  * a corrupt meta.json (invalid JSON) is SKIPPED with a stderr warning naming the
    folder; the other rows survive; exit 0 (T-03-02-02 — never fabricate a row);
  * a meta failing ``validate_meta`` (missing provenance) is likewise skipped;
  * no ``.tmp`` file is left behind and the live ledger is never partial-written
    (atomic ``os.replace``);
  * an empty ``experiments/`` yields a 0-row ledger, exit 0.

Scripts are exercised as SUBPROCESSES via ``run_script`` (the documented
``--workspace`` contract) so collection never crashes while the module is absent
(RED). GREEN: Task 2.
"""

from __future__ import annotations

import json


# --------------------------------------------------------------------------- #
# Fixtures / helpers.
# --------------------------------------------------------------------------- #
def _meta(exp_id, *, status="SUCCESS", cv_mean=0.5, seed=42, commit="abc1234"):
    """A well-formed canonical meta.json dict (validate_meta → [])."""
    return {
        "schema_version": 1,
        "exp_id": exp_id,
        "created": "2026-07-11T14:22:07Z",
        "idea": f"idea for {exp_id}",
        "hypothesis": "h",
        "status": status,
        "failure_reason": None,
        "metric": "roc_auc",
        "greater_is_better": True,
        "cv_scheme": "StratifiedKFold",
        "n_folds": 5,
        "fold_scores": [0.5, 0.5, 0.5, 0.5, 0.5],
        "cv_mean": cv_mean,
        "cv_std": 0.0,
        "provenance": {
            "run_id": "r-" + exp_id,
            "artifact_hash": "sha256:deadbeef",
            "git_commit": commit,
            "git_dirty": False,
            "seed": seed,
        },
        "result_path": f"experiments/{exp_id}/result.json",
        "verdict_path": f"experiments/{exp_id}/VERDICT.md",
        "artifacts": [],
    }


def _write_meta(ws, exp_id, meta_obj):
    exp_dir = ws / "experiments" / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "meta.json").write_text(json.dumps(meta_obj, indent=2))


def _seed_control(ws):
    (ws / "control").mkdir(parents=True, exist_ok=True)


def _ledger_lines(ws):
    text = (ws / "control" / "ledger.jsonl").read_text()
    return [ln for ln in text.splitlines() if ln.strip()]


def _to_row(meta):
    import experiment_meta

    return experiment_meta.to_ledger_row(meta)


# --------------------------------------------------------------------------- #
# Happy path: full rebuild from folders.
# --------------------------------------------------------------------------- #
def test_two_folders_produce_two_sorted_rows(run_script, tmp_workspace):
    ws = tmp_workspace
    _seed_control(ws)
    # Write out-of-order to prove sorting by exp_id.
    m2 = _meta("exp-002", cv_mean=0.7)
    m1 = _meta("exp-001", cv_mean=0.6)
    _write_meta(ws, "exp-002", m2)
    _write_meta(ws, "exp-001", m1)

    proc = run_script("rebuild_ledger.py", "--workspace", ws, cwd=ws)
    assert proc.returncode == 0, proc.stderr

    lines = _ledger_lines(ws)
    assert len(lines) == 2
    rows = [json.loads(ln) for ln in lines]
    assert rows[0] == _to_row(m1)
    assert rows[1] == _to_row(m2)
    assert [r["exp_id"] for r in rows] == ["exp-001", "exp-002"]


def test_delete_then_rebuild_is_byte_identical(run_script, tmp_workspace):
    ws = tmp_workspace
    _seed_control(ws)
    _write_meta(ws, "exp-001", _meta("exp-001", cv_mean=0.6))
    _write_meta(ws, "exp-002", _meta("exp-002", cv_mean=0.7))

    assert run_script("rebuild_ledger.py", "--workspace", ws, cwd=ws).returncode == 0
    first = (ws / "control" / "ledger.jsonl").read_bytes()

    (ws / "control" / "ledger.jsonl").unlink()
    assert run_script("rebuild_ledger.py", "--workspace", ws, cwd=ws).returncode == 0
    second = (ws / "control" / "ledger.jsonl").read_bytes()

    assert first == second


def test_empty_experiments_yields_zero_row_ledger(run_script, tmp_workspace):
    ws = tmp_workspace
    _seed_control(ws)
    (ws / "experiments").mkdir(parents=True, exist_ok=True)

    proc = run_script("rebuild_ledger.py", "--workspace", ws, cwd=ws)
    assert proc.returncode == 0, proc.stderr
    assert _ledger_lines(ws) == []


# --------------------------------------------------------------------------- #
# Corrupt / invalid metas: skip-and-warn, never fabricate (T-03-02-02).
# --------------------------------------------------------------------------- #
def test_corrupt_meta_is_skipped_with_named_warning(run_script, tmp_workspace):
    ws = tmp_workspace
    _seed_control(ws)
    _write_meta(ws, "exp-001", _meta("exp-001", cv_mean=0.6))
    _write_meta(ws, "exp-002", _meta("exp-002", cv_mean=0.7))
    # exp-003 has invalid JSON.
    bad = ws / "experiments" / "exp-003"
    bad.mkdir(parents=True, exist_ok=True)
    (bad / "meta.json").write_text("{ this is not json ")

    proc = run_script("rebuild_ledger.py", "--workspace", ws, cwd=ws)
    assert proc.returncode == 0, proc.stderr
    assert "exp-003" in proc.stderr

    ids = [json.loads(ln)["exp_id"] for ln in _ledger_lines(ws)]
    assert ids == ["exp-001", "exp-002"]
    assert "exp-003" not in ids


def test_meta_failing_validation_is_skipped_with_warning(run_script, tmp_workspace):
    ws = tmp_workspace
    _seed_control(ws)
    _write_meta(ws, "exp-001", _meta("exp-001", cv_mean=0.6))
    # exp-002 is valid JSON but missing provenance → validate_meta fails.
    invalid = _meta("exp-002", cv_mean=0.7)
    del invalid["provenance"]
    _write_meta(ws, "exp-002", invalid)

    proc = run_script("rebuild_ledger.py", "--workspace", ws, cwd=ws)
    assert proc.returncode == 0, proc.stderr
    assert "exp-002" in proc.stderr

    ids = [json.loads(ln)["exp_id"] for ln in _ledger_lines(ws)]
    assert ids == ["exp-001"]


# --------------------------------------------------------------------------- #
# Atomicity: no .tmp residue, no partial live-file.
# --------------------------------------------------------------------------- #
def test_rebuild_leaves_no_tmp_file(run_script, tmp_workspace):
    ws = tmp_workspace
    _seed_control(ws)
    _write_meta(ws, "exp-001", _meta("exp-001", cv_mean=0.6))

    assert run_script("rebuild_ledger.py", "--workspace", ws, cwd=ws).returncode == 0
    residue = list((ws / "control").glob("ledger.jsonl*.tmp")) + list(
        (ws / "control").glob("*.tmp")
    )
    assert residue == []
