"""SETUP-04 egress allowlist shape + D-09 merge + fail-clear pins.

The generated workspace .claude/settings.json must carry the deny-by-default
egress allowlist in `sandbox.network.allowedDomains` (the layer that scopes the
kaggle CLI). GREEN target: 01-03. RED now (init_workspace.py does not exist yet).

Note: these tests assert generated-settings CORRECTNESS (exact host membership,
merge, fail-clear). Runtime wildcard/host ENFORCEMENT is the 01-03 Task 3
human-verify checkpoint's job, not asserted here.
"""

import json
from pathlib import Path

# The mandatory host set (D-08). storage.googleapis.com is the GCS-backend gotcha:
# kaggle competitions download 302-redirects to signed GCS URLs.
REQUIRED_HOSTS = {
    "www.kaggle.com",
    "storage.googleapis.com",
    "pypi.org",
    "files.pythonhosted.org",
    "github.com",
}


def _domains(settings_path):
    settings = json.loads(Path(settings_path).read_text())
    return settings, set(settings["sandbox"]["network"]["allowedDomains"])


def test_egress_allowlist(tmp_workspace, run_script):
    """Generated settings.json is valid JSON; allowedDomains ⊇ required hosts; sandbox enabled."""
    ws = tmp_workspace
    res = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert res.returncode == 0, res.stderr

    settings, domains = _domains(ws / ".claude" / "settings.json")
    assert REQUIRED_HOSTS <= domains                # exact-host superset (incl. the GCS gotcha)
    assert settings["sandbox"]["enabled"] is True
    # WR-05: the fail-closed flag must be written on a fresh scaffold — dropping it
    # would silently reopen the "socat/bubblewrap absent -> unsandboxed, egress
    # open" hole while the rest of the suite stays green.
    assert settings["sandbox"]["failIfUnavailable"] is True


def test_egress_allowlist_merges_existing(tmp_workspace, run_script):
    """D-09: an existing .claude/settings.json is deep-merged, not skipped."""
    ws = tmp_workspace
    claude_dir = ws / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        json.dumps(
            {
                "env": {"FOO": "bar"},                          # unrelated user key
                "sandbox": {"network": {"allowedDomains": ["example.com"]}},
            }
        )
    )

    res = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert res.returncode == 0, res.stderr

    settings, domains = _domains(claude_dir / "settings.json")
    assert settings["env"]["FOO"] == "bar"          # user key preserved
    assert "example.com" in domains                 # pre-existing entry kept
    assert REQUIRED_HOSTS <= domains                # required hosts unioned in
    assert settings["sandbox"]["enabled"] is True
    # WR-05: merge_settings must FORCE the fail-closed flag on even when merging
    # onto a pre-existing settings.json that lacked it (fail-closed hardening).
    assert settings["sandbox"]["failIfUnavailable"] is True


def test_egress_allowlist_malformed_fails_clearly(tmp_workspace, run_script):
    """D-02/D-09: a corrupt .claude/settings.json is not clobbered; non-zero exit; path named."""
    ws = tmp_workspace
    claude_dir = ws / ".claude"
    claude_dir.mkdir()
    corrupt = b"{ not valid json"
    (claude_dir / "settings.json").write_bytes(corrupt)

    res = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert res.returncode != 0                                      # fail-clear
    assert "settings.json" in (res.stdout + res.stderr)            # offending path named
    assert (claude_dir / "settings.json").read_bytes() == corrupt  # byte-for-byte unchanged
