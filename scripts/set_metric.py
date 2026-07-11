#!/usr/bin/env python3
"""set_metric.py — the D-08 metric setter (AI decides the enum, tooling writes it).

Mirrors the Phase-2 "AI decides / tooling writes" flow (``analyze_data.py --cv-scheme``,
``capture_competition.py --set-competition-type``): the AI reads the captured
``competition.md`` "Evaluation metric" prose, decides the enum, and passes ``--metric``;
this script writes ``config.json.metric``. The direction is LOOKED UP from
``metric_registry`` for known names — it can never be mistyped. ``custom`` is the only
name whose direction cannot be looked up, so it REQUIRES an explicit
``--greater-is-better`` / ``--no-greater-is-better`` (block, don't guess).

Stdlib-only (D-06): it imports the registry's NAME strings, never scikit-learn.
Self-locating + ``--workspace`` argparse in / exit-code out, non-interactive.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from init_workspace import set_config_field  # noqa: E402  (self-location must precede import)
from kaggle_gateway import LIMIT_NEEDS_USER  # noqa: E402
from metric_registry import REGISTRY, SUPPORTED  # noqa: E402

# Reserved block-don't-guess exit code for the SKILL precondition "metric uncaptured /
# unmappable in competition.md". Reuse the EX_CONFIG (78) convention so every
# "ask the user, don't guess" branch shares one value (kaggle_gateway.LIMIT_NEEDS_USER).
METRIC_NOT_CAPTURED = LIMIT_NEEDS_USER

# argparse-style usage error: a custom metric supplied without an explicit direction.
CUSTOM_NEEDS_DIRECTION = 2


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="set_metric.py",
        description="Commit config.json.metric (D-08). The AI passes the enum it decided "
                    "from the captured Evaluation-metric prose; tooling writes it and the "
                    "direction is looked up from the registry (never free-typed).",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    ap.add_argument("--metric", choices=SUPPORTED, required=True,
                    help="The AI's decision from the captured metric prose. Enum-validated.")
    ap.add_argument("--greater-is-better", action=argparse.BooleanOptionalAction, default=None,
                    help="Direction for a CUSTOM metric only "
                         "(--greater-is-better / --no-greater-is-better). REQUIRED when "
                         "--metric custom; IGNORED for known metrics (looked up from REGISTRY).")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    config_path = args.workspace / "control" / "config.json"

    if args.metric == "custom":
        if args.greater_is_better is None:
            print(
                "set_metric: --greater-is-better/--no-greater-is-better is REQUIRED for a "
                "custom metric — direction cannot be looked up (block, don't guess).",
                file=sys.stderr,
            )
            return CUSTOM_NEEDS_DIRECTION
        gib = args.greater_is_better
    else:
        # Known metric: direction is LOOKED UP from the registry, never taken from the
        # flag — so it cannot be mistyped into the numeric-affecting config field.
        gib = REGISTRY[args.metric]["greater_is_better"]

    # set_config_field is fail-clear: a missing/corrupt config.json is left byte-intact
    # and returns non-zero (MalformedControlJSON posture); 0 on a successful write.
    rc = set_config_field(config_path, ("metric",), {"name": args.metric, "greater_is_better": gib})
    if rc == 0:
        print(f"metric set to {args.metric} (greater_is_better={gib}).")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
