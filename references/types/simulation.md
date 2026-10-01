# Simulation competitions (`agent`)

Template: `agent` — one file (`main.py`) whose **last top-level function** is
`agent(observation, configuration)`. The default is a ConnectX heuristic.

- `kx run exp-NNN` runs locally in a **throwaway** environment
  (`uv run --no-project --with kaggle-environments`, ~117 packages, never installed into
  the skill): one self-play episode must end with every status `DONE` (Kaggle's own
  validation), then the win rate (W=1, D=0.5, L=0, both seats, 10 episodes each) against
  `random`, `negamax` and **every earlier agent in this workspace** is the "CV".
  Override the environment name with `experiment.json` → `local.env` when it differs from
  the competition slug.
- Built-in baselines are weak: a 20–0 local record once meant a falling ladder rating.
  Treat the ladder rating as ground truth and keep earlier agents in the pool.
- `kx submit exp-NNN` proposes uploading `main.py`; after the user confirms,
  `--confirm <token>` submits it (ConnectX allows 2/day). `kx lb` reads back the rating (starts at 600, moves for
  hours), counts W/L/D from episode replays (replays go to `cache/`, never committed: they
  name other players), and trends the rating. Don't block on convergence: re-run later.
