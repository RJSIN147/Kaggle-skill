"""SETUP-03/04 credential detection, precedence, consent-gated fixes, no-leak.

GREEN target: 01-04. All RED now (check_credentials.py does not exist yet).
Tests drive check_credentials.py as a subprocess against a seeded workspace so
they exercise the documented `--workspace`/`--yes` contract without importing
internal functions.
"""

import json
import os
from pathlib import Path


SECRET_KEY = "a" * 32  # a legacy-API-key-shaped secret VALUE (must never be echoed)


def _state(ws):
    return json.loads((Path(ws) / "control" / "state.json").read_text())


def _write_kaggle_json(home, username="kaggleuser", key=SECRET_KEY, mode=0o600):
    kdir = Path(home) / ".kaggle"
    kdir.mkdir(parents=True, exist_ok=True)
    kj = kdir / "kaggle.json"
    kj.write_text(json.dumps({"username": username, "key": key}))
    kj.chmod(mode)
    return kj


def test_precedence(seeded_workspace, tmp_path, run_script, clean_kaggle_env):
    """SETUP-03 (D-04): env KAGGLE_USERNAME/KAGGLE_KEY takes precedence over a kaggle.json.

    HERMETIC (WR-06): PATH is scrubbed to an empty dir so shutil.which("kaggle")
    is None and the live-validation branch is skipped — this test only exercises
    source detection, so it must never make a network round-trip against a real
    kaggle CLI (which the 01-04 Task 3 checkpoint installs) with fabricated creds.
    """
    ws = seeded_workspace
    home = tmp_path / "home"
    _write_kaggle_json(home, username="fileuser", key="f" * 32)
    empty_bin = tmp_path / "empty-bin"   # no `kaggle` -> which() -> None (offline-safe)
    empty_bin.mkdir()

    res = run_script(
        "check_credentials.py", "--workspace", ws, cwd=ws,
        extra_env={
            "PATH": str(empty_bin),
            "HOME": str(home), "KAGGLE_USERNAME": "envuser", "KAGGLE_KEY": SECRET_KEY,
        },
    )
    out = (res.stdout + res.stderr).lower()
    assert "environment" in out           # env is canonical and wins over the file
    assert SECRET_KEY not in (res.stdout + res.stderr)   # raw key value never printed


def test_kaggle_missing(seeded_workspace, tmp_path, run_script, clean_kaggle_env):
    """SETUP-03 (D-07): kaggle CLI absent -> UNVALIDATED + install remediation.

    HERMETIC: the command-not-found branch must be exercised deterministically,
    regardless of whether a `kaggle` binary happens to be installed on the host.
    (The 01-04 Task 3 checkpoint explicitly installs `kaggle`; relying on its
    ambient absence — as an earlier version did — is a false green that flips to
    FAIL the moment the CLI is present, taking the auth-failure branch instead.)

    We scrub the subprocess PATH to an empty dir so the script's own
    ``shutil.which("kaggle")`` returns None, and point HOME at an empty dir so the
    detection never depends on (or reads) the developer's real ~/.kaggle. The
    assertions below are UNCHANGED — still UNVALIDATED + install remediation.
    """
    ws = seeded_workspace
    empty_bin = tmp_path / "empty-bin"   # contains no `kaggle` -> which() -> None
    empty_bin.mkdir()
    empty_home = tmp_path / "empty-home"  # no ~/.kaggle -> no real-cred dependence
    empty_home.mkdir()
    res = run_script(
        "check_credentials.py", "--workspace", ws, cwd=ws,
        extra_env={"PATH": str(empty_bin), "HOME": str(empty_home)},
    )
    assert _state(ws)["credentials"] == "UNVALIDATED"
    out = (res.stdout + res.stderr).lower()
    assert "install" in out and "kaggle" in out          # remediation shown


def test_chmod_600(seeded_workspace, tmp_path, run_script, clean_kaggle_env):
    """SETUP-04: a group/world-readable kaggle.json is self-healed to 0o600 (with consent).

    HERMETIC (WR-06): PATH scrubbed to an empty dir -> no live kaggle call; this
    test only exercises the chmod self-heal.
    """
    ws = seeded_workspace
    home = tmp_path / "home"
    kj = _write_kaggle_json(home, mode=0o644)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()

    run_script(
        "check_credentials.py", "--workspace", ws, "--yes", cwd=ws,
        extra_env={"PATH": str(empty_bin), "HOME": str(home)},
    )
    assert (kj.stat().st_mode & 0o777) == 0o600


def test_chmod_600_requires_consent(seeded_workspace, tmp_path, run_script, clean_kaggle_env):
    """D-03/D-06a: without --yes the chmod fix is only reported; with --yes it applies.

    HERMETIC (WR-06): PATH scrubbed to an empty dir -> no live kaggle call on
    either invocation; the test only exercises the consent-gated chmod.
    """
    ws = seeded_workspace
    home = tmp_path / "home"
    kj = _write_kaggle_json(home, mode=0o644)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()

    res = run_script(
        "check_credentials.py", "--workspace", ws, cwd=ws,
        extra_env={"PATH": str(empty_bin), "HOME": str(home)},
    )
    assert (kj.stat().st_mode & 0o777) == 0o644                     # untouched without consent
    reported = (res.stdout + res.stderr).lower()
    assert "chmod" in reported or "600" in (res.stdout + res.stderr)  # proposed fix surfaced

    run_script(
        "check_credentials.py", "--workspace", ws, "--yes", cwd=ws,
        extra_env={"PATH": str(empty_bin), "HOME": str(home)},
    )
    assert (kj.stat().st_mode & 0o777) == 0o600                     # self-healed with consent


def test_env_population_requires_consent(seeded_workspace, tmp_path, run_script, clean_kaggle_env):
    """D-06b: .env is populated from kaggle.json only with consent; offered otherwise; no secret printed.

    HERMETIC (WR-06): PATH scrubbed to an empty dir -> no live kaggle call on
    either invocation; the test only exercises the consent-gated .env population.
    """
    ws = seeded_workspace
    home = tmp_path / "home"
    _write_kaggle_json(home, username="kaggleuser", key=SECRET_KEY)
    env_file = ws / ".env"
    env_file.write_text("KAGGLE_USERNAME=\nKAGGLE_KEY=\n")
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()

    # Without consent: only offered, .env unchanged, no raw secret in output.
    res = run_script(
        "check_credentials.py", "--workspace", ws, cwd=ws,
        extra_env={"PATH": str(empty_bin), "HOME": str(home)},
    )
    assert env_file.read_text() == "KAGGLE_USERNAME=\nKAGGLE_KEY=\n"
    assert SECRET_KEY not in (res.stdout + res.stderr)

    # With consent: populated from kaggle.json.
    run_script(
        "check_credentials.py", "--workspace", ws, "--yes", cwd=ws,
        extra_env={"PATH": str(empty_bin), "HOME": str(home)},
    )
    populated = env_file.read_text()
    assert "kaggleuser" in populated and SECRET_KEY in populated


def test_malformed_state_json_fail_clear(seeded_workspace, tmp_path, run_script, clean_kaggle_env):
    """WR-02 (D-02): a corrupt control/state.json is NOT clobbered; next_exp_id never reset.

    Mirrors init_workspace's fail-clear contract: the offending path is named,
    the exit is non-zero, and the corrupt bytes are preserved byte-for-byte.
    HERMETIC: PATH scrubbed to an empty dir so the write-state path is reached
    deterministically (no live API / no dependence on an installed kaggle).
    """
    ws = seeded_workspace
    corrupt = b"{ not valid json"
    state = Path(ws) / "control" / "state.json"
    state.write_bytes(corrupt)

    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    empty_home = tmp_path / "empty-home"
    empty_home.mkdir()

    res = run_script(
        "check_credentials.py", "--workspace", ws, cwd=ws,
        extra_env={"PATH": str(empty_bin), "HOME": str(empty_home)},
    )
    assert res.returncode != 0                                   # fail-clear
    assert "state.json" in (res.stdout + res.stderr)             # offending path named
    assert state.read_bytes() == corrupt                        # byte-for-byte unchanged


def test_subprocess_output_no_secret(seeded_workspace, tmp_path, run_script, clean_kaggle_env):
    """D-04/V7: captured `kaggle` subprocess stderr is never surfaced raw (token-shaped string masked/omitted)."""
    ws = seeded_workspace
    token = "kagat_" + "z" * 40  # OAuth-token-shaped string
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    stub = fake_bin / "kaggle"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "401 Unauthorized token={token}" 1>&2\n'
        "exit 1\n"
    )
    stub.chmod(0o755)

    res = run_script(
        "check_credentials.py", "--workspace", ws, cwd=ws,
        extra_env={
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
            "KAGGLE_USERNAME": "kaggleuser",
            "KAGGLE_KEY": SECRET_KEY,
        },
    )
    combined = res.stdout + res.stderr
    assert token not in combined                     # raw subprocess stderr not echoed
    lowered = combined.lower()
    assert "unvalidated" in lowered or "401" in combined or "fail" in lowered
