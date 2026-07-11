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
from pathlib import Path
from string import Template

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
    src = Template(raw).safe_substitute(
        {
            "slug": slug,
            "exp_id": exp_id,
            "exp_dir": f"experiments/{exp_id}",
            "cv_scheme": cv_scheme,
            "metric_name": metric_name,
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
