"""test_kernel_live.py — opt-in LIVE integration stub for the full kernel loop (EXP-05).

Marked ``live`` and therefore EXCLUDED from the default suite (pyproject `addopts = -m 'not
live'`). It is DESELECTED — never a failure — in normal runs. Run it deliberately at the phase
human-verify checkpoint with a real Kaggle credential:

    uv run pytest -m live tests/test_kernel_live.py

This is the single place the three genuinely-live-only unknowns get confirmed (research
Assumptions A1/A2/A3):
  1. the exact **T4×2** accelerator string for ``--accelerator`` / ``machine_shape`` (A1);
  2. the real ``kaggle kernels logs`` format + the finalized D-11 marker set (A3);
  3. the ``kaggle kernels status`` render — ``has status "KernelWorkerStatus.<TOKEN>"`` (A2).

It documents (does not yet execute) the full push→poll→pull→record loop against a real GPU
kernel and is intentionally skipped even under ``-m live`` until 04-02/03/04 land the scripts.
"""

import pytest


@pytest.mark.live
def test_full_kernel_loop_push_poll_pull_record(run_script, tmp_path):
    """Full loop against a REAL Kaggle GPU kernel: convert → push (T4×2) → poll → pull →
    record. Confirms the T4×2 accelerator string, the real log format/marker set, and the
    status render. Skipped until the kernel scripts exist and a human runs the checkpoint."""
    pytest.skip(
        "live kernel push is a manual human-verify checkpoint (burns GPU quota); "
        "run at the 04 phase gate once convert/push/poll/pull/record are GREEN"
    )
