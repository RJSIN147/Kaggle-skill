"""regen_strategy full-overwrite semantics (MEM-02/03, D-11/D-12/D-13), plan 03-05 Task 1.

``strategy.md`` is a PURE FUNCTION of ``control/ledger.jsonl`` (the FACTS) plus an
AI-authored ``--reasoning-file`` fragment (the REASONING). Unlike ``competition.md``'s
section-safe-merge, it is FULLY OVERWRITTEN atomically each cycle (D-12) so a stale hand
edit can never survive and misrepresent the ledger. This suite pins:

  * FACTS are tooling-rendered from the ledger: current-best is picked by the metric's
    direction (``max(cv_mean)`` if ``greater_is_better`` else ``min``) among SUCCESS rows,
    NOT taken from the reasoning file (T-03-05-01 / T-03-05-04);
  * an empty ledger renders "None yet." and an empty tried-list, exit 0;
  * the ``--reasoning-file`` markdown appears VERBATIM in the output (AI owns reasoning);
  * a pre-existing hand-edited ``strategy.md`` is fully clobbered (D-12 non-preservation)
    and the verbatim generated-each-cycle header is present;
  * the overwrite is atomic — no leftover ``.tmp`` residue;
  * a missing ``--reasoning-file`` blocks with a clear non-zero error (mechanical sections
    stay tooling-owned — the tool never authors reasoning);
  * the script does NOT use ``replace_section`` (full overwrite, not a merge).

Scripts are exercised as SUBPROCESSES via ``run_script`` (the documented ``--workspace``
contract) so collection never crashes while the module is absent (RED). GREEN: Task 1.
"""

from __future__ import annotations

import json
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

HEADER = "Generated each cycle from control/ledger.jsonl — manual edits are overwritten."


# --------------------------------------------------------------------------- #
# Fixtures / helpers.
# --------------------------------------------------------------------------- #
def _row(exp_id, *, status="SUCCESS", idea=None, cv_mean=0.5, cv_std=0.0,
         metric="roc_auc", greater_is_better=True):
    """A derived ledger.jsonl row (the 11-key subset experiment_meta emits)."""
    return {
        "exp_id": exp_id,
        "status": status,
        "idea": idea or f"idea for {exp_id}",
        "metric": metric,
        "greater_is_better": greater_is_better,
        "cv_mean": cv_mean,
        "cv_std": cv_std,
        "git_commit": "abc1234",
        "seed": 42,
        "created": "2026-07-11T14:22:07Z",
        "verdict_path": f"experiments/{exp_id}/VERDICT.md",
    }


def _seed(ws, *, rows=None, greater_is_better=True, slug="titanic"):
    """Seed a workspace control-plane: config.json (metric) + ledger.jsonl."""
    ctrl = ws / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    (ctrl / "config.json").write_text(
        json.dumps(
            {
                "workspace_version": 1,
                "competition_slug": slug,
                "execution_target": "local",
                "cv": {"scheme": "StratifiedKFold"},
                "metric": {"name": "roc_auc", "greater_is_better": greater_is_better},
                "created": "2026-01-01T00:00:00Z",
            }
        )
    )
    rows = rows or []
    text = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n") if rows else ""
    (ctrl / "ledger.jsonl").write_text(text)


def _write_reasoning(ws, body):
    p = ws / "reasoning.md"
    p.write_text(body)
    return p


def _strategy_text(ws):
    return (ws / "strategy.md").read_text()


# --------------------------------------------------------------------------- #
# FACTS: current-best is tooling-rendered by the metric's direction.
# --------------------------------------------------------------------------- #
def test_current_best_picks_max_when_greater_is_better(run_script, tmp_workspace):
    ws = tmp_workspace
    _seed(
        ws,
        rows=[
            _row("exp-001", idea="low score", cv_mean=0.60),
            _row("exp-002", idea="high score", cv_mean=0.80),
        ],
        greater_is_better=True,
    )
    reasoning = _write_reasoning(ws, "## Hypothesis queue\n1. try more features.")

    proc = run_script("regen_strategy.py", "--workspace", ws,
                      "--reasoning-file", reasoning, cwd=ws)
    assert proc.returncode == 0, proc.stderr

    out = _strategy_text(ws)
    cb = out.split("## Current best", 1)[1].split("##", 1)[0]
    # The higher-cv_mean experiment is the current best.
    assert "exp-002" in cb
    assert "exp-001" not in cb


def test_current_best_picks_min_when_lower_is_better(run_script, tmp_workspace):
    ws = tmp_workspace
    _seed(
        ws,
        rows=[
            _row("exp-001", idea="high error", cv_mean=0.60, greater_is_better=False),
            _row("exp-002", idea="low error", cv_mean=0.20, greater_is_better=False),
        ],
        greater_is_better=False,
    )
    reasoning = _write_reasoning(ws, "## Hypothesis queue\n1. regularize.")

    proc = run_script("regen_strategy.py", "--workspace", ws,
                      "--reasoning-file", reasoning, cwd=ws)
    assert proc.returncode == 0, proc.stderr

    out = _strategy_text(ws)
    # Lower cv_mean is best when lower_is_better; it must be the one named in Current best.
    cb = out.split("## Current best", 1)[1].split("##", 1)[0]
    assert "exp-002" in cb
    assert "exp-001" not in cb


def test_failed_rows_never_win_current_best(run_script, tmp_workspace):
    ws = tmp_workspace
    _seed(
        ws,
        rows=[
            _row("exp-001", status="FAILED", cv_mean=None, cv_std=None),
            _row("exp-002", idea="the only success", cv_mean=0.70),
        ],
        greater_is_better=True,
    )
    reasoning = _write_reasoning(ws, "next.")
    proc = run_script("regen_strategy.py", "--workspace", ws,
                      "--reasoning-file", reasoning, cwd=ws)
    assert proc.returncode == 0, proc.stderr
    cb = _strategy_text(ws).split("## Current best", 1)[1].split("##", 1)[0]
    assert "exp-002" in cb
    assert "exp-001" not in cb


# --------------------------------------------------------------------------- #
# Empty ledger → "None yet." + empty tried-list.
# --------------------------------------------------------------------------- #
def test_empty_ledger_renders_none_yet(run_script, tmp_workspace):
    ws = tmp_workspace
    _seed(ws, rows=[])
    reasoning = _write_reasoning(ws, "## Hypothesis queue\n1. baseline LightGBM.")

    proc = run_script("regen_strategy.py", "--workspace", ws,
                      "--reasoning-file", reasoning, cwd=ws)
    assert proc.returncode == 0, proc.stderr

    out = _strategy_text(ws)
    assert "None yet." in out
    assert HEADER in out
    # No exp rows anywhere in the tried-list.
    assert "exp-0" not in out


# --------------------------------------------------------------------------- #
# REASONING: verbatim splice; facts are NOT sourced from the reasoning file.
# --------------------------------------------------------------------------- #
def test_reasoning_file_appears_verbatim(run_script, tmp_workspace):
    ws = tmp_workspace
    _seed(ws, rows=[_row("exp-001", cv_mean=0.70)])
    fragment = (
        "## Hypothesis queue\n"
        "1. Add target encoding for high-cardinality categoricals.\n"
        "2. Try a CatBoost second model.\n\n"
        "## Next action\n"
        "Run exp-002 with the target-encoding idea.\n"
    )
    reasoning = _write_reasoning(ws, fragment)

    proc = run_script("regen_strategy.py", "--workspace", ws,
                      "--reasoning-file", reasoning, cwd=ws)
    assert proc.returncode == 0, proc.stderr
    assert fragment.strip() in _strategy_text(ws)


def test_current_best_number_not_from_reasoning_file(run_script, tmp_workspace):
    ws = tmp_workspace
    # Ledger says the best is 0.70; the reasoning file lies with a fake 0.99.
    _seed(ws, rows=[_row("exp-001", idea="real", cv_mean=0.70)], greater_is_better=True)
    reasoning = _write_reasoning(ws, "Current best is 0.99 (a lie the AI typed).")

    proc = run_script("regen_strategy.py", "--workspace", ws,
                      "--reasoning-file", reasoning, cwd=ws)
    assert proc.returncode == 0, proc.stderr

    cb = _strategy_text(ws).split("## Current best", 1)[1].split("##", 1)[0]
    # The FACT section names the real ledger number, never the fabricated one.
    assert "0.7" in cb
    assert "0.99" not in cb


# --------------------------------------------------------------------------- #
# D-12: full overwrite clobbers a hand edit; header present.
# --------------------------------------------------------------------------- #
def test_hand_edited_strategy_is_fully_replaced(run_script, tmp_workspace):
    ws = tmp_workspace
    _seed(ws, rows=[_row("exp-001", cv_mean=0.70)])
    (ws / "strategy.md").write_text("MY PRECIOUS HAND EDIT that must not survive.\n")
    reasoning = _write_reasoning(ws, "## Hypothesis queue\n1. next.")

    proc = run_script("regen_strategy.py", "--workspace", ws,
                      "--reasoning-file", reasoning, cwd=ws)
    assert proc.returncode == 0, proc.stderr

    out = _strategy_text(ws)
    assert "MY PRECIOUS HAND EDIT" not in out  # clobbered (D-12)
    assert HEADER in out


# --------------------------------------------------------------------------- #
# Atomicity: no .tmp residue.
# --------------------------------------------------------------------------- #
def test_regen_leaves_no_tmp_file(run_script, tmp_workspace):
    ws = tmp_workspace
    _seed(ws, rows=[_row("exp-001", cv_mean=0.70)])
    reasoning = _write_reasoning(ws, "next.")

    assert run_script("regen_strategy.py", "--workspace", ws,
                      "--reasoning-file", reasoning, cwd=ws).returncode == 0
    residue = list(ws.glob("strategy.md*.tmp")) + list(ws.glob("*.tmp"))
    assert residue == []


# --------------------------------------------------------------------------- #
# --reasoning-file is required (block, don't author reasoning).
# --------------------------------------------------------------------------- #
def test_missing_reasoning_file_blocks(run_script, tmp_workspace):
    ws = tmp_workspace
    _seed(ws, rows=[_row("exp-001", cv_mean=0.70)])

    proc = run_script("regen_strategy.py", "--workspace", ws,
                      "--reasoning-file", ws / "does-not-exist.md", cwd=ws)
    assert proc.returncode != 0
    assert "reasoning" in (proc.stderr + proc.stdout).lower()
    # Nothing was written on the block.
    assert not (ws / "strategy.md").exists()


# --------------------------------------------------------------------------- #
# WR-02: a corrupt / non-object ledger line is skipped, not fatal.
# --------------------------------------------------------------------------- #
def test_corrupt_ledger_line_is_skipped_not_fatal(run_script, tmp_workspace):
    """WR-02: a truncated final line (from an interrupted write) or a non-object line must
    NOT abort regen with a JSONDecodeError/AttributeError traceback. The good rows still
    render; the bad lines are skipped-and-warned."""
    ws = tmp_workspace
    _seed(ws, rows=[_row("exp-001", idea="the good row", cv_mean=0.70)])
    # Append a scalar line and a truncated (unparseable) final line after the valid row.
    ledger = ws / "control" / "ledger.jsonl"
    ledger.write_text(ledger.read_text() + "5\n" + '{"exp_id":"exp-002","cv_mean":0.9')
    reasoning = _write_reasoning(ws, "## Hypothesis queue\n1. next.")

    proc = run_script("regen_strategy.py", "--workspace", ws,
                      "--reasoning-file", reasoning, cwd=ws)
    assert proc.returncode == 0, proc.stderr
    out = _strategy_text(ws)
    # The valid row still drives the facts; the truncated exp-002 never lands.
    cb = out.split("## Current best", 1)[1].split("##", 1)[0]
    assert "exp-001" in cb
    assert "exp-002" not in out


# --------------------------------------------------------------------------- #
# D-12: full overwrite, NOT a section-safe-merge.
# --------------------------------------------------------------------------- #
def test_script_does_not_use_replace_section():
    src = (SCRIPTS_DIR / "regen_strategy.py").read_text()
    assert "replace_section" not in src
    assert "os.replace" in src
