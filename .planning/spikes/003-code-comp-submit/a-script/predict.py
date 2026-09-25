"""Spike 003a: a SCRIPT kernel submitted to a CODE competition (equity-post-hct, late submission).

Trains a small LightGBM on train.csv and writes /kaggle/working/submission.csv for test.csv.
On the scoring rerun Kaggle swaps in the hidden test set; the same code must just work.
"""
import json
import os
from pathlib import Path

import lightgbm as lgb
import pandas as pd

SLUG = "equity-post-hct-survival-predictions"
CANDIDATES = [
    Path(f"/kaggle/input/competitions/{SLUG}"),  # observed mount (spike 002)
    Path(f"/kaggle/input/{SLUG}"),
    Path(f"/kaggle/input/{SLUG.replace('hct', 'HCT')}"),  # older notebooks use this spelling
]
base = next((p for p in CANDIDATES if p.is_dir()), None)
if base is None:  # slugs are case-sensitive on disk (canonical ref: equity-post-HCT-...)
    base = next((p.parent for p in Path("/kaggle/input").rglob("sample_submission.csv")
                 if p.parent.name.lower() == SLUG), None)
listing = sorted(str(p) for p in Path("/kaggle/input").rglob("*.csv"))[:20]
print("SPIKE003_INPUT=" + json.dumps({"base": str(base), "csvs": listing}))
if base is None:
    raise FileNotFoundError(f"competition data not found; tried {CANDIDATES}")

train = pd.read_csv(base / "train.csv")
test = pd.read_csv(base / "test.csv")
sample = pd.read_csv(base / "sample_submission.csv")
feats = [c for c in train.columns if c not in ("ID", "efs", "efs_time")]
for c in feats:
    if train[c].dtype == object or test[c].dtype == object:
        cats = pd.Categorical(pd.concat([train[c], test[c]]).astype(str)).categories
        train[c] = pd.Categorical(train[c].astype(str), categories=cats)
        test[c] = pd.Categorical(test[c].astype(str), categories=cats)

model = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=31, verbose=-1, random_state=42)
model.fit(train[feats], train["efs"])
risk = model.predict_proba(test[feats])[:, 1]  # higher = event more likely = higher risk

sub = pd.DataFrame({sample.columns[0]: test["ID"], sample.columns[1]: risk})
sub.to_csv("/kaggle/working/submission.csv", index=False)
print("SPIKE003_DONE " + json.dumps({
    "rows": len(sub), "cols": list(sub.columns), "sample_cols": list(sample.columns),
    "rerun": os.environ.get("KAGGLE_IS_COMPETITION_RERUN"),
}))
