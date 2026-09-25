# Simulation Agents (`agent` submission mode)

## Requirements

- Simulation competitions are in v2 scope, with ConnectX as the cheap test bed. They get an **agent track**, not a
  kernel track:
  1. ephemeral local evaluation
  2. a file-upload submit, run by the human
  3. read-back of the rating and episodes
- `kaggle-environments` runs **ephemerally** (`uv run --no-project --with kaggle-environments …`). It is never
  installed into the repo env.
- The human runs every submission. Claude prepares and validates, hands over the command, and confirms by
  read-back.
- Never commit replays or logs that contain other players' names.

## How to Build It

1. **Agent file:** one Python file, whose **last top-level function** is the agent:
   `def agent(observation, configuration) -> int`.
   - Keep it stdlib-only where possible.
   - See `sources/004-*/main.py`, a win → block → avoid-giving-a-win → centre heuristic.
2. **Local validation**, the exact check Kaggle runs: a full self-play episode must finish with every status
   `DONE`.

   ```python
   from kaggle_environments import evaluate, make
   env = make("connectx", debug=True); env.run([AGENT, AGENT])
   assert all(s.status == "DONE" for s in env.steps[-1])
   ```

3. **Local "CV"** is the win rate against a **strong pool**, playing both seats:

   ```python
   rewards = evaluate("connectx", [AGENT, opp], num_episodes=10) + \
             [list(reversed(r)) for r in evaluate("connectx", [opp, AGENT], num_episodes=10)]
   ```

   Built-in `random` and `negamax` are too weak. Add previous versions of your own agent and strong public agents.
4. **Submit** (human): `! .venv/bin/kaggle competitions submit <comp> -f main.py -m "<exp id>: <msg>"`. On success
   it prints an upload bar and `Successfully submitted to Connect X`.
5. **Read back:**

   | Step | Command |
   |---|---|
   | Rating | `competitions submissions <comp> --format json`; `publicScore` is the rating (**600.0** initial) |
   | Episodes | `competitions episodes <submission_id> --format json`; decode with `JSONDecoder().raw_decode` |
   | Replay | `competitions replay <episode_id> -p <dir>`; has `rewards`, `statuses`, `steps`, `info.Agents[].Name` |
   | Agent log | `competitions logs <episode_id> <agent_index> -p <dir>`; per step `{duration, stdout, stderr}`, which is the timeout-debugging surface |

6. **Report** the rating trend and W/L/D, counted from replays, since episode listings carry only
   `id/type/state/createTime/endTime`. Don't block on rating convergence. The ladder rating is the ground truth to
   trend, like the CV→LB gap. See `sources/004-*/epwait.py`.

## What to Avoid

- **Installing `kaggle-environments` into the project.** It pulls in **117 packages** (jax, jaxlib, transformers,
  open-spiel, litellm, pygame, …).
- **`json.loads(stdout)` on `competitions episodes --format json`.** The CLI prints the JSON array **followed by a
  prose hint line**, so a naive parser sees "no episodes". Decode only the leading JSON value.
- **Trusting wins against the built-in baselines.** Locally the agent went 20–0 vs random and 16–3–1 vs negamax,
  yet on the ladder it went L/L/D and the rating fell from 600 to 397.6, then recovered to 528.6.
- **Reading the `games` tag as "simulation".** Use the profile's rules (`simulations` tag, a
  `kaggle-environments*` dir, or a root `main.py`/`agents.md`, with no sample submission).

## Constraints

- The validation episode (`EPISODE_TYPE_VALIDATION`, self-play) completes about 2.5 min after submit.
- The rating moves for hours. Live example: 600 → 472.7 → 397.6 → 403.3 → 528.6 over about 15 min.
- The ConnectX daily limit is **2**. Read `max_daily_submissions` from the profile for other simulation comps.
- Per-step agent duration is logged; the live example's maximum was 6.5 ms. Use it to catch timeouts.

## Origin

Synthesized from spikes: 004 (+ 001 for simulation detection)
Source files available in: sources/004-connectx-agent/
