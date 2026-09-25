"""Spike helper: read back submissions for competitions (read-only). Prints one line per submission.

Usage: python subs.py <competition> [<competition> ...]
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

KAGGLE = str(Path(__file__).resolve().parents[2] / ".venv" / "bin" / "kaggle")


def main(comps):
    print("now_utc", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))
    for comp in comps:
        out = subprocess.run([KAGGLE, "competitions", "submissions", comp, "--format", "json"],
                             capture_output=True, text=True, timeout=90)
        try:
            rows = json.loads(out.stdout)
        except ValueError:
            print(comp, "UNPARSEABLE rc=", out.returncode, out.stdout[:200], out.stderr[:200])
            continue
        for s in rows[:5]:
            print(comp, s.get("ref"), s.get("date"), s.get("status"), "public=", s.get("publicScore"),
                  "private=", s.get("privateScore"), "|", s.get("description"), "|", s.get("fileName"))


if __name__ == "__main__":
    main(sys.argv[1:])
