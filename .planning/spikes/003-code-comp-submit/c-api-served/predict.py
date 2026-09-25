"""Spike 003c: an API-SERVED code competition (um-game-playing-strength-of-mcts-variants).

The host's `kaggle_evaluation` gateway calls predict() in batches; on the scoring rerun
(KAGGLE_IS_COMPETITION_RERUN set) we must serve(); on an interactive/batch run we exercise the
local gateway, which writes submission.parquet to the cwd (/kaggle/working).
Constant-zero predictor: this spike validates the submission PATH, not the model.
"""
import json
import os
import sys
from pathlib import Path

import polars as pl

SLUG = "um-game-playing-strength-of-mcts-variants"
CANDIDATES = [Path("/kaggle/input/competitions") / SLUG, Path("/kaggle/input") / SLUG]
comp = next((p for p in CANDIDATES if p.is_dir()), None)
print("SPIKE003C_ENV=" + json.dumps({
    "comp": str(comp), "rerun": os.getenv("KAGGLE_IS_COMPETITION_RERUN"), "cwd": os.getcwd(),
}), flush=True)
if comp is None:
    raise FileNotFoundError(f"competition data not found; tried {CANDIDATES}")
sys.path.append(str(comp))  # kaggle_evaluation ships inside the competition data

import kaggle_evaluation.mcts_inference_server  # noqa: E402


def predict(test: pl.DataFrame, sample_sub: pl.DataFrame) -> pl.DataFrame:
    return sample_sub.with_columns(pl.lit(0.0).alias("utility_agent1"))


server = kaggle_evaluation.mcts_inference_server.MCTSInferenceServer(predict)
if os.getenv("KAGGLE_IS_COMPETITION_RERUN"):
    server.serve()
else:
    # The host gateway's DEFAULT paths point at the old /kaggle/input/<slug>/ mount, which no
    # longer exists (data is under /kaggle/input/competitions/<slug>/) — pass them explicitly.
    server.run_local_gateway((str(comp / "test.csv"), str(comp / "sample_submission.csv")))
    out = Path("submission.parquet")
    print("SPIKE003C_LOCAL_GATEWAY_DONE " + json.dumps({
        "exists": out.exists(), "rows": pl.read_parquet(out).height if out.exists() else None,
    }), flush=True)
