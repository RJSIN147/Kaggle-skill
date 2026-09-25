"""Spike helper: wait for one or more Kaggle kernels to reach a terminal status.

Usage: python kwait.py <owner/slug> [<owner/slug> ...] [--every 10] [--budget 600]
Prints one line per poll; exits 0 when all are terminal, 3 on budget expiry.
"""

import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

KAGGLE = str(Path(__file__).resolve().parents[2] / ".venv" / "bin" / "kaggle")
TERMINAL = {"COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED", "CANCEL_REQUESTED"}


def status(slug):
    out = subprocess.run([KAGGLE, "kernels", "status", slug], capture_output=True, text=True, timeout=60)
    m = re.search(r"KernelWorkerStatus\.([A-Z_]+)", out.stdout + out.stderr)
    return m.group(1) if m else f"?rc={out.returncode}"


def main(argv):
    every, budget, slugs = 10, 600, []
    it = iter(argv)
    for a in it:
        if a == "--every":
            every = int(next(it))
        elif a == "--budget":
            budget = int(next(it))
        else:
            slugs.append(a)
    t0 = time.time()
    while True:
        st = {s: status(s) for s in slugs}
        print(datetime.now(timezone.utc).strftime("%H:%M:%S"), " ".join(f"{s.split('/')[-1]}={v}" for s, v in st.items()), flush=True)
        if all(v in TERMINAL for v in st.values()):
            return 0
        if time.time() - t0 > budget:
            return 3
        time.sleep(every)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
