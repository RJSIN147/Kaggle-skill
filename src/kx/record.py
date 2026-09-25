"""The fail-closed recorder: output/ + run facts -> meta.json -> ledger.

The classification ladder, in order (first hit wins, every miss is FAILED):
  1. status rung   kernel status ERROR -> kernel_error; CANCEL_ACKNOWLEDGED -> runtime_limit;
                   a local run with a non-zero exit -> kernel_error
  2. log rung      the pulled log carries a traceback/OOM/kill marker -> kernel_error;
                   a kernel run whose log cannot be read fails closed -> kernel_error
  3. result rung   result.json missing / malformed / non-finite / mean != mean(folds) /
                   wrong metric / out of the metric's range
  4. preds rung    OOF + test predictions invalid under kx-preds/1 -> predictions_invalid

A FAILED record keeps idea + hypothesis, carries a null cv_mean (never a
fabricated score), and points at the traceback, log and partial outputs.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import uuid
from pathlib import Path

from kx import preds
from kx.ledger import rebuild_ledger_file
from kx.metrics import REGISTRY
from kx.util import utc_now, write_json

FAILURE_REASONS = ("missing_result", "schema_invalid", "non_finite", "out_of_range",
                   "kernel_error", "runtime_limit", "predictions_invalid")

KERNEL_ERROR_MARKERS = (
    "Traceback (most recent call last)",
    "\nError:",
    "\nException:",
    "Your notebook tried to allocate more memory than is available",
    "Killed",
    "Notebook Exceeded",
)

REQUIRED_RESULT_KEYS = ("metric", "n_folds", "fold_scores", "cv_mean", "cv_std")
DEFAULT_SEED = 42
TRACEBACK_TAIL_LINES = 40


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def log_records(log_text: str) -> list[dict] | None:
    try:
        parsed = json.loads(log_text)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    if isinstance(parsed, list) and all(isinstance(r, dict) for r in parsed):
        return parsed
    return None


def log_streams(log_text: str) -> tuple[str, str]:
    """(all text, stderr text) of a Kaggle log (JSON records) or plain text."""
    recs = log_records(log_text)
    if recs is None:
        return log_text, log_text
    all_text = "\n".join(str(r.get("data", "")) for r in recs)
    err = "".join(str(r.get("data", "")) for r in recs if r.get("stream_name") == "stderr")
    return all_text, err


def scan_log(log_text: str) -> bool:
    """True when a failure marker appears. Pure pattern match; never echoed."""
    text, _ = log_streams(log_text)
    return any(m in text for m in KERNEL_ERROR_MARKERS)


_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def traceback_tail(log_text: str) -> str | None:
    _, err = log_streams(log_text)
    err = _ANSI.sub("", err)
    i = err.rfind("Traceback (most recent call last)")
    if i < 0:
        return None
    lines = err[i:].splitlines()
    block = [lines[0]]
    for line in lines[1:]:
        block.append(line)
        if line and not line[0].isspace():  # the exception line ends the traceback
            break
    return "\n".join(block[-TRACEBACK_TAIL_LINES:])


def validate_result(result, metric_cfg: dict) -> str | None:
    """None when result.json passes; else a failure reason. Never trusts cv_mean."""
    if not isinstance(result, dict):
        return "schema_invalid"
    for key in REQUIRED_RESULT_KEYS:
        if key not in result:
            return "schema_invalid"
    fs, n, mean, std = result["fold_scores"], result["n_folds"], result["cv_mean"], result["cv_std"]
    if not isinstance(fs, list) or not fs or not all(_is_number(s) for s in fs):
        return "schema_invalid"
    if not isinstance(n, int) or isinstance(n, bool) or len(fs) != n or n < 2:
        return "schema_invalid"
    if not _is_number(mean) or not _is_number(std):
        return "schema_invalid"
    if not all(math.isfinite(float(s)) for s in fs) or not math.isfinite(float(mean)) \
            or not math.isfinite(float(std)):
        return "non_finite"
    if abs(float(mean) - statistics.mean(float(s) for s in fs)) >= 1e-6:
        return "schema_invalid"
    name = metric_cfg["name"]
    if result["metric"] != name:
        return "schema_invalid"
    lo, hi = metric_cfg.get("range") or REGISTRY.get(name, REGISTRY["custom"])["range"]
    lo = -math.inf if lo is None else lo
    hi = math.inf if hi is None else hi
    if not (lo <= float(mean) <= hi) or not all(lo <= float(s) <= hi for s in fs):
        return "out_of_range"
    return None


def _read_json(path: Path):
    try:
        return json.loads(path.read_text()), None
    except FileNotFoundError:
        return None, "missing_result"
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None, "schema_invalid"


def classify(run: dict, output_dir: Path, log_text: str | None, metric_cfg: dict,
             require_predictions: bool = True):
    """(status, failure_reason, valid_result) by the ladder above."""
    backend = run.get("backend", "kernel")
    st = run.get("status")
    if backend == "kernel":
        if isinstance(st, str) and st == "ERROR":
            return "FAILED", "kernel_error", None
        if isinstance(st, str) and st == "CANCEL_ACKNOWLEDGED":
            return "FAILED", "runtime_limit", None
        if log_text is None or scan_log(log_text):
            return "FAILED", "kernel_error", None
    else:
        if run.get("timed_out"):
            return "FAILED", "runtime_limit", None
        if run.get("exit_code") not in (0, None):
            return "FAILED", "kernel_error", None
        if log_text is not None and scan_log(log_text):
            return "FAILED", "kernel_error", None
    result, err = _read_json(output_dir / "result.json")
    if err:
        return "FAILED", err, None
    if isinstance(result, dict) and result.get("incomplete") is True:
        return "FAILED", "runtime_limit", None  # stopped at its time budget (resumable)
    reason = validate_result(result, metric_cfg)
    if reason:
        return "FAILED", reason, None
    if (require_predictions or result.get("predictions") is not None) and \
            preds.validate(output_dir, result.get("predictions"), int(result["n_folds"])):
        return "FAILED", "predictions_invalid", None
    return "SUCCESS", None, result


def record(ws: Path, exp_dir: Path, spec: dict, run: dict, metric_cfg: dict,
           log_text: str | None, verdict_stub: str,
           require_predictions: bool = True) -> tuple[dict, list[str]]:
    """Classify, write meta.json + VERDICT.md stub, rebuild the ledger.
    Returns (meta, ledger warnings)."""
    rel = f"experiments/{exp_dir.name}"
    output_dir = exp_dir / "output"
    status, reason, result = classify(run, output_dir, log_text, metric_cfg,
                                      require_predictions)

    code = exp_dir / spec.get("code_file", "train.py")
    artifact_hash = "sha256:" + hashlib.sha256(code.read_bytes()).hexdigest() if code.is_file() \
        else "sha256:missing"
    seed = result.get("seed") if result and _is_number(result.get("seed")) else DEFAULT_SEED
    manifest, _ = _read_json(output_dir / "kx_manifest.json")
    manifest = manifest if isinstance(manifest, dict) else {}

    meta = {
        "schema_version": 2,
        "exp_id": spec.get("exp_id") or exp_dir.name,
        "created": spec.get("created"),
        "recorded": utc_now(),
        "idea": spec.get("idea"),
        "hypothesis": spec.get("hypothesis"),
        "template": spec.get("template"),
        "cv_reasoning": (spec.get("cv") or {}).get("reasoning"),
        "runtime": spec.get("runtime"),
        "status": status,
        "failure_reason": reason,
        "metric": metric_cfg["name"],
        "greater_is_better": metric_cfg.get("greater_is_better"),
        "n_folds": None,
        "fold_scores": [],
        "cv_mean": None,
        "cv_std": None,
        "predictions": None,
        "subsample": run.get("subsample"),
        "provenance": {
            "run_id": uuid.uuid4().hex,
            "artifact_hash": artifact_hash,
            "git_commit": run.get("git_commit") or "uncommitted",
            "seed": seed,
        },
        "backend": run.get("backend", "kernel"),
        "environment": {
            "python": manifest.get("python"),
            "libraries": manifest.get("libraries"),
            "docker_image": run.get("docker_image"),
            "machine_shape": run.get("machine_shape"),
            "platform": manifest.get("platform"),
        },
        "result_path": f"{rel}/output/result.json",
        "verdict_path": f"{rel}/VERDICT.md",
    }
    raw, _ = _read_json(output_dir / "result.json")
    if reason == "runtime_limit" and isinstance(raw, dict) and raw.get("incomplete") is True \
            and run.get("status") == "COMPLETE":
        meta["resumable"] = True
        meta["stopped_at"] = raw.get("stopped_at")
    if run.get("backend", "kernel") == "kernel":
        meta["kernel"] = {k: run.get(k) for k in (
            "kernel_ref", "kernel_version", "accelerator", "enable_internet", "is_private",
            "status", "failure_message_quarantined", "upstream", "resumed_from_version")}
    if result is not None:
        meta.update({
            "n_folds": result["n_folds"],
            "fold_scores": result["fold_scores"],
            "cv_mean": result["cv_mean"],
            "cv_std": result["cv_std"],
            "predictions": result.get("predictions"),
            "agent_eval": {k: result[k] for k in ("validation", "opponents") if k in result}
            or None,
        })
    else:
        partial = sorted(p.name for p in output_dir.iterdir()) if output_dir.is_dir() else []
        detail = {"partial_outputs": partial}
        if log_text is not None:
            tb = traceback_tail(log_text)
            if tb:
                (output_dir / "traceback.txt").write_text(tb + "\n")
                detail["traceback"] = f"{rel}/output/traceback.txt"
                detail["error_line"] = tb.splitlines()[-1][:300]
        if run.get("log_file"):
            detail["log"] = run["log_file"]
        meta["failure_detail"] = detail

    write_json(exp_dir / "meta.json", meta)
    verdict = exp_dir / "VERDICT.md"
    if not verdict.exists():
        verdict.write_text(verdict_stub)
    _, warnings = rebuild_ledger_file(ws)
    return meta, warnings
