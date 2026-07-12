#!/usr/bin/env python3
"""regen_strategy.py — regenerate strategy.md from the ledger each cycle (MEM-02/03, D-11/D-12).

The `regen` entry point of the D-02 idempotent loop (`scaffold -> run -> record ->
regen_strategy`). `strategy.md` is a PURE FUNCTION of `control/ledger.jsonl` (the FACTS) plus
an AI-authored `--reasoning-file` markdown fragment (the REASONING), so a stale hand-edit can
never survive to misrepresent the ledger.

Two halves, deliberately split by who authors them:

  * **FACTS (tooling-rendered, cannot drift or be fabricated — T-03-05-01/04).** From
    `ledger.jsonl` this module computes the CURRENT BEST by the metric's DIRECTION
    (`max(cv_mean)` if `greater_is_better` else `min`, among `status=="SUCCESS"` rows) and the
    TRIED-LIST DIGEST (one line per row — the D-13 never-repeat surface). The current-best
    number comes from the ledger, never from the AI. Direction is read from the
    tooling-written `config.json.metric.greater_is_better` (03-01), not free-typed.

  * **REASONING (AI-authored, fresh each cycle).** The `--reasoning-file` fragment (hypothesis
    queue + next action) is spliced into the doc VERBATIM. The tool never authors reasoning; if
    the file is missing it BLOCKS (mechanical sections stay tooling-owned).

Phase 5 (SCORE-02) EXTENDS this contract with ONE more FACTS renderer — it does not fork it.
`_lb_gap_body` joins `control/submissions.jsonl` (the canonical LB record) against the ledger on
`exp_id` (the DERIVED D-11 view — the experiment folder is never reopened) and renders the CV→LB
gap trend plus the D-10 rank-inversion alarm. Those LB numbers are FACTS, exactly like
current-best: they come only from the two JSONL files and the AI can never type them. CV remains
the DECISION metric everywhere; the gap is observed and trended, never used to pick an experiment.

Unlike competition.md's section-safe-merge helper (competition_doc), strategy.md is
FULLY OVERWRITTEN ATOMICALLY each cycle (D-12, the deliberate opposite): render header + FACTS
+ REASONING to a sibling `.tmp` and `os.replace` it onto `strategy.md`. A crash mid-write leaves
the previous file intact; a hand edit is clobbered on the next regen.

Portability (CLAUDE.md §Stack Patterns): self-locating via `Path(__file__)`, `--workspace`-driven,
stdlib-only (no ML stack), non-interactive (argparse in / exit-code out).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lb_gap  # noqa: E402
import submissions_log  # noqa: E402

# The verbatim D-12 header note every regenerated strategy.md carries so a human reading it
# knows it is machine-owned and any manual edit will be overwritten on the next cycle.
HEADER_NOTE = "Generated each cycle from control/ledger.jsonl — manual edits are overwritten."


def _is_number(value) -> bool:
    """True for a real int/float (bools are NOT numbers here)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _read_ledger(path: Path) -> list[dict]:
    """Parse `control/ledger.jsonl` into a list of row dicts (empty/missing → []).

    Each non-blank line is one derived row (`experiment_meta.to_ledger_row` shape). A blank
    line is skipped; an empty file is a valid empty ledger.
    """
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        # Fail-clear, matching rebuild_ledger's posture (WR-02): a single malformed line
        # (e.g. a truncated final line from an interrupted write) must NOT abort strategy
        # regeneration with a raw traceback. Skip-and-warn, and skip non-object rows so a
        # scalar/list line cannot later raise AttributeError on r.get(...).
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"regen: skipping unparseable ledger line: {exc}.", file=sys.stderr)
            continue
        if not isinstance(row, dict):
            print("regen: skipping non-object ledger line.", file=sys.stderr)
            continue
        rows.append(row)
    return rows


def _read_greater_is_better(config_path: Path) -> tuple[bool | None, str | None]:
    """Fail-clear read of `config.json.metric.greater_is_better`. Returns (gib, error_msg).

    The direction is what orders the current-best pick, so it MUST come from the
    tooling-written config (T-03-05-04) — never guessed. A missing/corrupt config or an
    unset metric blocks with a clear message (run set_metric.py first).
    """
    if not config_path.exists():
        return None, f"no {config_path} — run init/set_metric first."
    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        return None, f"{config_path.name} is not valid JSON (left untouched): {exc}."
    metric_field = config.get("metric")
    if not isinstance(metric_field, dict) or metric_field.get("greater_is_better") is None:
        return None, "config.json.metric is not set — run set_metric.py first (D-08)."
    return bool(metric_field["greater_is_better"]), None


def _read_slug(config_path: Path) -> str:
    """Best-effort read of `config.json.competition_slug` for the doc title (defaults "")."""
    try:
        config = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    slug = config.get("competition_slug")
    return slug if isinstance(slug, str) else ""


def _fmt_score(cv_mean, cv_std) -> str:
    """Render `cv_mean±cv_std`, or an em-dash when the mean is absent (a FAILED row)."""
    if not _is_number(cv_mean):
        return "—"
    std = cv_std if _is_number(cv_std) else 0.0
    return f"{cv_mean:g}±{std:g}"


def _current_best_body(rows: list[dict], greater_is_better: bool) -> str:
    """FACT: the best SUCCESS row by the metric's direction, or "None yet." (empty/no success).

    Among `status=="SUCCESS"` rows with a numeric `cv_mean`, pick `max` if `greater_is_better`
    else `min`. The number is sourced ONLY from the ledger (never the reasoning file), so it
    cannot be fabricated or drift (T-03-05-01).
    """
    winners = [r for r in rows if r.get("status") == "SUCCESS" and _is_number(r.get("cv_mean"))]
    if not winners:
        return "None yet."
    pick = max if greater_is_better else min
    best = pick(winners, key=lambda r: r["cv_mean"])
    metric = best.get("metric") or "?"
    idea = best.get("idea") or "(no idea recorded)"
    verdict = best.get("verdict_path") or ""
    verdict_link = f"[verdict]({verdict})" if verdict else "(no verdict)"
    return (
        f"**{best.get('exp_id')}** — {_fmt_score(best.get('cv_mean'), best.get('cv_std'))} "
        f"({metric}) — idea: \"{idea}\" — {verdict_link}"
    )


def _tried_list_body(rows: list[dict]) -> str:
    """FACT: one line per ledger row — the D-13 never-repeat digest.

    Renders `exp-NNN | idea | status | cv_mean±std | verdict link` per row. An empty ledger
    renders an explicit "no experiments" note (never a fabricated row).
    """
    if not rows:
        return "_No experiments recorded yet._"
    lines = []
    for r in rows:
        verdict = r.get("verdict_path") or ""
        verdict_link = f"[verdict]({verdict})" if verdict else "(no verdict)"
        idea = r.get("idea") or "(no idea recorded)"
        lines.append(
            f"- {r.get('exp_id')} | {idea} | {r.get('status')} | "
            f"{_fmt_score(r.get('cv_mean'), r.get('cv_std'))} | {verdict_link}"
        )
    return "\n".join(lines)


def _lb_gap_body(sub_rows: list[dict], ledger_rows: list[dict], greater_is_better: bool) -> str:
    """FACT: the CV→LB gap trend + the D-10 divergence alarm (SCORE-02).

    The THIRD tooling-rendered facts section, sourced ONLY by joining `control/submissions.jsonl`
    against `control/ledger.jsonl` on `exp_id` (`lb_gap.join_cv_lb` — the DERIVED D-11 view). Like
    current-best, every number here is TOOLING-WRITTEN: the AI's `--reasoning-file` cannot
    fabricate an LB score or a gap, and a stale copy cannot drift (T-05-06-01).

    Renders, in order: the per-submission gap table ordered by `scored_at` (the TREND), a plain
    count of the submissions that carry no number yet, and the alarm — which is HONEST below two
    scored points rather than printing a fabricated all-clear (T-05-06-03).

    CV stays the DECISION metric: this section OBSERVES and WARNS. It never picks an experiment,
    and no LB number here is allowed to override a CV-based decision (SCORE-02).
    """
    joined = lb_gap.join_cv_lb(sub_rows, ledger_rows)

    blocks: list[str] = []
    if not joined:
        blocks.append("None yet.")
    else:
        lines = [
            "| exp | cv_mean | lb_score | gap (lb − cv) |",
            "| --- | --- | --- | --- |",
        ]
        for r in joined:
            lines.append(
                f"| {r['exp_id']} | {r['cv_mean']:g} | {r['lb_score']:g} | {r['gap']:+g} |"
            )
        blocks.append("\n".join(lines))

    # Submissions that carry no number yet — stated plainly, never counted as a score.
    pending = sum(1 for r in sub_rows if isinstance(r, dict) and r.get("status") == "PENDING")
    failed = sum(1 for r in sub_rows if isinstance(r, dict) and r.get("status") == "FAILED")
    notes: list[str] = []
    if pending:
        notes.append(
            f"{pending} submission(s) PENDING (not yet scored) — run `fetch_lb.py` to score them."
        )
    if failed:
        notes.append(f"{failed} submission(s) FAILED — Kaggle does not charge these (D-13).")
    if notes:
        blocks.append("\n".join(f"_{n}_" for n in notes))

    blocks.append(lb_gap.alarm_body(lb_gap.to_pairs(joined), greater_is_better))
    return "\n\n".join(blocks)


def _render(slug: str, rows: list[dict], sub_rows: list[dict], greater_is_better: bool,
            reasoning: str) -> str:
    """Assemble the full strategy.md document (header + FACTS + verbatim REASONING)."""
    title = f"# Strategy — {slug}" if slug else "# Strategy"
    return (
        f"{title}\n\n"
        f"> {HEADER_NOTE}\n\n"
        f"## Current best\n\n"
        f"{_current_best_body(rows, greater_is_better)}\n\n"
        f"## Tried-list digest\n\n"
        f"{_tried_list_body(rows)}\n\n"
        f"## CV-to-LB gap\n\n"
        f"{_lb_gap_body(sub_rows, rows, greater_is_better)}\n\n"
        f"## Reasoning (hypothesis queue & next action)\n\n"
        f"{reasoning.strip()}\n"
    )


def _atomic_write(path: Path, text: str) -> None:
    """Crash-safe full overwrite: render to a sibling `.tmp` then `os.replace` (D-12).

    NOT a section-merge (that is competition.md's job); strategy.md is a pure function of
    ledger + reasoning-file, so the whole file is replaced atomically each cycle.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="regen_strategy.py",
        description="Regenerate strategy.md as a pure function of control/ledger.jsonl (FACTS) "
                    "plus an AI-authored --reasoning-file (REASONING). Fully overwrites the "
                    "file atomically each cycle (D-12) — a hand edit is clobbered; the "
                    "current-best number is tooling-rendered from the ledger, never AI-typed.",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    ap.add_argument("--reasoning-file", type=Path, required=True,
                    help="Path to the AI-authored markdown reasoning fragment (hypothesis "
                         "queue + next action). REQUIRED — the tool never authors reasoning.")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()

    # REASONING is AI-owned and REQUIRED: block rather than author it ourselves so the
    # mechanical sections stay tooling-owned (D-11).
    reasoning_path = args.reasoning_file
    if not reasoning_path.is_file():
        print(
            f"cannot regen: --reasoning-file {reasoning_path} not found — the AI must author "
            f"the hypothesis-queue + next-action fragment first (D-11).",
            file=sys.stderr,
        )
        return 1
    reasoning = reasoning_path.read_text()

    config_path = ws / "control" / "config.json"
    greater_is_better, cfg_err = _read_greater_is_better(config_path)
    if cfg_err is not None:
        print(f"cannot regen: {cfg_err}", file=sys.stderr)
        return 1

    rows = _read_ledger(ws / "control" / "ledger.jsonl")
    # The LB record is Phase-5-new: a workspace that has never submitted simply has no
    # submissions.jsonl, and read_rows returns [] for it (fail-clear, skip-and-warn on a
    # corrupt line — T-05-06-05). Regen must never fail because nothing has been submitted.
    sub_rows = submissions_log.read_rows(ws)
    slug = _read_slug(config_path)

    rendered = _render(slug, rows, sub_rows, greater_is_better, reasoning)
    _atomic_write(ws / "strategy.md", rendered)

    best = _current_best_body(rows, greater_is_better)
    print(f"regenerated strategy.md from {len(rows)} ledger row(s). "
          f"Current best: {best if best != 'None yet.' else 'None yet.'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
