#!/usr/bin/env python3
"""pull_kernel.py — fetch kernel output + log + image provenance (EXP-05, D-14).

The FETCH step of the kernel loop
(`scaffold -> convert -> push -> poll -> PULL -> record`). Once `poll_kernel.py`
reports COMPLETE, this pulls the kernel's output into `experiments/exp-NNN`
using the SAME `result.json` + `artifacts/` contract the local runner produces,
writes the execution log to `kernel_log.txt` (staged for the recorder's
silent-failure scan), and records image/version provenance
(`docker_image` + `machine_shape`) into `kernel_run.json` (D-14 record-don't-pin).

Three gateway calls (each via `run_kaggle` — no-echo, timeout-bounded,
exit-code-only):

  1. `kernels output <slug> -p <exp-dir> --force` → result.json, oof.npy, rendered
     .ipynb as FLAT files. Kernel output is NOT a compressed archive — there is
     deliberately NO archive-extraction / zip-slip logic here (contrast
     download_data.py, which DOES extract a competition archive; that logic is NOT
     reused).
  2. `kernels logs <slug>` → the full execution log string, written to
     `exp-dir/kernel_log.txt` and NEVER echoed. The log is Kaggle-sourced
     UNTRUSTED text (possibly large / token-shaped): it crosses to the recorder by
     PATH only and no executed path/command is ever derived from its content
     (V5/V7 no-derive).
  3. `kernels pull <slug> -m -p <tmp>` → regenerated metadata whose `docker_image`
     (gcr.io/…@sha256:) + `machine_shape` are MERGED into `kernel_run.json`,
     preserving every existing key (D-14: we RECORD the image, we never PIN it).

The output + log fetches are REQUIRED (they are the result contract); a provenance
hiccup is NON-BLOCKING (record-don't-pin) — it degrades to a null image rather
than losing the already-pulled output. On a required-step failure the reserved
gateway codes get their own remediation (127 CLI-missing / 124 timeout), else the
raw buffer is quarantined via `dump_last_error` and the pull fails closed — the
buffer is NEVER printed.

Portability + safety (CLAUDE.md): stdlib-only, self-locating via `Path(__file__)`,
`--workspace`-driven, non-interactive (argparse in / exit-code out). It never runs
`git add -A` — only kernel_run.json is tracked; artifacts + kernel_log.txt are
gitignored (see scripts/templates/gitignore.tmpl).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from kaggle_gateway import _append_line_if_absent, dump_last_error, run_kaggle  # noqa: E402

# Runtime gitignore retrofit lines (mirror gitignore.tmpl) — guarantee the ignore
# for an ALREADY-scaffolded workspace whose .gitignore predates this pattern.
_LOG_IGNORE_REL = "experiments/*/kernel_log.txt"
_NPY_IGNORE_REL = "experiments/*/*.npy"

# Candidate keys for image/version provenance in the regenerated metadata. Kept
# provenance-only (V5): these values are RECORDED into kernel_run.json and NEVER
# used to build a path or command.
_PROVENANCE_KEYS = ("docker_image", "machine_shape")


def _read_kernel_run(path: Path):
    """Fail-clear read of ``kernel_run.json`` (mirrors record_experiment._read_json).

    Returns the parsed dict, or ``None`` (after a clear message) when the file is
    absent or not valid JSON — the file is left byte-intact and the caller blocks.
    """
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        print(
            f"cannot pull: no {path} — push + poll the kernel first.",
            file=sys.stderr,
        )
        return None
    except (json.JSONDecodeError, OSError) as exc:
        print(
            f"cannot pull: {path.name} is not valid JSON and was left untouched "
            f"(fail-clear): {exc}.",
            file=sys.stderr,
        )
        return None
    if not isinstance(data, dict):
        print(
            f"cannot pull: {path.name} is not a JSON object (fail-clear).",
            file=sys.stderr,
        )
        return None
    return data


def _handle_required_rc(ws: Path, rc: int, out: str, what: str) -> int | None:
    """Map a required-step ``run_kaggle`` result to an exit code, or ``None`` on ok.

    Reserved gateway codes get their own remediation (127 = CLI missing, 124 =
    timeout); any other non-zero quarantines the raw buffer via ``dump_last_error``
    and fails closed. The buffer is NEVER printed (it can carry a secret).
    """
    if rc == 127:
        print(
            f"cannot pull: the kaggle CLI is not on PATH ({what}) — install it and "
            "retry.",
            file=sys.stderr,
        )
        return rc
    if rc == 124:
        print(f"cannot pull: `kaggle kernels {what}` timed out.", file=sys.stderr)
        return rc
    if rc != 0:
        dump_last_error(ws, out)
        print(
            f"cannot pull: `kaggle kernels {what}` failed. Raw output withheld "
            "(may carry a secret) and quarantined to control/raw/last-error.txt.",
            file=sys.stderr,
        )
        return rc
    return None


def _merge_provenance(run_path: Path, kernel_run: dict, timeout: int, slug: str,
                      ws: Path) -> None:
    """Best-effort merge of image/version provenance into ``kernel_run.json`` (D-14).

    Pulls the regenerated metadata via ``kernels pull -m`` into a temp dir and
    merges ``docker_image`` + ``machine_shape`` into ``kernel_run.json``, preserving
    every existing key. This is RECORD-don't-pin provenance, so ANY failure (missing
    CLI, timeout, non-zero rc, absent metadata / keys) degrades silently to the
    existing null values — it never blocks or fails the pull. The pulled values are
    NEVER used to derive a path/command (V5).
    """
    try:
        with tempfile.TemporaryDirectory() as tmp:
            rc, out = run_kaggle(
                "kernels", "pull", slug, "-m", "-p", tmp, timeout=timeout
            )
            if rc != 0:
                return
            meta_path = Path(tmp) / "kernel-metadata.json"
            if not meta_path.is_file():
                return
            meta = json.loads(meta_path.read_text())
            if not isinstance(meta, dict):
                return
            changed = False
            for key in _PROVENANCE_KEYS:
                value = meta.get(key)
                if value is not None:
                    kernel_run[key] = value
                    changed = True
            if changed:
                run_path.write_text(json.dumps(kernel_run, indent=2) + "\n")
    except Exception:
        # Provenance is record-don't-pin (D-14): a probe must NEVER change the pull
        # outcome. Swallow everything — the null image/shape stays.
        return


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="pull_kernel.py",
        description="Pull a completed Kaggle kernel's output (result.json + "
                    "artifacts + rendered .ipynb) into experiments/exp-NNN, write "
                    "the execution log to kernel_log.txt for the recorder, and "
                    "record image provenance in kernel_run.json (EXP-05, D-14).",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    ap.add_argument("--exp-dir", required=True,
                    help="Experiment folder relative to the workspace "
                         "(e.g. experiments/exp-001).")
    ap.add_argument("--timeout", type=int, default=300,
                    help="Seconds to bound each kaggle call before it is a clean "
                         "handled error (default: 300).")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()

    exp_rel = args.exp_dir
    exp_dir = (ws / exp_rel).resolve()
    run_path = exp_dir / "kernel_run.json"

    kernel_run = _read_kernel_run(run_path)
    if kernel_run is None:
        return 1

    slug = kernel_run.get("kernel_slug")
    if not isinstance(slug, str) or not slug:
        print(
            f"cannot pull: {run_path.name} has no kernel_slug — re-run "
            f"push_kernel.py.",
            file=sys.stderr,
        )
        return 1

    # Ensure the artifact + log ignores are present for an already-scaffolded
    # workspace BEFORE writing any pulled (possibly heavy/untrusted) files.
    _append_line_if_absent(ws / ".gitignore", _LOG_IGNORE_REL)
    _append_line_if_absent(ws / ".gitignore", _NPY_IGNORE_REL)

    # 1) REQUIRED: pull the output as FLAT files (result.json, oof.npy, .ipynb).
    #    No archive extraction — kernel output is not compressed (no zip-slip here).
    rc, out = run_kaggle(
        "kernels", "output", slug, "-p", str(exp_dir), "--force", timeout=args.timeout
    )
    failed = _handle_required_rc(ws, rc, out, "output")
    if failed is not None:
        return failed

    # 2) REQUIRED: pull the execution log and WRITE it to kernel_log.txt — never
    #    echo it (Kaggle-sourced untrusted text; V5/V7). The recorder consumes the
    #    PATH, not the content.
    rc, out = run_kaggle("kernels", "logs", slug, timeout=args.timeout)
    failed = _handle_required_rc(ws, rc, out, "logs")
    if failed is not None:
        return failed
    log_path = exp_dir / "kernel_log.txt"
    log_path.write_text(out)

    # 3) NON-BLOCKING (D-14 record-don't-pin): merge docker_image + machine_shape
    #    provenance into kernel_run.json; any failure degrades to a null image.
    _merge_provenance(run_path, kernel_run, args.timeout, slug, ws)

    print(
        f"pull ok — {slug} output landed in {exp_rel}/ (result.json + artifacts + "
        f"rendered .ipynb). Execution log written to {exp_rel}/kernel_log.txt. "
        f"Record it with: record_experiment.py --exp-dir {exp_rel} "
        f"--kernel-log {exp_rel}/kernel_log.txt."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
