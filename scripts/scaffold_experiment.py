#!/usr/bin/env python3
"""scaffold_experiment.py — mint a fresh exp-NNN and render its experiment.py (D-02).

The `scaffold` entry point of the D-02 separate-idempotent-entry-points cycle
(`scaffold_experiment -> run -> record -> regen_strategy`). It:

  * reads the id cursor `state.json.next_exp_id` (starts at 1) and mints a zero-padded
    `exp-NNN` folder with an `artifacts/` dir;
  * renders `templates/experiment.py.tmpl` into `experiments/exp-NNN/experiment.py`,
    injecting the RESOLVED `registry_entry` literal for the competition's configured
    metric (Blocker-2) plus the CV scheme — so the minted script is self-contained and
    kernel-portable (imports NO skill code; scripts/metric_registry.py stays the single
    source of truth, the experiment only ever holds a per-experiment SNAPSHOT);
  * writes a `meta.json` STUB carrying the AI's idea/hypothesis/created/exp_id (numeric
    result fields stay null — the recorder fills them, D-05);
  * advances the cursor via `set_config_field(state, ("next_exp_id",), n + 1)`.

Idempotent (D-02): `create_if_absent` never clobbers an existing `experiment.py`, and the
cursor is advanced only AFTER a successful mint so an id is never re-consumed. A
missing/corrupt control JSON is left byte-intact and blocks with a non-zero exit (the
MalformedControlJSON fail-clear posture) — NOTHING is created in that case.

Stdlib-only (D-14): `metric_registry` is stdlib (it only NAMES the sklearn callable); the
ML code lives entirely in the template this script writes. Self-locating + `--workspace`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Charset gate for values that get rendered into the executed experiment.py (CR-01).
# The primary defense is repr()-quoting every rendered literal (so ANY value is inert);
# these gates are defense-in-depth — block a malformed slug / unknown cv scheme early
# (block, don't guess) rather than mint a harness from a suspicious control-plane value.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_CV_SCHEMES = ("KFold", "StratifiedKFold", "GroupKFold", "TimeSeriesSplit")
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from init_workspace import (  # noqa: E402  (self-location must precede import)
    _iso_now,
    _render_text,
    create_if_absent,
    set_config_field,
)
from metric_registry import REGISTRY  # noqa: E402


def _read_control_json(path: Path):
    """Fail-clear read of a control-plane JSON leaf file.

    Returns the parsed dict, or None (after printing a clear message) when the file is
    absent or not valid JSON — the same MalformedControlJSON posture the setters use, so
    a corrupt file is left byte-intact and the caller blocks with a non-zero exit.
    """
    if not path.exists():
        print(f"cannot scaffold: no {path} — run init first.", file=sys.stderr)
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(
            f"cannot scaffold: {path.name} is not valid JSON and was left untouched "
            f"(fail-clear, D-02): {exc}.",
            file=sys.stderr,
        )
        return None


def _json_inner(value: str) -> str:
    """JSON-escape a string WITHOUT the surrounding quotes (the template supplies them)."""
    return json.dumps(value)[1:-1]


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="scaffold_experiment.py",
        description="Mint a fresh exp-NNN experiment folder and render its experiment.py "
                    "from the harness template (EXP-01, D-02).",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    ap.add_argument("--idea", required=True,
                    help="The AI's idea for this experiment (one or two sentences). "
                         "Passed straight into the meta stub — EXP-01.")
    ap.add_argument("--hypothesis", required=True,
                    help="The falsifiable claim this run tests. Passed into the meta stub.")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()
    config_path = ws / "control" / "config.json"
    state_path = ws / "control" / "state.json"

    # Fail-clear reads FIRST — before any folder is created — so a corrupt control JSON
    # blocks with nothing written (and the cursor never advances).
    config = _read_control_json(config_path)
    if config is None:
        return 1
    state = _read_control_json(state_path)
    if state is None:
        return 1

    # Metric contract (D-08): resolve REGISTRY[config metric name] AT SCAFFOLD TIME and
    # render the resolved entry as a literal into experiment.py (single source of truth
    # stays scripts/metric_registry.py). Block, don't guess, if it is missing/unknown.
    metric_field = config.get("metric")
    if not isinstance(metric_field, dict) or metric_field.get("name") is None:
        print(
            "cannot scaffold: config.json.metric is not set — run set_metric.py first (D-08).",
            file=sys.stderr,
        )
        return 1
    metric_name = metric_field["name"]
    if metric_name not in REGISTRY:
        print(
            f"cannot scaffold: unknown metric '{metric_name}' (not in metric_registry).",
            file=sys.stderr,
        )
        return 1
    registry_entry = REGISTRY[metric_name]

    cv_scheme = (config.get("cv") or {}).get("scheme")
    if cv_scheme is None:
        print(
            "cannot scaffold: config.json.cv.scheme is not set — decide the CV scheme "
            "first (D-05).",
            file=sys.stderr,
        )
        return 1
    # Re-validate the CV scheme against the allowed enum before rendering it into the
    # executed harness (block, don't guess — CR-01 defense-in-depth).
    if cv_scheme not in _CV_SCHEMES:
        print(
            f"cannot scaffold: unknown cv scheme '{cv_scheme}' — expected one of "
            f"{_CV_SCHEMES}.",
            file=sys.stderr,
        )
        return 1

    slug = config.get("competition_slug") or ""
    # A non-empty slug must be a well-formed Kaggle slug. An empty slug is tolerated
    # (renders to an inert ''); a malformed non-empty slug blocks (CR-01 defense-in-depth).
    if slug and not _SLUG_RE.match(slug):
        print(
            f"cannot scaffold: competition_slug {slug!r} is not a valid Kaggle slug "
            f"(expected {_SLUG_RE.pattern}).",
            file=sys.stderr,
        )
        return 1

    # Id cursor: read-mint-then-advance. A non-int/invalid cursor blocks.
    n = state.get("next_exp_id")
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        print(
            f"cannot scaffold: state.json.next_exp_id is invalid ({n!r}) — expected a "
            f"positive integer.",
            file=sys.stderr,
        )
        return 1

    exp_id = f"exp-{n:03d}"
    exp_dir = ws / "experiments" / exp_id
    (exp_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    # Render the harness template with the resolved registry_entry literal + cv scheme.
    # Every config-sourced value is rendered as a PROPERLY QUOTED Python literal via
    # repr() — never interpolated raw inside hand-written quotes — so no slug/cv_scheme/
    # metric value can break out of its string literal and inject code into the harness
    # that run_local.py executes (CR-01). Mirrors how registry_entry is already emitted.
    experiment_src = _render_text(
        "experiment.py.tmpl",
        {
            "slug_literal": repr(slug),
            "exp_id_literal": repr(exp_id),
            "exp_dir_literal": repr(f"experiments/{exp_id}"),
            "cv_scheme_literal": repr(cv_scheme),
            "metric_name_literal": repr(metric_name),
            "registry_entry": repr(registry_entry),
        },
    )
    create_if_absent(exp_dir / "experiment.py", experiment_src)

    # Meta STUB: idea/hypothesis/created/exp_id filled; numeric fields stay null/[] (the
    # recorder fills them and carries these stub fields forward — 03-04). status="pending"
    # until the recorder sets SUCCESS/FAILED.
    meta_src = _render_text(
        "meta.json.tmpl",
        {
            "EXP_ID": exp_id,
            "CREATED": _iso_now(),
            "IDEA": _json_inner(args.idea),
            "HYPOTHESIS": _json_inner(args.hypothesis),
            "STATUS": "pending",
            "RUN_ID": "",
            "ARTIFACT_HASH": "",
            "GIT_COMMIT": "",
            "SEED": "",
            "RESULT_PATH": f"experiments/{exp_id}/result.json",
            "VERDICT_PATH": f"experiments/{exp_id}/VERDICT.md",
        },
    )
    create_if_absent(exp_dir / "meta.json", meta_src)

    # Advance the id cursor ONLY after a successful mint (idempotent — never re-consumes
    # an id). set_config_field is fail-clear on state.json too.
    rc = set_config_field(state_path, ("next_exp_id",), n + 1)
    if rc != 0:
        return rc

    print(f"scaffolded {exp_id} at experiments/{exp_id} (metric={metric_name}, cv={cv_scheme}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
