"""SETUP-04 (T-cred-echo): no loop script echoes a raw credential VALUE.

Static scan over the loop scripts' source: a credential value must only reach
output via mask()/env-name, never printed raw. GREEN once all three scripts
exist and are clean (01-02/03/04).

Phase 5 (T-05-01-02) extends the scan to the four submission scripts and adds a BEHAVIORAL
guard: a token-shaped sentinel riding on a raw Kaggle CLI buffer must never reach
stdout/stderr — it is QUARANTINED via ``dump_last_error`` to the gitignored
``control/raw/last-error.txt``. Those tests are RED until 05-03/04/05 build the scripts.
"""

import importlib
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

EXPECTED_SCRIPTS = ["init_workspace.py", "check_credentials.py", "leak_scan.py"]

# The Phase 5 submission surface. Scanned by the SAME static rules; kept in a separate list
# so the Phase 1 nodes above stay GREEN while these are still RED.
PHASE5_SCRIPTS = [
    "submissions_log.py",
    "check_submission.py",
    "submit.py",
    "fetch_lb.py",
]

# A print/f-string that interpolates a secret-named variable directly.
_SECRET_VAR = r"(?:key|token|secret|password|api_token)"
LEAK_PATTERNS = [
    re.compile(r"print\s*\([^)]*\{\s*" + _SECRET_VAR + r"\b[^}]*\}", re.IGNORECASE),
    re.compile(r"echo[^\n]*\$\{?KAGGLE_(?:KEY|API_TOKEN)", re.IGNORECASE),
]


def test_scripts_exist():
    """RED until the loop scripts are implemented (01-02/03/04)."""
    missing = [s for s in EXPECTED_SCRIPTS if not (SCRIPTS_DIR / s).is_file()]
    assert not missing, f"loop scripts not implemented yet: {missing}"


def _scan(names):
    """Static scan: report any script that is missing or echoes a raw credential value."""
    offenders = []
    for name in names:
        p = SCRIPTS_DIR / name
        if not p.is_file():
            offenders.append(f"{name}: NOT IMPLEMENTED")  # keep RED while unbuilt
            continue
        for lineno, line in enumerate(p.read_text().splitlines(), start=1):
            if "mask(" in line:  # masked output is the sanctioned path
                continue
            for pat in LEAK_PATTERNS:
                if pat.search(line):
                    offenders.append(f"{name}:{lineno}: {line.strip()[:80]}")
    return offenders


def test_no_credential_value_echoed():
    """No script prints a raw credential value (mask() / env-name only)."""
    assert not _scan(EXPECTED_SCRIPTS), "possible raw-credential echo"


# --------------------------------------------------------------------------- #
# Phase 5 (T-05-01-02): the same guarantee across the submission surface.
# --------------------------------------------------------------------------- #
def test_phase5_scripts_exist():
    """RED until 05-03/04/05 implement the submission scripts."""
    missing = [s for s in PHASE5_SCRIPTS if not (SCRIPTS_DIR / s).is_file()]
    assert not missing, f"submission scripts not implemented yet: {missing}"


def test_no_credential_value_echoed_by_submission_scripts():
    offenders = _scan(PHASE5_SCRIPTS)
    assert not offenders, f"possible raw-credential echo: {offenders}"


def test_submission_scripts_never_print_the_raw_cli_buffer():
    """A raw Kaggle buffer may carry a token-shaped string — it is QUARANTINED, never echoed.

    The sanctioned path is ``kaggle_gateway.dump_last_error`` (writing the gitignored
    ``control/raw/last-error.txt``). A bare ``print(out)`` / ``print(combined)`` of the CLI
    buffer is the leak, and this is the same posture ``classify_gate`` already enforces.
    """
    missing = [s for s in PHASE5_SCRIPTS if not (SCRIPTS_DIR / s).is_file()]
    assert not missing, f"submission scripts not implemented yet: {missing}"

    raw_echo = re.compile(
        r"print\s*\(\s*(?:f?['\"][^'\"]*\{)?\s*(out|combined|stdout|stderr|buf|buffer)\b"
    )
    offenders = []
    for name in PHASE5_SCRIPTS:
        src = (SCRIPTS_DIR / name).read_text()
        for lineno, line in enumerate(src.splitlines(), start=1):
            if raw_echo.search(line):
                offenders.append(f"{name}:{lineno}: {line.strip()[:80]}")
    assert not offenders, (
        f"a raw CLI buffer is being printed (use dump_last_error instead): {offenders}"
    )

    # The scripts that touch the CLI must ROUTE quarantining through the gateway.
    for name in ("submit.py", "fetch_lb.py"):
        src = (SCRIPTS_DIR / name).read_text()
        assert "run_kaggle" in src, f"{name} must route every CLI call through the gateway (D-16)"
        assert "dump_last_error" in src, f"{name} must quarantine a failed buffer, not print it"


def test_submit_quarantines_a_token_shaped_buffer(tmp_workspace, monkeypatch, capsys):
    """BEHAVIORAL: the sentinel in a fail-open CLI buffer never reaches stdout/stderr.

    ``tests/fixtures/submissions/submit_upload_failed.txt`` carries a ``kagat_``-prefixed,
    token-shaped sentinel alongside the real fail-open literal. Feeding it to a monkeypatched
    gateway must produce a FRAMEWORK-authored failure message — with the sentinel quarantined
    to ``control/raw/last-error.txt``, never printed.
    """
    # Imported INSIDE the body so collection never crashes at RED (submit.py is 05-05).
    mod = importlib.import_module("submit")

    from test_submit import FAIL_OPEN_UPLOAD, _fake_gateway, _seed_ws

    ws = _seed_ws(tmp_workspace)
    fake, _ = _fake_gateway(submit_rc=0, submit_out=FAIL_OPEN_UPLOAD, readback=[])
    monkeypatch.setattr(mod, "run_kaggle", fake)

    rc = mod.main(["--workspace", str(ws), "--exp-id", "exp-007", "--confirm"])
    assert rc != 0

    out = capsys.readouterr()
    transcript = out.out + out.err
    assert "TOKENLEAK_SENTINEL" not in transcript, "a token-shaped string reached the terminal"
    assert "kagat_" not in transcript, "an OAuth token prefix reached the terminal"
    assert FAIL_OPEN_UPLOAD not in transcript, "the raw CLI buffer was echoed verbatim"

    # ...and it went to the gitignored quarantine file instead.
    quarantine = ws / "control" / "raw" / "last-error.txt"
    assert quarantine.is_file(), "the failed buffer must be quarantined via dump_last_error"
    assert "TOKENLEAK_SENTINEL" in quarantine.read_text()
