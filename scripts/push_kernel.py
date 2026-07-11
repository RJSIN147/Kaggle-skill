#!/usr/bin/env python3
"""push_kernel.py — generate kernel-metadata, push, and persist the handoff (EXP-05).

The `push` entry point of the kernel-path front half
(`scaffold -> convert -> push -> poll -> pull -> record`). It takes the notebook
`convert_notebook.py` produced and pushes it to a live Kaggle kernel, then writes
`experiments/exp-NNN/kernel_run.json` — the handoff state that `poll_kernel.py`
(D-08) and `pull_kernel.py` re-read WITHOUT re-pushing (D-03).

What it does, in order (every kaggle call routed through the gateway — no-echo,
timeout-bounded, exit-code-only; a raw status/quota/push buffer is NEVER printed):

  1. Fail-clear read of control/config.json → competition_slug (validated with
     `_SLUG_RE`; block a malformed non-empty slug, don't guess) + the EFFECTIVE
     internet flag from config["kernel"]["enable_internet"] (default false, D-06).
  2. Resolve <username> via `kaggle config view` (match the `- username:` line;
     NEVER echo the buffer). The kernel id is built ONLY from the validated slug +
     parsed username + exp-NNN — never from Kaggle prose (V5 no-derive).
  3. Render kernel-metadata.json (enable_internet rendered explicitly; default
     false — an internet-on push is an auditable exception recorded in kernel_run).
  4. D-13 NON-BLOCKING quota heads-up: a best-effort `kaggle quota` note that is
     ALWAYS skipped on any failure and NEVER blocks the push.
  5. `kaggle kernels push -p <exp_dir>` (optional --accelerator override).
  6. Best-effort parse of the auto-assigned kernel version from the push output
     (provenance-only, D-05 — NEVER used to build a path/command; null on no match).
  7. Write kernel_run.json (json.dumps(..., indent=2)+"\n") with the effective
     internet flag recorded (D-06 guard) and status="PENDING".

Portability + safety (CLAUDE.md): stdlib-only, self-locating via `Path(__file__)`,
`--workspace`-driven, non-interactive (argparse in / exit-code out).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Charset gates for values that enter the kernel id (CR-01 / V5 defense-in-depth).
# A non-empty slug MUST be a well-formed Kaggle slug before it enters the id (block,
# don't guess) — mirrors scaffold_experiment._SLUG_RE. The username comes from Kaggle
# prose (`config view`); constrain it too so nothing exotic rides into the id/push.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_USERNAME_LINE_RE = re.compile(r"^\s*-\s*username:\s*(\S+)\s*$", re.MULTILINE)
# Provenance-only version scrape from the push output. NEVER used to build a path or
# command (V5 no-derive) — just recorded in kernel_run.json for D-05 traceability.
_VERSION_RE = re.compile(r"[Vv]ersion\s+(\d+)")

# Verified accelerator IDs (RESEARCH). The T4×2 string is UNVERIFIED (Assumption A1)
# and is deliberately NOT a hard default — the template's enable_gpu:true is always
# valid; --accelerator is an explicit opt-in override.
_ACCELERATORS = ("NvidiaTeslaT4", "NvidiaTeslaP100")

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from init_workspace import _iso_now, _render_text  # noqa: E402
from kaggle_gateway import dump_last_error, run_kaggle  # noqa: E402


def _read_control_json(path: Path):
    """Fail-clear read of a control-plane JSON leaf (mirrors scaffold_experiment).

    Returns the parsed dict, or None (after a clear message) when the file is absent
    or not valid JSON — the file is left byte-intact and the caller blocks non-zero.
    """
    if not path.exists():
        print(f"cannot push: no {path} — run init first.", file=sys.stderr)
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(
            f"cannot push: {path.name} is not valid JSON and was left untouched "
            f"(fail-clear): {exc}.",
            file=sys.stderr,
        )
        return None


def _resolve_username(ws: Path) -> str | None:
    """Resolve the Kaggle username via `kaggle config view` (D-05).

    Matches the `- username: <name>` line; the raw buffer is NEVER echoed (it can
    carry a token-shaped string). On a missing CLI / timeout / non-zero rc / no
    username line, the raw output is quarantined via dump_last_error and None is
    returned (the caller fails closed).
    """
    rc, out = run_kaggle("config", "view", timeout=30)
    if rc == 127:
        print(
            "cannot push: the kaggle CLI is not on PATH — install it and run "
            "`kaggle config view` to confirm auth.",
            file=sys.stderr,
        )
        return None
    if rc == 124:
        print("cannot push: `kaggle config view` timed out.", file=sys.stderr)
        return None
    if rc != 0:
        dump_last_error(ws, out)
        print(
            "cannot push: `kaggle config view` failed — check credentials. Raw "
            "output withheld (may carry a secret) and quarantined to "
            "control/raw/last-error.txt.",
            file=sys.stderr,
        )
        return None
    m = _USERNAME_LINE_RE.search(out)
    if not m:
        dump_last_error(ws, out)
        print(
            "cannot push: could not read a username from `kaggle config view` "
            "output (withheld). Confirm auth with `kaggle config view`.",
            file=sys.stderr,
        )
        return None
    username = m.group(1)
    if not _USERNAME_RE.match(username):
        # Defense-in-depth: refuse an exotic username before it enters the kernel id.
        print(
            "cannot push: resolved username is not a well-formed Kaggle handle — "
            "refusing to build a kernel id from it (block, don't guess).",
            file=sys.stderr,
        )
        return None
    return username


def _quota_heads_up() -> None:
    """D-13 NON-BLOCKING GPU-quota heads-up. NEVER blocks or fails the push.

    Best-effort: one `kaggle quota` call; on ANY failure (missing CLI, timeout,
    non-zero rc, unparseable JSON) the note is silently skipped. The raw buffer is
    never echoed — only a framework-authored summary line derived from parsed fields.
    """
    try:
        rc, out = run_kaggle("quota", "--format", "json", timeout=30)
        if rc != 0:
            return
        start = out.find("{")
        arr = out.find("[")
        if arr != -1 and (start == -1 or arr < start):
            start = arr
        if start == -1:
            return
        parsed = json.loads(out[start:])
        rows = parsed if isinstance(parsed, list) else [parsed]
        for row in rows:
            if not isinstance(row, dict):
                continue
            remaining = row.get("remaining")
            resource = row.get("resource", "compute")
            if isinstance(remaining, (int, float)):
                print(
                    f"quota heads-up (non-blocking): ~{remaining}h {resource} "
                    f"remaining this period. The push proceeds regardless."
                )
                return
    except Exception:
        # A quota probe must NEVER change the push outcome (D-13). Swallow everything.
        return


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="push_kernel.py",
        description="Generate kernel-metadata.json, push the experiment notebook to "
                    "a private GPU kernel, and persist kernel_run.json handoff state "
                    "(EXP-05, D-04/05/06).",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    ap.add_argument("--exp-dir", required=True,
                    help="Experiment folder relative to the workspace "
                         "(e.g. experiments/exp-001).")
    ap.add_argument("--accelerator", default=None, choices=_ACCELERATORS,
                    help="Optional accelerator override (verified IDs only). Default: "
                         "the template's enable_gpu:true.")
    ap.add_argument("--timeout", type=int, default=300,
                    help="Seconds to bound the push before it is a clean handled "
                         "error (default: 300).")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()

    exp_rel = args.exp_dir
    exp_dir = (ws / exp_rel).resolve()
    exp_id = Path(exp_rel).name  # e.g. "exp-001"
    if not (exp_dir / "experiment.ipynb").is_file():
        print(
            f"cannot push: {exp_rel}/experiment.ipynb not found — run "
            f"convert_notebook.py first.",
            file=sys.stderr,
        )
        return 1

    config = _read_control_json(ws / "control" / "config.json")
    if config is None:
        return 1

    slug = config.get("competition_slug") or ""
    if not slug or not _SLUG_RE.match(slug):
        print(
            f"cannot push: competition_slug {slug!r} is missing or not a valid "
            f"Kaggle slug (expected {_SLUG_RE.pattern}).",
            file=sys.stderr,
        )
        return 1

    # Effective internet flag (D-06): default false when the kernel leaf is absent.
    kernel_cfg = config.get("kernel")
    enable_internet = bool((kernel_cfg or {}).get("enable_internet", False))

    username = _resolve_username(ws)
    if username is None:
        return 1

    kernel_slug = f"{username}/{slug}-{exp_id}"
    title = f"{slug}-{exp_id}"

    # Render kernel-metadata.json — a per-push BUILD ARTIFACT: write/overwrite it,
    # never create_if_absent. enable_internet is rendered as a bare JSON bool literal.
    metadata = _render_text(
        "kernel-metadata.json.tmpl",
        {
            "KERNEL_ID": kernel_slug,
            "TITLE": title,
            "ENABLE_INTERNET": "true" if enable_internet else "false",
            "COMPETITION_SLUG": slug,
        },
    )
    (exp_dir / "kernel-metadata.json").write_text(metadata)

    # D-13 non-blocking quota heads-up BEFORE the push (never blocks it).
    _quota_heads_up()

    push_argv = ["kernels", "push", "-p", str(exp_dir)]
    if args.accelerator:
        push_argv += ["--accelerator", args.accelerator]
    rc, out = run_kaggle(*push_argv, timeout=args.timeout)
    if rc == 127:
        print(
            "cannot push: the kaggle CLI is not on PATH — install it and retry.",
            file=sys.stderr,
        )
        return rc
    if rc == 124:
        print(
            f"cannot push: `kaggle kernels push` timed out after {args.timeout}s.",
            file=sys.stderr,
        )
        return rc
    if rc != 0:
        dump_last_error(ws, out)
        print(
            "cannot push: `kaggle kernels push` failed. Raw output withheld (may "
            "carry a secret) and quarantined to control/raw/last-error.txt.",
            file=sys.stderr,
        )
        return rc

    # Provenance-only version scrape (D-05): null when unparseable. NEVER used to
    # build a path/command (V5). The exact push-output version string is unverified
    # (Assumption A4), so a miss is expected and harmless.
    vm = _VERSION_RE.search(out or "")
    kernel_version = int(vm.group(1)) if vm else None

    kernel_run = {
        "exp_id": exp_id,
        "kernel_slug": kernel_slug,
        "kernel_version": kernel_version,
        "code_file": "experiment.ipynb",
        "competition_slug": slug,
        "accelerator": args.accelerator or "enable_gpu",
        "enable_internet": enable_internet,
        "pushed_at": _iso_now(),
        "status": "PENDING",
        "backend": "kernel",
        "docker_image": None,
        "machine_shape": None,
    }
    (exp_dir / "kernel_run.json").write_text(json.dumps(kernel_run, indent=2) + "\n")

    print(
        f"push ok — {kernel_slug} submitted. Handoff written to "
        f"{exp_rel}/kernel_run.json. Poll it with: poll_kernel.py "
        f"--workspace {ws} --exp-dir {exp_rel}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
