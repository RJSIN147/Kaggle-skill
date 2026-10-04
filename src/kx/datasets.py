"""kx dataset push: a private Kaggle dataset from a local folder (wheels for an offline
install, weights, lookup tables), to attach with ``kx new --dataset owner/slug``.

Same rules as a kernel push: always private, never retried. ``control/datasets.json``
keeps a PUSHING record before the upload; if kx is interrupted, the next push reads back
whether a new version landed instead of uploading again. Files that look like credentials
are refused before anything leaves the machine.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from kx import envelope as E
from kx import workspace
from kx.leak_scan import scan_text
from kx.util import KxError, atomic_write, read_json, utc_now

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")
CREDENTIAL_NAMES = {"kaggle.json", "access_token", ".env", "credentials", "credentials.json",
                    "id_rsa", "id_ed25519"}
SCAN_BYTES = 1_000_000  # text files up to this size are scanned for credential patterns


def _state_path(ws: Path) -> Path:
    return workspace.control(ws) / "datasets.json"


def _load(ws: Path) -> dict:
    p = _state_path(ws)
    return read_json(p) if p.exists() else {}


def _save(ws: Path, state: dict) -> None:
    atomic_write(_state_path(ws), json.dumps(state, indent=2) + "\n")


def credential_files(folder: Path) -> list[str]:
    """Files that must never be uploaded: credential names, keys, or credential patterns."""
    bad = []
    for f in sorted(folder.rglob("*")):
        if not f.is_file():
            continue
        rel = str(f.relative_to(folder))
        if f.name in CREDENTIAL_NAMES or f.suffix in (".pem", ".key"):
            bad.append(rel)
            continue
        if f.stat().st_size <= SCAN_BYTES:
            try:
                text = f.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            if scan_text(text):
                bad.append(rel)
    return bad


def _version(adapter, ref: str) -> int | None:
    """The dataset's current version, or None when it does not exist."""
    try:
        st = adapter.dataset_state(ref)
    except KxError as exc:
        # Kaggle answers 403 (not 404) for a dataset that does not exist: confirm with a
        # listing of this account's own datasets before concluding it is missing.
        if any(e.startswith(("http_404", "http_403")) for e in exc.errors) and \
                _mine(adapter, ref) is None:
            return None
        raise
    v = st.get("current_version_number")
    return v if isinstance(v, int) else None


def _mine(adapter, ref: str) -> dict | None:
    return next((d for d in adapter.my_datasets(ref.split("/", 1)[1])
                 if d["ref"].lower() == ref.lower()), None)


def _write_metadata(folder: Path, ref: str, title: str) -> None:
    mp = folder / "dataset-metadata.json"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text())
        except json.JSONDecodeError as exc:
            raise KxError("invalid", "dataset-metadata.json in that folder is not valid JSON",
                          errors=["bad_dataset_metadata"]) from exc
        if meta.get("id") != ref:
            raise KxError("invalid", f"{mp.name} in that folder belongs to {meta.get('id')!r}, "
                          f"not {ref}", errors=["bad_dataset_metadata"])
        return
    mp.write_text(json.dumps({"title": title, "id": ref,
                              "licenses": [{"name": "CC0-1.0"}]}, indent=2) + "\n")


def cmd_dataset(ws: Path, args, adapter) -> dict:
    workspace.require_workspace(ws)
    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        raise KxError("invalid", f"{args.folder} is not a folder", errors=["bad_folder"])
    if not SLUG_RE.match(args.slug or ""):
        raise KxError("invalid", "--slug: 3-50 lowercase letters, digits and dashes",
                      errors=["bad_slug"])
    bad = credential_files(folder)
    if bad:
        raise KxError("invalid", "refusing to upload files that look like credentials: "
                      + ", ".join(bad[:5]), errors=["credential_in_folder"])
    if not any(f.is_file() and f.name != "dataset-metadata.json" for f in folder.rglob("*")):
        raise KxError("invalid", "the folder has no files to upload", errors=["empty_folder"])
    owner = adapter.username
    if owner is None:
        adapter.load()
        owner = adapter.username
    ref = f"{owner}/{args.slug}"
    state = _load(ws)
    rec = state.get(ref) or {}
    current = _version(adapter, ref)
    use = f"kx new --dataset {ref} --idea '...' --hypothesis '...'"
    if rec.get("status") == "PUSHING":
        prev = rec.get("prev_version")
        if current is not None and (prev is None or current > prev):
            state[ref] = rec | {"status": "PUSHED", "version": current, "read_back": utc_now()}
            _save(ws, state)
            return E.make("dataset", "ok", f"an interrupted push of {ref} reached Kaggle as "
                          f"version {current}; kx read it back and did not upload again",
                          data={"dataset": ref, "version": current, "private": True},
                          next_action=E.run(use))
    if current is not None:
        # A new version inherits the dataset's visibility: never add files to a public one.
        mine = _mine(adapter, ref)
        if not mine or mine.get("is_private") is not True:
            raise KxError("invalid", f"{ref} exists and is not private (or its visibility "
                          "cannot be read): kx only uploads to private datasets. Pick another "
                          "--slug.", errors=["dataset_not_private"])
    _write_metadata(folder, ref, args.title or args.slug.replace("-", " "))
    state[ref] = {"status": "PUSHING", "prev_version": current, "folder": str(folder),
                  "push_started": utc_now()}
    _save(ws, state)
    try:
        resp = adapter.dataset_push(str(folder), new=current is None,
                                    notes=args.notes or f"kx dataset push {utc_now()}")
    except KxError as exc:
        if exc.next_action is None:
            exc.next_action = E.run(f"kx dataset push {args.folder} --slug {args.slug}",
                                    "Run it once more: kx reads back whether the upload "
                                    "reached Kaggle and uploads only if it did not.")
        raise
    if resp.get("error"):
        state.pop(ref)
        _save(ws, state)
        raise KxError("error", "Kaggle refused the dataset upload (message quarantined)",
                      errors=["dataset_push_error"], quarantine=str(resp["error"]))
    version = _version(adapter, ref)
    state[ref] = {"status": "PUSHED", "version": version, "folder": str(folder),
                  "pushed_at": utc_now()}
    _save(ws, state)
    return E.make("dataset", "ok", f"{ref} {'created' if current is None else 'updated'} "
                  f"(private, version {version}); Kaggle may take a minute to process it",
                  data={"dataset": ref, "version": version, "private": True,
                        "created": current is None},
                  next_action=E.run(use, "Attach it to the experiment that needs it."))
