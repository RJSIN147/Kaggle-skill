"""LIVE (PROF-01..03): profile the spike-001 set of 20 competitions from the real API
and score the classifier against the hand-verified truth table.

Run: uv run pytest -m live -s tests/live/test_live_profiles.py
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conftest import competition_fixture  # noqa: E402
from test_init_sync import TRUTH  # noqa: E402

from kx.adapter import KaggleAdapter  # noqa: E402
from kx.profile import build_profile  # noqa: E402
from kx.util import KxError  # noqa: E402

pytestmark = pytest.mark.live
ALL = sorted(TRUTH) + ["nvidia-nemotron-model-reasoning-challenge"]
REPORT = Path(os.environ.get("KX_LIVE_REPORT", "/tmp/kx-live/profiles.json"))


@pytest.fixture(scope="module")
def adapter(real_home):
    return KaggleAdapter()


@pytest.fixture(scope="module")
def real_home():
    # The unit-test fixture hides the real credential; live tests need it back.
    return Path.home()


def _sync(adapter, slug):
    comp = adapter.competition(slug)
    summary = adapter.files_summary(slug)
    root = adapter.list_tree(slug)
    nested = None
    if comp.get("user_has_entered"):
        nested = {}
        for d in (root.get("directories") or [])[:25]:
            name = d.get("name")
            try:
                listing = adapter.list_tree(slug, path=name)
                nested[name] = {"files": [f.get("name") for f in listing.get("files") or []]}
            except KxError as exc:
                nested[name] = {"error": ",".join(exc.errors)}
    return build_profile(slug, comp, summary, root, nested)


def test_live_profiles_match_truth(adapter):
    rows, mode_ok, api_ok = [], 0, 0
    for slug in ALL:
        prof = _sync(adapter, slug)
        d = prof["derived"]
        truth = TRUTH.get(slug, ("unknown", {"text", "tabular"}, False))
        m_ok = d["submission_mode"] == truth[0]
        mode_ok += m_ok
        api_ok += d["api_served"] is truth[2]
        spike = competition_fixture(slug)
        sp = build_profile(slug, spike["competition"], spike["files_summary"], spike["tree_root"],
                           spike.get("tree_depth1") or None)["derived"]
        drift = {k: (sp[k], d[k]) for k in ("total_bytes", "file_count", "local_feasible",
                                             "daily_limit", "code_only", "late_submissions_open",
                                             "metric", "expected_output") if sp[k] != d[k]}
        rows.append({"slug": slug, "canonical_ref": prof["canonical_ref"],
                     "mode": d["submission_mode"], "mode_ok": m_ok, "api_served": d["api_served"],
                     "modality": d["modality"], "modality_ok": d["modality"] in truth[1],
                     "expected_output": d["expected_output"], "daily_limit": d["daily_limit"],
                     "code_only": d["code_only"], "late_open": d["late_submissions_open"],
                     "metric": d["metric"], "bytes": d["total_bytes"], "files": d["file_count"],
                     "local_feasible": d["local_feasible"], "sync_pass": prof["sync_pass"],
                     "drift_vs_spike": drift, "reasons": d["reasons"]})
        assert "description" not in json.dumps(prof)
        if not m_ok:
            assert d["submission_mode"] == "unknown", f"{slug}: WRONG mode {d['submission_mode']}"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(rows, indent=1))
    print(f"\nmode {mode_ok}/{len(ALL)}  api_served {api_ok}/{len(ALL)}  report: {REPORT}")
    for r in rows:
        print(f"{r['slug'][:40]:40} {r['mode']:12} {'ok ' if r['mode_ok'] else 'X  '}"
              f"{r['modality']:10} out={r['expected_output']} daily={r['daily_limit']} "
              f"late={r['late_open']} pass={r['sync_pass']} drift={r['drift_vs_spike']}")
    assert mode_ok >= 19 and api_ok == len(ALL)
