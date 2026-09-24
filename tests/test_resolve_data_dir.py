"""test_resolve_data_dir.py — the D-03 backend-agnostic data path + kernel-portability.

These tests are STDLIB-ONLY on purpose (no numpy/sklearn import) so they stay GREEN in
the default offline suite even when the ML env is not synced. ``resolve_data_dir`` lives
in ``scripts/templates/experiment.py.tmpl`` and uses only ``pathlib``/``os``; the heavy
ML imports in the same template are LAZY (inside ``run_cv``/``_make_splitter``), so the
rendered module imports cleanly here for the resolver + static portability checks.

The leakage-safe ``run_cv`` behaviour is covered separately in ``test_run_cv.py`` (which
skips cleanly when sklearn is absent).
"""

import importlib.util
import sys
import types
from pathlib import Path
from string import Template

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = REPO_ROOT / "scripts" / "templates" / "experiment.py.tmpl"


def render_experiment(tmp_path, *, slug="titanic", exp_id="exp-001",
                      cv_scheme="StratifiedKFold", metric_name="roc_auc",
                      registry_entry=None):
    """Render experiment.py.tmpl into a temp workspace and import the module.

    Writes to ``<tmp>/experiments/<exp_id>/experiment.py`` so ``__file__.parents[2]``
    is the workspace root (the D-03 fallback ``<ws>/data``).
    """
    from metric_registry import REGISTRY  # stdlib; on sys.path via conftest

    entry = registry_entry if registry_entry is not None else REGISTRY[metric_name]
    exp_dir = tmp_path / "experiments" / exp_id
    (exp_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    raw = TEMPLATE.read_text()
    # CR-01: every config-sourced value is rendered as a repr()-quoted Python literal
    # (the template now carries bare $*_literal placeholders, no hand-written quotes).
    src = Template(raw).safe_substitute(
        {
            "slug_literal": repr(slug),
            "exp_id_literal": repr(exp_id),
            "exp_dir_literal": repr(f"experiments/{exp_id}"),
            "cv_scheme_literal": repr(cv_scheme),
            "metric_name_literal": repr(metric_name),
            "registry_entry": repr(entry),
        }
    )
    path = exp_dir / "experiment.py"
    path.write_text(src)

    mod_name = f"rendered_exp_{exp_id.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_override_wins(tmp_path):
    mod = render_experiment(tmp_path)
    assert mod.resolve_data_dir("titanic", "/some/explicit/path") == Path("/some/explicit/path")


def test_kaggle_mount_preferred_when_present(tmp_path, monkeypatch):
    mod = render_experiment(tmp_path)
    slug = "titanic"
    real_is_dir = Path.is_dir

    def fake_is_dir(self):
        if str(self) == f"/kaggle/input/{slug}":
            return True
        return real_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", fake_is_dir)
    assert mod.resolve_data_dir(slug) == Path(f"/kaggle/input/{slug}")


def test_falls_back_to_workspace_data(tmp_path):
    mod = render_experiment(tmp_path)
    # No /kaggle/input mount, no override -> parents[2]/data == workspace data/.
    assert mod.resolve_data_dir("titanic") == tmp_path.resolve() / "data"


def test_template_is_kernel_portable():
    """The rendered experiment carries a registry_entry LITERAL and imports no skill code.

    Per D-03 the same file must run on a Kaggle kernel that has no ``scripts/``; per
    Blocker-2 the scorer is resolved from the rendered ``registry_entry["sklearn_callable"]``,
    never by ``getattr`` on the config metric name.
    """
    src = TEMPLATE.read_text()
    assert "import metric_registry" not in src
    assert "from metric_registry" not in src
    assert 'registry_entry["sklearn_callable"]' in src


def test_template_renders_resolved_registry_entry_literal(tmp_path):
    """The rendered module holds the resolved registry_entry as a module-level literal."""
    from metric_registry import REGISTRY

    mod = render_experiment(tmp_path, metric_name="roc_auc")
    assert mod.registry_entry == REGISTRY["roc_auc"]
    assert mod.registry_entry["sklearn_callable"] == "roc_auc_score"
    assert mod.METRIC_NAME == "roc_auc"


# --------------------------------------------------------------------------- #
# quick 260925-66x — kernel-safe harness (live-observed 2026-09-25 on Kaggle/papermill):
#   BUG 2: ipykernel injects `-f <connection-file.json>` into sys.argv -> argparse exits 2.
#   BUG 3: IPython reports ANY SystemExit raised in a cell (even 0) as an error.
#   BUG 4: outputs must land FLAT in /kaggle/working (pull_kernel.py contract).
#   + resolve_data_dir hardening: /kaggle/input/competitions/<slug>; no __file__ in a cell.
# None of these tests touch the real /kaggle.
# --------------------------------------------------------------------------- #


def _fake_kaggle_dirs(monkeypatch, present):
    """Make Path.is_dir True only for `present` among /kaggle paths; real elsewhere."""
    real_is_dir = Path.is_dir

    def fake_is_dir(self):
        s = str(self)
        if s.startswith("/kaggle"):
            return s in present
        return real_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", fake_is_dir)


def test_parse_args_tolerates_ipykernel_argv(tmp_path, monkeypatch):
    mod = render_experiment(tmp_path)
    monkeypatch.setattr(mod, "KAGGLE_WORKING", str(tmp_path / "no_such_working"))
    args = mod.parse_args(["-f", "/root/.local/share/jupyter/runtime/kernel-abc.json"])
    assert args.exp_dir == "experiments/exp-001"
    assert args.slug == "titanic"
    assert args.seed == 42


def test_parse_args_reads_ipykernel_sys_argv_when_argv_none(tmp_path, monkeypatch):
    mod = render_experiment(tmp_path)
    monkeypatch.setattr(mod, "KAGGLE_WORKING", str(tmp_path / "no_such_working"))
    monkeypatch.setattr(sys, "argv", ["ipykernel_launcher.py", "-f", "x.json"])
    args = mod.parse_args()  # must NOT raise SystemExit
    assert args.slug == "titanic"


def test_exp_dir_switches_to_kaggle_working_on_kernel(tmp_path, monkeypatch):
    mod = render_experiment(tmp_path)
    working = tmp_path / "kaggle_working"
    working.mkdir()
    monkeypatch.setattr(mod, "KAGGLE_WORKING", str(working))
    assert mod.on_kaggle_kernel() is True
    assert mod.resolve_exp_dir("experiments/exp-001") == str(working)
    assert mod.parse_args([]).exp_dir == str(working)


def test_exp_dir_unchanged_off_kernel(tmp_path, monkeypatch):
    mod = render_experiment(tmp_path)
    monkeypatch.setattr(mod, "KAGGLE_WORKING", str(tmp_path / "no_such_working"))
    assert mod.on_kaggle_kernel() is False
    assert mod.parse_args([]).exp_dir == "experiments/exp-001"
    assert mod.parse_args(["--exp-dir", "custom"]).exp_dir == "custom"


def test_finish_is_silent_under_ipykernel(tmp_path, monkeypatch):
    mod = render_experiment(tmp_path)
    monkeypatch.setitem(sys.modules, "ipykernel", types.ModuleType("ipykernel"))
    mod._finish(0)
    mod._finish(3)


def test_finish_exits_with_code_as_script(tmp_path, monkeypatch):
    mod = render_experiment(tmp_path)
    monkeypatch.delitem(sys.modules, "ipykernel", raising=False)
    with pytest.raises(SystemExit) as exc3:
        mod._finish(3)
    assert exc3.value.code == 3
    with pytest.raises(SystemExit) as exc0:
        mod._finish(0)
    assert exc0.value.code == 0


def test_main_guard_routes_through_finish(tmp_path):
    render_experiment(tmp_path)
    src = (tmp_path / "experiments" / "exp-001" / "experiment.py").read_text()
    assert "_finish(main())" in src
    assert "raise SystemExit(main())" not in src
    assert "parse_known_args" in src
    assert "data_dir: " in src


def test_kaggle_competitions_mount_used_when_flat_absent(tmp_path, monkeypatch):
    mod = render_experiment(tmp_path)
    _fake_kaggle_dirs(monkeypatch, {"/kaggle/input/competitions/titanic"})
    assert mod.resolve_data_dir("titanic") == Path("/kaggle/input/competitions/titanic")


def test_flat_mount_preferred_over_competitions_mount(tmp_path, monkeypatch):
    mod = render_experiment(tmp_path)
    _fake_kaggle_dirs(
        monkeypatch, {"/kaggle/input/titanic", "/kaggle/input/competitions/titanic"}
    )
    assert mod.resolve_data_dir("titanic") == Path("/kaggle/input/titanic")


def test_no_mount_no_file_raises_filenotfound_naming_paths(tmp_path, monkeypatch):
    mod = render_experiment(tmp_path)
    _fake_kaggle_dirs(monkeypatch, set())
    monkeypatch.delitem(mod.__dict__, "__file__")
    with pytest.raises(FileNotFoundError) as exc:
        mod.resolve_data_dir("titanic")
    msg = str(exc.value)
    assert "/kaggle/input/titanic" in msg
    assert "/kaggle/input/competitions/titanic" in msg
