"""Experiment templates: which exist, what they fit, and how they render.

``select`` picks the template for the confirmed profile (modality + submission
mode). Modes with no template (writeup, artifact_upload, unknown) return None:
kx says so instead of guessing.
"""

from __future__ import annotations

import ast
from pathlib import Path
from string import Template

from kx import experiment
from kx.metrics import REGISTRY
from kx.util import KxError
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
    "timeseries": {
        "file": "timeseries/train.py.tmpl",
        "modalities": {"tabular"},
        "modes": {"csv_upload", "code_kernel"},
        "needs_cv": True,
        "needs_metric": True,
        "auto": False,  # chosen by the AI (with a recorded reason) for time-ordered data
        "summary": "walk-forward (expanding window) CV for time-ordered data",
    },
}

def _deep_values(spec: dict, profile: dict) -> dict:
    """Stage, own kernel slug (resume), upstream (infer), time budget, model sources."""
    import json as _json

    from kx import kernel

    ws = Path(profile["_ws"])
    cfg = _json.loads((ws / "control" / "config.json").read_text())
    state = _json.loads((ws / "control" / "state.json").read_text())
    owner = (state.get("credentials") or {}).get("username") or "owner"
    wsid = cfg.get("workspace_id", "ws")
    upstream = None
    kernels = (spec.get("sources") or {}).get("kernels") or []
    ups = [k[1:] for k in kernels if k.startswith("@")]
    if ups:
        upstream = {"ref": f"{owner}/{kernel.kernel_slug(profile['slug'], wsid, ups[0])}",
                    "exp_id": ups[0]}
    limit = int((spec.get("runtime") or {}).get("limit_s") or 3600)
    return {
        "STAGE_LIT": repr("infer" if spec["template"] == "deep-infer" else "train"),
        "KERNEL_SLUG_LIT": repr(kernel.kernel_slug(profile["slug"], wsid, spec["exp_id"])),
        "UPSTREAM_LIT": repr(upstream),
        "TIME_BUDGET_LIT": repr(max(60, int(limit * 0.85))),
        "MODEL_SOURCES_LIT": repr(list((spec.get("sources") or {}).get("models") or [])),
    }


TEMPLATES["deep"] = {
    "file": "deep/train.py.tmpl",
    "modalities": {"image", "text", "audio"},
    "modes": {"csv_upload", "code_kernel"},
    "needs_cv": True,
    "needs_metric": True,
    "default_accelerator": "NvidiaTeslaT4",
    "default_limit_s": 3600,
    "extra_values": _deep_values,
    "summary": "PyTorch image/text fold loop: AMP, per-epoch checkpoints, time-budgeted resume",
}
TEMPLATES["deep-infer"] = {
    "file": "deep/train.py.tmpl",
    "modalities": {"image", "text", "audio"},
    "modes": {"csv_upload", "code_kernel"},
    "needs_cv": True,
    "needs_metric": True,
    "auto": False,  # chosen by `kx new --after <deep experiment>`
    "default_accelerator": "cpu",
    "default_limit_s": 1800,
    "extra_values": _deep_values,
    "summary": "inference stage: loads an upstream deep experiment's fold models",
}

def _inference_values(spec: dict, profile: dict) -> dict:
    vals = _deep_values(spec, profile)
    up = ast.literal_eval(vals["UPSTREAM_LIT"])
    eff = profile.get("effective") or profile.get("derived") or {}
    files = [f.get("name") or "" for f in (profile.get("root_listing") or {}).get("files") or []]
    test = _pick_file(files, "test") or "test.csv"
    sample = eff.get("sample_submission") or "sample_submission.csv"
    return {"UPSTREAM_LIT": vals["UPSTREAM_LIT"],
            "UPSTREAM_EXP": (up or {}).get("exp_id", "?"),
            "OUTPUT_NAME": eff.get("expected_output") or "submission.csv",
            "GATEWAY_PATHS_LIT": repr((test, sample))}


TEMPLATES["inference"] = {
    "file": "inference/predict.py.tmpl",
    "modalities": {"tabular"},
    "modes": {"code_kernel", "csv_upload"},
    "needs_cv": True,
    "needs_metric": True,
    "auto": False,  # chosen by `kx new --after <tabular experiment>` in code competitions
    "default_accelerator": "cpu",
    "default_limit_s": 3600,
    "extra_values": _inference_values,
    "code_file": "predict.py",
    "summary": "code-competition inference: upstream fold models -> expected output "
               "(API-served: kaggle_evaluation server)",
}

TEMPLATES["agent"] = {
    "file": "agent/main.py.tmpl",
    "modalities": {"none", "tabular", "structured", "image", "text", "audio"},
    "modes": {"agent"},
    "select": lambda eff: eff.get("submission_mode") == "agent",
    "needs_cv": False,
    "needs_metric": False,
    "predictions": False,
    "target": "local",
    "code_file": "main.py",
    "summary": "single-file simulation agent; local self-play validation + win rate vs a pool",
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
        if info.get("select") or info.get("auto") is False:
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
        "COMPETITION_REF": profile["canonical_ref"],
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
        "HARNESS": template_text("common/harness.py.tmpl").rstrip(),
        "HOST_METRIC": host_metric_block(profile.get("_ws"), metric_cfg),
    }
    values.update(info.get("extra_values", lambda s, p: {})(spec, profile))
    return Template(template_text(info["file"])).safe_substitute(**values)


def host_metric_block(ws, metric_cfg: dict | None) -> str:
    """Inline the user-confirmed host metric kernel as a `host_metric` namespace.

    Kernels are single files, so the code travels inside the script (as a string
    literal, executed into its own namespace so its names never clash). The sha256
    recorded at adoption is re-checked here.
    """
    import hashlib

    hm = (metric_cfg or {}).get("host_metric")
    if not hm or ws is None:
        return "host_metric = None  # no host metric kernel adopted"
    code = (Path(ws) / hm["file"]).read_text()
    if hashlib.sha256(code.encode()).hexdigest() != hm["sha256"]:
        raise KxError("error", "the adopted host metric file changed since the user confirmed it",
                      errors=["host_metric_changed"],
                      next_action={"kind": "run", "command": f"kx research metric --use-metric {hm['ref']}"})
    return (f"# === HOST METRIC ({hm['ref']}, confirmed by the user; sha256 {hm['sha256'][:12]}) ===\n"
            f"HOST_METRIC_SOURCE = {code!r}\n\n\n"
            "def _load_host_metric():\n"
            "    import types\n\n"
            "    ns = {'__name__': 'host_metric'}\n"
            "    exec(compile(HOST_METRIC_SOURCE, 'host_metric.py', 'exec'), ns)\n"
            "    return types.SimpleNamespace(**ns)\n\n\n"
            "class _LazyHostMetric:\n"
            "    \"\"\"Loaded on first use, so the AI block can install its dependencies first\n"
            "    (e.g. offline wheels from an attached kernel).\"\"\"\n"
            "    _ns = None\n\n"
            "    def __getattr__(self, name):\n"
            "        if _LazyHostMetric._ns is None:\n"
            "            _LazyHostMetric._ns = _load_host_metric()\n"
            "        return getattr(_LazyHostMetric._ns, name)\n\n\n"
            "host_metric = _LazyHostMetric()")


AI_START, AI_END = "# === AI BLOCK", "# === END AI BLOCK"


def copy_ai_block(src_code: str, dst_code: str) -> str:
    """Replace dst's AI block with src's (both rendered from the same template)."""
    def span(code):
        i = code.index(AI_START)
        return i, code.index(AI_END, i)
    si, sj = span(src_code)
    di, dj = span(dst_code)
    return dst_code[:di] + src_code[si:sj] + dst_code[dj:]


def harness_hash(code: str) -> str | None:
    return experiment.harness_hash(code)
