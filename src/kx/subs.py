"""control/submissions.jsonl: the leaderboard record.

One row per proposed submission. `kx submit` writes a PROPOSED row carrying a marker
(`kx:<exp_id>:<nonce>`) that is also the submit message, so `kx lb` can match Kaggle's
read-back to it. Statuses: PROPOSED -> (user confirms) SUBMITTING -> SUBMITTED |
SUBMIT_ERROR -> PENDING -> SCORED | FAILED. A PROPOSED row nobody confirmed stays out
of the leaderboard view. HANDED_OVER is the pre-0.3 equivalent of SUBMITTED.
Provenance: file sha256 (file uploads) or kernel ref + version (code competitions).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from kx.util import atomic_write, utc_now

MARKER_RE = re.compile(r"kx:(exp-\d{3,}):([0-9a-f]{6,})")


def path(ws: Path) -> Path:
    return ws / "control" / "submissions.jsonl"


def read(ws: Path) -> list[dict]:
    p = path(ws)
    if not p.exists():
        return []
    rows = []
    for ln in p.read_text().splitlines():
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def write(ws: Path, rows: list[dict]) -> None:
    atomic_write(path(ws), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def parse_status(raw) -> str | None:
    s = str(raw or "").upper()
    for key, ours in (("PENDING", "PENDING"), ("COMPLETE", "SCORED"), ("ERROR", "FAILED")):
        if key in s:
            return ours
    return None


def parse_score(raw) -> float | None:
    """Kaggle sends scores as strings; "" means not scored. Never coerce to 0.0."""
    if raw in (None, ""):
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def parse_utc(raw) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def charged_today(remote: list[dict], now: datetime | None = None) -> int:
    """Submissions that count against today's (UTC) limit: failed ones do not."""
    now = now or datetime.now(timezone.utc)
    n = 0
    for s in remote:
        d = parse_utc(s.get("date"))
        if d and d.date() == now.date() and parse_status(s.get("status")) != "FAILED":
            n += 1
    return n


def reconcile(rows: list[dict], remote: list[dict]) -> list[dict]:
    """Attach Kaggle's read-back to our rows by marker; returns rows that changed."""
    by_marker = {}
    for s in remote:
        m = MARKER_RE.search(str(s.get("description") or ""))
        if m:
            by_marker[m.group(0)] = s
    changed = []
    for r in rows:
        s = by_marker.get(r.get("marker"))
        if s is None:
            continue
        before = (r.get("status"), r.get("public_score"), r.get("private_score"))
        st = parse_status(s.get("status")) or r.get("status")
        r.update({"kaggle_ref": s.get("ref"), "status": st, "submitted_at": s.get("date"),
                  "public_score": parse_score(s.get("public_score")),
                  "private_score": parse_score(s.get("private_score")),
                  "team_name": s.get("team_name"), "read_back_at": utc_now()})
        if st == "SCORED" and not r.get("scored_at"):
            r["scored_at"] = utc_now()
        if st == "FAILED":
            r["error"] = "Kaggle rejected the submission (message not recorded)"
        if before != (r.get("status"), r.get("public_score"), r.get("private_score")):
            changed.append(r)
    return changed


def outcome(replay: dict, team_name: str | None) -> tuple[str, list[int]] | None:
    """(W/L/D, our seat indexes) of one episode from its replay, or None if unknown."""
    names = (replay.get("info") or {}).get("TeamNames") or []
    rewards = replay.get("rewards") or []
    ours = [i for i, n in enumerate(names) if team_name and n == team_name]
    if not ours or len(rewards) != len(names) or any(r is None for r in rewards):
        return None
    if len(ours) == len(names):
        return "self", ours
    mine = max(rewards[i] for i in ours)
    theirs = max(r for i, r in enumerate(rewards) if i not in ours)
    return ("W" if mine > theirs else "L" if mine < theirs else "D"), ours
