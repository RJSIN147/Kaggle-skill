"""Spike 004 local evaluation: validate main.py with kaggle-environments before any submission.

Run: uv run --with kaggle-environments python evaluate.py  (isolated, nothing installed globally)
"""
import json
from pathlib import Path

from kaggle_environments import evaluate, make

HERE = Path(__file__).parent
AGENT = str(HERE / "main.py")

# 1) The exact validation Kaggle performs: a full self-play episode must finish without errors.
env = make("connectx", debug=True)
env.run([AGENT, AGENT])
statuses = [s.status for s in env.steps[-1]]
print("self-play final statuses:", statuses)

# 2) Strength vs the built-in baselines (reward: 1 win, -1 loss, 0 draw).
out = {}
for opp in ("random", "negamax"):
    rewards = evaluate("connectx", [AGENT, opp], num_episodes=10) + [
        list(reversed(r)) for r in evaluate("connectx", [opp, AGENT], num_episodes=10)
    ]
    mine = [r[0] if r[0] is not None else -1 for r in rewards]
    out[opp] = {"episodes": len(mine), "wins": sum(1 for x in mine if x == 1),
                "losses": sum(1 for x in mine if x == -1)}
print("vs baselines:", json.dumps(out))
(HERE / "local_eval.json").write_text(json.dumps({"self_play_statuses": statuses, "vs": out}, indent=2) + "\n")
