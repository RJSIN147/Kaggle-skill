---
phase: 9
status: passed
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
| 5. Writeup checklist (unchanged) | kaggle-measuring-agi: `kx submit --writeup` fetched the pages and drafted `writeup/CHECKLIST.md`; the AI filled 7 criteria from the Evaluation page (50/30/20 weighting, template headings). User submits by hand. |

## Read-back results (2026-10-02, the user ran the four handed-over commands)

Workspaces recreated in `~/kaggle-live/` after a reboot wiped `/tmp`. `kx lb` matched every
submission by its `kx:exp-…:…` marker:

| Competition | Mode | CV | Public | Private | Provenance |
|---|---|---|---|---|---|
| titanic | csv_upload | 0.82153 | 0.75358 | — | file sha256 a3791c61… |
| equity-post-HCT | code_kernel | 0.63820 (host metric) | 0.64548 | 0.65145 | kernel …-1d58-exp-002 v1 |
| um-mcts | code_kernel, API-served | 0.468065 (RMSE) | 0.46271 | 0.46998 | kernel …-6303-exp-002 v1 (PENDING → SCORED in ~10 min) |
| connectx | agent | win rate 0.85 | rating 600 → 233.8 | — | 6 episodes from replays: 1 self-play validation, W0 L5 D0 |

Live fix: agent ratings are kept out of the CV→LB gap (not on the win-rate scale).
ConnectX confirms the spike lesson: beating random/negamax locally does not predict the ladder.

## Confirm-then-submit (2026-10-02, user request: no more copy-pasted commands)

`kx submit exp-NNN` now proposes (confirmation lines + one-time token); only
`kx submit exp-NNN --confirm <token>` after the user's explicit yes submits, through the SDK.
Live on Titanic: proposal shown to the user via AskUserQuestion (file, sha256, CV, best
submitted, 9/10 slots, message) → user chose "Yes, submit" → `--confirm bf454eee --force-cv`
→ Kaggle ref 56759642 → `kx lb` matched the marker, SCORED 0.75358 (same file as ref
56758423, same score). A second, unconfirmed proposal from the same session stayed PROPOSED
and out of the LB view. Unit-tested refusals: wrong/used token, changed file, proposal > 1 h,
checks re-run at confirm (slots), marker already on Kaggle (no double submit), submit error →
SUBMIT_ERROR + `kx lb` first.

Extra read-backs: nlp-getting-started exp-001 CV F1 0.7086 → public 0.78148 (handed over before
this change; user ran it).
