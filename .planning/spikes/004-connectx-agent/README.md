---
spike: 004
name: connectx-agent
type: standard
validates: "Given a ConnectX agent validated locally with kaggle-environments, when main.py is submitted via the CLI, then the validation episode, ladder episodes, replays, agent logs and a rating are all readable via the CLI"
verdict: VALIDATED
related: [001, 003]
tags: [simulation, connectx, kaggle-environments, episodes, rating]
---

# Spike 004: ConnectX simulation agent

## What This Validates

Given a ConnectX agent validated locally with `kaggle-environments`, when `main.py` is submitted
via the CLI, then the whole simulation loop is observable from the CLI: validation episode,
ladder episodes, replays, agent logs, and the submission's skill rating.

## Research

- Submission = one Python file whose last top-level function is the agent
  `agent(observation, configuration)` → column index. Uploaded with
  `kaggle competitions submit connectx -f main.py -m ...` (a FILE upload, not a kernel).
- Read-back surface (CLI 2.2.3): `competitions submissions` (rating in `publicScore`),
  `competitions episodes <submission_id>`, `competitions replay <episode_id>`,
  `competitions logs <episode_id> <agent_index>`.
- Local harness: `kaggle_environments.make("connectx")`, `env.run([...])`, `evaluate(...)` with
  built-in `random` / `negamax` opponents.

## How to Run

```bash
cd .planning/spikes/004-connectx-agent
uv run --no-project --with kaggle-environments python evaluate.py      # local validation + baselines
# human action (spends a submission): ! .venv/bin/kaggle competitions submit connectx -f main.py -m "..."
../../../.venv/bin/python epwait.py <submission_id> --budget 900       # episodes + rating read-back
../../../.venv/bin/kaggle competitions replay <episode_id> -p out
../../../.venv/bin/kaggle competitions logs <episode_id> 0 -p out
```

## Investigation Trail

1. **Local validation** (isolated `uv run --with kaggle-environments`): self-play finished
   `['DONE','DONE']`; vs `random` 20–0; vs `negamax` 16 W / 3 L / 1 D (`local_eval.json`).
   Surprise: `kaggle-environments` now installs **117 packages** (jax, jaxlib, transformers,
   open-spiel, litellm, pygame, …) — only install it ephemerally, and only for simulation comps.
2. **Submit** (run by the user with `!` — auto-mode denies submissions): upload bar +
   `Successfully submitted to Connect X`; read-back `ref 56536074`, `fileName main.py`, PENDING.
3. **Validation episode** (`EPISODE_TYPE_VALIDATION`, self-play) COMPLETED ~2.5 min after submit;
   replay JSON has `rewards`, `statuses`, `steps`, `info.Agents[].Name`; agent log JSON has
   per-step `{duration, stdout, stderr}` (max 6.5 ms here) — the debugging surface for timeouts.
4. **Rating:** submission → `COMPLETE` with `publicScore 600.0` (initial μ), then ladder games moved
   it 600 → 472.7 → 397.6 → 403.3 within ~12 min.
5. **Parser trap:** `competitions episodes --format json` prints the JSON array **followed by a
   plain-text hint line** (`Use "kaggle competitions replay <episode_id>" …`) → `json.loads(stdout)`
   fails and a naive reader sees "no episodes". Fixed with `JSONDecoder().raw_decode` on the
   leading array (`epwait.py`).
6. **Ladder results** (from replays; opponents' names not committed): episodes 113082879 L,
   113084072 L, 113085245 D (43 steps) — consistent with the rating path. Episode listings carry
   only `id/type/state/createTime/endTime`; outcomes/opponents need the replay.

## Results

**Verdict: VALIDATED.** The full simulation loop — local validate → submit file → validation
episode → ladder episodes → replay/log download → rating — is reachable from the CLI.

**Signal for the build (`agent` submission mode):**

- `kx` needs an **agent track**, not a kernel track: local evaluation harness (ephemeral
  `uv run --with kaggle-environments`), file-upload submit (human-run), rating + episode read-back.
- **Local baselines are a weak proxy**: 16–3 vs negamax locally, yet L/L/D and a falling rating on
  the ladder. The simulation "CV" = win-rate vs a *stronger local pool* (previous own versions +
  strong public agents), and the ladder rating is the ground truth to trend (like the CV→LB gap).
- Parse CLI JSON defensively (leading-value decode) — some commands append prose after the JSON.
- Ratings move for hours; `kx lb` should report rating + episode W/L/D from replays, not block on
  convergence. ConnectX daily limit is 2 (spike 001).
