"""Spike 001 probe: pull STRUCTURED competition facts from kaggle.api (no prose scraping).

Usage: .venv/bin/python probe.py <slug> [<slug> ...]   → writes raw/<slug>.json
Never prints credentials; only competition metadata.
"""

import json
import sys
from pathlib import Path

from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.competitions.types.competition_api_service import (
    ApiGetCompetitionDataFilesSummaryRequest,
    ApiGetCompetitionRequest,
    ApiListDataTreeFilesRequest,
)

OUT = Path(__file__).parent / "raw"
OUT.mkdir(exist_ok=True)


def plain(obj, depth=0):
    """KaggleObject -> plain JSON-able structure (best effort)."""
    if depth > 6:
        return str(obj)
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [plain(x, depth + 1) for x in obj]
    if isinstance(obj, dict):
        return {k: plain(v, depth + 1) for k, v in obj.items()}
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    fields = getattr(obj, "_fields", None)
    if fields:
        out = {}
        for f in fields:
            name = getattr(f, "field_name", None) or getattr(f, "name", None)
            if not name:
                continue
            try:
                out[name] = plain(getattr(obj, name), depth + 1)
            except Exception as exc:  # noqa: BLE001 — probe, record and move on
                out[name] = f"<err {type(exc).__name__}>"
        return out
    return str(obj)


def probe(client, slug):
    rec = {"slug": slug}
    cc = client.competitions.competition_api_client
    try:
        r = ApiGetCompetitionRequest()
        r.competition_name = slug
        rec["competition"] = plain(cc.get_competition(r))
    except Exception as exc:  # noqa: BLE001
        rec["competition_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    try:
        r = ApiGetCompetitionDataFilesSummaryRequest()
        r.competition_name = slug
        rec["files_summary"] = plain(cc.get_competition_data_files_summary(r))
    except Exception as exc:  # noqa: BLE001
        rec["files_summary_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    try:
        r = ApiListDataTreeFilesRequest()
        r.competition_name = slug
        r.page_size = 200
        rec["tree_root"] = plain(cc.list_data_tree_files(r))
    except Exception as exc:  # noqa: BLE001
        rec["tree_root_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    # Depth-1 listing of each root directory. LIVE FINDING (2026-09-25): this 403s unless the
    # user has joined the competition (accepted rules) — root listing + files summary do not.
    rec["tree_depth1"] = {}
    for d in (rec.get("tree_root") or {}).get("directories") or []:
        name = d.get("name")
        try:
            r = ApiListDataTreeFilesRequest()
            r.competition_name = slug
            r.path = name
            r.page_size = 50
            res = plain(cc.list_data_tree_files(r))
            rec["tree_depth1"][name] = {
                "files": [f.get("name") for f in res.get("files") or []][:50],
                "directories": [x.get("name") for x in res.get("directories") or []][:20],
            }
        except Exception as exc:  # noqa: BLE001
            rec["tree_depth1"][name] = {"error": f"{type(exc).__name__}: {str(exc)[:80]}"}
    return rec


def main(slugs):
    api = KaggleApi()
    api.authenticate()
    with api.build_kaggle_client() as client:
        for slug in slugs:
            rec = probe(client, slug)
            (OUT / f"{slug}.json").write_text(json.dumps(rec, indent=2, default=str))
            comp = rec.get("competition", {})
            print(
                f"{slug:55s} code_only={comp.get('is_kernels_submissions_only')!s:5s} "
                f"metric={comp.get('evaluation_metric')!r:40.40s} "
                f"errs={[k for k in rec if k.endswith('_error')]}"
            )


if __name__ == "__main__":
    main(sys.argv[1:])
