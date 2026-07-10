"""COMP-01/02 egress: `api.kaggle.com` must be on the generated allowlist (narrow).

CLI 2.2.3 (kagglesdk `KaggleEnv.PROD`) routes `competitions pages / files / list /
download` to `https://api.kaggle.com/v1/{service}/{request}` (VERIFIED-LIVE, 02-RESEARCH
§CRITICAL EGRESS FINDING). That host is ABSENT from the Phase 1 allowlist, so a properly
sandboxed workspace blocks ALL of Phase 2 until it is added. This pins that the generated
`.claude/settings.json` carries `api.kaggle.com` while keeping the Phase 1 required hosts
and NOT broadening to a bare / whole-tree wildcard (T-02-EGRESS: add ONLY the one verified
host, no wildcard broadening).

GREEN target: 02-01 Task 2 (adds the host to settings.json.tmpl). RED now (template lacks it).

Note: these tests assert generated-settings CORRECTNESS (host membership + narrowness);
runtime egress ENFORCEMENT is the 01-03 human-verify checkpoint's job, not asserted here.
"""

import json
from pathlib import Path

# The Phase 1 mandatory host set (mirrors tests/test_settings.py REQUIRED_HOSTS).
# storage.googleapis.com is the GCS-backend gotcha: `competitions download` 302-redirects
# to signed GCS URLs.
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


def _generate_settings(ws, run_script):
    res = run_script("init_workspace.py", "--workspace", ws, "--slug", "titanic", cwd=ws)
    assert res.returncode == 0, res.stderr
    return _domains(ws / ".claude" / "settings.json")


def test_api_kaggle_host_on_generated_allowlist(tmp_workspace, run_script):
    """The CLI 2.2.3 API endpoint host `api.kaggle.com` is on the generated allowlist."""
    _settings, domains = _generate_settings(tmp_workspace, run_script)
    assert "api.kaggle.com" in domains


def test_phase1_required_hosts_still_present(tmp_workspace, run_script):
    """Adding api.kaggle.com must not drop any Phase 1 required host (incl. the GCS gotcha)."""
    _settings, domains = _generate_settings(tmp_workspace, run_script)
    assert REQUIRED_HOSTS <= domains


def test_allowlist_stays_narrow_no_wildcard(tmp_workspace, run_script):
    """Narrow allowlist (T-02-EGRESS): no bare `*`, no `*.kaggle.com`, no whole-tree wildcard."""
    _settings, domains = _generate_settings(tmp_workspace, run_script)
    assert "*" not in domains
    assert "*.kaggle.com" not in domains
    # No entry may broaden to the entire kaggle.com subtree.
    assert not any(d.startswith("*.") and d.endswith("kaggle.com") for d in domains)
