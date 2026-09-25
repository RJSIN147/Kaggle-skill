"""Spike 002 kernel C: runs past its `kernels push -t` limit — what status / output do we get?"""
import time
from pathlib import Path

Path("/kaggle/working/started.txt").write_text("started")
print("SPIKE002_C_START", flush=True)
for i in range(30):
    time.sleep(10)
    print(f"SPIKE002_C_TICK {i}", flush=True)
    Path("/kaggle/working/progress.txt").write_text(str(i))
print("SPIKE002_C_FINISHED_UNEXPECTEDLY", flush=True)
