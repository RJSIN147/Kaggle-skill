"""Ledger: the meta.json <-> ledger.jsonl schema and the pure-function rebuild.

``experiments/exp-*/meta.json`` is canonical; ``control/ledger.jsonl`` is a derived
index rebuilt in full (atomically) from those folders after every record, so it is
byte-stable and self-heals. A meta that fails to parse or validate is skipped with
a warning, never fabricated into a row. ``git_commit``/``seed`` are read from
``meta["provenance"]`` only, so a decoy top-level value cannot poison provenance.
"""

from __future__ import annotations

import json
from pathlib import Path

from kx.util import atomic_write

STATUSES = ("SUCCESS", "FAILED")
REQUIRED_TOP_KEYS = ("exp_id", "status")
REQUIRED_PROVENANCE_KEYS = ("run_id", "artifact_hash", "git_commit", "seed")

# The exact, ordered key set of a derived ledger row (byte-stable rebuild).
LEDGER_ROW_KEYS = (
    "exp_id", "status", "idea", "metric", "greater_is_better", "cv_mean", "cv_std",
    "git_commit", "seed", "created", "verdict_path",
)


def to_ledger_row(meta: dict) -> dict:
    """The 11-key derived row, in fixed order. A pure projection (no validation)."""
    provenance = meta.get("provenance") or {}
    return {
        "exp_id": meta.get("exp_id"),
        "status": meta.get("status"),
        "idea": meta.get("idea"),
        "metric": meta.get("metric"),
        "greater_is_better": meta.get("greater_is_better"),
        "cv_mean": meta.get("cv_mean"),
        "cv_std": meta.get("cv_std"),
        "git_commit": provenance.get("git_commit"),
        "seed": provenance.get("seed"),
        "created": meta.get("created"),
        "verdict_path": meta.get("verdict_path"),
    }


def validate_meta(meta) -> list[str]:
    """Human-readable errors; ``[]`` means well-formed. A FAILED meta with a null
    ``cv_mean`` is valid: status + provenance are what make a row auditable."""
    if not isinstance(meta, dict):
        return [f"meta must be a JSON object, got {type(meta).__name__}"]
    errors: list[str] = []
    for key in REQUIRED_TOP_KEYS:
        if key not in meta or meta[key] in (None, ""):
            errors.append(f"missing required key: {key}")
    status = meta.get("status")
    if status is not None and status not in STATUSES:
        errors.append(f"status must be one of {STATUSES}, got {status!r}")
    provenance = meta.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("missing required key: provenance (must be an object)")
    else:
        for key in REQUIRED_PROVENANCE_KEYS:
            if key not in provenance or provenance[key] in (None, ""):
                errors.append(f"missing required provenance key: provenance.{key}")
    return errors


def _iter_meta_paths(ws: Path) -> list[Path]:
    exp_root = ws / "experiments"
    if not exp_root.is_dir():
        return []
    return sorted(exp_root.glob("exp-*/meta.json"), key=lambda p: p.parent.name)


def rebuild_ledger_file(ws: Path) -> tuple[list[dict], list[str]]:
    """Rewrite ``control/ledger.jsonl`` from the meta folders. Returns (rows, warnings)."""
    rows: list[dict] = []
    warnings: list[str] = []
    for meta_path in _iter_meta_paths(ws):
        folder = meta_path.parent.name
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            warnings.append(f"ledger: skipped {folder} (meta.json is not valid JSON)")
            continue
        errors = validate_meta(meta)
        if errors:
            warnings.append(f"ledger: skipped {folder} ({'; '.join(errors)})")
            continue
        rows.append(to_ledger_row(meta))
    lines = [json.dumps(row, separators=(",", ":")) for row in rows]
    atomic_write(ws / "control" / "ledger.jsonl", ("\n".join(lines) + "\n") if lines else "")
    return rows, warnings


def read_ledger(ws: Path) -> list[dict]:
    """Parse ``control/ledger.jsonl`` (missing -> []); malformed lines are skipped."""
    path = ws / "control" / "ledger.jsonl"
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
