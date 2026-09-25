---
phase: 6
status: passed
verified: 2026-09-25
method: live run on Titanic (workspace /tmp/kx-live/titanic) + offline suite (133 passed)
---

# Phase 6 verification — kx core & live kernel loop

Built directly (outside GSD execution) from 06-RESEARCH.md / 06-PATTERNS.md.

| Criterion | Evidence (live unless noted) |
|---|---|
| 1. `uv sync` + `kx init` in one step, masked, no prompts | `uv sync --project <skill>` then `uv run --project <skill> kx status` from empty `/tmp/kx-empty` → envelope, folder untouched. `kx init titanic` → `ok`, "credential validated for ravijotsinha", masked `KGAT_…ebac`, scaffold commit made. No-credential path → `needs_user`, no prompt (test_cli_contract). |
| 2. One JSON envelope + `next_action`; `experiment.json` validated before push | Every live command returned one envelope; the loop init → sync → confirm → metric → new → run → strategy was driven by `next_action` alone. `kx run exp-002` with `<TODO>` still in `cv.reasoning` → `invalid`, "nothing was pushed". |
| 3. `kx sync titanic` → structured-only profile | canonical ref `titanic`, metric "Categorization Accuracy" (suggestion `accuracy`), 10/day, code-only False, 3 csv files / 93,081 B, root listing; no `description`/URL in profile.json. |
| 4. Live core-value cycle | exp-001: private CPU script kernel `ravijotsinha/kx-titanic-67fc-exp-001` v1, internet false + private read back, COMPLETE in < 90 s; recorded SUCCESS accuracy 0.8215 ± 0.0201 (5 folds); `oof.csv`/`test_preds.csv` in kx-preds/1 validated; image digest `gcr.io/kaggle-images/python@sha256:dafd4ce5…`; manifest: py 3.12.13, numpy 2.0.2, pandas 2.3.3, sklearn 1.6.1, lightgbm 4.6.0. Verdict gate refused `kx strategy` until VERDICT.md was written; strategy committed (c2a5335). |
| 5. Fail-closed + digest + v1 removals | exp-002 (raises) → ERROR → FAILED(kernel_error), cv null, traceback kept. exp-003 (NaN score, kernel COMPLETE) → FAILED(non_finite). Digest lists all 3 ideas (strategy commit 31e2c85). v1 `scripts/` and superseded tests deleted; egress allowlist is an opt-in doc marked UNVERIFIED; `test_core07_removals.py` greps the superseded tokens. |

Fix found live: the traceback extractor included nbconvert lines after the exception;
now it stops at the exception line (regression test uses the real log fixture).
