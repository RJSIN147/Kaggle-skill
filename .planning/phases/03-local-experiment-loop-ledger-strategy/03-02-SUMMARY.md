---
phase: 03-local-experiment-loop-ledger-strategy
plan: 02
subsystem: ledger
tags: [ledger, provenance, schema, rebuild, templates]
requires:
  - scripts/competition_doc.py (pure-helper convention)
  - scripts/init_workspace.py (self-location + argparse --workspace conventions)
provides:
  - experiment_meta.to_ledger_row  # single-source meta.json -> ledger.jsonl row
  - experiment_meta.validate_meta   # fail-closed meta validation
  - rebuild_ledger.py               # atomic full rebuild from meta folders
  - scripts/templates/meta.json.tmpl
  - scripts/templates/VERDICT.md.tmpl
affects:
  - control/ledger.jsonl  # derived index, rebuilt as a pure function of the folders
tech-stack:
  added: []
  patterns:
    - pure stdlib schema module (no import-time I/O, no main)
    - atomic tempfile + os.replace overwrite
    - skip-and-warn on corrupt/invalid input (never fabricate)
key-files:
  created:
    - scripts/experiment_meta.py
    - scripts/rebuild_ledger.py
    - scripts/templates/meta.json.tmpl
    - scripts/templates/VERDICT.md.tmpl
    - tests/test_experiment_meta.py
    - tests/test_rebuild_ledger.py
  modified: []
decisions:
  - meta.json is canonical; ledger.jsonl is derived and fully rebuildable (MEM-01)
  - ledger row schema lives in ONE module (experiment_meta) imported by recorder + rebuilder
  - meta.json.tmpl uses ${TOKEN} tokens that are valid JSON both raw and post-substitution
metrics:
  duration: ~15m
  completed: 2026-07-11
  tasks: 3
  files: 6
---

# Phase 3 Plan 02: Ledger Contract & Provenance Backbone Summary

Established the git-backed ledger contract: a pure-stdlib `experiment_meta` module that owns the `meta.json` ⇄ `ledger.jsonl` row schema in one place, a `rebuild_ledger.py` that reconstructs `ledger.jsonl` as a pure function of the per-experiment folders (atomic, skip-and-warn on corrupt metas), and the canonical `meta.json` / `VERDICT.md` templates.

## What Was Built

- **`scripts/experiment_meta.py`** — pure stdlib helper (no `main()`, no import-time I/O; mirrors `competition_doc.py`). `to_ledger_row(meta)` derives the exact 11-key one-line subset, sourcing `git_commit` + `seed` from `meta["provenance"]` (never top-level, so a decoy top-level value cannot poison provenance — T-03-02-01). Key order is fixed (`LEDGER_ROW_KEYS`) so a rebuild is byte-stable. `validate_meta(meta)` returns human-readable error strings (`[]` == valid): required top-level keys, `status ∈ {SUCCESS,FAILED}`, and the four provenance keys. A FAILED meta with a null `cv_mean` still validates and still yields a row.
- **`scripts/rebuild_ledger.py`** — globs `experiments/exp-*/meta.json`, sorts by `exp_id`, validates + derives each row, and writes `control/ledger.jsonl` atomically (tempfile + `os.replace`). A meta that fails to parse or fails `validate_meta` is SKIPPED with a stderr warning naming the folder — never fabricated (T-03-02-02). Empty `experiments/` → a 0-row ledger. Full rebuild makes the ledger a pure function of the folders (MEM-01), so a hand-corrupted ledger self-heals.
- **`scripts/templates/meta.json.tmpl`** — full canonical shape including a nested `provenance` object (run_id / artifact_hash / git_commit / git_dirty / seed). Uses `${TOKEN}` placeholders that keep the file valid JSON BOTH raw (recorder `json.loads` path) and after `string.Template.safe_substitute` (the `_render_text` contract); derived-post-run numeric fields default to `null`/`[]`.
- **`scripts/templates/VERDICT.md.tmpl`** — worked/didn't/why prose skeleton (Idea / Hypothesis / Result / Verdict) that explicitly states numbers are tooling-written and the AI references them, never hand-types (D-05).

## How to Verify

- `uv run pytest tests/test_experiment_meta.py tests/test_rebuild_ledger.py -x -q` → 18 passed.
- `grep -rn "import sklearn\|import pandas\|import numpy" scripts/experiment_meta.py scripts/rebuild_ledger.py` → nothing (D-06 stdlib split).
- Delete `control/ledger.jsonl` then re-run `rebuild_ledger.py` → byte-identical file.
- Full non-live suite: `uv run pytest -q -k "not live"` → 108 passed, 8 deselected (no regressions).

## TDD Gate Compliance

Both behavior-adding tasks followed RED → GREEN:
- `test(03-02)` experiment_meta RED (`b173b5f`) → `feat(03-02)` GREEN (`78dd532`).
- `test(03-02)` rebuild_ledger RED (`02c7780`) → `feat(03-02)` GREEN (`8f5e536`).
No REFACTOR commits were needed (implementations were clean on first green).

## Deviations from Plan

None — plan executed exactly as written. The plan's Task 3 action mentioned `__EXP_ID__`-style placeholders "rendered via string.Template.safe_substitute", but `string.Template` substitutes `$`-prefixed tokens, not `__…__`. The authoritative Task 3 automated verify uses `string.Template(...).safe_substitute({'EXP_ID':...})`, so `${EXP_ID}` tokens were used to satisfy the verify. This is the correct reading of the acceptance criteria, not a scope change.

## Threat Model Coverage

- **T-03-02-01 (Tampering, provenance):** `to_ledger_row` copies `git_commit`/`seed` straight from `meta.provenance`; `validate_meta` requires all four provenance keys before a row is emitted. Test `test_to_ledger_row_sources_git_commit_and_seed_from_provenance` pins the decoy-rejection.
- **T-03-02-02 (Repudiation, corrupt meta):** rebuild skips-and-warns (stderr names the folder), never fabricates; atomic `os.replace` means no partial live-file write. Pinned by the corrupt/invalid-meta and no-`.tmp`-residue tests.
- **T-03-02-03 (Tampering, corrupt ledger):** ledger is a pure function of the folders — a full rebuild self-heals it. Pinned by `test_delete_then_rebuild_is_byte_identical`.
- **T-03-02-04 (Info disclosure, git staging):** deferred to 03-04 (recorder) per the register — no staging happens in this plan.

## Known Stubs

None. The two templates default derived numeric fields to `null`/`[]` by design — these are tooling-written by the recorder (03-04), not stubs; the meta template's identity/provenance fields are `${TOKEN}` placeholders the scaffolder/recorder fill.

## Self-Check: PASSED

All 7 created files exist on disk; all 6 commits (`b173b5f`, `78dd532`, `02c7780`, `8f5e536`, `4b1695f`, `751d755`) are present in git history.
