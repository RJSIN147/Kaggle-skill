"""Local evaluation of a simulation agent (runs in a THROWAWAY environment).

Invoked by kx as
  uv run --no-project --with kaggle-environments python agent_eval.py --env connectx \
      --agent main.py --pool prev1.py prev2.py --episodes 10 --out output/result.json
It never imports kx: kaggle-environments pulls ~117 packages, so it is never installed
into the skill environment.

1. Validation: one self-play episode must end with every status DONE (Kaggle's own check).
2. "CV": win rate against each opponent (built-in baselines + earlier agents), playing both
   seats; W=1, D=0.5, L=0. Each opponent is one "fold" in result.json.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--pool", nargs="*", default=[])
    ap.add_argument("--baselines", nargs="*", default=["random", "negamax"])
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--exp-id", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    from kaggle_environments import evaluate, make

    agent = str(Path(a.agent).resolve())
    env = make(a.env, debug=True)
    env.run([agent, agent])
    statuses = [s.status for s in env.steps[-1]]
    validation = {"self_play_statuses": statuses, "ok": all(s == "DONE" for s in statuses)}
    print("KX_VALIDATION=" + json.dumps(validation), flush=True)
    if not validation["ok"]:
        raise SystemExit("self-play validation failed: " + ", ".join(statuses))

    opponents = list(a.baselines) + [str(Path(p).resolve()) for p in a.pool]
    per, scores = [], []
    for opp in opponents:
        first = evaluate(a.env, [agent, opp], num_episodes=a.episodes)
        second = evaluate(a.env, [opp, agent], num_episodes=a.episodes)
        w = d = lost = 0
        for mine, theirs in [(r[0], r[1]) for r in first] + [(r[1], r[0]) for r in second]:
            if mine is None or theirs is None:
                lost += 1  # an error/timeout on our side counts as a loss
            elif mine > theirs:
                w += 1
            elif mine < theirs:
                lost += 1
            else:
                d += 1
        rate = (w + 0.5 * d) / max(1, w + d + lost)
        name = opp if opp in a.baselines else Path(opp).parent.name or Path(opp).name
        per.append({"opponent": name, "wins": w, "draws": d, "losses": lost, "win_rate": rate})
        scores.append(rate)
        print(f"vs {name}: W{w} D{d} L{lost} -> {rate:.3f}", flush=True)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "exp_id": a.exp_id, "metric": "win_rate", "n_folds": len(scores),
        "fold_scores": scores, "cv_mean": statistics.mean(scores),
        "cv_std": statistics.pstdev(scores) if len(scores) > 1 else 0.0,
        "greater_is_better": True, "validation": validation, "opponents": per,
        "episodes_per_seat": a.episodes, "submission_file": Path(a.agent).name,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
