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


def best_row(rows: list[dict], greater_is_better: bool) -> dict | None:
    winners = [r for r in rows if r.get("status") == "SUCCESS" and _is_number(r.get("cv_mean"))]
    if not winners:
        return None
    return (max if greater_is_better else min)(winners, key=lambda r: r["cv_mean"])


def current_best_body(rows: list[dict], greater_is_better: bool) -> str:
    best = best_row(rows, greater_is_better)
    if best is None:
        return "None yet."
    v = best.get("verdict_path") or ""
    return (f"**{best.get('exp_id')}** — {fmt_score(best.get('cv_mean'), best.get('cv_std'))} "
            f"({best.get('metric') or '?'}) — idea: \"{best.get('idea') or '(none)'}\" — "
            + (f"[verdict]({v})" if v else "(no verdict)"))


def tried_lines(rows: list[dict]) -> list[str]:
    """The never-repeat digest: one line per experiment, FAILED included."""
    out = []
    for r in rows:
        v = r.get("verdict_path") or ""
        out.append(f"- {r.get('exp_id')} | {r.get('idea') or '(no idea recorded)'} | "
                   f"{r.get('status')} | {fmt_score(r.get('cv_mean'), r.get('cv_std'))} | "
                   + (f"[verdict]({v})" if v else "(no verdict)"))
    return out


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
    pending = sum(1 for r in sub_rows if r.get("status") == "PENDING")
    if pending:
        blocks.append(f"_{pending} submission(s) PENDING — run `kx lb` to read them back._")
    blocks.append(lb_gap.alarm_body(lb_gap.to_pairs(joined), greater_is_better))
    return "\n\n".join(blocks)


def research_body(ideas: list[dict]) -> str:
    open_ideas = [i for i in ideas if i.get("status", "open") == "open"]
    if not open_ideas:
        return "_No research ideas queued (run `kx research`)._"
    return "\n".join(f"- [{i.get('source_type', 'research')}: {i.get('source', '?')}] "
                     f"{i.get('idea')}" for i in open_ideas)


def render(title: str, rows: list[dict], sub_rows: list[dict], ideas: list[dict],
           greater_is_better: bool, reasoning: str) -> str:
    digest = "\n".join(tried_lines(rows)) or "_No experiments recorded yet._"
    return (
        f"# Strategy — {title}\n\n> {HEADER_NOTE}\n\n"
        f"## Current best\n\n{current_best_body(rows, greater_is_better)}\n\n"
        f"## Tried-list digest\n\n{digest}\n\n"
        f"## CV-to-LB gap\n\n{lb_gap_body(sub_rows, rows, greater_is_better)}\n\n"
        f"## Research-sourced ideas\n\n{research_body(ideas)}\n\n"
        f"## Reasoning (hypothesis queue & next action)\n\n{reasoning.strip()}\n"
    )


def write(ws: Path, title: str, rows, sub_rows, ideas, greater_is_better: bool,
          reasoning: str) -> None:
    atomic_write(ws / "strategy.md", render(title, rows, sub_rows, ideas, greater_is_better,
                                            reasoning))
