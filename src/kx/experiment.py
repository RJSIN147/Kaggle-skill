"""experiment.json: the declaration of one experiment, validated before any run.

A stdlib validator in the style of ledger.validate_meta: it returns a list of
readable errors, rejects unknown keys (catches typos like "acclerator") and
rejects the "<TODO>" placeholder anywhere.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

SCHEMA_VERSION = 1
PLACEHOLDER = "<TODO>"

# Live-verified accelerator ids only (P100 is retired upstream; multi-GPU shapes
# are unverified). cpu -> enable_gpu false; NvidiaTeslaT4 -> enable_gpu true.
ACCELERATORS = ("cpu", "NvidiaTeslaT4")
TARGETS = ("kernel", "local")
MAX_LIMIT_S = 12 * 3600  # Kaggle's 12 h session maximum

HARNESS_MARKER = "# === KX HARNESS"
AI_STUB = "KX_TODO"  # a template's unwritten AI block (custom); kx run refuses it

TOP_KEYS = {"schema_version", "exp_id", "created", "idea", "hypothesis", "template",
            "template_reason", "runtime", "sources", "cv", "code_file", "harness_sha256",
            "local", "kind", "parent", "expected_effect", "evidence", "third_party"}
# experiment: a model run; diagnostic: `kx diagnose` (never a model comparison or a
# submission); cv_check: the parent's model under a different CV scheme.
KINDS = ("experiment", "diagnostic", "cv_check", "no_cv")
EXPECT_DIRECTIONS = ("better", "worse", "same")
EXPECT_KEYS = {"direction", "delta"}
RUNTIME_KEYS = {"target", "accelerator", "limit_s", "internet", "docker_image"}
# Live-verified 2026-10-04: a GPU kernel pinned to a CPU image (gcr.io/kaggle-images/...)
# runs, but without an NVIDIA driver. GPU images are kaggle-private-byod / kaggle-gpu-images.
CPU_IMAGE_ON_GPU = ("runtime.docker_image is a CPU image (gcr.io/kaggle-images/…): on a GPU it "
                    "has no NVIDIA driver. Pin the GPU image of the same period "
                    "(gcr.io/kaggle-private-byod/… or kaggle-gpu-images/…), e.g. "
                    "--image-from an exp-NNN that ran on a GPU")


def is_cpu_image(img: str) -> bool:
    return img.startswith("gcr.io/kaggle-images/")


# Kaggle's own images only (a digest or a tag); pinned with kx new --docker-image/--image-from
DOCKER_IMAGE_RE = re.compile(r"^gcr\.io/kaggle-[a-z0-9-]+/python(@sha256:[0-9a-f]{64}|:[A-Za-z0-9._-]+)$")
SOURCE_KEYS = {"competition", "datasets", "kernels", "models"}
CV_KEYS = {"n_folds", "reasoning", "scheme"}
LOCAL_KEYS = {"subsample", "env"}

EXP_ID_RE = re.compile(r"^exp-\d{3,}$")
_DATASET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
# A kernel source is owner/slug, or @exp-NNN: this workspace's upstream experiment,
# resolved to its kernel at run time (pushed only after the upstream completes).
_KERNEL_RE = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9][A-Za-z0-9_.-]*|@exp-\d{3,})$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*/[^/\s]+/[^/\s]+/[^/\s]+/\d+$")


def harness_hash(code: str) -> str | None:
    """sha256 of everything from the harness marker on, or None when absent."""
    i = code.find(HARNESS_MARKER)
    if i < 0:
        return None
    return hashlib.sha256(code[i:].encode()).hexdigest()


def draft(exp_id: str, created: str, idea: str, hypothesis: str, template: str,
          template_reason: str, competition: str, n_folds: int = 5,
          accelerator: str = "cpu", limit_s: int = 1800, target: str = "kernel",
          kind: str = "experiment", parent: str | None = None,
          expected_effect: dict | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "exp_id": exp_id,
        "created": created,
        "kind": kind,
        "parent": parent,
        "idea": idea,
        "hypothesis": hypothesis,
        "expected_effect": expected_effect,
        "template": template,
        "template_reason": template_reason,
        "runtime": {"target": target, "accelerator": accelerator, "limit_s": limit_s,
                    "internet": False},
        "sources": {"competition": competition, "datasets": [], "kernels": [], "models": []},
        "cv": {"n_folds": n_folds, "reasoning": PLACEHOLDER},
        "code_file": "train.py",
    }


def _has_placeholder(obj) -> bool:
    if isinstance(obj, str):
        return PLACEHOLDER in obj
    if isinstance(obj, dict):
        return any(_has_placeholder(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_placeholder(v) for v in obj)
    return False


def _nonempty_str(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate(spec, *, exp_dir: Path, profile: dict | None, templates: dict,
             allow_kernel_sources: bool = True) -> list[str]:
    """Readable errors for an experiment.json; [] means it may be run."""
    if not isinstance(spec, dict):
        return ["experiment.json must be a JSON object"]
    errs: list[str] = []
    for k in sorted(set(spec) - TOP_KEYS):
        errs.append(f"unknown key: {k}")
    from kx import provenance

    errs += provenance.validate(spec.get("third_party"))
    if _has_placeholder(spec):
        errs.append(f"a field still holds the {PLACEHOLDER} placeholder")
    if spec.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"schema_version must be {SCHEMA_VERSION}")
    exp_id = spec.get("exp_id")
    if not isinstance(exp_id, str) or not EXP_ID_RE.match(exp_id):
        errs.append("exp_id must look like exp-NNN")
    elif exp_id != exp_dir.name:
        errs.append(f"exp_id {exp_id} does not match the folder {exp_dir.name}")
    for k in ("idea", "hypothesis"):
        if not _nonempty_str(spec.get(k)):
            errs.append(f"{k} must be a non-empty string")
    if spec.get("kind", "experiment") not in KINDS:
        errs.append(f"kind must be one of {KINDS}")
    parent = spec.get("parent")
    if parent is not None:
        if not isinstance(parent, str) or not EXP_ID_RE.match(parent):
            errs.append("parent must be an experiment id (exp-NNN) or null")
        elif parent == exp_id:
            errs.append("an experiment cannot be its own parent")
        elif not (exp_dir.parent / parent / "experiment.json").is_file():
            errs.append(f"parent {parent} does not exist")
    exp = spec.get("expected_effect")
    if exp is not None:
        if not isinstance(exp, dict) or set(exp) - EXPECT_KEYS:
            errs.append(f"expected_effect must be an object with keys {sorted(EXPECT_KEYS)}")
        else:
            if exp.get("direction") not in EXPECT_DIRECTIONS:
                errs.append(f"expected_effect.direction must be one of {EXPECT_DIRECTIONS}")
            d = exp.get("delta")
            if d is not None and not (isinstance(d, (int, float)) and not isinstance(d, bool)):
                errs.append("expected_effect.delta must be a number or null")
    ev = spec.get("evidence")
    if ev is not None and not (isinstance(ev, list) and all(
            isinstance(e, dict) and set(e) == {"ref", "value"} and _nonempty_str(e.get("ref"))
            for e in ev)):
        errs.append("evidence must be a list of {ref, value} objects (set by kx new --evidence)")
    tmpl = spec.get("template")
    if tmpl not in templates:
        errs.append(f"template must be one of {sorted(templates)}")

    rt = spec.get("runtime")
    if not isinstance(rt, dict):
        errs.append("runtime must be an object")
        rt = {}
    for k in sorted(set(rt) - RUNTIME_KEYS):
        errs.append(f"unknown key: runtime.{k}")
    if rt.get("target") not in TARGETS:
        errs.append(f"runtime.target must be one of {TARGETS}")
    if rt.get("accelerator") not in ACCELERATORS:
        errs.append(f"runtime.accelerator must be one of {ACCELERATORS} (live-verified ids only)")
    lim = rt.get("limit_s")
    if not _is_int(lim) or not (60 <= lim <= MAX_LIMIT_S):
        errs.append(f"runtime.limit_s must be an int in [60, {MAX_LIMIT_S}]")
    if not isinstance(rt.get("internet"), bool):
        errs.append("runtime.internet must be true or false")
    img = rt.get("docker_image")
    if img is not None and not (isinstance(img, str) and DOCKER_IMAGE_RE.match(img)):
        errs.append("runtime.docker_image must be a Kaggle image "
                    "(gcr.io/kaggle-…/python@sha256:… or :tag)")
    elif img and rt.get("accelerator", "cpu") != "cpu" and is_cpu_image(img):
        errs.append(CPU_IMAGE_ON_GPU)

    src = spec.get("sources")
    if not isinstance(src, dict):
        errs.append("sources must be an object")
        src = {}
    for k in sorted(set(src) - SOURCE_KEYS):
        errs.append(f"unknown key: sources.{k}")
    comp = src.get("competition")
    if profile is not None and comp is not None and str(comp).lower() != profile.get("slug"):
        errs.append(f"sources.competition must be the synced competition {profile.get('slug')!r}")
    for key, rx in (("datasets", _DATASET_RE), ("kernels", _KERNEL_RE), ("models", _MODEL_RE)):
        vals = src.get(key, [])
        if not isinstance(vals, list) or not all(isinstance(v, str) and rx.match(v) for v in vals):
            errs.append(f"sources.{key} must be a list of valid Kaggle refs")
    if src.get("kernels") and not allow_kernel_sources:
        errs.append("sources.kernels is not supported for this run")

    cv = spec.get("cv")
    if not isinstance(cv, dict):
        errs.append("cv must be an object")
        cv = {}
    for k in sorted(set(cv) - CV_KEYS):
        errs.append(f"unknown key: cv.{k}")
    tinfo = templates.get(tmpl) or {}
    if tinfo.get("needs_cv", True):
        if not _is_int(cv.get("n_folds")) or cv.get("n_folds") < 2:
            errs.append("cv.n_folds must be an int >= 2")
        if not _nonempty_str(cv.get("reasoning")):
            errs.append("cv.reasoning must explain the CV scheme")

    local = spec.get("local")
    if local is not None:
        if not isinstance(local, dict):
            errs.append("local must be an object")
        else:
            for k in sorted(set(local) - LOCAL_KEYS):
                errs.append(f"unknown key: local.{k}")
            sub = local.get("subsample")
            if sub is not None and not (isinstance(sub, (int, float)) and not isinstance(sub, bool)
                                        and 0 < sub <= 1):
                errs.append("local.subsample must be a fraction in (0, 1]")

    code_file = spec.get("code_file")
    if not isinstance(code_file, str) or "/" in code_file or not code_file.endswith(".py"):
        errs.append("code_file must be a .py file name in the experiment folder")
    else:
        path = exp_dir / code_file
        if not path.is_file():
            errs.append(f"code_file {code_file} does not exist")
        else:
            code = path.read_text()
            try:
                ast.parse(code)
            except SyntaxError as exc:
                errs.append(f"{code_file} has a syntax error at line {exc.lineno}")
            if AI_STUB in code:
                errs.append(f"{code_file} still holds the {AI_STUB} stub: write the AI block")
            want = spec.get("harness_sha256")
            if want and harness_hash(code) != want:
                errs.append(f"the KX HARNESS section of {code_file} was modified; only the AI "
                            "block may change")
    return errs
