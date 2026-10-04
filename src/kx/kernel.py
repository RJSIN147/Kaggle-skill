"""Script kernels: metadata, push with read-back, bounded poll, safe pull.

Facts this relies on (kaggle 2.2.3, live-verified in the spikes):
* status/output always act on the latest kernel version, so the version is
  read back and checked before outputs are trusted;
* a push can return no version number: read it back, never guess;
* poll status is the KernelWorkerStatus enum name; CANCEL_REQUESTED is still
  in flight, CANCEL_ACKNOWLEDGED is how a runtime-limit stop ends.
"""

from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path

from kx.adapter import safe_join
from kx.util import KxError, utc_now, write_json

TERMINAL = {"COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED"}
IN_FLIGHT = {"QUEUED", "RUNNING", "NEW_SCRIPT", "CANCEL_REQUESTED"}

BASE_DELAY = 10.0
MAX_DELAY = 60.0
MAX_CONSECUTIVE_ERRORS = 5
TITLE_MAX = 50
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def kernel_slug(comp_slug: str, workspace_id: str, exp_id: str, suffix: str = "") -> str:
    """kx-<comp>-<wsid>-<exp>[-suffix], lowercase, <= 50 chars (longer titles 500)."""
    tail = f"-{workspace_id}-{exp_id}" + (f"-{suffix}" if suffix else "")
    head = re.sub(r"[^a-z0-9-]+", "-", f"kx-{comp_slug.lower()}").strip("-")
    head = head[: TITLE_MAX - len(tail)].rstrip("-")
    return f"{head}{tail}"


def build_metadata(owner: str, slug: str, spec: dict, profile: dict) -> dict:
    if not _USERNAME_RE.match(owner or ""):
        raise KxError("error", "the Kaggle username looks invalid", errors=["bad_username"])
    rt = spec["runtime"]
    gpu = rt["accelerator"] != "cpu"
    src = spec.get("sources") or {}
    comp = profile["slug"] if profile else (src.get("competition") or "").lower()
    return {
        "id": f"{owner}/{slug}",
        "title": slug,
        "code_file": spec.get("code_file", "train.py"),
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": gpu,
        "enable_tpu": False,
        "enable_internet": bool(rt.get("internet", False)),
        "competition_sources": [comp] if comp else [],
        "dataset_sources": list(src.get("datasets") or []),
        "kernel_sources": list(src.get("kernels") or []),
        "model_sources": list(src.get("models") or []),
        **({"docker_image": rt["docker_image"]} if rt.get("docker_image") else {}),
    }


def push_checked(adapter, meta: dict, code_text: str, limit_s: int) -> dict:
    """Push, then fail closed on any error or server-flag mismatch. Returns read-back facts.
    A refusal raised after Kaggle answered carries ``answered = True``: that push did not
    leave a usable version, so the caller may push again. Anything else (a timeout, a
    dropped connection) may have landed and must be read back first."""
    resp = adapter.push(meta, code_text, limit_s) or {}
    try:
        return _check_push(adapter, meta, resp)
    except KxError as exc:
        exc.answered = True
        raise


def _check_push(adapter, meta: dict, resp: dict) -> dict:
    err = str(resp.get("error") or "")
    if "accept this competition's rules" in err:
        # Classified by pattern only; the server text itself is quarantined.
        comps = meta.get("competition_sources") or ["<competition>"]
        raise KxError("needs_user", "the user must accept the competition's rules before a kernel "
                                    "can mount its data", errors=["rules_not_accepted"],
                      quarantine=err,
                      next_action={"kind": "ask_user",
                                   "instruction": "Ask the user to open https://www.kaggle.com/"
                                                  f"competitions/{comps[0]}/rules and accept the "
                                                  "rules (a browser step), then say when done.",
                                   "then": "re-run the same kx run command"})
    if "gpu session" in err.lower():
        raise KxError("needs_user", f"Kaggle allows at most {GPU_SESSION_CAP} GPU sessions at "
                      "once and that many are running", errors=["gpu_session_limit"],
                      quarantine=err,
                      next_action={"kind": "ask_user",
                                   "instruction": "Tell the user Kaggle's GPU session cap is "
                                                  "reached; wait for a running GPU kernel to "
                                                  "finish (or stop one in the browser).",
                                   "then": "re-run the same kx run command"})
    if "quota" in err.lower():
        raise KxError("needs_user", "Kaggle refused the push: the accelerator quota is used up",
                      errors=["accelerator_quota"], quarantine=err,
                      next_action={"kind": "ask_user",
                                   "instruction": "Tell the user the weekly GPU quota is used "
                                                  "up; run on CPU (--accelerator cpu) or wait "
                                                  "for the refresh.",
                                   "then": "re-run the same kx run command"})
    if resp.get("error"):
        raise KxError("error", "Kaggle rejected the kernel push (server message quarantined "
                      "in control/raw/last-error.txt)", errors=["push_error"],
                      quarantine=str(resp.get("error")))
    bad = []
    for key in ("invalid_competition_sources", "invalid_dataset_sources",
                "invalid_kernel_sources", "invalid_model_sources", "invalid_tags"):
        bad += list(resp.get(key) or [])
    if bad:
        raise KxError("invalid", "Kaggle says some sources are invalid", errors=["invalid_sources"],
                      data={"invalid_sources": bad})
    return verify_pushed(adapter, meta, resp.get("version_number"))


def verify_pushed(adapter, meta: dict, version_hint: int | None = None) -> dict:
    """Read the pushed kernel back and fail closed on a server-flag mismatch."""
    owner, slug = meta["id"].split("/", 1)
    md = adapter.get_kernel(owner, slug)
    version = version_hint or md.get("current_version_number")
    if not isinstance(version, int):
        raise KxError("error", "could not read back the pushed kernel version",
                      errors=["version_unknown"])
    if md.get("is_private") is not True:
        raise KxError("error", "the pushed kernel is not private", errors=["server_flags_mismatch"])
    if bool(md.get("enable_internet")) != bool(meta["enable_internet"]):
        raise KxError("error", "the pushed kernel's internet setting differs from the declaration",
                      errors=["server_flags_mismatch"])
    if meta.get("docker_image") and md.get("docker_image") != meta["docker_image"]:
        raise KxError("error", "Kaggle did not pin the requested docker image",
                      errors=["server_flags_mismatch"],
                      data={"requested": meta["docker_image"], "got": md.get("docker_image")})
    return {"kernel_version": version, "is_private": md.get("is_private"),
            "enable_internet": md.get("enable_internet"), "docker_image": md.get("docker_image"),
            "machine_shape": clean(md.get("machine_shape"))}


def clean(value):
    """Kaggle renders an unset enum as the string "None"; store a real null."""
    return None if value in (None, "", "None") else value


def poll(status_fn, *, budget_s: float, now=time.monotonic, sleep=time.sleep,
         rng: random.Random | None = None, max_errors: int = MAX_CONSECUTIVE_ERRORS) -> dict:
    """Poll until terminal, budget expiry (detach, never cancel) or repeated errors.

    ``status_fn()`` returns (status_name, failure_message) or raises. Each sleep is
    clamped to the remaining budget so the call never overruns its caller's timeout.
    """
    rng = rng or random.Random()
    start = now()
    errors = attempt = 0
    last = None
    while True:
        try:
            name, failure = status_fn()
        except KxError:
            name, failure = None, None
        if name is None:
            errors += 1
            if errors >= max_errors:
                return {"outcome": "transient", "status": last}
        else:
            errors = 0
            last = name
            if name in TERMINAL:
                return {"outcome": "terminal", "status": name, "failure_message": failure}
        remaining = budget_s - (now() - start)
        if remaining <= 0:
            return {"outcome": "budget", "status": last}
        delay = rng.uniform(0.5, min(BASE_DELAY * (2 ** attempt), MAX_DELAY))
        sleep(max(0.0, min(delay, remaining)))
        attempt += 1


def pull(adapter, owner: str, slug: str, out: Path) -> dict:
    """Download every output file into out/ (safe paths only) and the log."""
    out.mkdir(parents=True, exist_ok=True)
    listing = adapter.list_output(owner, slug)
    files, refused = [], []
    for f in listing.get("files") or []:
        name = f.get("file_name")
        try:
            dest = safe_join(out, name)
        except ValueError:
            refused.append(str(name)[:80])
            continue
        adapter.download(f["url"], dest)
        files.append(str(dest.relative_to(out.resolve())))
    log_text = listing.get("log")
    log_file = None
    if isinstance(log_text, str):
        (out / "kernel.log").write_text(log_text)
        log_file = "kernel.log"
    return {"files": files, "refused": refused, "log_text": log_text, "log_file": log_file}


GPU_SESSION_CAP = 2  # Kaggle runs at most 2 GPU batch sessions at once (seen live 2026-10)


def gpu_check(ws: Path, adapter, spec: dict) -> tuple[dict, list[str]]:
    """Before a GPU push: the account's weekly GPU quota and this workspace's running GPU
    kernels. Informs and warns; Kaggle itself enforces both limits."""
    warnings: list[str] = []
    running = []
    for rp in sorted((ws / "experiments").glob("exp-*/kernel_run.json")):
        try:
            r = json.loads(rp.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if r.get("accelerator", "cpu") != "cpu" and not r.get("recorded") \
                and r.get("status") not in TERMINAL and rp.parent.name != spec["exp_id"]:
            running.append(rp.parent.name)
    info: dict = {"running_gpu_kernels": running}
    if len(running) >= GPU_SESSION_CAP:
        warnings.append(f"Kaggle runs at most {GPU_SESSION_CAP} GPU sessions at once and "
                        f"{', '.join(running)} may still be running; this push may be refused. "
                        "Finish or poll those first (`kx run <exp>`).")
    try:
        q = adapter.accelerator_quota()
    except KxError:
        return info, warnings + ["could not read the GPU quota from Kaggle"]
    g = q.get("gpu") or {}
    if not all(isinstance(g.get(k), (int, float)) for k in ("used_s", "reserved_s", "allowed_s")):
        return info, warnings
    left = g["allowed_s"] - g["used_s"] - g["reserved_s"]
    info |= {"gpu_hours_used": round(g["used_s"] / 3600, 1),
             "gpu_hours_reserved": round(g["reserved_s"] / 3600, 1),
             "gpu_hours_allowed": round(g["allowed_s"] / 3600, 1),
             "gpu_hours_left": round(left / 3600, 1), "quota_refresh": q.get("refresh")}
    limit = spec["runtime"]["limit_s"]
    if left < limit:
        warnings.append(f"GPU quota: {left / 3600:.1f} h left this week (refresh "
                        f"{q.get('refresh')}), but this run may take up to {limit / 3600:.1f} h; "
                        "Kaggle stops a kernel when the quota runs out")
    return info, warnings


def intent_record(meta: dict, spec: dict, prev_version: int | None, git_commit: str) -> dict:
    """Saved before a push. If kx is interrupted mid-push, the next ``kx run`` finds this
    and reads back whether the push landed (``landed_version``) instead of pushing again."""
    return {"backend": "kernel", "kernel_ref": meta["id"], "status": "PUSHING",
            "push_started": utc_now(), "prev_version": prev_version, "git_commit": git_commit,
            "accelerator": spec["runtime"]["accelerator"], "limit_s": spec["runtime"]["limit_s"],
            "recorded": False}


def landed_version(adapter, meta: dict, prev_version: int | None) -> int | None:
    """The version an interrupted push created, or None when Kaggle has no newer version
    than ``prev_version`` (the push never landed). A failed read raises: never guess."""
    owner, slug = meta["id"].split("/", 1)
    try:
        md = adapter.get_kernel(owner, slug)
    except KxError as exc:
        # Kaggle answers 403 (not 404) for a kernel that does not exist (live 2026-10-04):
        # confirm with a listing of this account's own kernels before concluding that.
        if any(e.startswith(("http_404", "http_403")) for e in exc.errors) and \
                meta["id"].lower() not in {r.lower() for r in adapter.my_kernel_refs(slug)}:
            return None
        raise
    v = md.get("current_version_number")
    if isinstance(v, int) and (prev_version is None or v > prev_version):
        return v
    return None


def new_run_record(meta: dict, spec: dict, pushed: dict, git_commit: str) -> dict:
    return {
        "backend": "kernel",
        "kernel_ref": meta["id"],
        "kernel_version": pushed["kernel_version"],
        "pushed_at": utc_now(),
        "status": "QUEUED",
        "git_commit": git_commit,
        "accelerator": spec["runtime"]["accelerator"],
        "limit_s": spec["runtime"]["limit_s"],
        "enable_internet": pushed["enable_internet"],
        "is_private": pushed["is_private"],
        "docker_image": pushed.get("docker_image"),
        "machine_shape": pushed.get("machine_shape"),
        "recorded": False,
    }


def save_run(exp_dir: Path, run: dict) -> None:
    write_json(exp_dir / "kernel_run.json", run)
