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
import csv
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Phase 2 wrote the sample-submission filename here (capture_competition.py). REUSE the
# signal — never re-derive the heuristic, and never hard-code a guessed
# `sample_submission.csv` (titanic's file is `gender_submission.csv`).
TYPE_SIGNALS_REL = "control/raw/competition-type-signals.json"

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


def _find_sample_submission(ws: Path) -> Path | None:
    """Locate the competition's sample-submission file under ``data/`` (the R4 ladder).

    1. ``control/raw/competition-type-signals.json`` -> ``signals.submission_csv_in_manifest``
       (Phase 2's heuristic — CONSUMED, not re-derived), if that file exists under ``data/``.
    2. Else a case-insensitive ``data/*submission*.csv`` scan.
    3. Else None -> the header is unresolvable and NOTHING is guessed.

    ⚠ The Phase 2 signal takes the FIRST manifest match, so a competition shipping several
    ``*submission*.csv`` files could mis-pick. main() PRINTS the chosen file so a human can
    spot a wrong pick, and check_submission.py's validation against it is the real backstop.
    """
    data_dir = ws / "data"
    signals_path = ws / TYPE_SIGNALS_REL
    if signals_path.exists():
        try:
            signals = (json.loads(signals_path.read_text()) or {}).get("signals") or {}
        except (json.JSONDecodeError, AttributeError):
            signals = {}  # a corrupt/odd signals file degrades to the glob — never blocks
        named = signals.get("submission_csv_in_manifest")
        if isinstance(named, str) and named:
            # Basename only — the signal is a manifest name, never a path to follow.
            candidate = data_dir / Path(named).name
            if candidate.is_file():
                return candidate

    if data_dir.is_dir():
        for path in sorted(data_dir.iterdir()):
            name = path.name.lower()
            if path.is_file() and "submission" in name and name.endswith(".csv"):
                return path
    return None


def _read_submission_header(path: Path) -> list[str]:
    """Return the sample file's header row (stdlib csv), or [] if it has none."""
    try:
        with path.open(newline="") as fh:
            return next(csv.reader(fh), [])
    except OSError:
        return []


def _render_submission_header(src: str, id_column, target_column) -> str | None:
    """Rewrite the template's ``ID_COLUMN`` / ``TARGET_COLUMN`` default lines with literals.

    The harness WRITES submission.csv, and on a Kaggle kernel it can read neither
    ``control/`` nor any skill code (D-03) — so the header must be baked in as a LITERAL at
    scaffold time, exactly like SLUG / EXP_ID / METRIC_NAME / CV_SCHEME. Values are rendered
    via ``repr()`` (a lambda replacement, so a backslash in a header can never be read as a
    regex escape), keeping every config/data-sourced literal inert (CR-01).

    None => the harness skips submission emission entirely and still records a valid CV
    result (graceful, D-09). Returns None if the template no longer carries the lines to
    rewrite (block, don't silently emit a header-less harness).
    """
    for name, value in (("ID_COLUMN", id_column), ("TARGET_COLUMN", target_column)):
        src, n = re.subn(
            rf"(?m)^{name} = .*$",
            lambda _m, v=value, k=name: f"{k} = {v!r}",
            src,
            count=1,
        )
        if n != 1:
            return None
    return src


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

    # Submission header (D-09): read the id/target column names off the competition's OWN
    # sample-submission file so the harness writes a correctly-headed submission.csv by
    # construction. Unresolvable => both render as None => no submission is emitted (the
    # experiment still records a valid CV result). NEVER guess a header.
    sample_path = _find_sample_submission(ws)
    id_column = target_column = None
    header: list[str] = []
    if sample_path is not None:
        header = _read_submission_header(sample_path)
    if len(header) >= 2:
        id_column, target_column = header[0], header[1]

    exp_id = f"exp-{n:03d}"
    exp_dir = ws / "experiments" / exp_id

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
    rendered = _render_submission_header(experiment_src, id_column, target_column)
    if rendered is None:
        print(
            "cannot scaffold: experiment.py.tmpl no longer carries the ID_COLUMN / "
            "TARGET_COLUMN submission-header lines to render (block, don't guess).",
            file=sys.stderr,
        )
        return 1

    (exp_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    create_if_absent(exp_dir / "experiment.py", rendered)

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

    # Always say WHERE the submission header came from — the Phase 2 signal takes the first
    # manifest match, so a human must be able to spot a wrong pick.
    if id_column is None:
        print(
            "  submission header: NONE found (no data/*submission*.csv) — the experiment "
            "will record a CV result but emit no submission.csv (D-09)."
        )
    else:
        print(
            f"  submission header: id={id_column!r}, target={target_column!r} "
            f"(read from data/{sample_path.name})."
        )
        if len(header) > 2:
            print(
                f"  NOTE: {sample_path.name} has {len(header)} columns (multi-target). "
                f"Rendered columns 0 and 1; override via run_cv(submission_agg=...) or a "
                f"hand-edited writer if that is wrong."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
