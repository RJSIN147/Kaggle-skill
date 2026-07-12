#!/usr/bin/env python3
"""poll_kernel.py — bounded, 429-safe status poller with detach-not-cancel (EXP-05, D-08/09/10).

The MIDDLE of the kernel loop
(`scaffold -> convert -> push -> POLL -> pull -> record`). It re-reads the
`kernel_run.json` handoff `push_kernel.py` wrote (D-03) — the `kernel_slug`
ONLY — and polls `kaggle kernels status <slug>` under an exponential,
capped, jittered backoff bounded by an overall wall-clock budget (~2h). It
NEVER re-pushes and NEVER cancels.

Three load-bearing postures:

  * Status parse is a VERIFIED-enum regex, NOT a case-insensitive grep (the
    shepsci anti-pattern): a `Failure message:` body that happens to embed the
    word COMPLETE never yields a false terminal token (Pitfall 2). An
    unparseable / non-zero poll is TRANSIENT — tolerated up to a
    consecutive-failure threshold, never misread as kernel death (Pitfall 3,
    D-10).
  * Backoff is exponential with a cap + full jitter (D-10): a single blip is
    retried; the loop never storms Kaggle with 429s and every sleep is
    budget-safe (jitter can never exceed the cap).
  * On OUR-side budget expiry with the kernel still IN_FLIGHT the poller
    DETACHES — it writes `kernel_run.json.status="DETACHED"` and returns a
    DISTINCT exit code, and it NEVER issues a `kernels cancel` (D-09). Re-running
    poll reattaches from the same handoff.

Every kaggle call is routed through the gateway (no-echo, timeout-bounded,
exit-code-only); a raw status/failure buffer is NEVER printed — it can carry a
token-shaped string — and on a persistent failure it is quarantined via
`dump_last_error` (D-11).

Portability + safety (CLAUDE.md): stdlib-only (argparse, json, re, time,
random), self-locating via `Path(__file__)`, `--workspace`-driven,
non-interactive (argparse in / exit-code out).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from kaggle_gateway import dump_last_error, run_kaggle  # noqa: E402

# --------------------------------------------------------------------------- #
# The VERIFIED KernelWorkerStatus enum (04-RESEARCH Code Examples — copy exactly).
# `kaggle kernels status` has NO --format json, so the token is parsed from the
# CLI's `... has status "KernelWorkerStatus.<TOKEN>"` prose line via regex.
# --------------------------------------------------------------------------- #
TERMINAL = {"COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED"}
IN_FLIGHT = {"QUEUED", "RUNNING", "NEW_SCRIPT", "CANCEL_REQUESTED"}

# Anchored on the literal `status "..."` token — tolerates both the
# `KernelWorkerStatus.NAME` and a bare `NAME` render (Assumption A2). Because the
# STATUS line is matched by its `status "` prefix, a `Failure message:` body that
# embeds COMPLETE/RUNNING can NEVER produce a false token (Pitfall 2).
_STATUS_RE = re.compile(r'status\s+"(?:KernelWorkerStatus\.)?([A-Z_]+)"')

# --------------------------------------------------------------------------- #
# Backoff constants (D-10) — exponential from ~10s, doubling, capped, full-jitter.
# --------------------------------------------------------------------------- #
BASE_DELAY = 10.0       # first inter-poll delay (seconds)
BACKOFF_MULTIPLIER = 2.0
MAX_DELAY = 120.0       # cap — no single sleep exceeds this (429-safe)
DEFAULT_BUDGET_S = 7200  # ~2h overall wall-clock budget (D-08)
DEFAULT_POLL_TIMEOUT = 60  # per-call run_kaggle timeout
MAX_CONSECUTIVE_ERRORS = 5  # transient blips tolerated before fail-closed (D-10)

# --------------------------------------------------------------------------- #
# Reserved exit codes — DISTINCT per outcome so the SKILL/caller can branch.
# 0 = COMPLETE; the rest are non-zero and mutually distinct. 124/127 are reserved
# by the gateway (timeout / CLI-missing) and surfaced verbatim.
# --------------------------------------------------------------------------- #
EXIT_COMPLETE = 0
EXIT_TERMINAL_FAIL = 2   # kernel reached ERROR or CANCEL_ACKNOWLEDGED
EXIT_DETACHED = 3        # our-side budget expired, kernel still in-flight (D-09)
EXIT_TRANSIENT_FAIL = 4  # consecutive transient errors exceeded the threshold


def classify_status(combined: str) -> str | None:
    """Return the KernelWorkerStatus token from a status buffer, or ``None``.

    ``None`` means the buffer was unparseable (a transient blip / garbage) and
    the caller MUST retry — it is NEVER a false terminal (D-10). The regex is
    anchored on the literal ``status "..."`` token, so a ``Failure message:``
    body embedding COMPLETE/RUNNING can never leak a false token (Pitfall 2).
    """
    m = _STATUS_RE.search(combined)
    return m.group(1) if m else None


def compute_delay(
    attempt: int,
    rng: random.Random | None = None,
    *,
    base: float = BASE_DELAY,
    multiplier: float = BACKOFF_MULTIPLIER,
    cap: float = MAX_DELAY,
) -> float:
    """Exponential-with-cap backoff for poll ``attempt`` (0-indexed), full-jitter.

    With ``rng is None`` returns the deterministic capped base
    ``min(base * multiplier**attempt, cap)`` (monotonic in ``attempt``, capped at
    ``cap``). With an ``rng`` returns ``rng.uniform(0, base)`` — FULL jitter, so the
    sleep is always in ``(0, base]`` and therefore can never exceed the cap
    (budget-safe, decorrelated across independent RNG states).

    ``base`` / ``multiplier`` / ``cap`` are KEYWORD-ONLY and DEFAULT to this module's
    kernel constants, so every existing caller is unaffected. They exist so a caller
    working at a DIFFERENT TIME SCALE reuses this (already-tested) jitter math instead
    of forking it: the Phase-5 leaderboard poll (``fetch_lb.poll_lb``) scores in
    seconds-to-minutes, not the hours a kernel takes, so it passes
    ``base=LB_BASE_DELAY`` / ``cap=LB_MAX_DELAY`` — a 10s first tick and a 2-minute
    sleep would be absurd against a 30-second scorer.
    """
    delay = min(base * (multiplier ** attempt), cap)
    if rng is None:
        return delay
    return rng.uniform(0.0, delay)


def poll_loop(
    status_fn,
    *,
    now,
    sleep,
    rng,
    budget_s,
    max_consecutive_errors,
    cancel_fn=None,
) -> dict:
    """Poll ``status_fn`` under bounded exponential backoff; return an outcome dict.

    ``status_fn()`` returns ``(rc, combined)`` (the ``run_kaggle`` shape). A poll
    is TERMINAL when ``rc == 0`` and ``classify_status`` yields a ``TERMINAL``
    token; IN_FLIGHT tokens keep polling; ``rc != 0`` or an unparseable buffer is
    a TRANSIENT error tolerated up to ``max_consecutive_errors`` consecutive
    failures (the counter resets on any clean parse — a single blip is never
    kernel death, Pitfall 3).

    Injected ``now`` / ``sleep`` / ``rng`` make the loop deterministic + testable.
    The loop stops at three points, each with a distinct ``reason``:

      * ``reason="terminal"``  — a TERMINAL token (``status`` = the token).
      * ``reason="budget"``    — OUR wall-clock budget expired with the kernel
        still in-flight ⇒ DETACH (``status="DETACHED"``, ``terminal=False``).
        ``cancel_fn`` is NEVER called (D-09).
      * ``reason="transient"`` — consecutive transient errors hit the threshold
        ⇒ fail-closed (``terminal=False``); ``last_out`` carries the last buffer
        for quarantine.

    ``cancel_fn`` is accepted ONLY to PROVE it is never invoked — detach, not
    cancel. It is deliberately unused on every code path.
    """
    start = now()
    consecutive_errors = 0
    attempt = 0
    last_out = ""
    last_token: str | None = None
    while True:
        rc, out = status_fn()
        last_out = out
        token = classify_status(out) if rc == 0 else None
        if token is None:
            # Transient blip (non-zero rc or unparseable buffer). Tolerate up to
            # the threshold, then fail-closed — never misread as kernel death.
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                return {
                    "terminal": False,
                    "status": "ERROR",
                    "reason": "transient",
                    "last_out": last_out,
                }
        else:
            consecutive_errors = 0  # a clean parse resets the blip counter
            last_token = token
            if token in TERMINAL:
                return {
                    "terminal": True,
                    "status": token,
                    "reason": "terminal",
                    "last_out": last_out,
                }
            # else: an IN_FLIGHT token — keep polling.

        # OUR-side budget check BEFORE sleeping: on expiry with an in-flight (or
        # still-indeterminate) kernel, DETACH — never cancel (D-09).
        if (now() - start) >= budget_s:
            return {
                "terminal": False,
                "status": "DETACHED",
                "reason": "budget",
                "last_out": last_out,
                "last_token": last_token,
            }

        sleep(compute_delay(attempt, rng=rng))
        attempt += 1


def _read_kernel_run(path: Path):
    """Fail-clear read of ``kernel_run.json`` (mirrors record_experiment._read_json).

    Returns the parsed dict, or ``None`` (after a clear message) when the file is
    absent or not valid JSON — the file is left byte-intact and the caller blocks.
    """
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        print(
            f"cannot poll: no {path} — push the kernel first (push_kernel.py).",
            file=sys.stderr,
        )
        return None
    except (json.JSONDecodeError, OSError) as exc:
        print(
            f"cannot poll: {path.name} is not valid JSON and was left untouched "
            f"(fail-clear): {exc}.",
            file=sys.stderr,
        )
        return None
    if not isinstance(data, dict):
        print(
            f"cannot poll: {path.name} is not a JSON object (fail-clear).",
            file=sys.stderr,
        )
        return None
    return data


def _write_status(path: Path, kernel_run: dict, status: str) -> None:
    """Merge ``status`` into ``kernel_run`` and write it back canonically.

    Same write style as push_kernel (``json.dumps(..., indent=2)+"\\n"``); all
    existing keys are preserved (D-03) — poll only flips ``status``.
    """
    kernel_run["status"] = status
    path.write_text(json.dumps(kernel_run, indent=2) + "\n")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="poll_kernel.py",
        description="Poll a pushed Kaggle kernel to a terminal status under a "
                    "bounded, jittered, 429-safe backoff. On our-side budget "
                    "expiry it DETACHES (never cancels) and is resumable "
                    "(EXP-05, D-08/09/10).",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    ap.add_argument("--exp-dir", required=True,
                    help="Experiment folder relative to the workspace "
                         "(e.g. experiments/exp-001).")
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET_S,
                    help="Overall wall-clock poll budget in seconds before a "
                         f"detach (default: {DEFAULT_BUDGET_S}, ~2h).")
    ap.add_argument("--poll-timeout", type=int, default=DEFAULT_POLL_TIMEOUT,
                    help="Per-call run_kaggle timeout in seconds "
                         f"(default: {DEFAULT_POLL_TIMEOUT}).")
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
            f"cannot poll: {run_path.name} has no kernel_slug — re-run "
            f"push_kernel.py.",
            file=sys.stderr,
        )
        return 1

    def _status_fn():
        # Route the status poll through the gateway (no-echo, timeout-bounded).
        # NEVER a bare subprocess and NEVER a cancel argv (detach-not-cancel).
        return run_kaggle("kernels", "status", slug, timeout=args.poll_timeout)

    result = poll_loop(
        _status_fn,
        now=time.monotonic,
        sleep=time.sleep,
        rng=random.Random(),
        budget_s=args.budget,
        max_consecutive_errors=MAX_CONSECUTIVE_ERRORS,
        cancel_fn=None,  # explicit: poll NEVER cancels (D-09).
    )

    reason = result["reason"]

    if reason == "terminal":
        token = result["status"]
        _write_status(run_path, kernel_run, token)
        if token == "COMPLETE":
            print(
                f"poll complete — {slug} reached COMPLETE. Pull its output with: "
                f"pull_kernel.py --workspace {ws} --exp-dir {exp_rel}."
            )
            return EXIT_COMPLETE
        # ERROR / CANCEL_ACKNOWLEDGED — a terminal, non-success end state.
        print(
            f"poll finished — {slug} reached terminal status {token}. Pull the "
            f"log for the failure reason with: pull_kernel.py --workspace {ws} "
            f"--exp-dir {exp_rel}.",
            file=sys.stderr,
        )
        return EXIT_TERMINAL_FAIL

    if reason == "budget":
        # DETACH, not cancel (D-09): record the detach and stop. A re-run
        # reattaches from the same handoff.
        _write_status(run_path, kernel_run, "DETACHED")
        print(
            f"poll budget ({args.budget}s) expired — {slug} is still running. "
            f"DETACHED (never cancelled); status set to DETACHED in "
            f"{exp_rel}/kernel_run.json. Re-run poll_kernel.py to reattach."
        )
        return EXIT_DETACHED

    # reason == "transient": consecutive transient errors exceeded the threshold.
    dump_last_error(ws, result.get("last_out", ""))
    print(
        f"cannot poll: {MAX_CONSECUTIVE_ERRORS} consecutive status errors — "
        "giving up (fail-closed). Raw output withheld (may carry a secret) and "
        "quarantined to control/raw/last-error.txt. Re-run poll_kernel.py to "
        "retry.",
        file=sys.stderr,
    )
    return EXIT_TRANSIENT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
