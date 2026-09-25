"""Spike 002 kernel D: a script that raises — ERROR status, or COMPLETE-with-traceback?"""
from pathlib import Path

Path("/kaggle/working/partial.txt").write_text("written before the crash")
print("SPIKE002_D_BEFORE_CRASH", flush=True)
raise RuntimeError("SPIKE002_D deliberate failure")
