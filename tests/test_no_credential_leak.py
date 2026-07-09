"""SETUP-04 (T-cred-echo): no loop script echoes a raw credential VALUE.

Static scan over the loop scripts' source: a credential value must only reach
output via mask()/env-name, never printed raw. GREEN once all three scripts
exist and are clean (01-02/03/04). RED now (scripts do not exist yet).
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

EXPECTED_SCRIPTS = ["init_workspace.py", "check_credentials.py", "leak_scan.py"]

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


def test_no_credential_value_echoed():
    """No script prints a raw credential value (mask() / env-name only)."""
    offenders = []
    for name in EXPECTED_SCRIPTS:
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
    assert not offenders, f"possible raw-credential echo: {offenders}"
