"""strategy.md: regenerated each cycle from the ledger (facts) + the AI's reasoning.

Every number is rendered from control/ledger.jsonl or control/submissions.jsonl,
never typed by the AI; the reasoning file (hypothesis queue + next action) is
spliced in verbatim. The whole file is replaced atomically.
"""

from __future__ import annotations

import json
from pathlib import Path

from kx import lb_gap
from kx.util import atomic_write

HEADER_NOTE = "Generated each cycle from control/ledger.jsonl — manual edits are overwritten."


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def fmt_score(mean, std) -> str:
    if not _is_number(mean):
        return "—"
    return f"{mean:g}±{(std if _is_number(std) else 0.0):g}"


def comparable_rows(rows: list[dict]) -> list[dict]:
    """Model runs whose CV can be ranked: full-data SUCCESS, not a diagnostic."""
    return [r for r in rows if r.get("status") == "SUCCESS" and _is_number(r.get("cv_mean"))
            and not r.get("subsample")  # a subsample CV is not comparable
            and r.get("kind", "experiment") != "diagnostic"]


def best_row(rows: list[dict], greater_is_better: bool,
             reference_hash: str | None = None) -> dict | None:
    """The best comparable run; with a reference CV scheme, the best within it."""
    winners = comparable_rows(rows)
    if reference_hash:
        winners = [r for r in winners if r.get("fold_hash") == reference_hash] or winners
    if not winners:
        return None
    return (max if greater_is_better else min)(winners, key=lambda r: r["cv_mean"])


def current_best_body(rows: list[dict], greater_is_better: bool,
                      reference_hash: str | None = None, metric_label: str | None = None) -> str:
    best = best_row(rows, greater_is_better, reference_hash)
    if best is None:
        return "None yet."
    v = best.get("verdict_path") or ""
    return (f"**{best.get('exp_id')}** — {fmt_score(best.get('cv_mean'), best.get('cv_std'))} "
            f"({metric_label or best.get('metric') or '?'}) — idea: "
            f"\"{best.get('idea') or '(none)'}\" — "
            + (f"[verdict]({v})" if v else "(no verdict)"))


def tried_lines(rows: list[dict], reference_hash: str | None = None) -> list[str]:
    """The never-repeat digest: one line per experiment, FAILED included."""
    out = []
    for r in rows:
        v = r.get("verdict_path") or ""
        sub = f" (subsample {r['subsample']:g})" if isinstance(r.get("subsample"), (int, float)) \
            else ""
        kind = r.get("kind") or "experiment"
        tag = f" [{kind}]" if kind != "experiment" else ""
        origin = f" (from {r['parent']})" if r.get("parent") else ""
        vs = f" | vs parent: {r['vs_parent']}" if r.get("vs_parent") else ""
        if reference_hash and r.get("fold_hash") and r["fold_hash"] != reference_hash:
            vs += " | other CV scheme"
        out.append(f"- {r.get('exp_id')}{tag}{origin} | {r.get('idea') or '(no idea recorded)'} | "
                   f"{r.get('status')} | {fmt_score(r.get('cv_mean'), r.get('cv_std'))}{sub}{vs} | "
                   + (f"[verdict]({v})" if v else "(no verdict)"))
    return out


def calibration_line(rows: list[dict]) -> str | None:
    """How the pre-registered directions fared against the paired comparisons."""
    out = [r.get("prediction") for r in rows]
    judged = [o for o in out if o in ("matched", "missed")]
    unresolved = out.count("unresolved")
    if not judged and not unresolved:
        return None
    unjudged = sum(1 for r in rows if r.get("parent") and r.get("prediction") is None)
    return (f"Pre-registered predictions: {judged.count('matched')} of {len(judged)} matched"
            + (f", {unresolved} unresolved (an effect too small for the folds to confirm)"
               if unresolved else "")
            + (f"; {unjudged} more with a parent could not be compared" if unjudged else "")
            + ".")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def lb_gap_body(sub_rows: list[dict], rows: list[dict], greater_is_better: bool) -> str:
    joined = lb_gap.join_cv_lb(sub_rows, rows)
    blocks = []
    if not joined:
        blocks.append("None yet.")
    else:
        lines = ["| exp | cv_mean | lb_score | gap (lb − cv) |", "| --- | --- | --- | --- |"]
        for r in joined:
            lines.append(f"| {r['exp_id']} | {r['cv_mean']:g} | {r['lb_score']:g} | {r['gap']:+g} |")
        blocks.append("\n".join(lines))
    pending = sum(1 for r in sub_rows if r.get("status") in
                  ("HANDED_OVER", "SUBMITTING", "SUBMITTED", "PENDING"))
    if pending:
        blocks.append(f"_{pending} submission(s) awaiting read-back — run `kx lb`._")
    blocks.append(lb_gap.alarm_body(lb_gap.to_pairs(joined), greater_is_better))
    return "\n\n".join(blocks)


def research_body(ideas: list[dict]) -> str:
    open_ideas = [i for i in ideas if i.get("status", "open") == "open"]
    if not open_ideas:
        return "_No research ideas queued (run `kx research`)._"
    return "\n".join(f"- [{i.get('source_type', 'research')}: {i.get('source', '?')}] "
                     f"{i.get('idea')}" for i in open_ideas)


def render(title: str, rows: list[dict], sub_rows: list[dict], ideas: list[dict],
           greater_is_better: bool, reasoning: str, validation_body: str | None = None,
           reference_hash: str | None = None, metric_label: str | None = None) -> str:
    digest = "\n".join(tried_lines(rows, reference_hash)) or "_No experiments recorded yet._"
    best = current_best_body(rows, greater_is_better, reference_hash, metric_label)
    calib = calibration_line(rows)
    if calib:
        best += f"\n\n{calib}"
    valid = f"## Validation\n\n{validation_body}\n\n" if validation_body else ""
    return (
        f"# Strategy — {title}\n\n> {HEADER_NOTE}\n\n"
        f"## Current best\n\n{best}\n\n{valid}"
        f"## Tried-list digest\n\n{digest}\n\n"
        f"## CV-to-LB gap\n\n{lb_gap_body(sub_rows, rows, greater_is_better)}\n\n"
        f"## Research-sourced ideas\n\n{research_body(ideas)}\n\n"
        f"## Reasoning (hypothesis queue & next action)\n\n{reasoning.strip()}\n"
    )


def write(ws: Path, title: str, rows, sub_rows, ideas, greater_is_better: bool,
          reasoning: str, validation_body: str | None = None,
          reference_hash: str | None = None, metric_label: str | None = None) -> None:
    atomic_write(ws / "strategy.md", render(title, rows, sub_rows, ideas, greater_is_better,
                                            reasoning, validation_body, reference_hash,
                                            metric_label))
