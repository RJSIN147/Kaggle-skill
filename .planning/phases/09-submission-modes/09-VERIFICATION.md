---
phase: 9
status: awaiting_user_submits
verified: 2026-09-26
method: live runs (/tmp/kx-live/{titanic,equity,mcts,connectx,writeup}) + offline suite
---

# Phase 9 verification — submission modes

kx has no code path that submits (static test). Everything up to the hand-over ran live;
the read-back half needs the user to run the four handed-over commands.

| Criterion | Evidence so far |
|---|---|
| 1. Candidate checks + exact command, never submits | `kx submit` checks recorded SUCCESS, not subsample, late status, daily slots (Kaggle read-back, UTC), CV vs best submitted (`--force-cv`), expected file vs sample columns/rows; returns `needs_user` with the command. Unit-tested refusals. |
| 2. csv_upload on Titanic + read-back + `kx lb` | Command handed over for exp-001 (CV 0.8215). **Pending:** user runs it; then `kx lb` (reconcile by `kx:exp-001:<nonce>` marker, file sha256). |
| 3. code_kernel (file output + API-served) | equity: training kernel with host metric (C-index 0.6382) → `inference` kernel wrote `submission.csv` → command `-k … -v 1 -f submission.csv` (verified COMPLETE, latest version, internet off). um-mcts: training (RMSE 0.468, ruleset-grouped CV) → `inference` kernel started the `kaggle_evaluation` server, ran the local gateway with explicit paths, wrote `submission.parquet` (two live bugs fixed on the way: polars/pyarrow string dtypes and all-null object columns are now aligned to training dtypes). **Pending:** user runs both commands; `kx lb` polls (~20 min API-served). |
| 4. ConnectX agent | `agent` template; `kx run` in a throwaway `uv run --no-project --with kaggle-environments` env: self-play validation DONE, win rate 0.875 ± 0.125 (random 1.0, negamax 0.75, both seats). Command handed over. **Pending:** user upload; `kx lb` then reads rating + episodes and counts W/L/D from replays (unit-tested). |
| 5. Writeup checklist | kaggle-measuring-agi: `kx submit --writeup` fetched the pages and drafted `writeup/CHECKLIST.md`; the AI filled 7 criteria from the Evaluation page (50/30/20 weighting, template headings). User submits by hand. |
