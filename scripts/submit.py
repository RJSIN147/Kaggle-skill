#!/usr/bin/env python3
"""submit.py — the ONE place in this codebase that spends a real submission slot (SCORE-01).

⚠ A Kaggle submission is IRREVERSIBLE and consumes a scarce daily slot. This script is
therefore the most safety-critical file in the framework, and it is built around a single
hard-won fact:

  **`kaggle competitions submit` is FAIL-OPEN on its exit code.** Read from the installed
  CLI 2.2.3 source: a 404 slug and a failed upload BOTH print a message and exit **0** —
  the client swallows its own 404 before it can propagate, and a failed upload returns a
  message object rather than an error. ``rc == 0`` is therefore NOT proof that the
  submission landed.

    | bad/closed slug (404) | exit 0 ⚠ | a known failure literal on stdout |
    | upload failed         | exit 0 ⚠ | a known failure literal on stdout |
    | auth failure (401)    | exit 1   | HTTPError                         |
    | 403 rules gate        | exit 1   | -> classify_gate -> UI_GATE (77)  |
    | success               | exit 0   | a SERVER-AUTHORED message — NEVER PARSED |

  So success is established by READ-BACK, not by an exit code: a NEW row in
  ``competitions submissions`` whose ``description`` carries our ``exp-NNN`` and whose
  date is at/after this run started. That read-back is simultaneously (a) the proof, (b)
  the only channel that yields the Kaggle ``ref`` id — the submit call DISCARDS it — and
  (c) the first tick of the leaderboard poll. This is structurally identical to Phase 4's
  "a kernel can report COMPLETE and still have lied".

Four more load-bearing postures:

  * ⚠ WRITE ORDERING. The PENDING row (exp_id + ref + file hash) is appended to
    ``control/submissions.jsonl`` BEFORE the poll begins. The slot is spent the instant
    Kaggle accepts the upload; if the poll then crashes and nothing was written, the
    submission is invisible locally — its provenance is gone forever and its CV→LB gap
    can never be computed. A crash mid-poll must never orphan a spent slot.
  * NO DOUBLE-SPEND. Idempotence here means "re-running is SAFE", not "re-running
    re-submits": an existing non-FAILED row for the same ``exp_id`` whose file hash MATCHES
    — **or is UNKNOWN** — is REFUSED before the gateway is ever called. The unknown-hash
    case is the load-bearing one: a row back-filled by ``fetch_lb --reconcile`` carries
    ``file_sha256: None`` (Kaggle never returns the bytes it was sent), and that is the row
    the framework's OWN recovery advice produces after a failed read-back. Matching on hash
    alone would let the recovery path become the double-spend path. Bytes we cannot prove
    DIFFERENT are treated as possibly the SAME. A genuine second submission requires an
    explicit ``--resubmit``.
  * TOCTOU. The file is re-hashed immediately before the argv is built; if it changed
    since validation, the bytes about to be uploaded are not the bytes that were checked,
    so the submit is refused.
  * D-11. The leaderboard score is written ONLY to ``control/submissions.jsonl``.
    ``experiments/exp-NNN/meta.json`` is NEVER touched — the experiment folder is
    immutable after record, and per-experiment CV→LB views are DERIVED by joining on
    ``exp_id``.

Kaggle's raw output is MATCHED, never echoed (it can carry a token-shaped string): it is
quarantined via ``dump_last_error`` to the gitignored ``control/raw/last-error.txt``.

Portability + safety (CLAUDE.md): stdlib-only, self-locating (``Path(__file__)``),
``--workspace``-driven, NEVER interactive — the human-confirmation loop lives in SKILL.md
and arrives here as ``--confirm`` (D-05). Every Kaggle call routes through
``kaggle_gateway.run_kaggle`` (D-16).

  * D-02. The file is VALIDATED against the competition's own reference sample (exact
    header, exact row count, order-independent id set, no blank/NaN predictions) INSIDE
    this script, immediately before the TOCTOU re-hash. check_submission.py runs the same
    checks for free, but "never submit an unvalidated file" cannot be an invariant that
    depends on the caller having remembered to run the free gate first.
  * D-04 + D-06. The BUDGET gate and the CV gate are likewise enforced INSIDE this script
    (:func:`_gate`), for exactly the same reason. check_submission.py computes both for
    free — but it is free precisely because it is SKIPPABLE, and a user who runs
    ``submit.py --confirm`` directly must not thereby get NEITHER gate. The policy is
    IMPORTED (``submission_gate.decide``, ``submissions_log.remaining_slots``), never
    re-derived: the human and the machine must see the SAME decision.

    ⭐ ``--confirm`` overrides EXACTLY what ``decide`` says a human can confirm:
    ``requires_confirmation`` TRUE (a within-noise CV gain; the last ASSUMED slot) is a
    judgment call and it gets through — D-05, never a silent hard refusal. But an
    EXHAUSTED budget, an UNKNOWABLE budget (``remaining is None`` — the fail-closed
    sentinel) and an experiment with NO READABLE CV are ``requires_confirmation`` FALSE:
    there is nothing coherent to confirm, and ``--confirm`` does NOT override them.

Exit codes: 0 = SCORED | 2 = submission FAILED (Kaggle ERROR) | 3 = DETACHED (PENDING —
re-run fetch_lb.py) | 4 = transient / fail-closed | 65 = the submission file is missing, or
does not validate against the competition's sample (D-02) | 69 = this competition is not a
CSV-submit competition (D-01) | 75 = the gate declined to spend a slot (no --confirm, a
double-spend, or a D-04/D-06 block --confirm cannot override) | 77 = a UI gate. 124/127
from the gateway are surfaced VERBATIM.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_submission import (  # noqa: E402
    _as_number,
    _read_ledger,
    _resolve_reference,
    best_submitted_cv,
    validate_submission,
)
from fetch_lb import (  # noqa: E402
    # The terminal codes (2 = FAILED, 3 = DETACHED) are returned by record_outcome, which
    # is the ONE recorder both entry points share — so they are deliberately not re-imported.
    DEFAULT_POLL_TIMEOUT,
    EXIT_SCORED,
    EXIT_TRANSIENT_FAIL,
    LB_BUDGET_S,
    MAX_CONSECUTIVE_ERRORS,
    by_ref,
    cv_mean,
    poll_lb,
    read_config,
    read_submissions,
    record_outcome,
    submissions_url,
)
from kaggle_gateway import (  # noqa: E402
    GATE_BLOCKED,
    SUBMIT_UNSUPPORTED,
    UI_GATE,
    VALIDATION_FAILED,
    classify_gate,
    dump_last_error,
    run_kaggle,
)
from submission_gate import NOISE_K_DEFAULT, decide  # noqa: E402
from submissions_log import (  # noqa: E402
    COUNT_UNAVAILABLE,
    append_row,
    charged_today,
    file_sha256,
    find_by_exp_id,
    new_row,
    parse_status,
    read_rows,
    remaining_slots,
    submissions_argv,
)

SUBMIT_TIMEOUT = 300  # an upload is slower than a status read
SUBMISSION_CSV = "submission.csv"

# The exp id is OURS (argv), not Kaggle's — but it becomes a path component, so it is
# validated against the exact minted shape before it is ever joined to a directory.
_EXP_ID_RE = re.compile(r"^exp-\d{3}$")

# ⚠ THE FAIL-OPEN SIGNATURES. These two strings are hardcoded in the CLI client and are
# printed WHILE IT EXITS 0. Matching them is what turns a silent lie into a loud failure.
# They are MATCHED here and never echoed — the framework authors its own message, because
# the surrounding buffer can carry a secret.
FAIL_OPEN_MARKERS = (
    "Could not find competition",
    "Could not submit to competition",
)


def _pre_flight(ws: Path, args):
    """Resolve config + the submission file, or return an exit code.

    Returns ``(config, slug, csv_path, digest)`` on success, or an ``int`` exit code on
    refusal. ``config`` rides along because :func:`_gate` needs the metric direction, the
    daily limit and its provenance — re-reading the file there would be a second read of a
    document that could have changed underneath us mid-run.
    """
    config = read_config(ws)
    if config is None:
        return EXIT_TRANSIENT_FAIL

    slug = config.get("competition_slug")
    if not isinstance(slug, str) or not slug:
        print("cannot submit: control/config.json has no competition_slug.", file=sys.stderr)
        return EXIT_TRANSIENT_FAIL

    # D-01: a CODE competition submits a KERNEL, not a file. There is no safe CSV path
    # here, so refuse BEFORE the gateway is touched rather than spend a slot discovering it.
    competition = config.get("competition")
    comp_type = competition.get("type") if isinstance(competition, dict) else None
    if comp_type != "csv":
        print(
            f"cannot submit: competition.type is {comp_type!r}, not 'csv'. A code/notebook "
            "competition submits a KERNEL, not a file, and an 'unknown' type is not proven "
            "safe to submit to. Refusing rather than spending a slot on a guess.",
            file=sys.stderr,
        )
        return SUBMIT_UNSUPPORTED

    if not _EXP_ID_RE.match(args.exp_id or ""):
        print(
            f"cannot submit: --exp-id {args.exp_id!r} is not of the form exp-NNN.",
            file=sys.stderr,
        )
        return VALIDATION_FAILED

    # CONFINE the experiment path under ws/experiments/ — a resolved child, never an escape.
    exp_root = (ws / "experiments").resolve()
    exp_dir = (exp_root / args.exp_id).resolve()
    if exp_dir.parent != exp_root:
        print(
            f"cannot submit: {args.exp_id} does not resolve inside {exp_root}.",
            file=sys.stderr,
        )
        return VALIDATION_FAILED

    csv_path = exp_dir / SUBMISSION_CSV
    if not csv_path.is_file():
        print(
            f"cannot submit: no {csv_path}. The experiment harness writes it — run the "
            "experiment first (run_local.py, or pull_kernel.py for the kernel path). Note "
            "submission.csv is gitignored by design: its provenance is the file hash "
            "recorded in control/submissions.jsonl, not the git tree.",
            file=sys.stderr,
        )
        return VALIDATION_FAILED

    # ------------------------------------------------------------------ #
    # D-02 — NEVER SUBMIT AN UNVALIDATED FILE.
    #
    # check_submission.py runs exactly this validation for FREE, and the agent is told to
    # run it first. But submit.py is the ONE script that spends the irreversible resource,
    # so it must not TRUST that the free gate was run — an invariant enforced only by
    # "the caller remembered to" is not enforced. Every other irreversible invariant in
    # this script (the D-01 type refusal, TOCTOU, the double-spend guard, --confirm) is
    # mechanical; this one is too.
    #
    # ⚠ And the failure is NOT free, even though Kaggle does not charge processing errors
    # (D-13): a header / id-set mismatch is frequently SCORED rather than rejected. A
    # wrong-but-parseable file burns a real slot AND lands a garbage score on the board.
    #
    # The validators are IMPORTED from check_submission, never re-derived here: a second
    # copy would be a second thing to keep in sync, and a validator that silently drifted
    # from the one the human was shown would be worse than no validator at all.
    # ------------------------------------------------------------------ #
    ref = _resolve_reference(ws)
    if ref is None:
        print(
            "REFUSING to submit: there is nothing to validate submission.csv AGAINST — no "
            "reference file under data/ (neither the Phase 2 manifest signal nor a "
            "*submission*.csv scan found one) and no data/test.csv to derive the id set "
            "from. An unvalidated file is NEVER submitted (D-02). No slot was spent — "
            "re-download the competition data and re-run.",
            file=sys.stderr,
        )
        return VALIDATION_FAILED

    # PRINT the chosen reference (as check_submission does): the Phase 2 signal takes the
    # FIRST manifest match and is flagged WEAK by its own author, so a human must be able
    # to spot a wrong pick — a silently-wrong reference validates a garbage file clean.
    print(f"validating {csv_path.name} against reference: {ref.label} ({ref.count} rows)")

    reason, message = validate_submission(csv_path, ref)
    if reason is not None:
        print(
            f"REFUSING to submit [{reason}]: {message}\n"
            "  NO SLOT WAS SPENT. Kaggle only refuses a file it cannot process (D-13) — a "
            "structurally wrong but PARSEABLE file is SCORED, which would burn a real, "
            "irreversible slot and land a garbage score on the leaderboard.\n"
            "  Fix the harness, re-run the experiment, then re-check with "
            "check_submission.py.",
            file=sys.stderr,
        )
        return VALIDATION_FAILED

    return config, slug, csv_path, file_sha256(csv_path)


def _gate(ws: Path, args, config: dict, slug: str) -> int | None:
    """The D-04 BUDGET gate + the D-06 CV gate — enforced HERE, before any slot is spent.

    ``None`` means "proceed"; an ``int`` is the exit code of a refusal.

    ⚠ WHY THIS EXISTS AT ALL (WR-02). Phase 5's goal is "submit under CV-first discipline
    WITH BUDGET GATING", and until now that was only half true in code: this script imported
    neither ``submission_gate`` nor ``submissions_log.remaining_slots``, so BOTH gates were
    enforced only by the FREE, advisory ``check_submission.py`` and by prose in SKILL.md. A
    user who skipped the free gate and ran ``submit.py --confirm`` got NEITHER — and spent a
    real, irreversible slot they could not get back. This is the D-02 asymmetry exactly: the
    ONE script that spends the irreversible resource must not TRUST that the free gate was
    run first. An invariant enforced only by "the caller remembered to" is not enforced.

    The policy is IMPORTED, never re-derived: ``submission_gate.decide`` makes the decision
    and ``submissions_log.remaining_slots`` counts the budget, exactly as ``check_submission``
    calls them. A second, drifting copy of the gate would be worse than no gate at all — the
    whole point is that the HUMAN (who read check_submission's render) and the MACHINE (which
    spends the slot) see the SAME decision.

    ⭐ WHAT ``--confirm`` OVERRIDES — and the line is drawn by ``decide``'s OWN
    ``requires_confirmation`` flag, not by a second policy invented here:

      * ``requires_confirmation`` TRUE — a within-noise CV gain, or the last ASSUMED slot.
        A genuine JUDGMENT CALL about real numbers the human is entitled to weigh. D-05
        guarantees the framework never silently hard-refuses, and SKILL.md's exit-75 loop
        (check → the human decides → ``submit.py --confirm``) IS this path. ``--confirm``
        is that informed "yes" and it gets through — but the gate's position is PRINTED
        first, so a user who skipped the free gate still sees the numbers at the point of
        spend. A silent override is indistinguishable from no gate at all.
      * ``requires_confirmation`` FALSE — an EXHAUSTED budget, an UNKNOWABLE budget, or an
        experiment with NO READABLE CV. In the gate module's own words: *"there is nothing
        coherent to confirm, because we do not know what we would be confirming."*
        ``--confirm`` does NOT override these. It is an acknowledgement that a slot will be
        spent; it is not a licence to spend one that does not exist, or one the framework
        could not account for. A count we could not establish is a REFUSAL to spend, never
        "plenty left".

    The budget read goes through ``fetch_lb.read_submissions(..., runner=run_kaggle)`` — the
    ONE reader, and the INJECTABLE one: it takes the gateway as an ARGUMENT, so a caller
    that substituted the gateway is HONOURED rather than silently bypassed. (Its predecessor
    ``submissions_log.fetch_submissions`` resolved ``run_kaggle`` from its OWN module
    globals, which would have let a REAL Kaggle call escape from inside a supposedly-mocked
    test. WR-01 deleted it; the argv now lives once, in ``submissions_log.submissions_argv``.)
    """
    metric = config.get("metric") or {}
    greater_is_better = metric.get("greater_is_better")
    if not isinstance(greater_is_better, bool):
        # The direction is TOOLING-WRITTEN (set_metric.py), never guessed. Without it the
        # gate cannot even tell which way "better" points — so it cannot judge the CV.
        print(
            "REFUSING to submit: control/config.json -> metric is missing "
            "name/greater_is_better, so the framework cannot tell which way 'better' points "
            "and cannot judge this experiment's CV at all. The metric direction is never "
            "guessed — run set_metric.py and re-run. No slot was spent.",
            file=sys.stderr,
        )
        return GATE_BLOCKED

    # ---------------------------------------------------------------- D-04 budget ----
    # Kaggle's OWN submissions list is the authority — there is no submission-quota command
    # (`kaggle quota` is GPU/TPU hours only). An unfetchable or unparseable count is the
    # COUNT_UNAVAILABLE (-1) sentinel, which remaining_slots maps to None => BLOCK.
    kaggle_rows = read_submissions(slug, timeout=args.poll_timeout, runner=run_kaggle)
    charged = (
        charged_today(kaggle_rows, datetime.now(timezone.utc))
        if kaggle_rows is not None
        else COUNT_UNAVAILABLE
    )
    submission_cfg = config.get("submission") or {}
    remaining = remaining_slots(submission_cfg.get("daily_limit"), charged)

    # ---------------------------------------------------------------- D-06 CV --------
    # The ledger is the ONE source of the CV (D-11) — joined on exp_id, never re-derived
    # from meta.json, and never denormalized into the submission row.
    ledger = _read_ledger(ws)
    ours = next(
        (
            row
            for row in ledger
            if row.get("exp_id") == args.exp_id and row.get("status") == "SUCCESS"
        ),
        {},
    )

    noise_k = submission_cfg.get("noise_k")
    if _as_number(noise_k) is None:
        # An already-scaffolded workspace predates the template's noise_k key.
        noise_k = NOISE_K_DEFAULT

    verdict = decide(
        cand_cv=_as_number(ours.get("cv_mean")),
        cand_std=_as_number(ours.get("cv_std")),
        best_cv=best_submitted_cv(ws, ledger, greater_is_better),
        greater_is_better=greater_is_better,
        remaining=remaining,
        limit_provenance=submission_cfg.get("limit_provenance"),
        k=noise_k,
    )

    # ---------------------------------------------------------------- Render ---------
    # The material is printed BEFORE the slot goes, on EVERY path — cleared, overridden or
    # refused. The user who skipped the free gate is still shown the numbers.
    budget = "UNKNOWN (fail closed)" if remaining is None else str(remaining)
    print(f"gate: {budget} slot(s) left today (UTC day; charged={charged})")
    for line in verdict["reasons"]:
        print(f"  - {line}")
    for line in verdict["warnings"]:
        print(f"  ! {line}")

    if verdict["recommendation"] == "SUBMIT":
        # A SUBMIT that still wants confirmation (D-08: the LAST slot under an ASSUMED
        # limit) is satisfied — this function is only reached WITH --confirm.
        return None

    if verdict["requires_confirmation"]:
        # D-05 — the gate takes a POSITION; it does not hold a veto. --confirm is the
        # human's explicit, informed override of a judgment call.
        print(
            "OVERRIDE: the gate's position is BLOCKED, but this is a JUDGMENT CALL (the "
            "numbers above are real and readable), and --confirm is your explicit "
            "acknowledgement. D-05: the framework never silently hard-refuses. Spending the "
            "slot."
        )
        return None

    # BLOCKED with requires_confirmation False — there is NOTHING COHERENT TO CONFIRM.
    print(
        "REFUSING to submit: the gate BLOCKED this submission, and it is NOT a judgment "
        "call --confirm can override. --confirm acknowledges that a slot will be SPENT; it "
        "is not a licence to spend one that does not exist, or one the framework could not "
        "account for. NO SLOT WAS SPENT.\n"
        "  - budget EXHAUSTED: wait for the UTC day to roll over. If you believe the "
        "recorded daily_limit is wrong, fix the NUMBER (capture_competition.py "
        "--daily-limit N) — never override a count you think is wrong.\n"
        "  - budget UNKNOWABLE: run check_submission.py (FREE), which classifies the cause "
        "precisely (a 403 rules gate, a missing CLI, a timeout, an unrecognized Kaggle "
        "status literal) instead of guessing a count.\n"
        "  - no readable CV: record the experiment (record_experiment.py) so it carries a "
        "real cv_mean. CV is the decision metric (SCORE-02).",
        file=sys.stderr,
    )
    return GATE_BLOCKED


def _refuse_double_spend(ws: Path, exp_id: str, digest: str) -> tuple[bool, str]:
    """``(refuse, why)`` — is a re-submit of ``exp_id`` a possible DOUBLE-SPEND?

    Re-running submit.py must be SAFE, which means it must not RE-SUBMIT. A FAILED row is
    not a spend (D-13: Kaggle never charged a processing error), so it never blocks.

    ⚠ A ROW WITH NO RECORDED HASH BLOCKS ON ``exp_id`` ALONE. The guard cannot be keyed on
    sha-equality alone, because the rows produced by the framework's OWN RECOVERY PATH have
    no sha to compare: ``fetch_lb --reconcile`` back-fills an out-of-band submission with
    ``file_sha256: None`` — correctly, since Kaggle never returns the bytes it was sent.

    That is precisely the scenario this guard exists for. When submit.py's read-back fails
    it prints "a slot MAY still have been spent … run `fetch_lb.py --reconcile` to back-fill
    it". If a hash-less row then failed to match, the user who FOLLOWED THAT ADVICE and
    re-ran ``submit.py --confirm`` would sail past the guard and spend a SECOND REAL SLOT on
    the same experiment. The recovery path would BE the double-spend path.

    So the asymmetry decides it: we cannot PROVE the bytes differ, and the cost of being
    wrong is irreversible. FAIL CLOSED — and reserve ``--resubmit`` as the human's
    deliberate, explicit "yes, spend another slot".

    A row whose hash IS recorded and DIFFERS is a proven-different file: it never blocks
    (a genuinely new submission.csv for the same experiment still submits).
    """
    for row in read_rows(ws):
        if row.get("exp_id") != exp_id or row.get("status") == "FAILED":
            continue

        recorded = row.get("file_sha256")
        if recorded == digest:
            return True, (
                f"REFUSING to submit: {exp_id} already has a non-FAILED submission of these "
                "EXACT bytes recorded in control/submissions.jsonl (kaggle_ref "
                f"{row.get('kaggle_ref')}). No slot was spent.\n"
                "  - to record the leaderboard score of that submission: fetch_lb.py "
                f"--exp-id {exp_id}\n"
                "  - to deliberately spend ANOTHER slot on the same file: re-run with "
                "--resubmit"
            )

        if not recorded:
            # An out-of-band / reconciled submission: the bytes are UNKNOWN, not different.
            return True, (
                f"REFUSING to submit: {exp_id} already has a non-FAILED submission "
                f"(kaggle_ref {row.get('kaggle_ref')}) whose file hash was NEVER RECORDED — "
                "it was back-filled from Kaggle by `fetch_lb.py --reconcile`, and Kaggle "
                "does not return the bytes it was sent.\n"
                "  That slot is ALREADY SPENT. Because the hash is unknown, this file cannot "
                "be PROVEN different from the one already submitted, so the submit is "
                "REFUSED rather than risk an irreversible double-spend. No slot was spent "
                "now.\n"
                "  - to record the leaderboard score of that submission: fetch_lb.py "
                f"--exp-id {exp_id}\n"
                "  - if this really is a NEW file and you mean to spend another slot: "
                "re-run with --resubmit"
            )

    return False, ""


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()

    checked = _pre_flight(ws, args)
    if isinstance(checked, int):
        return checked
    config, slug, csv_path, digest = checked
    exp_id = args.exp_id

    if not args.resubmit:
        refuse, why = _refuse_double_spend(ws, exp_id, digest)
        if refuse:
            print(why)
            return GATE_BLOCKED

    # The -m message is the ONLY exp_id <-> Kaggle correlation channel: it round-trips into
    # the `description` field on read-back, which is how the submission is later confirmed
    # and matched. The exp_id PREFIX is the load-bearing part; the CV score is a courtesy.
    cv = cv_mean(ws, exp_id)
    message = f"{exp_id} | cv={cv:.6f}" if cv is not None else exp_id

    # The competition is POSITIONAL (never -c). No code-competition flag and no host/admin
    # flag is EVER passed: the real dry run is --dry-run, right below.
    submit_argv = (
        "competitions", "submit", slug,
        "-f", str(csv_path),
        "-m", message,
    )

    if args.dry_run:
        print("--dry-run: NO slot spent, nothing written. This is the exact command:")
        print("  kaggle " + " ".join(submit_argv))
        return EXIT_SCORED

    # D-05: block by default. The human's confirmation loop lives in SKILL.md and arrives
    # here as an explicit flag — this script is never interactive.
    if not args.confirm:
        print(
            "REFUSING to submit without --confirm: a submission is IRREVERSIBLE and spends "
            "one of a small number of daily slots. Inspect the exact command with --dry-run, "
            "then re-run with --confirm.",
            file=sys.stderr,
        )
        return GATE_BLOCKED

    # ------------------------------------------------------------------ #
    # D-04 + D-06 — THE BUDGET GATE AND THE CV GATE (WR-02). Enforced HERE, mechanically,
    # because check_submission.py is FREE and SKIPPABLE and this script is neither. It sits
    # AFTER --confirm (an unconfirmed run is already refused, so there is nothing to read a
    # budget for) and BEFORE the TOCTOU re-hash and the gateway — no slot can be spent past
    # it. --dry-run returns above: it is a purely LOCAL rehearsal that never touches Kaggle.
    # ------------------------------------------------------------------ #
    blocked = _gate(ws, args, config, slug)
    if blocked is not None:
        return blocked

    # TOCTOU (T-05-05-03): the bytes validated must be the bytes uploaded.
    if file_sha256(csv_path) != digest:
        print(
            f"REFUSING to submit: {csv_path.name} changed while this command was preparing. "
            "The validated bytes are not the bytes that would be sent. No slot was spent — "
            "re-run to re-validate the current file.",
            file=sys.stderr,
        )
        return EXIT_TRANSIENT_FAIL

    # ------------------------------------------------------------------ #
    # SPEND THE SLOT. Everything below treats rc == 0 as ADVISORY ONLY.
    # ------------------------------------------------------------------ #
    started = datetime.now(timezone.utc)
    rc, payload = run_kaggle(*submit_argv, timeout=SUBMIT_TIMEOUT)

    if rc != 0:
        dump_last_error(ws, payload)
        if rc in (124, 127):
            # Gateway-reserved: a timeout / a missing CLI. Surfaced VERBATIM, never remapped.
            print(
                f"submit did not run (gateway exit {rc}: the CLI is missing from PATH, or "
                "the call timed out). No slot was spent.",
                file=sys.stderr,
            )
            return rc
        if "403" in payload or "forbidden" in payload.lower():
            print(classify_gate(payload, slug), file=sys.stderr)
            return UI_GATE
        print(
            f"submit failed (exit {rc}) — Kaggle rejected the call, so NO slot was spent. "
            "The raw CLI output is withheld (it can carry a secret) and was quarantined to "
            "control/raw/last-error.txt.",
            file=sys.stderr,
        )
        return EXIT_TRANSIENT_FAIL

    # ⚠ rc == 0 AND a known failure literal ⇒ a FAIL-OPEN LIE, detected by MATCHING the
    # output. Nothing landed and nothing is recorded as spent.
    if any(marker in payload for marker in FAIL_OPEN_MARKERS):
        dump_last_error(ws, payload)
        print(
            "submit exited 0 but its output matched a known FAILURE signature. The Kaggle "
            "CLI exits 0 EVEN WHEN THE SUBMISSION FAILED (an unknown or closed competition, "
            "or an upload that did not land), so the framework detected this by matching the "
            "CLI's output rather than by trusting its exit code. NOTHING was submitted and "
            "NO slot was spent.\n"
            f"  - check that '{slug}' in control/config.json is the right competition and is "
            "still accepting submissions.\n"
            "  - the raw CLI output was withheld (it can carry a secret) and quarantined to "
            "control/raw/last-error.txt.",
            file=sys.stderr,
        )
        return EXIT_TRANSIENT_FAIL

    # rc == 0 with no failure literal is STILL NOT PROOF. The success string is
    # server-authored and deliberately un-pinned — it is never parsed.

    # ------------------------------------------------------------------ #
    # CONFIRM BY READ-BACK. This IS the proof, it recovers the Kaggle ref, and it is the
    # first poll tick.
    # ------------------------------------------------------------------ #
    kaggle_rows = read_submissions(slug, timeout=args.poll_timeout, runner=run_kaggle)
    confirmed = (
        find_by_exp_id(kaggle_rows, exp_id, since=started)
        if kaggle_rows is not None
        else None
    )
    if confirmed is None:
        print(
            f"CANNOT CONFIRM the submission for {exp_id}: the read-back shows no matching "
            "Kaggle submission at or after this run started. NOT claiming success — the "
            "CLI's exit code is not proof, and only a read-back is. A slot MAY still have "
            "been spent.\n"
            f"  - check your submissions page: {submissions_url(slug)}\n"
            "  - if the submission is there, run `fetch_lb.py --reconcile` to back-fill it.",
            file=sys.stderr,
        )
        return EXIT_TRANSIENT_FAIL

    ref = confirmed.get("ref")

    # ⚠ WRITE THE PENDING ROW BEFORE POLLING (T-05-05-04). From here on the slot is
    # provably spent, so its provenance (exp_id <-> ref <-> file hash) must survive a
    # crash, a network death, or a Ctrl-C during the poll below. D-07: --reason is
    # recorded only when supplied; its absence is never an error.
    append_row(ws, new_row(
        exp_id=exp_id,
        kaggle_ref=ref,
        competition_slug=slug,
        file=f"experiments/{exp_id}/{SUBMISSION_CSV}",
        file_sha256=digest,
        message=message,
        submitted_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        status="PENDING",
        public_score=None,
        private_score=None,
        scored_at=None,
        override_reason=args.reason or None,
        error_description=None,
    ))

    # The confirming read-back doubles as the first poll tick: when Kaggle has already
    # scored the submission, there is nothing left to wait for.
    status = parse_status(confirmed.get("status"))
    if status in ("SCORED", "FAILED"):
        result = {
            "terminal": True,
            "status": status,
            "reason": "terminal",
            "row": confirmed,
            "last_out": "",
        }
    else:
        def _status_fn():
            return read_status_payload(slug, args.poll_timeout)

        try:
            result = poll_lb(
                _status_fn,
                now=time.monotonic,
                sleep=time.sleep,
                rng=random.Random(),
                budget_s=args.budget_s,
                max_consecutive_errors=MAX_CONSECUTIVE_ERRORS,
                select=lambda krows: by_ref(krows, ref),
            )
        except Exception as exc:  # noqa: BLE001 — a crashed poll must not eat the slot
            print(
                f"the leaderboard poll crashed ({type(exc).__name__}). The submission WAS "
                f"accepted (ref {ref}) and its PENDING row is already on disk, so NOTHING "
                "was lost — run `fetch_lb.py` to record the score.",
                file=sys.stderr,
            )
            return EXIT_TRANSIENT_FAIL

    # D-11: the outcome lands in control/submissions.jsonl and NOWHERE else. meta.json is
    # never written — the experiment folder is immutable after record.
    return record_outcome(ws, slug, result, exp_id=exp_id, ref=ref)


def read_status_payload(slug: str, timeout: int):
    """One read-only leaderboard poll tick, in the ``run_kaggle`` ``(rc, payload)`` shape.

    Routed through THIS module's gateway reference so the poll is exercised — and proven
    read-only — from the captured argv, without ever executing a command. The ARGV is the
    shared ``submissions_log.submissions_argv`` (WR-01), never a fourth private copy.
    """
    return run_kaggle(*submissions_argv(slug), timeout=timeout)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="submit.py",
        description="Submit an experiment's submission.csv to Kaggle. IRREVERSIBLE: it "
                    "spends one of a small number of daily slots. Success is confirmed by "
                    "READ-BACK, never by the CLI's (fail-open) exit code.",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    ap.add_argument("--exp-id", required=True,
                    help="The experiment whose submission.csv to submit (exp-NNN).")
    ap.add_argument("--confirm", action="store_true",
                    help="The human's explicit confirmation (D-05). Without it, nothing is "
                         "submitted. It overrides a gate BLOCK that is a JUDGMENT CALL (a "
                         "within-noise CV gain; the last assumed slot) — but NOT an "
                         "exhausted budget, an unknowable budget, or an experiment with no "
                         "readable CV: those are not confirmable.")
    ap.add_argument("--resubmit", action="store_true",
                    help="Deliberately spend ANOTHER slot on a file already submitted for "
                         "this experiment (defeats the double-spend guard).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the exact command and exit 0 WITHOUT calling Kaggle. This "
                         "is the only safe rehearsal; the CLI has no such mode.")
    ap.add_argument("--reason",
                    help="Optional free-text note recorded with the submission (e.g. why a "
                         "gate was overridden). Never required (D-07).")
    ap.add_argument("--budget-s", "--budget", dest="budget_s", type=float,
                    default=float(LB_BUDGET_S),
                    help="Wall-clock leaderboard-poll budget in seconds before detaching "
                         f"(default: {LB_BUDGET_S}). On expiry the row stays PENDING and "
                         "fetch_lb.py records the score later.")
    ap.add_argument("--poll-timeout", type=int, default=DEFAULT_POLL_TIMEOUT,
                    help=f"Per-call gateway timeout (default: {DEFAULT_POLL_TIMEOUT}).")
    return ap


if __name__ == "__main__":
    raise SystemExit(main())
