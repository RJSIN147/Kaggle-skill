#!/usr/bin/env python3
"""rebuild_ledger.py — reconstruct control/ledger.jsonl from the meta.json folders.

``ledger.jsonl`` is a DERIVED index; ``experiments/*/meta.json`` are canonical
(MEM-01 / D-10). This entry point makes the ledger a PURE FUNCTION of those folders:
it globs ``experiments/exp-*/meta.json``, sorts by ``exp_id``, derives each row via
``experiment_meta.to_ledger_row``, and writes ``control/ledger.jsonl`` ATOMICALLY
(tempfile + ``os.replace``). Because it is a full rebuild (not an incremental append),
a hand-corrupted or partial ledger self-heals on a re-run.

Trust posture (fail-clear, T-03-02-02): a meta.json that will not parse
(``JSONDecodeError``) or that ``experiment_meta.validate_meta`` rejects is SKIPPED
with a ``stderr`` warning naming the folder — NEVER fabricated into a plausible row.
The other rows still land. The live ``ledger.jsonl`` is never partial-written: the
rebuild renders to a sibling ``.tmp`` and ``os.replace``s it onto the target, so a
crash mid-write leaves the previous ledger intact.

Portability (CLAUDE.md §Stack Patterns): self-locating via ``Path(__file__)``, takes
an explicit ``--workspace`` path, stdlib-only (imports ``experiment_meta`` — no ML
stack, the D-06 split).
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

from experiment_meta import to_ledger_row, validate_meta  # noqa: E402


def _iter_meta_paths(ws: Path) -> list[Path]:
    """All ``experiments/exp-*/meta.json`` paths, sorted by folder (== exp_id) name."""
    exp_root = ws / "experiments"
    if not exp_root.is_dir():
        return []
    return sorted(exp_root.glob("exp-*/meta.json"), key=lambda p: p.parent.name)


def _rows_from_folders(ws: Path) -> list[dict]:
    """Derive ledger rows from the meta folders, skip-and-warning on bad metas.

    A meta that fails to parse or fails ``validate_meta`` is dropped with a stderr
    warning naming its folder (T-03-02-02) — never fabricated into a row.
    """
    rows: list[dict] = []
    for meta_path in _iter_meta_paths(ws):
        folder = meta_path.parent.name
        try:
            meta = json.loads(meta_path.read_text())
        except json.JSONDecodeError as exc:
            print(
                f"rebuild: skipping {folder} — meta.json is not valid JSON "
                f"(left untouched, no row fabricated): {exc}.",
                file=sys.stderr,
            )
            continue
        errors = validate_meta(meta)
        if errors:
            print(
                f"rebuild: skipping {folder} — meta.json failed validation "
                f"(no row fabricated): {'; '.join(errors)}.",
                file=sys.stderr,
            )
            continue
        rows.append(to_ledger_row(meta))
    return rows


def _atomic_write(path: Path, text: str) -> None:
    """Crash-safe overwrite: render to a sibling ``.tmp`` then ``os.replace``.

    The live target is never partial-written; on a crash the previous file survives.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def rebuild_ledger_file(ws: Path) -> list[dict]:
    """Rewrite ``control/ledger.jsonl`` as a PURE FUNCTION of the meta folders (atomic).

    Derives one row per valid ``experiments/exp-*/meta.json`` (sorted by exp_id,
    skip-and-warn on corrupt/invalid), renders each as one compact JSON line, and
    ``os.replace``s the whole file atomically. Returns the derived rows.

    This is the ONE derivation used by BOTH entry points: ``main()`` (the on-demand
    repair tool) and ``record_experiment.py`` (the incremental recorder delegates
    here after writing each meta.json). Sharing this path is what makes the
    incrementally-built ledger BYTE-IDENTICAL to a full rebuild of the same folders
    (MEM-01) — SUCCESS and FAILED alike — instead of the two diverging.
    """
    rows = _rows_from_folders(ws)

    # Each row is one compact JSON line (matches the RESEARCH §Ledger derived-row
    # shape). A non-empty ledger is newline-terminated; an empty one is byte-empty.
    lines = [json.dumps(row, separators=(",", ":")) for row in rows]
    text = ("\n".join(lines) + "\n") if lines else ""

    _atomic_write(ws / "control" / "ledger.jsonl", text)
    return rows


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="rebuild_ledger.py",
        description="Rebuild control/ledger.jsonl as a pure function of the "
                    "experiments/*/meta.json folders (MEM-01). Corrupt metas are "
                    "skipped with a warning; the live ledger is replaced atomically.",
    )
    ap.add_argument("--workspace", type=Path, default=Path.cwd(),
                    help="Target workspace directory (default: cwd).")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ws = args.workspace.resolve()
    rebuild_ledger_file(ws)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
