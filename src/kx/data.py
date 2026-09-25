"""Local competition data: one bundle download, zip-slip-safe extraction.

Data lands in ``data/<canonical_ref>/`` (gitignored), the path the templates'
resolver reads through ``KX_DATA_DIR`` on local runs.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from kx import envelope as E
from kx.profile import effective
from kx.safe_extract import UnsafeArchiveMember, safe_extract
from kx.util import KxError, utc_now


def data_dir(ws: Path, profile: dict) -> Path:
    return ws / "data" / profile["canonical_ref"]


MAX_SINGLE_FILES = 10


def download_files(ws: Path, adapter, profile: dict, names: list[str]) -> dict:
    """A few named files (e.g. train/test/sample for a local subsample of data too
    large to take whole). Zipped files are extracted with the zip-slip guard."""
    if len(names) > MAX_SINGLE_FILES:
        raise KxError("invalid", f"at most {MAX_SINGLE_FILES} named files (per-file loops hit "
                                 "HTTP 429); download the bundle instead", errors=["too_many_files"])
    known = {f.get("name") for f in (profile.get("root_listing") or {}).get("files") or []}
    nested = profile.get("nested_listing") or {}
    for d, listing in nested.items():
        known |= {f"{d}/{f}" for f in listing.get("files") or []}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise KxError("invalid", f"not in the competition's file listing: {', '.join(unknown)}",
                      errors=["unknown_file"])
    dest = data_dir(ws, profile)
    sizes = {f.get("name"): int(f.get("total_bytes") or 0)
             for f in (profile.get("root_listing") or {}).get("files") or []}
    got = []
    for n in names:
        timeout = max(300.0, sizes.get(n, 0) / (2 * 1024**2) + 120)
        path = adapter.download_file(profile["slug"], n, ws / "cache", timeout)
        target_dir = dest / Path(n).parent
        if zipfile.is_zipfile(path):
            try:
                got += safe_extract(str(path), str(target_dir))
            except UnsafeArchiveMember as exc:
                raise KxError("error", "a downloaded file contains an unsafe path",
                              errors=["unsafe_archive"], quarantine=str(exc)) from exc
            path.unlink()
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            path.replace(target_dir / Path(n).name)
            got.append(n)
    return {"path": str(dest.relative_to(ws)), "files": len(got), "downloaded_at": utc_now(),
            "sample": sorted(got)[:10], "partial": True}


def download_bundle(ws: Path, adapter, profile: dict, force: bool = False,
                    files: list[str] | None = None) -> dict:
    eff = effective(profile)
    if not (profile.get("competition") or {}).get("user_has_entered"):
        raise KxError("needs_user", "join the competition before downloading its data",
                      errors=["not_joined"],
                      next_action=E.ask_user(
                          f"Ask the user to open https://www.kaggle.com/competitions/"
                          f"{profile['slug']}/rules and accept the rules in the browser.",
                          then=f"kx sync {profile['slug']} --download"))
    if files:
        return download_files(ws, adapter, profile, files)
    if not eff.get("local_feasible") and not force:
        raise KxError("invalid", "the profile marks this data as too large for local runs "
                                 f"({eff.get('total_bytes', 0) / 1024**3:.1f} GB, "
                                 f"{eff.get('file_count')} files); run on a kernel instead",
                      errors=["not_locally_feasible"],
                      next_action=E.run("kx new --idea '...' --hypothesis '...'",
                                        "Use a kernel run, or a local run on a subsample after an "
                                        "explicit user request (--force-download)."))
    dest = data_dir(ws, profile)
    cache = ws / "cache"
    # ~2 MB/s floor plus slack: a stalled download ends as an error, never a hang.
    timeout = max(300.0, eff.get("total_bytes", 0) / (2 * 1024**2) + 120)
    archive = adapter.download_bundle(profile["slug"], cache, timeout)
    try:
        if zipfile.is_zipfile(archive):
            names = safe_extract(str(archive), str(dest))
        else:
            dest.mkdir(parents=True, exist_ok=True)
            target = dest / archive.name
            archive.replace(target)
            names = [target.name]
    except UnsafeArchiveMember as exc:
        raise KxError("error", "the data bundle contains an unsafe path; nothing was extracted",
                      errors=["unsafe_archive"], quarantine=str(exc)) from exc
    finally:
        if archive.exists() and zipfile.is_zipfile(archive):
            archive.unlink()
    return {"path": str(dest.relative_to(ws)), "files": len(names), "downloaded_at": utc_now(),
            "sample": sorted(names)[:10]}
