"""Spike helper: poll submissions until the given refs leave PENDING (read-only).

Usage: python subwait.py --budget 2400 --every 60 <competition>:<ref> [...]
Prints each status change with UTC time; exits 0 when all are terminal, 3 on budget expiry.
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

KAGGLE = str(Path(__file__).resolve().parents[2] / ".venv" / "bin" / "kaggle")


def now():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def fetch(comp):
    out = subprocess.run([KAGGLE, "competitions", "submissions", comp, "--format", "json"],
                         capture_output=True, text=True, timeout=90)
    try:
        return {str(s.get("ref")): s for s in json.loads(out.stdout)}
    except ValueError:
        return {}


def main(argv):
    budget, every, targets = 2400, 60, []
    it = iter(argv)
    for a in it:
        if a == "--budget":
            budget = int(next(it))
        elif a == "--every":
            every = int(next(it))
        else:
            comp, ref = a.rsplit(":", 1)
            targets.append((comp, ref))
    last, t0 = {}, time.time()
    while True:
        rows = {}
        for comp in {c for c, _ in targets}:
            rows[comp] = fetch(comp)
        done = True
        for comp, ref in targets:
            s = rows[comp].get(ref, {})
            state = (s.get("status"), s.get("publicScore"), s.get("privateScore"))
            if state != last.get(ref):
                print(now(), comp, ref, *state, flush=True)
                last[ref] = state
            if not s or "PENDING" in str(s.get("status")):
                done = False
        if done:
            return 0
        if time.time() - t0 > budget:
            print(now(), "budget expired", flush=True)
            return 3
        time.sleep(every)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
