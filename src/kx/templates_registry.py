"""Experiment templates: which exist, what they fit, and how they render.

``select`` picks the template for the confirmed profile (modality + submission
mode). Modes with no template (writeup, artifact_upload, unknown) return None:
kx says so instead of guessing.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from kx import experiment
from kx.metrics import REGISTRY
from kx.workspace import template_text

TEMPLATES = {
    "tabular": {
        "file": "tabular/train.py.tmpl",
        "modalities": {"tabular"},
        "modes": {"csv_upload", "code_kernel"},
        "needs_cv": True,
        "needs_metric": True,
        "summary": "GBDT-ready tabular CV with an AI-written fold scheme",
    },
}

TABULAR_EXTS = (".csv", ".parquet")


def register(name: str, info: dict) -> None:
    TEMPLATES[name] = info


def select(effective: dict) -> tuple[str | None, str]:
    """(template name or None, reason) for a confirmed profile's effective facts."""
    mode, modality = effective.get("submission_mode"), effective.get("modality")
    if mode in ("writeup", "artifact_upload", "unknown", None):
        return None, f"no experiment template for submission mode {mode!r}"
    for name, info in TEMPLATES.items():
        pick = info.get("select")
        if pick and pick(effective):
            return name, f"profile matches {name} ({info['summary']})"
    for name, info in TEMPLATES.items():
        if info.get("select"):
            continue
        if mode in info["modes"] and modality in info["modalities"]:
            return name, f"profile is {modality} + {mode}"
    return None, f"no template fits modality {modality!r} with mode {mode!r}"


def _pick_file(names: list[str], stem: str) -> str | None:
    exact = [n for n in names if Path(n).stem.lower() == stem and n.lower().endswith(TABULAR_EXTS)]
    if exact:
        return exact[0]
    loose = [n for n in names if stem in n.lower() and n.lower().endswith(TABULAR_EXTS)
             and "submission" not in n.lower()]
    return loose[0] if loose else None


def render(name: str, spec: dict, profile: dict, metric_cfg: dict | None) -> str:
    info = TEMPLATES[name]
    eff = profile.get("effective") or profile.get("derived") or {}
    files = [f.get("name") or "" for f in (profile.get("root_listing") or {}).get("files") or []]
    metric_name = (metric_cfg or {}).get("name") or "custom"
    reg = REGISTRY.get(metric_name, REGISTRY["custom"])
    gib = (metric_cfg or {}).get("greater_is_better", reg["greater_is_better"])
    ptype = (metric_cfg or {}).get("prediction_type") or reg["prediction_type"] or "raw"
    metric_info = {"greater_is_better": gib, "prediction_type": ptype,
                   "sklearn_callable": reg["sklearn_callable"]}
    values = {
        "EXP_ID": spec["exp_id"],
        "EXP_ID_LIT": repr(spec["exp_id"]),
        "IDEA_LIT": repr(spec["idea"]),
        "COMPETITION_REF_LIT": repr(profile["canonical_ref"]),
        "SLUG_LIT": repr(profile["slug"]),
        "SAMPLE_LIT": repr(eff.get("sample_submission") or "sample_submission.csv"),
        "TRAIN_LIT": repr(_pick_file(files, "train") or "train.csv"),
        "TEST_LIT": repr(_pick_file(files, "test") or "test.csv"),
        "OUTPUT_LIT": repr(eff.get("expected_output") or "submission.csv"),
        "METRIC_LIT": repr(metric_name),
        "METRIC_INFO_LIT": repr(metric_info),
        "N_FOLDS_LIT": repr(int((spec.get("cv") or {}).get("n_folds") or 5)),
        "EXPECTED_OUTPUT_LIT": repr(eff.get("expected_output") or "submission.csv"),
        "API_SERVED_LIT": repr(bool(eff.get("api_served"))),
    }
    values.update(info.get("extra_values", lambda s, p: {})(spec, profile))
    return Template(template_text(info["file"])).safe_substitute(**values)


def harness_hash(code: str) -> str | None:
    return experiment.harness_hash(code)
