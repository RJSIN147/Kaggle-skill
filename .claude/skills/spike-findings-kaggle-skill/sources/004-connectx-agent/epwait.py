"""Spike 004 helper: poll a simulation submission's episodes + rating until ladder episodes appear.

Usage: python epwait.py <submission_id> [--budget 900] [--every 60]   (read-only)
"""

import json
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

KAGGLE = str(Path(__file__).resolve().parents[3] / ".venv" / "bin" / "kaggle")


def episodes(sub_id):
    out = subprocess.run([KAGGLE, "competitions", "episodes", sub_id, "--format", "json"],
                         capture_output=True, text=True, timeout=60)
    # LIVE FINDING: `--format json` prints the JSON array FOLLOWED by a plain-text hint line
    # ('Use "kaggle competitions replay <episode_id>" ...'), so json.loads() on stdout fails.
    # Decode only the leading JSON value.
    text = out.stdout.lstrip()
    if not text.startswith("["):
        return []
    try:
        return json.JSONDecoder().raw_decode(text)[0]
    except ValueError:
        return []


def rating(sub_id):
    out = subprocess.run([KAGGLE, "competitions", "submissions", "connectx", "--format", "json"],
                         capture_output=True, text=True, timeout=60)
    try:
        for s in json.loads(out.stdout):
            if str(s.get("ref")) == sub_id:
                return s.get("publicScore")
    except ValueError:
        pass
    return None


def main(argv):
    sub_id, budget, every = argv[0], 900, 60
    if "--budget" in argv:
        budget = int(argv[argv.index("--budget") + 1])
    if "--every" in argv:
        every = int(argv[argv.index("--every") + 1])
    t0 = time.time()
    while True:
        eps = episodes(sub_id)
        kinds = Counter(e.get("type", "?").split(".")[-1] for e in eps)
        print(datetime.now(timezone.utc).strftime("%H:%M:%S"), "episodes", dict(kinds), "rating", rating(sub_id), flush=True)
        if any("VALIDATION" not in k for k in kinds):
            Path(__file__).with_name("episodes.json").write_text(json.dumps(eps, indent=2) + "\n")
            return 0
        if time.time() - t0 > budget:
            return 3
        time.sleep(every)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
