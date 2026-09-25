"""Spike 001 classifier: raw/<slug>.json (structured API facts) -> competition profile.

Scores the heuristic against a hand-verified ground truth and writes profiles.json + results.md.
No prose scraping: only get_competition fields, the data-files summary and the root file tree.
"""

import json
from pathlib import Path

HERE = Path(__file__).parent

IMAGE = {".jpg", ".jpeg", ".png", ".dcm", ".tif", ".tiff", ".bmp", ".webp", ".nii", ".gz"}
AUDIO = {".ogg", ".wav", ".mp3", ".flac"}
TABULAR = {".csv", ".parquet", ".feather", ".tsv"}
JSONISH = {".json", ".jsonl"}
TAG_MODALITY = [  # checked in order; tags are host-curated and beat file extensions
    ({"nlp", "text classification", "text generation"}, "text"),
    ({"audio", "audio event classification", "speech"}, "audio"),
    ({"image", "computer vision", "image classification", "image segmentation"}, "image"),
]
LOCAL_BYTES_LIMIT = 5 * 1024**3   # >5 GB: download locally only on explicit request
LOCAL_FILES_LIMIT = 20_000        # huge file counts are painful to extract/iterate locally

# Hand-verified ground truth (mode, modality, api_served). Three rows were verified against
# the competition's own Evaluation / Submission-Requirements page (see pages/ + README).
TRUTH = {
    "titanic": ("csv_upload", "tabular", False),
    "playground-series-s6e2": ("csv_upload", "tabular", False),
    "digit-recognizer": ("csv_upload", {"tabular", "image"}, False),
    "spaceship-titanic": ("csv_upload", "tabular", False),
    "connectx": ("agent", "none", False),
    "arc-prize-2026-arc-agi-2": ("code_kernel", "structured", False),
    "rsna-knee-abnormality-detection": ("code_kernel", "image", False),
    "nvidia-nemotron-model-reasoning-challenge": ("artifact_upload", "text", False),
    "orbit-wars": ("agent", "none", False),
    "gemma-4-good-hackathon": ("writeup", "none", False),
    "kaggle-measuring-agi": ("writeup", "none", False),
    "pokemon-tcg-ai-battle-challenge-strategy": ("writeup", "none", False),
    "equity-post-hct-survival-predictions": ("code_kernel", "tabular", False),
    "jane-street-real-time-market-data-forecasting": ("code_kernel", "tabular", True),
    "isic-2024-challenge": ("code_kernel", "image", False),
    "llm-prompt-recovery": ("code_kernel", "text", False),
    "birdclef-2025": ("code_kernel", "audio", False),
    "m5-forecasting-accuracy": ("csv_upload", "tabular", False),
    "cooked-or-not": ("csv_upload", "image", False),
    "um-game-playing-strength-of-mcts-variants": ("code_kernel", "tabular", True),
}


def tag_names(comp):
    return {(t.get("name") if isinstance(t, dict) else str(t)).lower() for t in comp.get("tags") or []}


def profile(raw):
    comp = raw.get("competition") or {}
    tags = tag_names(comp)
    fsi = ((raw.get("files_summary") or {}).get("file_summary_info")) or {}
    ftypes = {(ft.get("extension") or "").lower(): ft for ft in fsi.get("file_types") or []}
    tree = raw.get("tree_root") or {}
    root_files = [f.get("name", "") for f in tree.get("files") or []]
    root_dirs = [d.get("name", "") for d in tree.get("directories") or []]

    data_bytes = sum(int(ft.get("total_size") or 0) for ft in ftypes.values())
    file_count = int(fsi.get("total_file_count") or 0)
    sample_sub = next((f for f in root_files if "submission" in f.lower()), None)
    nested_forbidden = False
    if sample_sub is None:  # pass 2: depth-1 listing (only works once the user has joined)
        for dname, listing in (raw.get("tree_depth1") or {}).items():
            if "error" in listing:
                nested_forbidden = nested_forbidden or "403" in listing["error"]
                continue
            hit = next((f for f in listing["files"] if "submission" in f.lower()), None)
            if hit:
                sample_sub = f"{dname}/{hit}"
                break
    api_served = "kaggle_evaluation" in root_dirs
    metric = (comp.get("evaluation_metric") or "").strip()
    code_only = bool(comp.get("is_kernels_submissions_only"))
    agentish = (
        "simulations" in tags
        or any(d.startswith("kaggle-environments") for d in root_dirs)
        or {"main.py", "agents.md"} & {f.lower() for f in root_files}
    )

    # --- submission mode (evidence ordered strongest-first) ---
    reasons = []
    if sample_sub:
        mode = "code_kernel" if code_only else "csv_upload"
        reasons.append(f"sample file {sample_sub!r} + is_kernels_submissions_only={code_only}")
    elif not metric:
        mode = "writeup"
        reasons.append("no evaluation_metric and no sample submission")
    elif agentish:
        mode = "agent"
        reasons.append("simulation signals (tag/kaggle-environments/main.py) and no sample submission")
    else:
        mode = "unknown"
        reasons.append(
            "metric present but no sample submission and no simulation signal — AI must read Evaluation page"
            + (" (nested listing 403: join the competition, then re-sync)" if nested_forbidden else "")
        )

    # --- modality ---
    modality = None
    for tagset, name in TAG_MODALITY:
        if tags & tagset:
            modality = name
            reasons.append(f"modality from tags {sorted(tags & tagset)}")
            break
    if modality is None:
        by_ext = {"image": 0, "audio": 0, "tabular": 0, "structured": 0}
        for ext, ft in ftypes.items():
            size = int(ft.get("total_size") or 0)
            if ext in IMAGE or ext in {".hdf5", ".h5"}:
                by_ext["image"] += size
            elif ext in AUDIO:
                by_ext["audio"] += size
            elif ext in TABULAR:
                by_ext["tabular"] += size
            elif ext in JSONISH:
                by_ext["structured"] += size
        if mode in ("agent", "writeup") and by_ext["tabular"] == 0:
            modality = "none"
        elif mode == "writeup":
            modality = "none"
        else:
            modality = max(by_ext, key=by_ext.get) if any(by_ext.values()) else "none"
        reasons.append(f"modality from file bytes {by_ext}")

    return {
        "slug": raw["slug"],
        "category": comp.get("category"),
        "submission_mode": mode,
        "api_served": api_served,
        "sample_submission": sample_sub,
        "nested_listing_forbidden": nested_forbidden,
        "modality": modality,
        "metric": metric or None,
        "custom_metric": "custom metric" in tags,
        "daily_limit": comp.get("max_daily_submissions"),
        "code_only": code_only,
        "submissions_disabled": comp.get("submissions_disabled"),
        "deadline": str(comp.get("deadline"))[:10],
        "data_bytes": data_bytes,
        "file_count": file_count,
        "local_feasible": data_bytes <= LOCAL_BYTES_LIMIT and file_count <= LOCAL_FILES_LIMIT,
        "tags": sorted(tags),
        "reasons": reasons,
    }


def main():
    profiles, rows, ok_mode, ok_mod, ok_api = [], [], 0, 0, 0
    for f in sorted((HERE / "raw").glob("*.json")):
        p = profile(json.loads(f.read_text()))
        profiles.append(p)
        t_mode, t_mod, t_api = TRUTH[p["slug"]]
        m_ok = p["submission_mode"] == t_mode
        d_ok = p["modality"] in (t_mod if isinstance(t_mod, set) else {t_mod})
        a_ok = p["api_served"] == t_api
        ok_mode += m_ok
        ok_mod += d_ok
        ok_api += a_ok
        gb = p["data_bytes"] / 1024**3
        rows.append(
            f"| {p['slug']} | {p['submission_mode']}{' (API)' if p['api_served'] else ''} "
            f"| {'✓' if m_ok else '✗ ' + t_mode} | {p['modality']} | {'✓' if d_ok else '✗ ' + str(t_mod)} "
            f"| {gb:.2f} GB / {p['file_count']:,} | {'yes' if p['local_feasible'] else 'no'} "
            f"| {p['daily_limit']} | {p['submissions_disabled']} |"
        )
    n = len(profiles)
    (HERE / "profiles.json").write_text(json.dumps(profiles, indent=2) + "\n")
    table = "\n".join(
        [
            "| Competition | Mode (derived) | Mode ok | Modality | Modality ok | Data | Local? | Daily | Subs disabled |",
            "|---|---|---|---|---|---|---|---|---|",
            *rows,
        ]
    )
    summary = f"mode {ok_mode}/{n} · modality {ok_mod}/{n} · api_served {ok_api}/{n}"
    (HERE / "results.md").write_text(f"# Spike 001 results\n\n{summary}\n\n{table}\n")
    print(summary)
    print(table)


if __name__ == "__main__":
    main()
