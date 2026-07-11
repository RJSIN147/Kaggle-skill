#!/usr/bin/env python3
"""record_experiment.py — the anti-lie recorder: validate, provenance, persist (EXP-04, D-05/D-06).

The `record` entry point of the D-02 idempotent loop (`scaffold -> run -> record ->
regen_strategy`) and the integrity spine of the phase. Numbers are TOOLING-WRITTEN: the AI
never hand-types a CV score. This recorder reads the on-disk `result.json` that
`experiment.py` emitted, applies a fail-closed validation ladder, RECOMPUTES
`mean(fold_scores)` to catch a lying notebook, attaches stdlib provenance, and persists the
result into the canonical `meta.json` + a derived `ledger.jsonl` row + a `VERDICT.md` stub.

Two guarantees behind success criterion 3 (a throwing notebook is a FAILURE, not a success;
every row carries provenance):

  1. **Fail-closed classification (D-06).** A run is SUCCESS only if `result.json` exists,
     parses, has the required keys/types, `len(fold_scores)==n_folds` and `n_folds>=2`, every
     score/mean/std is finite, `abs(cv_mean - statistics.mean(fold_scores)) < 1e-6` (the
     anti-lie recompute — the emitted cv_mean is NEVER trusted), the metric matches config,
     and cv_mean sits inside the metric's registered range. ANY failure — plus a non-zero run
     exit (`--run-exit-code`) — is FAILED with a `failure_reason` enum and a VERDICT stub. A
     failure is recorded WITH a verdict, never dropped and never appended as a success row.

  2. **Stub carry-forward on BOTH paths.** The scaffold-written `meta.json` stub carries the
     AI's idea/hypothesis/created/exp_id. The recorder reads it FIRST and preserves those
     fields into the final canonical meta on the SUCCESS and the FAILED path alike — so a
     failed attempt never loses its hypothesis (D-13 tried-list; `to_ledger_row` needs `idea`).

Provenance is stdlib-only (D-06 split — no sklearn/pandas/numpy import): run_id (uuid4),
artifact_hash (sha256 of experiment.py), git_commit (`git rev-parse --short HEAD`) with a
git_dirty flag, and the seed copied from result.json. Provenance staging is by EXPLICIT
path (`git add -- experiment.py meta.json`) — never a blanket stage, which the Phase-1 leak
guard forbids (it would sweep control/raw/last-error.txt).

Portability (CLAUDE.md §Stack Patterns): stdlib-only, self-locating, `--workspace`-driven,
non-interactive (argparse in / exit-code out).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
import sys
import uuid
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from init_workspace import _render_text, create_if_absent  # noqa: E402
from metric_registry import REGISTRY  # noqa: E402
from rebuild_ledger import rebuild_ledger_file  # noqa: E402

# The D-06 failure enum: every FAILED meta carries exactly one of these reasons so the
# tried-list and the verdict prompt can name WHY the cycle failed. `kernel_error` is the
# ONE reason added for the kernel path (D-11/D-12): a kernel log that carries a traceback /
# OOM / time-limit marker. Missing/invalid kernel result.json keeps mapping to the EXISTING
# missing_result/schema_invalid reasons — no kernel-specific proliferation (D-12).
FAILURE_REASONS = ("missing_result", "schema_invalid", "non_finite", "out_of_range",
                   "kernel_error")

# D-11 silent-failure markers scanned in a pulled Kaggle kernel log BEFORE its result.json
# is trusted. A kernel can report COMPLETE yet have thrown mid-notebook and still leave a
# stale/valid-looking result.json on disk — these markers catch that lie. Pure pattern-match:
# the log is untrusted Kaggle text, never echoed and never a source of an executed
# path/command (V5/V7).
_KERNEL_ERROR_MARKERS = (
    "Traceback (most recent call last)",
    "\nError:",
    "\nException:",
    "Your notebook tried to allocate more memory than is available",
    "Killed",
    "Notebook Exceeded",
)

# result.json keys required before a run can even be considered for SUCCESS (D-04).
REQUIRED_RESULT_KEYS = ("metric", "n_folds", "fold_scores", "cv_mean", "cv_std")

DEFAULT_SEED = 42  # D-09: mirrors the harness default when a failed run left no seed.


def _read_json(path: Path):
    """Return (parsed, error) — error is a machine string or None.

    A missing file is ``(None, "missing_result")`` and unparseable JSON is
    ``(None, "schema_invalid")`` — the first two rungs of the fail-closed ladder.
    """
    try:
        return json.loads(path.read_text()), None
    except FileNotFoundError:
        return None, "missing_result"
    except (json.JSONDecodeError, OSError):
        return None, "schema_invalid"


def scan_kernel_log(log_text: str) -> bool:
    """True if the kernel log carries a D-11 silent-failure marker (traceback / OOM / kill).

    Pure pattern-match — ``marker in text`` only. NEVER echoes the log and NEVER derives an
    executed path/command from its content (V5/V7). Handles Assumption A3: a Kaggle log may
    arrive as plain text OR as a JSON array of ``{"stream_name": ..., "data": ...}`` records;
    when it parses as such a list, the ``data`` fields are concatenated and that is scanned,
    otherwise the raw text is scanned as-is.
    """
    scan_target = log_text
    try:
        parsed = json.loads(log_text)
    except (json.JSONDecodeError, ValueError):
        parsed = None
    if isinstance(parsed, list) and all(isinstance(rec, dict) for rec in parsed):
        parts = [str(rec.get("data", "")) for rec in parsed]
        # Join on newline so a marker anchored on "\n" (\nError:/\nException:) is still
        # matchable across record boundaries.
        scan_target = "\n".join(parts)
    return any(marker in scan_target for marker in _KERNEL_ERROR_MARKERS)


def _read_config_metric(config_path: Path) -> tuple[str | None, str | None]:
    """Fail-clear read of ``config.json.metric.name``. Returns (metric_name, error_msg)."""
    if not config_path.exists():
        return None, f"no {config_path} — run init/set_metric first."
    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        return None, f"{config_path.name} is not valid JSON (left untouched): {exc}."
    metric_field = config.get("metric")
    if not isinstance(metric_field, dict) or metric_field.get("name") is None:
        return None, "config.json.metric is not set — run set_metric.py first (D-08)."
    name = metric_field["name"]
    if name not in REGISTRY:
        return None, f"unknown metric '{name}' (not in metric_registry)."
    return name, None


def _is_number(value) -> bool:
    """True for a real int/float (bools are NOT numbers here)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_result(result: dict, metric_name: str) -> str | None:
    """Run the fail-closed ladder (D-06, in order). Return a failure_reason or None (valid).

    NEVER trusts the emitted ``cv_mean``: step 4 recomputes ``statistics.mean(fold_scores)``
    and rejects any disagreement — the anti-lie guarantee (Pitfall 2).
    """
    # Step 2: required keys, correct types, fold-count agreement, >= 2 folds.
    for key in REQUIRED_RESULT_KEYS:
        if key not in result:
            return "schema_invalid"
    fold_scores = result["fold_scores"]
    n_folds = result["n_folds"]
    cv_mean = result["cv_mean"]
    cv_std = result["cv_std"]
    if not isinstance(fold_scores, list) or not fold_scores:
        return "schema_invalid"
    if not isinstance(n_folds, int) or isinstance(n_folds, bool):
        return "schema_invalid"
    if not all(_is_number(s) for s in fold_scores):
        return "schema_invalid"
    if not _is_number(cv_mean) or not _is_number(cv_std):
        return "schema_invalid"
    if len(fold_scores) != n_folds or n_folds < 2:
        return "schema_invalid"

    # Step 3: every score / mean / std is finite (catches NaN / inf a swallowed
    # exception may have written).
    if not all(math.isfinite(float(s)) for s in fold_scores):
        return "non_finite"
    if not math.isfinite(float(cv_mean)) or not math.isfinite(float(cv_std)):
        return "non_finite"

    # Step 4: the anti-lie recompute — the emitted mean must match mean(fold_scores).
    recomputed = statistics.mean(float(s) for s in fold_scores)
    if abs(float(cv_mean) - recomputed) >= 1e-6:
        return "schema_invalid"

    # Step 5: the emitted metric must match config. The "custom" escape hatch is honored
    # ONLY when config itself declared `custom` — otherwise a run configured for a bounded
    # metric (e.g. roc_auc in [0,1]) could self-report metric="custom" and sail past the
    # range gate with an implausible score (WR-03). When config names a known bounded
    # metric, require the result to report that SAME metric so its range is enforced.
    result_metric = result["metric"]
    allow_custom = metric_name == "custom"
    if result_metric != metric_name and not (allow_custom and result_metric == "custom"):
        return "schema_invalid"

    # Step 6: cv_mean and every fold score sit inside the metric's registered range.
    range_entry = REGISTRY.get(result_metric, REGISTRY[metric_name])
    lo, hi = range_entry["range"]
    if not (lo <= float(cv_mean) <= hi):
        return "out_of_range"
    if not all(lo <= float(s) <= hi for s in fold_scores):
        return "out_of_range"

    return None


def _git(args: list[str], ws: Path) -> str:
    """Run ``git <args>`` in ``ws``; return trimmed stdout, or "" on any failure."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(ws), capture_output=True, text=True, check=False
        )
    except OSError:
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _stage_provenance(ws: Path, *rels: str) -> None:
    """``git add --`` ONLY the named provenance paths that exist (never a blanket add).

    Mirrors capture_competition._stage_provenance: staging by explicit path keeps the
    sibling control/raw/last-error.txt (gitignored) out — exactly what the Phase-1 leak
    guard enforces. NEVER a blanket stage of the whole tree.
    """
    if not (ws / ".git").exists():
        return
    present = [rel for rel in rels if (ws / rel).exists()]
    if not present:
        return
    subprocess.run(
        ["git", "add", "--", *present],
        cwd=str(ws), capture_output=True, text=True, check=False,
    )


def _build_provenance(ws: Path, exp_dir: Path, exp_rel: str,
                      valid_result: dict | None) -> dict:
    """Assemble the EXP-04 provenance block from stdlib primitives (no ML import)."""
    artifact_hash = "sha256:" + hashlib.sha256(
        (exp_dir / "experiment.py").read_bytes()
    ).hexdigest()
    seed = DEFAULT_SEED
    if valid_result is not None and _is_number(valid_result.get("seed")):
        seed = valid_result["seed"]
    # dirty is computed BEFORE staging so it honestly reflects the uncommitted experiment
    # work (result.json / meta.json are uncommitted at record time — provenance never
    # falsely claims a clean commit).
    git_dirty = bool(_git(["status", "--porcelain", "--", exp_rel], ws))
    return {
        "run_id": uuid.uuid4().hex,
        "artifact_hash": artifact_hash,
        "git_commit": _git(["rev-parse", "--short", "HEAD"], ws),
        "git_dirty": git_dirty,
        "seed": seed,
    }


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="record_experiment.py",
        description="Validate an experiment's on-disk result.json (fail-closed), recompute "
                    "the mean to catch fabrication, attach provenance, and persist "
                    "meta.json + a ledger row + a VERDICT stub. A throwing/invalid run is "
                    "recorded as FAILED WITH a verdict, never a success (EXP-04, criterion 3).",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    ap.add_argument("--exp-dir", required=True,
                    help="Experiment folder relative to the workspace "
                         "(e.g. experiments/exp-001).")
    ap.add_argument("--run-exit-code", type=int, default=None,
                    help="The exit code from run_local.py. A non-zero value pre-classifies "
                         "the run as FAILED before result.json is even read.")
    ap.add_argument("--kernel-log", type=Path, default=None,
                    help="Path to a pulled Kaggle kernel log (kernel path only). When set, the "
                         "log is scanned for D-11 silent-failure markers as the FIRST rung of "
                         "the fail-closed ladder: a traceback/OOM hit records FAILED("
                         "kernel_error) BEFORE result.json is trusted. Absent = local path "
                         "(existing behavior, byte-for-byte unchanged).")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()
    exp_rel = args.exp_dir
    exp_dir = (ws / exp_rel).resolve()

    # The minted experiment.py is the provenance anchor; without it there is nothing to
    # record.
    if not (exp_dir / "experiment.py").is_file():
        print(f"cannot record: {exp_rel}/experiment.py not found — scaffold first.",
              file=sys.stderr)
        return 1

    # Config metric (fail-clear) — needed for the metric-match + range gates.
    metric_name, cfg_err = _read_config_metric(ws / "control" / "config.json")
    if cfg_err is not None:
        print(f"cannot record: {cfg_err}", file=sys.stderr)
        return 1

    # STUB CARRY-FORWARD (fail-clear): read the scaffold-written meta.json FIRST and pull
    # idea/hypothesis/created/exp_id. Without the stub we cannot preserve the hypothesis,
    # so we block rather than emit a blank record (Blocker-3; to_ledger_row needs idea).
    stub_path = exp_dir / "meta.json"
    stub, stub_err = _read_json(stub_path)
    if stub is None or not isinstance(stub, dict):
        print(
            f"cannot record: {exp_rel}/meta.json stub is missing or unreadable "
            f"({stub_err}) — scaffold the experiment first (D-02).",
            file=sys.stderr,
        )
        return 1
    carried = {
        "exp_id": stub.get("exp_id"),
        "created": stub.get("created"),
        "idea": stub.get("idea"),
        "hypothesis": stub.get("hypothesis"),
    }
    if not carried["exp_id"] or not carried["idea"]:
        print(
            f"cannot record: {exp_rel}/meta.json stub lacks exp_id/idea — a record must "
            f"carry the AI's authored idea (EXP-01, D-13).",
            file=sys.stderr,
        )
        return 1

    result_path = exp_dir / "result.json"

    # Classification ladder (kernel path only, D-11/D-12 + CR-01/WR-03). When --kernel-log is
    # provided, three AUTHORITATIVE kernel rungs decide BEFORE result.json is ever validated —
    # each classifies FAILED(kernel_error), so a stale valid result.json can never rescue a
    # confirmed or unverifiable failure (criterion 3, truth 11):
    #   1. CR-01 status rung: kernel_run.json.status (poll-written, authoritative) in
    #      {"ERROR", "CANCEL_ACKNOWLEDGED"} => a Kaggle-confirmed terminal FAILURE, unconditional.
    #      Exact membership only — the status is untrusted text, never substring/regex/eval/echoed.
    #   2. D-11 log-marker rung: a readable pulled log carrying a traceback/OOM/kill marker.
    #   3. WR-03 fail-closed rung: an unreadable/missing --kernel-log fails CLOSED — a kernel run
    #      whose expected log cannot be read is NEVER SUCCESS off a possibly-stale result.json.
    # A missing/garbage kernel_run.json simply does not trigger rung 1 (fail-clear via _read_json).
    # No kernel rung fired (or no --kernel-log at all) => fall through to the EXISTING run_failed /
    # _read_json / _validate_result ladder unchanged, so the local path stays byte-for-byte
    # identical. kernel_run is read ONCE here and reused by the provenance merge below.
    valid_result: dict | None = None
    kernel_error_hit = False
    kernel_run: dict | None = None
    if args.kernel_log is not None:
        parsed_kernel_run, _ = _read_json(exp_dir / "kernel_run.json")
        if isinstance(parsed_kernel_run, dict):
            kernel_run = parsed_kernel_run

        # Rung 1 — CR-01 authoritative status (before any log read / result validation).
        if kernel_run is not None and kernel_run.get("status") in {
            "ERROR", "CANCEL_ACKNOWLEDGED"
        }:
            status, failure_reason, kernel_error_hit = "FAILED", "kernel_error", True

        # Rungs 2 & 3 — log-marker scan, with WR-03 fail-closed on an unreadable log.
        if not kernel_error_hit:
            try:
                log_text = args.kernel_log.read_text()
            except (FileNotFoundError, OSError):
                # WR-03: fail CLOSED — never defer an unverifiable log to a stale result.json.
                status, failure_reason, kernel_error_hit = "FAILED", "kernel_error", True
            else:
                if scan_kernel_log(log_text):
                    status, failure_reason, kernel_error_hit = "FAILED", "kernel_error", True

    if not kernel_error_hit:
        # A non-zero run exit pre-classifies FAILED BEFORE reading result.json (a throwing run
        # can never be a success, even if a stale valid result.json exists).
        run_failed = args.run_exit_code is not None and args.run_exit_code != 0
        if run_failed:
            status = "FAILED"
            failure_reason = (
                "missing_result" if not result_path.exists() else "schema_invalid"
            )
        else:
            result, load_err = _read_json(result_path)
            if load_err is not None:
                status, failure_reason = "FAILED", load_err
            else:
                failure_reason = _validate_result(result, metric_name)
                if failure_reason is None:
                    status, valid_result = "SUCCESS", result
                else:
                    status = "FAILED"

    provenance = _build_provenance(ws, exp_dir, exp_rel, valid_result)

    # Build the canonical meta by MERGING the carried-forward stub fields with the
    # tooling-written numbers/status/provenance — on BOTH paths, so no record is ever
    # emitted without idea/hypothesis (criterion 2 / D-13).
    meta = {
        "schema_version": 1,
        "exp_id": carried["exp_id"],
        "created": carried["created"],
        "idea": carried["idea"],
        "hypothesis": carried["hypothesis"],
        "status": status,
        "failure_reason": failure_reason,
        "metric": None,
        "greater_is_better": None,
        "cv_scheme": None,
        "n_folds": None,
        "fold_scores": [],
        "cv_mean": None,
        "cv_std": None,
        "provenance": provenance,
        "result_path": f"{exp_rel}/result.json",
        "verdict_path": f"{exp_rel}/VERDICT.md",
        "artifacts": [],
    }
    if status == "SUCCESS" and valid_result is not None:
        range_entry = REGISTRY.get(valid_result["metric"], REGISTRY[metric_name])
        meta.update(
            {
                "metric": valid_result["metric"],
                "greater_is_better": valid_result.get(
                    "greater_is_better", range_entry["greater_is_better"]
                ),
                "cv_scheme": valid_result.get("cv_scheme"),
                "n_folds": valid_result["n_folds"],
                "fold_scores": valid_result["fold_scores"],
                "cv_mean": valid_result["cv_mean"],
                "cv_std": valid_result["cv_std"],
                "artifacts": valid_result.get("artifacts", []),
            }
        )

    # Kernel provenance merge (kernel path only, D-06/D-14 + CR-01 status audit). When
    # --kernel-log is set, this was a Kaggle-kernel run: pull the auditable provenance from
    # kernel_run.json (read ONCE above, reused here — never read twice) into meta so an
    # internet-ON kernel run is a VISIBLE, auditable exception (D-06) rather than a silent one.
    # The authoritative poll-written `status` is copied into meta["kernel"]["status"] on BOTH
    # the SUCCESS and the FAILED path, so WHY a run was classified is auditable. Fail-clear: a
    # missing or unreadable kernel_run.json never blocks the record — the meta simply carries
    # only the backend marker. The local path (no --kernel-log) is untouched, so its meta shape
    # is unchanged.
    if args.kernel_log is not None:
        if kernel_run is not None:
            kernel_block = {
                "backend": kernel_run.get("backend", "kernel"),
                "kernel_slug": kernel_run.get("kernel_slug"),
                "competition_slug": kernel_run.get("competition_slug"),
                "enable_internet": kernel_run.get("enable_internet"),
                "accelerator": kernel_run.get("accelerator"),
                "docker_image": kernel_run.get("docker_image"),
                "machine_shape": kernel_run.get("machine_shape"),
                "kernel_version": kernel_run.get("kernel_version"),
                "status": kernel_run.get("status"),
            }
            meta["kernel"] = kernel_block
        else:
            # No handoff file but this WAS a kernel run — still mark the backend so the record
            # is not mistaken for a local run.
            meta["kernel"] = {"backend": "kernel"}

    # Persist the canonical meta.json (overwrites the stub — an intentional finalize).
    stub_path.write_text(json.dumps(meta, indent=2) + "\n")

    # A VERDICT stub prompts the AI to write WHY (create-if-absent never clobbers a
    # verdict the AI already wrote on a re-record).
    create_if_absent(
        exp_dir / "VERDICT.md",
        _render_text("VERDICT.md.tmpl", {"exp_id": carried["exp_id"]}),
    )

    # Persist the derived ledger row for EVERY experiment — SUCCESS and FAILED alike
    # (MEM-01 / MEM-02). The canonical meta.json was just written above, so we regenerate
    # control/ledger.jsonl as a PURE FUNCTION of the meta folders via the same derivation
    # rebuild_ledger.py uses. This guarantees the incrementally-maintained ledger is
    # BYTE-IDENTICAL to a full rebuild of the identical folder set — the two can never
    # diverge, closing the gap where a FAILED experiment (correctly recorded in its own
    # meta.json) never reached the ledger and so stayed invisible to regen_strategy's
    # never-repeat tried-list. A FAILED row carries a null cv_mean (to_ledger_row derives
    # it straight from the meta) — a recorded fact, NEVER a fabricated score. Dedupe is
    # inherent (one folder → one row, so re-recording the same exp_id yields exactly one
    # row) and the write is atomic (tempfile + os.replace inside rebuild_ledger_file).
    rebuild_ledger_file(ws)

    # Stage the provenance-bearing files by EXPLICIT path (never a blanket stage).
    _stage_provenance(ws, f"{exp_rel}/experiment.py", f"{exp_rel}/meta.json")

    if status == "SUCCESS":
        print(f"recorded {carried['exp_id']} SUCCESS "
              f"(cv_mean={meta['cv_mean']}, metric={meta['metric']}). "
              f"Write the verdict at {exp_rel}/VERDICT.md.")
    else:
        print(f"recorded {carried['exp_id']} FAILED (reason={failure_reason}). "
              f"idea/hypothesis preserved; write WHY it failed at {exp_rel}/VERDICT.md. "
              f"A FAILED ledger row (null cv_mean, no fabricated score) was recorded so "
              f"the never-repeat tried-list sees this attempt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
