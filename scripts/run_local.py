#!/usr/bin/env python3
"""run_local.py — run a scaffolded experiment locally under `uv run --no-sync` (EXP-03, D-01).

The `run` entry point of the D-02 idempotent loop (`scaffold -> run -> record ->
regen_strategy`). It shells the scaffold-minted `experiment.py` inside the workspace ML env
and captures ONLY the child's exit code — it NEVER scrapes stdout for a score. The numbers
are TOOLING-WRITTEN: `experiment.py` emits `result.json` on disk, and `record_experiment.py`
(the next step) reads + validates that file (D-05). run_local is the request-response half:
"did the run succeed?" (exit code) and "where is result.json?" — nothing more.

Two load-bearing postures, copied verbatim from `analyze_data.run_adversarial_validation`
(the skill's only other `uv run` caller):

  * `--no-sync` (Pitfall 5): a workspace whose ML env is not synced degrades cleanly to a
    non-zero exit — NEVER a silent network package fetch. On a missing env the runner prints
    the `run \`uv sync\`` remediation and records nothing. Declare deps, validate, instruct —
    never install at runtime (CLAUDE.md).
  * timeout-bounded: a runaway experiment is a clean handled error, not a hang.

The recorder — not stdout — is the source of truth for the CV score (D-05). run_local
therefore returns the child exit code so the loop can pass it to `record_experiment.py`
(`--run-exit-code`), which pre-classifies a non-zero run as FAILED before even reading
result.json.

Portability (CLAUDE.md §Stack Patterns): stdlib-only, self-locating via `Path(__file__)`,
`--workspace`-driven, non-interactive (argparse in / exit-code out).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def _read_slug(config_path: Path) -> str | None:
    """Fail-clear read of `config.json.competition_slug`.

    Returns the slug (``""`` if unset), or ``None`` (after a clear message) when the file
    is present but not valid JSON — the same fail-clear posture the loop's setters use.
    A missing config is tolerated (slug ``""``): experiment.py carries a rendered default
    ``SLUG`` and only uses ``--slug`` to resolve its data dir.
    """
    if not config_path.exists():
        return ""
    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        print(
            f"cannot run: {config_path.name} is not valid JSON and was left untouched "
            f"(fail-clear): {exc}.",
            file=sys.stderr,
        )
        return None
    return config.get("competition_slug") or ""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="run_local.py",
        description="Run a scaffolded experiment.py locally under `uv run --no-sync`, "
                    "capturing ONLY the exit code (never a stdout score). Hands off to "
                    "record_experiment.py, which reads the on-disk result.json (EXP-03, D-05).",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    ap.add_argument("--exp-dir", required=True,
                    help="Experiment folder relative to the workspace "
                         "(e.g. experiments/exp-001).")
    ap.add_argument("--data-dir", default=None,
                    help="Override the resolved data dir (D-03). Default: experiment "
                         "auto-detects (Kaggle mount or workspace data/).")
    ap.add_argument("--timeout", type=int, default=600,
                    help="Seconds to bound the run before it is a clean handled error "
                         "(default: 600).")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()

    # The exp dir is workspace-relative; the subprocess runs with cwd=ws so a relative
    # path keeps result.json under the experiment folder (kernel-portable, D-03).
    exp_rel = args.exp_dir
    exp_dir = (ws / exp_rel).resolve()
    exp_py = exp_dir / "experiment.py"
    if not exp_py.is_file():
        print(
            f"cannot run: {exp_rel}/experiment.py not found — scaffold the experiment "
            f"first (scaffold_experiment.py).",
            file=sys.stderr,
        )
        return 1

    slug = _read_slug(ws / "control" / "config.json")
    if slug is None:
        return 1

    # `--no-sync` is LOAD-BEARING (Pitfall 5): a missing ML env yields a clean non-zero,
    # never a network install. Without `uv` on PATH there is no synced env at all — print
    # the remediation and record nothing.
    if shutil.which("uv") is None:
        print(
            "workspace ML env not synced — run `uv sync` (uv is not on PATH). "
            "Nothing was run and nothing was recorded.",
            file=sys.stderr,
        )
        return 1

    cmd = [
        "uv", "run", "--no-sync", "python", str(exp_py),
        "--exp-dir", str(exp_rel), "--slug", slug,
    ]
    if args.data_dir:
        cmd += ["--data-dir", str(args.data_dir)]

    try:
        proc = subprocess.run(
            cmd, cwd=str(ws), capture_output=True, text=True, timeout=args.timeout
        )
    except subprocess.TimeoutExpired:
        print(
            f"run timed out after {args.timeout}s — treated as a failed run "
            f"(no score recorded). Hand exit code 1 to record_experiment.py.",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"could not launch `uv run`: {exc} — nothing recorded.", file=sys.stderr)
        return 1

    exit_code = proc.returncode
    if exit_code != 0:
        # Surface the child's stderr tail for debugging — but NEVER parse stdout for a
        # score. A non-zero run is a FAILED experiment (possibly a missing/unsynced ML
        # env); the remediation for the env case is the same `uv sync`.
        tail = (proc.stderr or "").strip().splitlines()[-5:]
        if tail:
            print("\n".join(tail), file=sys.stderr)
        print(
            f"experiment.py exited {exit_code} — run recorded as FAILED. If the ML env "
            f"is absent, run `uv sync`. Pass --run-exit-code {exit_code} to "
            f"record_experiment.py.",
            file=sys.stderr,
        )
        return exit_code

    # Success: the child wrote result.json. The RECORDER (not this runner) reads and
    # validates it — we only report where it is (D-05).
    print(
        f"run ok (exit 0) — result.json expected at {exp_rel}/result.json. "
        f"Record it with: record_experiment.py --exp-dir {exp_rel} --run-exit-code 0."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
