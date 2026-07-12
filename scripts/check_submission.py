#!/usr/bin/env python3
"""check_submission.py — the FREE "should I submit this?" gate (SCORE-01 / SCORE-03).

⭐ **THIS SCRIPT IS FREE. IT NEVER SPENDS A SUBMISSION SLOT.**

That is the entire point of the D-14 three-way split (check / submit / fetch). The user —
or the AI — can ask "should I submit this?" and get the COMPLETE decision material without
touching the scarce, irreversible daily budget. The only Kaggle call this script is ever
permitted to make is the READ-ONLY authoritative submissions list, and
``tests/test_check_submission.py::test_never_submits`` proves that mechanically from the
captured argv on every code path (clear / blocked / validation-failed / unsupported).

The ladder — every rung FAILS CLOSED with a distinct exit code and a precise,
framework-authored message:

  1. **D-01 type refusal** → ``SUBMIT_UNSUPPORTED`` (69). ``competition.type`` is not
     exactly ``"csv"``. Short-circuits BEFORE any Kaggle call: it costs nothing to know a
     CSV path cannot serve this competition.
  2. **D-02 file validation** → ``VALIDATION_FAILED`` (65). Four stdlib-``csv`` checks
     against the competition's own reference file. A malformed file is caught here, before
     a slot is ever spent on garbage.
  3. **D-04 budget** — Kaggle's OWN submissions list is the authority (there is no
     submission-quota command). An unfetchable or unparseable count BLOCKS; it is never
     guessed.
  4. **D-05/D-06 decision** — delegated to the pure ``submission_gate`` policy.
  5. **Render** the material and return ``0`` (clear) or ``GATE_BLOCKED`` (75).

D-05 is held exactly: this script never auto-submits and never silently hard-refuses. It
takes a POSITION and prints the override command. The HUMAN makes the call.

Exit codes (``SKILL.md`` branches on the EXACT values):
  * ``0``   — CLEAR to submit
  * ``65``  — ``VALIDATION_FAILED``  (D-02)
  * ``69``  — ``SUBMIT_UNSUPPORTED`` (D-01)
  * ``75``  — ``GATE_BLOCKED``       (D-05 — NOT an error; the human may confirm and submit)
  * ``77``  — ``UI_GATE``            (a 403 on the read-back; ``classify_gate`` owns it)
  * ``124`` / ``127`` — the gateway's timeout / missing-CLI markers, passed through

Portability + safety (CLAUDE.md §Stack Patterns): stdlib-only — the plumbing tier is
pandas-free, so the CSVs are read with the ``csv`` module. Self-locating
(``Path(__file__)``), ``--workspace``-driven, argparse-in / exit-code-out, and NEVER
interactive (no prompt call anywhere — the human loop is ``SKILL.md``'s job, D-10).

Every Kaggle call routes through the gateway (D-16), which is bound at MODULE level so the
test suite can substitute it and prove the argv without executing anything. A raw CLI
buffer is MATCHED, never echoed — it can carry a token-shaped string — and is quarantined
via ``dump_last_error`` (T-05-04-06).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from kaggle_gateway import (  # noqa: E402
    GATE_BLOCKED,
    SUBMIT_UNSUPPORTED,
    UI_GATE,
    VALIDATION_FAILED,
    _parse_json_array,
    classify_gate,
    dump_last_error,
    run_kaggle,
)
from metric_registry import REGISTRY  # noqa: E402
from submission_gate import NOISE_K_DEFAULT, decide  # noqa: E402
from submissions_log import (  # noqa: E402
    COUNT_UNAVAILABLE,
    charged_today,
    read_rows,
    remaining_slots,
    submissions_argv,
)

CONFIG_REL = "control/config.json"
LEDGER_REL = "control/ledger.jsonl"
TYPE_SIGNALS_REL = "control/raw/competition-type-signals.json"

# The closed reason enum for a D-02 failure — the parallel of
# ``record_experiment.FAILURE_REASONS``. A validation failure is always ONE of these, never
# a free-form string, so the caller can branch on the machine reason while the human reads
# the precise message that accompanies it.
VALIDATION_REASONS = (
    "no_sample_reference",
    "unreadable_file",
    "header_mismatch",
    "row_count_mismatch",
    "id_set_mismatch",
    "blank_prediction",
)

# Values that are NOT a prediction. Compared case-insensitively after stripping. Any of
# these in a prediction column means the file carries a hole where a number must be, and
# Kaggle would either reject the file or score the hole as garbage — either way a slot is
# burnt for nothing.
_NON_VALUES = {
    "",
    "nan",
    "na",
    "n/a",
    "none",
    "null",
    "nil",
    "inf",
    "+inf",
    "-inf",
    "infinity",
    "+infinity",
    "-infinity",
    "nat",
}

# An exp id is framework-generated (`exp-007`); it is never Kaggle text. The anchored
# shape is enforced anyway, because it becomes a filesystem path (T-05-04-07).
_EXP_ID_RE = re.compile(r"^exp-\d{3}$")


# --------------------------------------------------------------------------- #
# Reading the control plane (read-only — this script WRITES NOTHING).
# --------------------------------------------------------------------------- #
def _read_json(path: Path):
    """Parse a JSON file, or ``None`` when absent/corrupt (never a traceback)."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _read_ledger(ws: Path) -> list[dict]:
    """Parse ``control/ledger.jsonl`` (the ``regen_strategy._read_ledger`` fail-clear posture).

    READ-ONLY, and the join NEVER opens ``meta.json``: everything the gate needs (``exp_id``,
    ``status``, ``cv_mean``, ``cv_std``, ``greater_is_better``) is ALREADY in the ledger row.
    Reaching into the experiment folder would create a second source of truth (D-11).
    """
    path = ws / LEDGER_REL
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"ledger: skipping unparseable line: {exc}.", file=sys.stderr)
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _as_number(value):
    """``value`` as a float, or ``None``. ``bool`` is excluded (``True`` is an ``int``)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


# --------------------------------------------------------------------------- #
# D-02 — the reference file. REUSE Phase 2's signal; never guess a filename.
# --------------------------------------------------------------------------- #
class Reference:
    """What the submission file is validated AGAINST, and where it came from.

    ``header`` is ``None`` for the ``test.csv`` fallback: that file legitimately does not
    know the name of the target column, so the header check is skipped and the id-set +
    row-count + blank checks carry the validation. It is still a REAL check, not a rubber
    stamp — a wrong id set is caught either way.
    """

    def __init__(self, *, label: str, header, ids: list[str], pred_values=None):
        self.label = label
        self.header = header
        self.ids = ids
        self.pred_values = pred_values or []

    @property
    def count(self) -> int:
        return len(self.ids)


def _read_csv(path: Path):
    """``(header, data_rows)`` via the stdlib ``csv`` module. Trailing blank lines dropped.

    RAISES on an unreadable file (``OSError`` / ``UnicodeDecodeError`` / ``csv.Error``).
    :func:`validate_submission` catches those to author a precise ``unreadable_file``
    reason; every other caller goes through :func:`_read_csv_or_none`, which fails closed.
    ⚠ There is no third option: an UNGUARDED call here is a raw traceback out of a gate
    SKILL.md promises is "argparse in, exit code out" (WR-09).
    """
    with path.open(newline="") as fh:
        rows = [row for row in csv.reader(fh)]
    while rows and not any(cell.strip() for cell in rows[-1]):
        rows.pop()
    if not rows:
        return [], []
    return [c.strip() for c in rows[0]], rows[1:]


def _read_csv_or_none(path: Path, *, role: str):
    """:func:`_read_csv`, or ``None`` after a clear message — never a traceback (WR-09).

    A reference file with a non-UTF-8 encoding, a NUL byte, or a permissions problem is a
    real, plausible corruption (a truncated download; a latin-1/UTF-16 file). Crashing on
    one takes the FREE gate out of the "exit code out" contract entirely — and a gate that
    crashes is a gate the agent may route around, which costs an irreversible slot.
    """
    try:
        return _read_csv(path)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        print(
            f"the {role} {path.name} could not be READ ({type(exc).__name__}: {exc}). "
            "FAILING CLOSED — a file we cannot read is not a file we can validate against.",
            file=sys.stderr,
        )
        return None


def _resolve_reference(ws: Path) -> Reference | None:
    """The R4 resolution ladder. ``None`` => nothing to validate against => FAIL CLOSED.

    1. ``control/raw/competition-type-signals.json`` → ``signals.submission_csv_in_manifest``
       (Phase 2's heuristic — CONSUMED, never re-derived). Titanic's reference file is
       ``gender_submission.csv``; a resolver that GUESSED the conventional name would pick
       the wrong file and report a bogus header mismatch.
    2. Else a case-insensitive ``data/*submission*.csv`` scan, first match.
    3. Else derive the expected id SET and row count from ``data/test.csv``'s FIRST column
       (D-02's explicit fallback).
    4. Else ``None``.

    ⚠ The Phase 2 signal takes the FIRST manifest match and its own comment flags the
    heuristic as WEAK. :func:`main` therefore PRINTS the chosen file so a human can spot a
    wrong pick (T-05-04-03) — a silently-wrong reference would validate a garbage file
    clean and spend a real slot on it.
    """
    data_dir = ws / "data"
    chosen: Path | None = None

    signals_doc = _read_json(ws / TYPE_SIGNALS_REL) or {}
    signals = signals_doc.get("signals") or {}
    named = signals.get("submission_csv_in_manifest")
    if isinstance(named, str) and named:
        # Basename ONLY — the signal is a manifest NAME, never a path to follow (a
        # `../../etc/passwd` value must not escape data/). T-05-04-03.
        candidate = data_dir / Path(named).name
        if candidate.is_file():
            chosen = candidate

    if chosen is None and data_dir.is_dir():
        for path in sorted(data_dir.iterdir()):
            name = path.name.lower()
            if path.is_file() and "submission" in name and name.endswith(".csv"):
                chosen = path  # rung 2: the case-insensitive glob
                break

    if chosen is not None:
        # WR-09: an unreadable reference is `None` => FAIL CLOSED, never a traceback. It
        # deliberately does NOT fall through to the weaker test.csv rung: a corrupt sample
        # is a broken workspace, and silently validating against a different, weaker
        # reference would hide that from the human who has to trust the result.
        read = _read_csv_or_none(chosen, role="reference file")
        if read is None:
            return None
        header, rows = read
        if len(header) >= 2 and rows:
            return Reference(
                label=chosen.name,
                header=header,
                ids=[r[0].strip() for r in rows if r],
                pred_values=[r[1].strip() for r in rows if len(r) > 1],
            )

    # Rung 3 — the test.csv fallback: the ids we must predict for are exactly test.csv's.
    test_path = data_dir / "test.csv"
    if test_path.is_file():
        read = _read_csv_or_none(test_path, role="id-set fallback")
        if read is None:
            return None
        header, rows = read
        if header and rows:
            return Reference(
                label="test.csv (id column fallback — no reference submission file found)",
                header=None,
                ids=[r[0].strip() for r in rows if r],
            )

    return None


# --------------------------------------------------------------------------- #
# D-02 — the four checks. Order matters: report the FIRST, most structural mismatch.
# --------------------------------------------------------------------------- #
def _is_non_value(cell: str) -> bool:
    """Is this cell a hole rather than a prediction? (blank / NaN / NA / null / inf)"""
    text = cell.strip()
    if text.lower() in _NON_VALUES:
        return True
    try:
        value = float(text)
    except ValueError:
        return False  # a non-numeric label (e.g. a class name) is legitimate.
    return math.isnan(value) or math.isinf(value)


def _looks_integral(values) -> bool:
    """Are ALL of these values integers (``0`` / ``1`` / ``3``, not ``0.4``)?"""
    if not values:
        return False
    for raw in values:
        try:
            value = float(raw)
        except ValueError:
            return False
        if not float(value).is_integer():
            return False
    return True


def validate_submission(csv_path: Path, ref: Reference) -> tuple[str | None, str]:
    """``(reason, message)`` — ``(None, "")`` means the file is well-formed.

    The message names the EXACT mismatch (real values, real counts, real column names). A
    validator that only says "invalid" teaches the user nothing and invites them to
    override blindly — which spends the slot the check exists to protect.
    """
    try:
        header, rows = _read_csv(csv_path)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return "unreadable_file", f"submission.csv could not be read: {exc}"

    if not header:
        return "header_mismatch", "submission.csv is empty — it has no header row."
    if len(header) < 2:
        return (
            "header_mismatch",
            f"submission.csv header {header} has only {len(header)} column(s) — a "
            "submission needs an id column and at least one prediction column.",
        )

    # 1. Exact column headers, ORDER-SENSITIVE (Kaggle is).
    if ref.header is not None and header != ref.header:
        return (
            "header_mismatch",
            f"header {header} != expected {ref.header} (from {ref.label}). Kaggle "
            "compares the header EXACTLY, including column order.",
        )

    # 2. Exact row count.
    if len(rows) != ref.count:
        return (
            "row_count_mismatch",
            f"row count {len(rows)} != expected {ref.count} (from {ref.label}). Every "
            "test id needs exactly one prediction row.",
        )

    # 3. The id SET — order-INDEPENDENT (Kaggle joins on the id, it does not zip by position).
    ours = [r[0].strip() if r else "" for r in rows]
    our_ids, expected_ids = set(ours), set(ref.ids)
    if our_ids != expected_ids:
        missing = sorted(expected_ids - our_ids)
        extra = sorted(our_ids - expected_ids)
        parts = []
        if missing:
            parts.append(
                f"{len(missing)} id(s) in {ref.label} are MISSING from your file "
                f"(first: {missing[0]})"
            )
        if extra:
            parts.append(
                f"{len(extra)} id(s) in your file are NOT in {ref.label} "
                f"(first: {extra[0]})"
            )
        if len(ours) != len(our_ids):
            parts.append(f"your file has {len(ours) - len(our_ids)} DUPLICATE id(s)")
        return "id_set_mismatch", "id set mismatch: " + "; ".join(parts) + "."

    # 4. No blank / NaN / NA / null / inf anywhere in a PREDICTION column (every column
    #    after the id). A hole here is not a prediction, and Kaggle will not treat it as one.
    for col_index in range(1, len(header)):
        holes = [
            (i, row[col_index])
            for i, row in enumerate(rows, start=2)  # start=2: row 1 is the header
            if col_index < len(row) and _is_non_value(row[col_index])
        ]
        short = [i for i, row in enumerate(rows, start=2) if col_index >= len(row)]
        if holes or short:
            first_row = holes[0][0] if holes else short[0]
            return (
                "blank_prediction",
                f"{len(holes) + len(short)} blank/NaN value(s) in prediction column "
                f"'{header[col_index]}' (first at row {first_row}). A blank is not a "
                "prediction — every row must carry a real value.",
            )

    return None, ""


def label_trap_warning(csv_path: Path, ref: Reference, metric_name: str) -> str | None:
    """The D-09 fold-averaged-hard-labels trap, caught for real — or ``None``.

    A LABEL metric (accuracy / f1 / qwk …) needs ``0`` / ``1``, but a run_cv that MEANS its
    fold predictions emits ``0.4`` / ``0.6``. The four structural checks above would pass
    that file happily — right shape, right ids, no blanks — and a real, irreversible slot
    would be spent on numbers Kaggle cannot use.

    The metric's ``prediction_type`` comes from the tooling-written config, never a guess:
    a probability metric (roc_auc / logloss) legitimately WANTS continuous values even when
    the reference file happens to show ``0`` / ``1``, so it must not be warned about.
    """
    entry = REGISTRY.get(metric_name) or {}
    if entry.get("prediction_type") not in ("label", None):
        return None  # proba / raw: continuous values are exactly right.
    if ref.header is None or not _looks_integral(ref.pred_values):
        return None

    # WR-09: guarded like every other read outside validate_submission. In practice main()
    # has already validated this exact file (so it IS readable), but a warning helper is the
    # last place that should be able to crash the gate it is decorating.
    read = _read_csv_or_none(csv_path, role="submission file")
    if read is None:
        return None
    _, rows = read
    offenders = [
        row[1].strip()
        for row in rows
        if len(row) > 1 and not _looks_integral([row[1].strip()])
    ]
    if not offenders:
        return None
    return (
        f"⚠ LABEL-METRIC TRAP (D-09): the metric '{metric_name}' scores LABELS and "
        f"{ref.label} contains only integers, but your file has {len(offenders)} "
        f"non-integer prediction(s) (first: {offenders[0]}). This is the signature of "
        f"fold predictions being AVERAGED instead of VOTED — a mean of 0 and 1 across "
        f"folds emits 0.4/0.6 where Kaggle wants 0/1. The file is structurally valid, so "
        f"nothing else would catch this. Fix the aggregation before spending a slot."
    )


# --------------------------------------------------------------------------- #
# D-04 — the budget. Kaggle's own list is the authority; the count is NEVER guessed.
# --------------------------------------------------------------------------- #
def fetch_submissions(ws: Path, slug: str, timeout: int = 60):
    """``(rows | None, exit_code | None)`` — the READ-ONLY authoritative submissions list.

    ⭐ This is the ONLY Kaggle call this script may ever make, and it is READ-ONLY. The
    ``submit`` subcommand is never constructed anywhere in this module (T-05-04-01).

    ``run_kaggle`` is called through THIS module's binding (the ``poll_kernel`` posture) so
    the suite can substitute the gateway and assert the exact argv without executing it.
    The ARGV, though, is not re-derived here: ``submissions_log.submissions_argv`` owns the
    one true command (WR-01). This function exists separately from
    ``fetch_lb.read_submissions`` only because it must CLASSIFY the failure — a 403 UI gate,
    a missing CLI, a timeout each need a different exit code, and that classification is
    what the free gate is FOR.

    An exit code is returned when the caller must terminate on it (a 403 UI gate, a missing
    CLI, a timeout); otherwise ``rows`` is ``None`` and the caller FAILS CLOSED.
    """
    rc, out = run_kaggle(*submissions_argv(slug), timeout=timeout)
    if rc == 127:
        print(
            "cannot check the budget: the kaggle CLI was not found on PATH. Install it "
            "(`uv pip install kaggle`) and re-run.",
            file=sys.stderr,
        )
        return None, rc
    if rc == 124:
        print(
            "cannot check the budget: the kaggle CLI timed out (a stalled/blocked "
            "egress). Check the egress allowlist and re-run.",
            file=sys.stderr,
        )
        return None, rc
    if rc != 0:
        # The raw buffer is quarantined, never echoed: it can carry a token-shaped string.
        dump_path = dump_last_error(ws, out)

        # ⚠ ONLY A 403 IS A UI GATE (WR-03). Mapping EVERY non-zero rc here told a user with
        # an expired token to "accept the competition rules and verify your phone" — and
        # `classify_gate` made a SECOND live Kaggle call (its preflight probe) to reach that
        # wrong conclusion. A 401 is an HTTPError -> exit 1; so is a 5xx, and so is a dead
        # network. `submit.py` has always guarded exactly this way; the two scripts must not
        # classify the same CLI failure differently.
        if "403" in out or "forbidden" in out.lower():
            # ONE classifier owns the gate (D-11/D-12) — never a second.
            print(classify_gate(out, slug), file=sys.stderr)
            print(
                f"  (raw CLI output quarantined to {dump_path.relative_to(ws)} — withheld "
                "from the terminal to avoid leaking a secret)",
                file=sys.stderr,
            )
            return None, UI_GATE

        print(
            f"cannot check the budget: the kaggle CLI failed (exit {rc}) and the failure is "
            "NOT a 403 gate. The raw output is withheld (it can carry a secret) and was "
            f"quarantined to {dump_path.relative_to(ws)}. Check your credentials "
            "(check_credentials.py) and the network, then re-run.",
            file=sys.stderr,
        )
        # rows=None => charged=-1 => remaining=None => BLOCKED. FAIL CLOSED, and the block
        # is rendered with the real reason rather than a guessed one.
        return None, None

    rows = _parse_json_array(out)
    if not isinstance(rows, list):
        return None, None  # unparseable payload => fail closed (never guess a count).
    return rows, None


# --------------------------------------------------------------------------- #
# The CV comparison set (D-06) — the best ALREADY-SUBMITTED CV.
# --------------------------------------------------------------------------- #
def best_submitted_cv(ws: Path, ledger: list[dict], greater_is_better: bool):
    """The best ``cv_mean`` among experiments that have ACTUALLY been submitted, or ``None``.

    "Submitted" means a ``control/submissions.jsonl`` row with status ``PENDING`` or
    ``SCORED``. A ``FAILED`` row is a submission Kaggle never accepted, so its experiment
    was never really on the board and must not set the bar others have to clear.

    ``None`` means NOTHING has been submitted yet — the comparison set is EMPTY, and the
    gate treats that as CLEAR (the first submission is never blocked for failing to beat a
    baseline that does not exist).
    """
    submitted = {
        row.get("exp_id")
        for row in read_rows(ws)
        if row.get("status") in ("PENDING", "SCORED")
    }
    scores = [
        cv
        for row in ledger
        if row.get("exp_id") in submitted and row.get("status") == "SUCCESS"
        for cv in [_as_number(row.get("cv_mean"))]
        if cv is not None
    ]
    if not scores:
        return None
    return max(scores) if greater_is_better else min(scores)


def _divergence_line(ws: Path, ledger: list[dict]) -> str:
    """The CV→LB divergence state, or the HONEST line when there is not enough evidence.

    Two scored submissions is the floor for a trend. Below it, the framework says so in
    plain words rather than rendering a confident-looking gap from a single point.
    """
    by_exp = {row.get("exp_id"): _as_number(row.get("cv_mean")) for row in ledger}
    gaps = [
        lb - by_exp[row.get("exp_id")]
        for row in read_rows(ws)
        if row.get("status") == "SCORED"
        for lb in [_as_number(row.get("public_score"))]
        if lb is not None and by_exp.get(row.get("exp_id")) is not None
    ]
    if len(gaps) < 2:
        return f"needs >=2 scored submissions (have {len(gaps)})"
    mean_gap = sum(gaps) / len(gaps)
    return (
        f"mean CV->LB gap over {len(gaps)} scored submissions: {mean_gap:+.6f} "
        f"(LB - CV; a large negative gap means the CV is optimistic)"
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Decide whether an experiment is worth a submission slot. FREE: this never "
            "submits and never spends a slot."
        )
    )
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--exp-id", help="e.g. exp-007")
    group.add_argument("--exp-dir", help="e.g. experiments/exp-007")
    return parser


def _resolve_exp_dir(ws: Path, args) -> Path | None:
    """The experiment directory, CONFINED under ``ws/experiments/`` (IN-01, T-05-04-07).

    Resolved and then containment-checked, so no ``--exp-dir ../../etc`` can point the
    validator (or a printed path) outside the workspace.
    """
    root = (ws / "experiments").resolve()
    if args.exp_id:
        if not _EXP_ID_RE.match(args.exp_id):
            print(
                f"invalid --exp-id {args.exp_id!r}: expected the form exp-007.",
                file=sys.stderr,
            )
            return None
        candidate = (root / args.exp_id).resolve()
    else:
        raw = Path(args.exp_dir)
        candidate = (raw if raw.is_absolute() else ws / raw).resolve()

    if candidate != root and root not in candidate.parents:
        print(
            f"refusing to read {candidate} — it is outside {root}. The experiment path "
            "is confined to the workspace.",
            file=sys.stderr,
        )
        return None
    return candidate


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()

    config = _read_json(ws / CONFIG_REL)
    if config is None:
        print(
            f"no readable {CONFIG_REL} in {ws} — is this a scaffolded workspace?",
            file=sys.stderr,
        )
        return 1

    # ---------------------------------------------------------------- 1. D-01 ----
    # The type refusal short-circuits BEFORE any Kaggle call. It costs NOTHING to know
    # the CSV path cannot serve this competition, so nothing is spent finding out.
    comp_type = (config.get("competition") or {}).get("type")
    if comp_type != "csv":
        named = comp_type if comp_type else "unknown"
        print(
            f"REFUSING to check a submission for competition.type={named!r} — the CSV "
            f"submission path is UNAVAILABLE here.\n"
            f"  A CODE competition is submitted by pushing a KERNEL and pointing Kaggle "
            f"at a kernel VERSION (`-k owner/slug -v N`), which is a different Kaggle "
            f"mechanism entirely and is out of scope for v1 — a CSV upload cannot serve "
            f"it.\n"
            f"  On an 'unknown' type the CSV path REFUSES rather than risk spending a "
            f"scarce, irreversible slot on a guess (the Phase 2 D-14 contract).\n"
            f"  If this competition really does take a CSV, set it explicitly in "
            f"{CONFIG_REL} -> competition.type and re-run.",
            file=sys.stderr,
        )
        return SUBMIT_UNSUPPORTED

    slug = config.get("competition_slug")
    if not isinstance(slug, str) or not slug:
        print(f"{CONFIG_REL} has no competition_slug.", file=sys.stderr)
        return 1

    exp_dir = _resolve_exp_dir(ws, args)
    if exp_dir is None:
        return 1
    exp_id = exp_dir.name

    csv_path = exp_dir / "submission.csv"
    if not csv_path.is_file():
        print(
            f"no submission.csv in {exp_dir} — re-run the experiment with a "
            "submission-emitting harness before checking it.",
            file=sys.stderr,
        )
        return VALIDATION_FAILED

    # ---------------------------------------------------------------- 2. D-02 ----
    ref = _resolve_reference(ws)
    if ref is None:
        print(
            f"[{VALIDATION_REASONS[0]}] nothing to validate against: no reference "
            "submission file under data/ (neither the Phase 2 manifest signal nor a "
            "*submission*.csv scan found one) AND no data/test.csv to derive the id set "
            "from. FAILING CLOSED — an unvalidated file is never submitted.",
            file=sys.stderr,
        )
        return VALIDATION_FAILED

    # PRINT the chosen reference: the Phase 2 heuristic takes the FIRST manifest match and
    # its own comment flags it as WEAK, so a human must be able to spot a wrong pick.
    print(f"validating {csv_path.name} against reference: {ref.label} ({ref.count} rows)")

    reason, message = validate_submission(csv_path, ref)
    if reason is not None:
        print(f"[{reason}] {message}", file=sys.stderr)
        print(
            "FAILING CLOSED (D-02): a malformed file is caught here, before a scarce, "
            "irreversible submission slot is spent on it.",
            file=sys.stderr,
        )
        return VALIDATION_FAILED

    metric = config.get("metric") or {}
    metric_name = metric.get("name")
    greater_is_better = metric.get("greater_is_better")
    if not metric_name or not isinstance(greater_is_better, bool):
        # The direction is TOOLING-WRITTEN (set_metric.py), never guessed. Without it the
        # gate cannot even tell which way "better" points — so it blocks.
        print(
            f"BLOCKED: {CONFIG_REL} -> metric is missing name/greater_is_better. The "
            "metric direction is never guessed — run set_metric.py and re-run.",
            file=sys.stderr,
        )
        return GATE_BLOCKED

    trap = label_trap_warning(csv_path, ref, metric_name)

    # ---------------------------------------------------------------- 3. D-04 ----
    rows, exit_code = fetch_submissions(ws, slug)
    if exit_code is not None:
        return exit_code

    charged = (
        charged_today(rows, datetime.now(timezone.utc))
        if rows is not None
        else COUNT_UNAVAILABLE
    )
    submission_cfg = config.get("submission") or {}
    daily_limit = submission_cfg.get("daily_limit")
    limit_provenance = submission_cfg.get("limit_provenance")
    remaining = remaining_slots(daily_limit, charged)

    # ---------------------------------------------------------------- 4. D-05 ----
    ledger = _read_ledger(ws)
    ours = next(
        (
            row
            for row in ledger
            if row.get("exp_id") == exp_id and row.get("status") == "SUCCESS"
        ),
        None,
    )
    if ours is None:
        print(
            f"BLOCKED: {exp_id} has no SUCCESS row in {LEDGER_REL} — there is no CV to "
            "reason about. Record the experiment first (record_experiment.py).",
            file=sys.stderr,
        )
        return GATE_BLOCKED

    cand_cv = _as_number(ours.get("cv_mean"))
    cand_std = _as_number(ours.get("cv_std"))
    best_cv = best_submitted_cv(ws, ledger, greater_is_better)

    noise_k = submission_cfg.get("noise_k")
    if _as_number(noise_k) is None:
        # An already-scaffolded workspace predates the template's noise_k key.
        noise_k = NOISE_K_DEFAULT

    verdict = decide(
        cand_cv=cand_cv,
        cand_std=cand_std,
        best_cv=best_cv,
        greater_is_better=greater_is_better,
        remaining=remaining,
        limit_provenance=limit_provenance,
        k=noise_k,
    )

    # ---------------------------------------------------------------- 5. Render ----
    direction = "higher is better" if greater_is_better else "lower is better"
    baseline = (
        "none yet — this is the FIRST submission"
        if best_cv is None
        else f"{best_cv:.6f}"
    )
    budget = "UNKNOWN (fail closed)" if remaining is None else str(remaining)
    # ⚠ WR-11 — `charged` is -1 (COUNT_UNAVAILABLE) when the count could not be established,
    # and that is a SENTINEL, not a number: submissions_log says of it "it is not a count:
    # callers MUST fail closed on it and never coerce it". SKILL.md tells the agent to relay
    # this line to the user VERBATIM, so "charged=-1" would put "minus one submissions" in
    # front of a human at the exact moment they decide whether to spend an irreversible slot.
    charged_text = "UNKNOWN" if charged == COUNT_UNAVAILABLE else str(charged)

    print()
    print(f"experiment:     {exp_id}")
    print(f"CV:             {cand_cv} +/- {cand_std}  ({metric_name}, {direction})")
    print(f"best submitted: {baseline}")
    print(f"noise bound:    k={noise_k} * cv_std")
    print(f"slots left:     {budget} today (UTC day; charged={charged_text})")
    print(f"CV->LB:         {_divergence_line(ws, ledger)}")
    print()

    if trap:
        print(trap)
        print()

    for line in verdict["reasons"]:
        print(f"  - {line}")
    for line in verdict["warnings"]:
        print(f"  ! {line}")
    print()

    clear = verdict["recommendation"] == "SUBMIT" and not verdict["requires_confirmation"]
    if trap:
        # The file is structurally valid but almost certainly carries averaged labels. Do
        # not hand back a clean bill of health — make the human confirm knowingly.
        clear = False

    print(f"RECOMMENDATION: {verdict['recommendation']}")
    if clear:
        print("CLEAR to submit. To spend the slot:")
    else:
        print(
            "This is a RECOMMENDATION, not a refusal (D-05) — you make the call. To "
            "override and submit anyway:"
        )
    print(
        f'  python3 scripts/submit.py --workspace {ws} --exp-id {exp_id} --confirm '
        f'[--reason "..."]'
    )
    print("  (--reason is OPTIONAL — D-07: the framework never demands a justification.)")

    return 0 if clear else GATE_BLOCKED


if __name__ == "__main__":
    raise SystemExit(main())
