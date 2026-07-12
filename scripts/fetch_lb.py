#!/usr/bin/env python3
"""fetch_lb.py — the D-03 detach fallback and the self-healing reconcile (SCORE-01).

⚠ THIS SCRIPT CAN NEVER SPEND A SLOT. It only ever READS Kaggle
(``competitions submissions``). The irreversible surface lives in ``submit.py`` and
nowhere else; nothing here can issue an upload argv.

It is the exact analogue of ``poll_kernel.py``'s resume posture: a poll is bounded by
OUR wall clock, and on expiry it DETACHES rather than cancelling — then a later run
RE-READS the handoff and finishes the job, never re-doing the side effect. The
leaderboard handoff already exists and is cleaner than ``kernel_run.json``: it is the
``control/submissions.jsonl`` row itself, which ``submit.py`` wrote (carrying its Kaggle
``ref``) BEFORE it began polling, precisely so a crash mid-poll can never orphan a slot
that was really spent.

Two entry paths:

  * RESUME (default) — take every ``PENDING`` row (or just ``--exp-id``'s), poll Kaggle
    under the bounded, jittered backoff, and transition the row IN PLACE to ``SCORED``
    or ``FAILED``. A second run is a byte-identical no-op: the row is no longer
    ``PENDING``, so there is nothing to do. Idempotent by construction.
  * ``--reconcile`` — mirror ``rebuild_ledger.py``'s self-healing posture, with KAGGLE
    as the authoritative source rather than the folders: BACK-FILL rows that exist on
    Kaggle but not locally, recovering out-of-band submissions (made on the website, on
    another machine, or in a prior session) whose existence D-04 already acknowledges.
    ⚠ Difference to hold: ``submissions.jsonl`` is CANONICAL, not derived — reconcile
    back-fills it from the one source that outranks it; it never regenerates it
    wholesale and it never deletes a local row.

Kaggle-authored text (``description``, ``status``, ``publicScore``) is UNTRUSTED. An
``exp_id`` is recovered ONLY through the strict anchored ``^exp-\\d{3}\\b`` regex, and no
filesystem path and no executed argv is ever derived from it. Scores are parsed by
``submissions_log.parse_score`` (``""`` → ``None``, never a fabricated ``0.0``). A raw
CLI buffer is MATCHED, never echoed — it is quarantined via ``dump_last_error``.

Portability + safety (CLAUDE.md): stdlib-only, self-locating (``Path(__file__)``),
``--workspace``-driven, NEVER interactive (argparse in / exit-code out). Every Kaggle
call routes through ``kaggle_gateway.run_kaggle`` (D-16). ``meta.json`` is NEVER written
(D-11): ``control/submissions.jsonl`` is the canonical leaderboard record.

Exit codes (mirroring ``poll_kernel.py``):
  0 = SCORED | 2 = submission FAILED (Kaggle ERROR) | 3 = DETACHED (still PENDING;
  re-run this script) | 4 = transient / fail-closed. 124/127 from the gateway are
  surfaced VERBATIM, never remapped.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from kaggle_gateway import _parse_json_array, dump_last_error, run_kaggle  # noqa: E402
from poll_kernel import compute_delay  # noqa: E402
from submissions_log import (  # noqa: E402
    new_row,
    parse_score,
    parse_status,
    parse_utc,
    read_rows,
    submissions_argv,
    upsert_row,
    write_rows,
)

# --------------------------------------------------------------------------- #
# Backoff constants at the LEADERBOARD time scale.
#
# Kaggle scores a submission in SECONDS-TO-MINUTES — not the hours a kernel takes — so
# the Phase 4 kernel constants are a starting point, not a mandate: a 10s first tick
# wastes the common case, and a 2-minute sleep is absurd against a 30-second scorer.
# The MATH is not forked: poll_kernel.compute_delay is imported and given these values.
# --------------------------------------------------------------------------- #
LB_BASE_DELAY = 5.0          # first inter-poll delay (kernel: 10.0)
LB_BACKOFF_MULTIPLIER = 2.0  # unchanged — proven
LB_MAX_DELAY = 30.0          # cap; no single sleep exceeds this (kernel: 120.0)
LB_BUDGET_S = 600            # 10 min overall wall clock, then DETACH (kernel: 7200)
DEFAULT_POLL_TIMEOUT = 60    # per-call run_kaggle timeout
MAX_CONSECUTIVE_ERRORS = 5   # transient blips tolerated before fail-closed

EXIT_SCORED = 0
EXIT_SUBMISSION_FAILED = 2   # Kaggle scored the submission as ERROR
EXIT_DETACHED = 3            # our budget expired; the row stays PENDING (never lost)
EXIT_TRANSIENT_FAIL = 4      # transient / fail-closed

CONFIG_REL = "control/config.json"
LEDGER_REL = "control/ledger.jsonl"

# Kaggle-authored `description` text is UNTRUSTED (T-05-05-06). The exp_id is recovered
# with a STRICT ANCHORED regex — never a substring scan — and is used ONLY as a join key
# into our own ledger. No path and no argv is ever built from it.
_EXP_ID_RE = re.compile(r"^(exp-\d{3})\b")


def submissions_url(slug: str) -> str:
    """The human's Kaggle submissions page (framework-built; the slug comes from
    ``config.json``/argv, never from Kaggle prose)."""
    return f"https://www.kaggle.com/competitions/{slug}/submissions"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Kaggle read — through the gateway ONLY (D-16), never a bare shell-out.
# --------------------------------------------------------------------------- #
def read_submissions(slug: str, *, timeout: int = DEFAULT_POLL_TIMEOUT, runner=None):
    """Kaggle's authoritative rows for ``slug``, or ``None`` (⇒ the caller fails closed).

    ⭐ THE ONE READER. ``runner`` defaults to THIS module's ``run_kaggle`` and exists so
    ``submit.py`` can pass its OWN gateway reference: the gateway is an ARGUMENT, not a
    module global, so a caller's monkeypatched gateway is HONOURED rather than silently
    bypassed (WR-01 — the trap that killed ``submissions_log.fetch_submissions``).

    The argv itself is not built here either: ``submissions_log.submissions_argv`` owns it,
    so the command exists in exactly one place (``--page-size 200`` is the CLI maximum; one
    page always covers today). The raw payload is PARSED, never printed — it can carry a
    token-shaped string.
    """
    call = runner if runner is not None else run_kaggle
    rc, payload = call(*submissions_argv(slug), timeout=timeout)
    if rc != 0:
        return None
    rows = _parse_json_array(payload)
    return rows if isinstance(rows, list) else None


def by_ref(rows, ref):
    """The Kaggle row whose ``ref`` is ``ref``, else ``None`` (an exact id match — the
    read-back already recovered the id, so the untrusted description is not re-used)."""
    for row in rows:
        if isinstance(row, dict) and row.get("ref") == ref:
            return row
    return None


# --------------------------------------------------------------------------- #
# The bounded poll — the poll_kernel.poll_loop shape at the leaderboard time scale.
# --------------------------------------------------------------------------- #
def poll_lb(
    status_fn,
    *,
    now,
    sleep,
    rng,
    budget_s,
    max_consecutive_errors,
    select=None,
) -> dict:
    """Poll ``status_fn`` to a leaderboard terminal under bounded backoff; return an
    outcome dict.

    ``status_fn()`` returns ``(rc, payload)`` — the ``run_kaggle`` shape — where the
    payload is a ``competitions submissions --format json`` array. ``select(rows)``
    picks OUR row from it (by Kaggle ``ref``); the default takes the first row.

    Injected ``now`` / ``sleep`` / ``rng`` make the loop deterministic and testable with
    NO REAL WAITING — without that seam the detach path could only be exercised by
    actually waiting out the budget. The loop stops at three points:

      * ``reason="terminal"``  — the row reached ``SCORED`` or ``FAILED``
        (``terminal=True``; ``row`` carries the Kaggle row so the caller can parse the
        scores).
      * ``reason="budget"``    — OUR wall-clock budget expired with the submission still
        PENDING ⇒ DETACH (``status="DETACHED"``, ``terminal=False``). Nothing is
        cancelled and NOTHING IS LOST: the caller leaves the row PENDING with its ref,
        and a later run of this script finishes it.
      * ``reason="transient"`` — ``max_consecutive_errors`` consecutive unparseable /
        failed polls ⇒ fail-closed (``terminal=False``); ``last_out`` carries the last
        buffer for quarantine. The counter RESETS on any clean parse: a single blip is
        never mistaken for a verdict.

    An unparseable status is TRANSIENT (retry), NEVER a false terminal — the
    ``parse_status`` contract.
    """
    start = now()
    consecutive_errors = 0
    attempt = 0
    last_payload = ""
    last_row = None

    while True:
        rc, payload = status_fn()
        last_payload = payload

        status = None
        row = None
        if rc == 0:
            rows = _parse_json_array(payload)
            if isinstance(rows, list):
                row = select(rows) if select is not None else (rows[0] if rows else None)
                if isinstance(row, dict):
                    status = parse_status(row.get("status"))

        if status is None:
            # Non-zero rc, unparseable payload, our row absent, or an unrecognized
            # status literal. All TRANSIENT — tolerated up to the threshold.
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                return {
                    "terminal": False,
                    "status": "ERROR",
                    "reason": "transient",
                    "row": last_row,
                    "last_out": last_payload,
                }
        else:
            consecutive_errors = 0  # a clean parse resets the blip counter
            last_row = row
            if status in ("SCORED", "FAILED"):
                return {
                    "terminal": True,
                    "status": status,
                    "reason": "terminal",
                    "row": row,
                    "last_out": last_payload,
                }
            # else: still PENDING — keep polling.

        # OUR-side budget check BEFORE sleeping: on expiry, DETACH (never cancel).
        if (now() - start) >= budget_s:
            return {
                "terminal": False,
                "status": "DETACHED",
                "reason": "budget",
                "row": last_row,
                "last_out": last_payload,
            }

        sleep(
            compute_delay(
                attempt,
                rng=rng,
                base=LB_BASE_DELAY,
                multiplier=LB_BACKOFF_MULTIPLIER,
                cap=LB_MAX_DELAY,
            )
        )
        attempt += 1


# --------------------------------------------------------------------------- #
# Local reads (fail-clear — never an aborting traceback).
# --------------------------------------------------------------------------- #
def read_config(ws: Path):
    """Parse ``control/config.json``, or ``None`` after a clear message."""
    path = Path(ws) / CONFIG_REL
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        print(
            f"cannot continue: no {CONFIG_REL} — scaffold the workspace first "
            "(init_workspace.py).",
            file=sys.stderr,
        )
        return None
    except (json.JSONDecodeError, OSError) as exc:
        print(
            f"cannot continue: {CONFIG_REL} is not valid JSON and was left untouched "
            f"(fail-clear): {exc}.",
            file=sys.stderr,
        )
        return None
    if not isinstance(data, dict):
        print(f"cannot continue: {CONFIG_REL} is not a JSON object.", file=sys.stderr)
        return None
    return data


def cv_mean(ws: Path, exp_id) -> float | None:
    """The experiment's ``cv_mean`` from ``control/ledger.jsonl``, or ``None``.

    D-11: the ledger is the ONE source of the CV score — it is JOINED on ``exp_id``, never
    denormalized into the submission row (a stale copy would silently poison the very gap
    this phase exists to measure).
    """
    if not exp_id:
        return None
    path = Path(ws) / LEDGER_REL
    if not path.exists():
        return None
    found = None
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # fail-clear: a malformed ledger line is skipped, never fatal
        if isinstance(row, dict) and row.get("exp_id") == exp_id:
            value = row.get("cv_mean")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                found = float(value)
    return found


# --------------------------------------------------------------------------- #
# The ONE outcome recorder — shared with submit.py so both entry points transition a
# row and report a score in exactly the same words and with exactly the same codes.
# --------------------------------------------------------------------------- #
def record_outcome(ws: Path, slug: str, result: dict, *, exp_id, ref) -> int:
    """Apply a :func:`poll_lb` outcome to ``control/submissions.jsonl``; return the exit code.

    The row is transitioned IN PLACE (``upsert_row`` — one row per submission). On a
    detach or a transient failure the row is deliberately LEFT ``PENDING`` with its ref:
    the slot is spent and its provenance must survive, and a later run of this script
    picks it up from exactly there.
    """
    reason = result.get("reason")

    if reason == "terminal":
        krow = result.get("row") or {}
        if result.get("status") == "SCORED":
            public = parse_score(krow.get("publicScore"))
            private = parse_score(krow.get("privateScore"))
            upsert_row(
                ws, ref,
                status="SCORED",
                public_score=public,
                private_score=private,
                scored_at=_now_iso(),
            )
            _report_score(ws, exp_id, ref, public)
            return EXIT_SCORED

        # Kaggle scored it as ERROR. D-13: RECORDED, but NOT COUNTED against the daily
        # limit — no special-case arithmetic is needed, because Kaggle simply never
        # charged it and D-04's authoritative count reflects that.
        upsert_row(ws, ref, status="FAILED", error_description=None)
        print(
            f"submission {ref} ({exp_id}) FAILED on Kaggle (a processing error). The CLI "
            "does NOT expose the reason — `errorDescription` is not in its field list — so "
            "none was recorded rather than fabricated. Read the real reason on your "
            f"submissions page: {submissions_url(slug)}",
            file=sys.stderr,
        )
        return EXIT_SUBMISSION_FAILED

    if reason == "budget":
        print(
            f"leaderboard poll budget expired — {exp_id} (ref {ref}) is still PENDING on "
            "Kaggle. DETACHED, never cancelled: the row keeps its ref and the slot is NOT "
            "lost. Re-run fetch_lb.py to record the score once Kaggle finishes scoring."
        )
        return EXIT_DETACHED

    # reason == "transient": consecutive errors hit the threshold.
    dump_last_error(ws, result.get("last_out", ""))
    print(
        f"cannot read the leaderboard: {MAX_CONSECUTIVE_ERRORS} consecutive status errors "
        f"— giving up (fail-closed). {exp_id} (ref {ref}) stays PENDING and its slot is NOT "
        "lost. Raw CLI output withheld (it may carry a secret) and quarantined to "
        "control/raw/last-error.txt. Re-run fetch_lb.py to retry.",
        file=sys.stderr,
    )
    return EXIT_TRANSIENT_FAIL


def _report_score(ws: Path, exp_id, ref, public) -> None:
    """Print the leaderboard score and the CV→LB gap (the D-11 join, computed on the fly)."""
    if public is None:
        print(f"{exp_id} (ref {ref}) is SCORED, but Kaggle reported no public score.")
        return
    cv = cv_mean(ws, exp_id)
    if cv is None:
        print(f"{exp_id} (ref {ref}) SCORED — public LB {public:.6f} (no CV score in the ledger).")
        return
    print(
        f"{exp_id} (ref {ref}) SCORED — public LB {public:.6f} | CV {cv:.6f} | "
        f"gap {public - cv:+.6f} (LB minus CV)."
    )


# --------------------------------------------------------------------------- #
# RESUME — re-read the handoff row; never re-do the side effect.
# --------------------------------------------------------------------------- #
def _resume(ws: Path, slug: str, args) -> int:
    rows = read_rows(ws)
    pending = [
        r for r in rows
        if r.get("status") == "PENDING"
        and (args.exp_id is None or r.get("exp_id") == args.exp_id)
    ]
    if not pending:
        scope = f" for {args.exp_id}" if args.exp_id else ""
        print(
            f"nothing pending{scope} — every recorded submission already has a terminal "
            "status. Nothing was polled and nothing was written."
        )
        return EXIT_SCORED

    codes = []
    for row in pending:
        ref = row.get("kaggle_ref")
        exp_id = row.get("exp_id")
        if ref is None:
            print(
                f"skipping a PENDING row for {exp_id!r}: it carries no kaggle_ref, so it "
                "cannot be matched against Kaggle. Run `fetch_lb.py --reconcile`.",
                file=sys.stderr,
            )
            codes.append(EXIT_TRANSIENT_FAIL)
            continue

        def _status_fn():
            # The raw (rc, payload) shape poll_lb wants — but the ARGV is the shared one.
            return run_kaggle(*submissions_argv(slug), timeout=args.poll_timeout)

        result = poll_lb(
            _status_fn,
            now=time.monotonic,
            sleep=time.sleep,
            rng=random.Random(),
            budget_s=args.budget_s,
            max_consecutive_errors=MAX_CONSECUTIVE_ERRORS,
            select=lambda krows, ref=ref: by_ref(krows, ref),
        )
        codes.append(record_outcome(ws, slug, result, exp_id=exp_id, ref=ref))

    # Worst-first: a fail-closed transient outranks a detach, which outranks a Kaggle-side
    # failure, which outranks a clean score.
    for code in (EXIT_TRANSIENT_FAIL, EXIT_DETACHED, EXIT_SUBMISSION_FAILED):
        if code in codes:
            return code
    return EXIT_SCORED


# --------------------------------------------------------------------------- #
# RECONCILE — back-fill from the one source that outranks the canonical file.
# --------------------------------------------------------------------------- #
def _row_from_kaggle(krow: dict, slug: str):
    """Build a local row for a Kaggle submission we have no record of, or ``None``.

    Nothing is fabricated: an unparseable status or date is SKIPPED-AND-WARNED (the
    rebuild_ledger posture), the ``exp_id`` is ``None`` when the description carries no
    anchored ``exp-NNN`` prefix, and ``file`` / ``file_sha256`` are ``None`` because the
    local bytes of an out-of-band submission are genuinely UNKNOWN — a hash we did not
    compute is never invented, and no path is ever derived from Kaggle's ``fileName``.
    """
    status = parse_status(krow.get("status"))
    if status is None:
        print(
            f"reconcile: skipping Kaggle submission {krow.get('ref')!r} — unrecognized "
            "status literal (recorded nothing rather than guess).",
            file=sys.stderr,
        )
        return None
    submitted = parse_utc(krow.get("date"))
    if submitted is None:
        print(
            f"reconcile: skipping Kaggle submission {krow.get('ref')!r} — unparseable date.",
            file=sys.stderr,
        )
        return None

    description = krow.get("description")
    exp_id = None
    if isinstance(description, str):
        match = _EXP_ID_RE.match(description.strip())
        if match:
            exp_id = match.group(1)

    terminal = status in ("SCORED", "FAILED")
    return new_row(
        exp_id=exp_id,
        kaggle_ref=krow.get("ref"),
        competition_slug=slug,
        file=None,
        file_sha256=None,
        message=description if isinstance(description, str) else None,
        submitted_at=submitted.strftime("%Y-%m-%dT%H:%M:%SZ"),
        status=status,
        public_score=parse_score(krow.get("publicScore")),
        private_score=parse_score(krow.get("privateScore")),
        scored_at=_now_iso() if terminal else None,
        override_reason=None,
        error_description=None,
    )


def _apply_kaggle(row: dict, krow: dict) -> bool:
    """Fold Kaggle's status/scores into an existing local row; return whether it changed.

    Returning "changed" (rather than always rewriting) is what makes ``--reconcile``
    BYTE-IDEMPOTENT: a second run re-derives the identical values, sees no delta, and the
    file is not touched — including ``scored_at``, which is stamped ONCE and then kept.
    """
    status = parse_status(krow.get("status"))
    if status is None:
        print(
            f"reconcile: leaving local row {row.get('kaggle_ref')!r} untouched — Kaggle "
            "reported an unrecognized status literal.",
            file=sys.stderr,
        )
        return False

    updates = {
        "status": status,
        "public_score": parse_score(krow.get("publicScore")),
        "private_score": parse_score(krow.get("privateScore")),
    }
    if status in ("SCORED", "FAILED") and not row.get("scored_at"):
        updates["scored_at"] = _now_iso()

    changed = any(row.get(key) != value for key, value in updates.items())
    if changed:
        row.update(updates)
    return changed


def _reconcile(ws: Path, slug: str, args) -> int:
    kaggle_rows = read_submissions(slug, timeout=args.poll_timeout)
    if kaggle_rows is None:
        print(
            "cannot reconcile: Kaggle's submission list could not be read (fail-closed — "
            "nothing was written). Re-run once the CLI/network recovers.",
            file=sys.stderr,
        )
        return EXIT_TRANSIENT_FAIL

    local = read_rows(ws)
    known = {}
    for row in local:
        known.setdefault(row.get("kaggle_ref"), row)

    added = []
    changed = False
    for krow in kaggle_rows:
        if not isinstance(krow, dict):
            continue
        ref = krow.get("ref")
        if ref is None:
            continue
        existing = known.get(ref)
        if existing is None:
            fresh = _row_from_kaggle(krow, slug)
            if fresh is None:
                continue
            known[ref] = fresh
            added.append(fresh)
            changed = True
        elif _apply_kaggle(existing, krow):
            changed = True

    if changed:
        # A full ATOMIC rewrite (tempfile + os.replace): a hand-corrupted or partially
        # written file self-heals, and no local row is ever deleted — reconcile only ever
        # ADDS and UPDATES.
        write_rows(ws, local + added)

    print(
        f"reconciled against Kaggle: {len(added)} submission(s) back-filled, "
        f"{len(local)} already known. control/submissions.jsonl "
        f"{'updated' if changed else 'unchanged'}."
    )
    return EXIT_SCORED


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="fetch_lb.py",
        description="Record the leaderboard score of an already-made submission. Resumes "
                    "a DETACHED poll by re-reading control/submissions.jsonl, and can "
                    "--reconcile the canonical file against Kaggle. It only ever READS "
                    "Kaggle: it can never spend a submission slot.",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    ap.add_argument("--exp-id",
                    help="Only resume this experiment (default: every PENDING row).")
    ap.add_argument("--reconcile", action="store_true",
                    help="Back-fill rows that exist on Kaggle but not locally (recovers "
                         "out-of-band submissions). Never deletes a local row.")
    ap.add_argument("--budget-s", "--budget", dest="budget_s", type=float,
                    default=float(LB_BUDGET_S),
                    help="Wall-clock poll budget in seconds before detaching "
                         f"(default: {LB_BUDGET_S}).")
    ap.add_argument("--poll-timeout", type=int, default=DEFAULT_POLL_TIMEOUT,
                    help=f"Per-call gateway timeout (default: {DEFAULT_POLL_TIMEOUT}).")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()

    config = read_config(ws)
    if config is None:
        return EXIT_TRANSIENT_FAIL

    slug = config.get("competition_slug")
    if not isinstance(slug, str) or not slug:
        print(
            f"cannot continue: {CONFIG_REL} has no competition_slug.",
            file=sys.stderr,
        )
        return EXIT_TRANSIENT_FAIL

    if args.reconcile:
        return _reconcile(ws, slug, args)
    return _resume(ws, slug, args)


if __name__ == "__main__":
    raise SystemExit(main())
