"""Competition profile built only from structured Kaggle API facts.

Inputs are the plain dicts from get_competition, the data-files summary and the
root (and, after joining, depth-1) file listing. Nothing is read from prose:
descriptions, URLs and thumbnails are dropped. The derived block (submission
mode, modality, expected output, local feasibility) is advisory evidence that
the user confirms (`kx confirm`) before kx relies on it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from kx import metrics

SCHEMA_VERSION = 1

MODES = ("csv_upload", "code_kernel", "agent", "writeup", "artifact_upload", "unknown")
MODALITIES = ("tabular", "image", "text", "audio", "structured", "none")

COMP_FIELDS = (
    "title", "category", "evaluation_metric", "max_daily_submissions",
    "is_kernels_submissions_only", "submissions_disabled", "deadline",
    "max_team_size", "host_name", "user_has_entered",
)

IMAGE = {".jpg", ".jpeg", ".png", ".dcm", ".tif", ".tiff", ".bmp", ".webp", ".nii", ".gz",
         ".h5", ".hdf5"}
AUDIO = {".ogg", ".wav", ".mp3", ".flac"}
TABULAR = {".csv", ".parquet", ".feather", ".tsv"}
JSONISH = {".json", ".jsonl"}
TAG_MODALITY = [  # host-curated tags beat file extensions; checked in order
    ({"nlp", "text classification", "text generation"}, "text"),
    ({"audio", "audio event classification", "speech"}, "audio"),
    ({"image", "computer vision", "image classification", "image segmentation"}, "image"),
]
LOCAL_BYTES_LIMIT = 5 * 1024**3
LOCAL_FILES_LIMIT = 20_000


def canonical_ref(comp: dict, slug: str) -> str:
    ref = str(comp.get("ref") or "").rstrip("/")
    tail = ref.rsplit("/", 1)[-1] if ref else ""
    return tail if tail and tail.lower() == slug.lower() else slug


def _tag_names(comp: dict) -> list[str]:
    out = []
    for t in comp.get("tags") or []:
        name = t.get("name") if isinstance(t, dict) else t
        if name:
            out.append(str(name).lower())
    return sorted(set(out))


def _parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _sample_file(root_files: list[str], nested: dict | None) -> tuple[str | None, bool]:
    """(sample submission path, nested listing refused) — root first, then depth 1."""
    hit = next((f for f in root_files if "submission" in f.lower()), None)
    if hit:
        return hit, False
    forbidden = False
    for dname, listing in sorted((nested or {}).items()):
        if listing.get("error"):
            forbidden = forbidden or "403" in str(listing["error"])
            continue
        sub = next((f for f in listing.get("files") or [] if "submission" in f.lower()), None)
        if sub:
            return f"{dname}/{sub}", False
    return None, forbidden


def classify(facts: dict, tags: list[str], file_types: list[dict], root_files: list[str],
             root_dirs: list[str], nested: dict | None) -> dict:
    """Submission mode, modality and friends, with the evidence as readable reasons."""
    reasons: list[str] = []
    sample, nested_forbidden = _sample_file(root_files, nested)
    api_served = "kaggle_evaluation" in root_dirs
    metric = (facts.get("evaluation_metric") or "").strip()
    code_only = bool(facts.get("is_kernels_submissions_only"))
    agentish = bool(
        "simulations" in tags
        or any(d.startswith("kaggle-environments") for d in root_dirs)
        or {"main.py", "agents.md"} & {f.lower() for f in root_files}
    )
    if sample:
        mode = "code_kernel" if code_only else "csv_upload"
        reasons.append(f"sample file {sample!r} and is_kernels_submissions_only={code_only}")
    elif not metric:
        mode = "writeup"
        reasons.append("no evaluation_metric and no sample submission file")
    elif agentish:
        mode = "agent"
        reasons.append("simulation signals (tag / kaggle-environments dir / main.py) and no sample file")
    else:
        mode = "unknown"
        reasons.append("a metric but no sample submission and no simulation signal: read the "
                       "Evaluation page and propose a mode"
                       + (" (nested listing refused: join the competition, then re-sync)"
                          if nested_forbidden else ""))
    if api_served:
        reasons.append("root has a kaggle_evaluation/ directory: API-served (the host gateway scores it)")

    modality = None
    for tagset, name in TAG_MODALITY:
        if set(tags) & tagset:
            modality = name
            reasons.append(f"modality {name} from tags {sorted(set(tags) & tagset)}")
            break
    if modality is None:
        by_ext = {"image": 0, "audio": 0, "tabular": 0, "structured": 0}
        for ft in file_types:
            ext = str(ft.get("extension") or "").lower()
            size = int(ft.get("total_size") or 0)
            if ext in IMAGE:
                by_ext["image"] += size
            elif ext in AUDIO:
                by_ext["audio"] += size
            elif ext in TABULAR:
                by_ext["tabular"] += size
            elif ext in JSONISH:
                by_ext["structured"] += size
        if mode == "writeup" or (mode == "agent" and by_ext["tabular"] == 0):
            modality = "none"
        else:
            modality = max(by_ext, key=by_ext.get) if any(by_ext.values()) else "none"
        reasons.append(f"modality {modality} from bytes by type {by_ext}")

    if api_served:
        expected_output = "submission.parquet"
    elif sample:
        # Output takes the sample's format: sample_submission.json -> submission.json.
        base = sample.rsplit("/", 1)[-1]
        expected_output = "submission" + (base[base.index("."):] if "." in base else ".csv")
    else:
        expected_output = None

    return {
        "submission_mode": mode,
        "api_served": api_served,
        "sample_submission": sample,
        "nested_listing_forbidden": nested_forbidden,
        "expected_output": expected_output,
        "modality": modality,
        "custom_metric": "custom metric" in tags,
        "reasons": reasons,
    }


def build_profile(slug: str, comp: dict, summary: dict, root: dict,
                  nested: dict | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    comp = comp or {}
    facts = {k: comp.get(k) for k in COMP_FIELDS}
    tags = _tag_names(comp)
    fsi = (summary or {}).get("file_summary_info") or {}
    file_types = [{k: t.get(k) for k in ("extension", "file_count", "total_size")}
                  for t in fsi.get("file_types") or []]
    total_bytes = sum(int(t.get("total_size") or 0) for t in file_types)
    file_count = int(fsi.get("total_file_count") or 0)
    root_files = [{"name": f.get("name"), "total_bytes": f.get("total_bytes")}
                  for f in (root or {}).get("files") or []]
    root_dirs = [d.get("name") if isinstance(d, dict) else d
                 for d in (root or {}).get("directories") or []]
    derived = classify(facts, tags, file_types, [f["name"] or "" for f in root_files],
                       [d or "" for d in root_dirs], nested)

    deadline = _parse_dt(facts.get("deadline"))
    closed = bool(deadline and deadline < now)
    late_open = (not facts.get("submissions_disabled")) if closed else None
    derived.update({
        "metric": (facts.get("evaluation_metric") or None),
        "metric_suggestion": metrics.suggest(facts.get("evaluation_metric")),
        "daily_limit": facts.get("max_daily_submissions"),
        "code_only": bool(facts.get("is_kernels_submissions_only")),
        "closed": closed,
        "late_submissions_open": late_open,
        "total_bytes": total_bytes,
        "file_count": file_count,
        "local_feasible": total_bytes <= LOCAL_BYTES_LIMIT and file_count <= LOCAL_FILES_LIMIT,
    })
    if closed:
        derived["reasons"].append(
            f"deadline passed; late submissions {'open' if late_open else 'closed'} "
            f"(submissions_disabled={facts.get('submissions_disabled')})")
    return {
        "schema_version": SCHEMA_VERSION,
        "slug": slug.lower(),
        "canonical_ref": canonical_ref(comp, slug),
        "competition": facts | {"tags": tags},
        "files_summary": {"total_file_count": file_count, "total_bytes": total_bytes,
                          "file_types": file_types},
        "root_listing": {"files": root_files, "directories": root_dirs},
        "nested_listing": nested,
        "derived": derived,
        "confirmed": None,
        "sync_pass": 2 if nested is not None else 1,
        "provenance": {"source": "kagglesdk get_competition + get_competition_data_files_summary "
                                 "+ list_data_tree_files", "synced_at": now.replace(microsecond=0)
                       .isoformat().replace("+00:00", "Z")},
    }


def effective(profile: dict) -> dict:
    """The derived facts with the user's confirmed overrides applied."""
    out = dict(profile.get("derived") or {})
    conf = profile.get("confirmed") or {}
    out.update(conf.get("overrides") or {})
    return out
