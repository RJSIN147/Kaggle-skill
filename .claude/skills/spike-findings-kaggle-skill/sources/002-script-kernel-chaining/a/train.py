"""Spike 002 kernel A: a SCRIPT kernel that records its runtime environment and writes artifacts."""
import json
import os
import pickle
import sys
from pathlib import Path

VERSION = "A-v3"
if VERSION == "A-v3":  # race probe: keep v3 RUNNING while B is pushed
    import time

    time.sleep(120)


def tree(root, depth=3, limit=40):
    out = []
    root = Path(root)
    if not root.exists():
        return [f"<missing {root}>"]
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        if len(d.relative_to(root).parts) > depth:
            dirnames[:] = []
            continue
        out.append(f"{d}/ ({len(dirnames)} dirs, {len(filenames)} files) e.g. {sorted(filenames)[:3]}")
        if len(out) >= limit:
            break
    return out


info = {
    "version": VERSION,
    "argv": sys.argv,
    "__file__": globals().get("__file__"),
    "cwd": os.getcwd(),
    "python": sys.version.split()[0],
    "ipykernel_loaded": "ipykernel" in sys.modules,
    # keys only — values can be tokens (e.g. KAGGLE_USER_SECRETS_TOKEN)
    "kaggle_env_keys": sorted(k for k in os.environ if k.startswith("KAGGLE")),
    "run_type": os.environ.get("KAGGLE_KERNEL_RUN_TYPE"),
    "input_tree": tree("/kaggle/input"),
    "working_exists": Path("/kaggle/working").is_dir(),
}
print("SPIKE002_INFO=" + json.dumps(info))

out = Path("/kaggle/working")
with open(out / "model.pkl", "wb") as fh:
    pickle.dump({"version": VERSION, "weights": [1, 2, 3]}, fh)
(out / "meta.json").write_text(json.dumps({"version": VERSION}))
(out / "sub").mkdir(exist_ok=True)
(out / "sub" / "nested.txt").write_text(VERSION)
(out / "info.json").write_text(json.dumps(info, indent=2))
print(f"SPIKE002_A_DONE version={VERSION}")
