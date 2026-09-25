"""Spike 002 kernel B: consumes kernel A's output via kernel_sources and reports where it was mounted."""
import json
import os
import pickle
from pathlib import Path

hits = []
for dirpath, _dirnames, filenames in os.walk("/kaggle/input"):
    for fn in filenames:
        hits.append(str(Path(dirpath) / fn))
print("SPIKE002_B_INPUT_FILES=" + json.dumps(sorted(hits)[:60]))

model_paths = [h for h in hits if h.endswith("model.pkl")]
result = {"input_files": sorted(hits)[:60], "model_paths": model_paths}
if model_paths:
    # Trusted input: model.pkl is written by OUR OWN kernel A (spike 002), mounted read-only.
    # Real model hand-off in v2 must still prefer non-pickle formats (json/npz/safetensors).
    with open(model_paths[0], "rb") as fh:
        result["loaded"] = pickle.load(fh)
nested = [h for h in hits if h.endswith("nested.txt")]
result["nested_paths"] = nested
print("SPIKE002_B_RESULT=" + json.dumps(result, default=str))
Path("/kaggle/working/b_result.json").write_text(json.dumps(result, indent=2, default=str))
