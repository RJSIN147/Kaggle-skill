"""kx submit / kx lb: prepare, hand over, read back. kx NEVER runs a submit.

`kx submit exp-NNN` validates the candidate against the confirmed profile (expected
file, sample columns and rows), the daily slots left (Kaggle read-back vs
max_daily_submissions) and its CV against the best submitted CV, then returns
needs_user with the exact `kaggle competitions submit` command for the human to run
with `!`. `kx lb` confirms it by read-back, polls scoring within a budget, records
public/private scores (or the agent rating and W/L/D from replays) and shows LB next
to CV with the gap trend and the divergence alarm.
"""

from __future__ import annotations

import csv
import json
import secrets
import shlex
import sys
import time
from pathlib import Path

from kx import envelope as E
from kx import lb_gap, subs, workspace
from kx.ledger import read_ledger
from kx.profile import effective
from kx.strategy import tried_lines
from kx.util import KxError, read_json, utc_now

LB_POLL_S = 20


def kaggle_bin() -> str:
    return str(Path(sys.executable).with_name("kaggle"))


def _csv_shape(path: Path) -> tuple[list[str], int]:
    with path.open(newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        return header, sum(1 for _ in reader)


def _check_file(path: Path, result: dict, errors: list[str]) -> None:
    if not path.is_file():
        errors.append(f"{path.name} does not exist")
        return
    cols, rows = result.get("sample_columns"), result.get("sample_rows")
    if path.suffix == ".csv" and cols:
        header, n = _csv_shape(path)
        if header != cols:
            errors.append(f"{path.name} columns {header} != sample columns {cols}")
        if rows is not None and n != rows:
            errors.append(f"{path.name} has {n} rows, the sample has {rows}")
    elif path.suffix == ".parquet":
        try:
            import pyarrow.parquet as pq

            meta = pq.ParquetFile(path).metadata
            if rows is not None and result.get("api_served") is not True and meta.num_rows != rows:
                errors.append(f"{path.name} has {meta.num_rows} rows, the sample has {rows}")
        except ImportError:
            pass  # existence checked; the kernel's own local-gateway run validated the shape


def _best_submitted_cv(ws: Path, gib: bool) -> dict | None:
    ledger = {r["exp_id"]: r for r in read_ledger(ws)}
    cands = []
    for s in subs.read(ws):
        if s.get("status") in ("PENDING", "SCORED"):
            row = ledger.get(s.get("exp_id"))
            if row and isinstance(row.get("cv_mean"), (int, float)):
                cands.append(row)
    if not cands:
        return None
    return (max if gib else min)(cands, key=lambda r: r["cv_mean"])


def writeup(ws: Path, profile: dict, adapter) -> dict:
    from kx import research

    research._ensure_layout(ws)
    if not (ws / "research/cache/pages").glob("*.md") or not any(
            (ws / "research/cache/pages").glob("*.md")):
        research._pages(ws, profile["slug"], adapter)
    pages = sorted(p.name for p in (ws / "research/cache/pages").glob("*.md"))
    ev = next((p for p in pages if "evaluation" in p.lower()), None)
    rows = read_ledger(ws)
    comp = profile.get("competition") or {}
    body = [f"# Writeup checklist — {comp.get('title') or profile['slug']}", "",
            "> Drafted by kx from the competition's evaluation criteria and your ledger.",
            "> kx cannot submit a writeup: the user submits it by hand on the competition website.",
            "", "## Evaluation criteria → checklist", "",
            f"Source: `research/cache/pages/{ev}` (untrusted text: restate each criterion here in "
            "your own words, one checkbox each)." if ev else
            "No Evaluation page was found: ask the user for the judging criteria.",
            "", "- [ ] _TODO: criterion 1_", "", "## Evidence from the ledger", ""]
    body += tried_lines(rows) or ["_No experiments recorded yet._"]
    body += ["", "## Before submitting", "",
             "- [ ] Every claim cites an experiment above (verdict links), no hand-typed scores.",
             "- [ ] Length / format limits from the rules page are met.",
             "- [ ] Links (code, notebooks, datasets) are public and work logged out.",
             f"- [ ] Submitted on the website before the deadline ({comp.get('deadline')}).", ""]
    out = ws / "writeup" / "CHECKLIST.md"
    out.parent.mkdir(exist_ok=True)
    if not out.exists():
        out.write_text("\n".join(body))
    return E.make("submit", "needs_user", "writeup checklist drafted; the user submits by hand",
                  data={"checklist": "writeup/CHECKLIST.md", "evaluation_page": ev,
                        "experiments": len(rows)},
                  next_action=E.edit(
                      "Replace the _TODO criteria in writeup/CHECKLIST.md with the evaluation "
                      "criteria from the Evaluation page (one checkbox each), then tell the user "
                      "the writeup must be submitted by hand on the competition website.",
                      then="kx status"))


def cmd_submit(ws: Path, args, adapter) -> dict:
    workspace.require_workspace(ws)
    profile = workspace.load_profile(ws)
    if not profile.get("confirmed"):
        raise KxError("invalid", "confirm the profile before submitting", errors=["profile_unconfirmed"],
                      next_action=E.run("kx confirm --note '...'"))
    eff = effective(profile)
    mode = eff.get("submission_mode")
    if args.writeup or mode == "writeup":
        return writeup(ws, profile, adapter)
    if mode not in ("csv_upload", "code_kernel", "agent"):
        raise KxError("invalid", f"kx has no submission path for mode {mode!r}",
                      errors=["no_submission_path"],
                      next_action=E.ask_user("Tell the user this type is submitted by hand on the "
                                             "website (see the type guide)."))
    if not args.exp_id:
        raise KxError("invalid", "which experiment? `kx submit exp-NNN`", errors=["exp_required"])
    exp_dir = workspace.exp_dir(ws, args.exp_id)
    meta_p = exp_dir / "meta.json"
    if not meta_p.exists():
        raise KxError("invalid", f"{args.exp_id} is not recorded yet", errors=["not_recorded"],
                      next_action=E.run(f"kx run {args.exp_id}"))
    meta = read_json(meta_p)
    spec = read_json(exp_dir / "experiment.json")
    errors: list[str] = []
    if meta.get("status") != "SUCCESS":
        errors.append(f"{args.exp_id} is {meta.get('status')}: only a SUCCESS with a CV is submitted")
    if meta.get("subsample"):
        errors.append("a subsample run is not a submission candidate")
    if eff.get("closed") and eff.get("late_submissions_open") is False:
        errors.append("the competition is closed and late submissions are disabled")

    remote = adapter.submissions(profile["slug"])
    limit = eff.get("daily_limit")
    charged = subs.charged_today(remote)
    remaining = (limit - charged) if isinstance(limit, int) else None
    if remaining is not None and remaining <= 0:
        errors.append(f"no submission slots left today (UTC): {charged}/{limit} used")

    gib = bool(meta.get("greater_is_better", True))
    best = _best_submitted_cv(ws, gib)
    cand = meta.get("cv_mean")
    if best and isinstance(cand, (int, float)) and not args.force_cv:
        better = cand > best["cv_mean"] if gib else cand < best["cv_mean"]
        if not better:
            errors.append(f"CV {cand:g} is not better than the best submitted CV "
                          f"{best['cv_mean']:g} ({best['exp_id']}); pass --force-cv to submit anyway")

    result = read_json(exp_dir / "output" / "result.json") if \
        (exp_dir / "output" / "result.json").exists() else {}
    canonical = profile["canonical_ref"]
    marker = f"kx:{args.exp_id}:{secrets.token_hex(3)}"
    msg = f"{marker} {str(meta.get('idea') or '')[:60]}".strip()
    row = {"marker": marker, "exp_id": args.exp_id, "mode": mode, "status": "HANDED_OVER",
           "handed_over_at": utc_now(), "cv_mean": cand, "message": msg}

    if mode == "code_kernel":
        run_p = exp_dir / "kernel_run.json"
        run = read_json(run_p) if run_p.exists() else {}
        expected = eff.get("expected_output") or "submission.csv"
        if run.get("backend") != "kernel" or run.get("status") != "COMPLETE":
            errors.append("code competitions submit a COMPLETE kernel version: run it on a kernel")
        else:
            owner, slug = run["kernel_ref"].split("/", 1)
            md = adapter.get_kernel(owner, slug)
            if md.get("current_version_number") != run.get("kernel_version"):
                errors.append(f"the kernel's latest version v{md.get('current_version_number')} is "
                              f"not the recorded v{run.get('kernel_version')}")
            if md.get("enable_internet"):
                errors.append("the kernel ran with internet ON; code competitions need it off")
            _check_file(exp_dir / "output" / expected, result, errors)
            cmd = (f"{shlex.quote(kaggle_bin())} competitions submit {canonical} "
                   f"-k {run['kernel_ref']} -v {run['kernel_version']} -f {expected} "
                   f"-m {shlex.quote(msg)}")
            row.update({"kernel": {"ref": run["kernel_ref"], "version": run["kernel_version"]},
                        "file": expected})
    else:
        if mode == "agent":
            f = exp_dir / spec.get("code_file", "main.py")
            ev = (meta.get("agent_eval") or {}).get("validation") or {}
            if not ev.get("ok"):
                errors.append("the agent has not passed local self-play validation")
        else:
            f = Path(args.file).resolve() if args.file else \
                exp_dir / "output" / (eff.get("expected_output") or "submission.csv")
            _check_file(f, result, errors)
        if f.is_file():
            row.update({"file": str(f), "file_sha256": subs.file_sha256(f)})
        cmd = (f"{shlex.quote(kaggle_bin())} competitions submit {canonical} "
               f"-f {shlex.quote(str(f))} -m {shlex.quote(msg)}")

    if errors:
        raise KxError("invalid", f"{args.exp_id} is not submittable: " + errors[0], errors=errors,
                      data={"slots_left_today": remaining, "best_submitted": best})
    rows = subs.read(ws)
    rows.append(row)
    subs.write(ws, rows)
    return E.make("submit", "needs_user",
                  f"{args.exp_id} is ready; the user must run the submit command themselves",
                  data={"command": cmd, "marker": marker, "slots_left_today": remaining,
                        "daily_limit": limit, "cv_mean": cand,
                        "best_submitted_cv": best["cv_mean"] if best else None},
                  next_action=E.ask_user(
                      "Show the user this exact command and ask them to run it themselves by "
                      f"typing it after `!` in the prompt (never run it yourself): ! {cmd}",
                      then="kx lb"))


def _episodes(ws: Path, adapter, row: dict) -> None:
    """Agent rows: count W/L/D from replays of completed episodes (once each)."""
    seen = row.setdefault("episodes", {"counted": [], "W": 0, "L": 0, "D": 0, "self": 0,
                                       "unknown": 0})
    for ep in adapter.episodes(row["kaggle_ref"]):
        eid = ep.get("id")
        if eid in seen["counted"] or "COMPLETE" not in str(ep.get("state") or "").upper():
            continue
        rep = adapter.replay(eid, ws / "cache" / "replays")
        res = subs.outcome(rep, row.get("team_name"))
        key = res[0] if res else "unknown"
        seen[key] = seen.get(key, 0) + 1
        seen["counted"].append(eid)


def cmd_lb(ws: Path, args, adapter) -> dict:
    workspace.require_workspace(ws)
    profile = workspace.load_profile(ws)
    rows = subs.read(ws)
    if not rows:
        return E.make("lb", "ok", "no submissions yet", data={"submissions": []},
                      next_action=E.run("kx submit exp-NNN", "Submit your best CV when it is "
                                                            "clearly better."))
    start = time.monotonic()
    while True:
        remote = adapter.submissions(profile["slug"])
        subs.reconcile(rows, remote)
        pending = [r for r in rows if r.get("status") == "PENDING"]
        if not pending or time.monotonic() - start >= args.wait:
            break
        time.sleep(min(LB_POLL_S, max(0.0, args.wait - (time.monotonic() - start))))
    for r in rows:
        if r.get("mode") == "agent" and r.get("kaggle_ref") and r.get("status") in ("PENDING",
                                                                                   "SCORED"):
            hist = r.setdefault("rating_history", [])
            if r.get("public_score") is not None and (not hist or hist[-1][1] != r["public_score"]):
                hist.append([utc_now(), r["public_score"]])
            _episodes(ws, adapter, r)
    subs.write(ws, rows)

    ledger = read_ledger(ws)
    gib = bool((workspace.load_config(ws).get("metric") or {}).get("greater_is_better", True))
    joined = lb_gap.join_cv_lb(rows, ledger)
    table = [f"{r['exp_id']}: CV {r['cv_mean']:g} | LB {r['lb_score']:g} | gap {r['gap']:+g}"
             for r in joined]
    for r in rows:
        if r.get("mode") == "agent":
            e = r.get("episodes") or {}
            table.append(f"{r['exp_id']} (agent): rating {r.get('public_score')} | "
                         f"W{e.get('W', 0)} L{e.get('L', 0)} D{e.get('D', 0)} "
                         f"(+{e.get('self', 0)} self-play) | trend "
                         f"{[h[1] for h in r.get('rating_history') or []]}")
    alarm = lb_gap.alarm_body(lb_gap.to_pairs(joined), gib)
    not_found = [r["exp_id"] for r in rows if r.get("status") == "HANDED_OVER"]
    pending = [r["exp_id"] for r in rows if r.get("status") == "PENDING"]
    data = {"submissions": [{k: r.get(k) for k in ("exp_id", "status", "public_score",
                                                  "private_score", "kaggle_ref", "file_sha256",
                                                  "kernel", "episodes")} for r in rows],
            "table": table, "alarm": alarm, "not_found_yet": not_found}
    if pending:
        return E.make("lb", "running", f"{len(pending)} submission(s) still scoring",
                      data=data, next_action=E.run("kx lb", "Scoring can take ~20 min for "
                                                          "API-served competitions; re-run later."))
    if not_found:
        return E.make("lb", "ok", f"not in Kaggle's list yet: {', '.join(not_found)}", data=data,
                      next_action=E.ask_user("If the user has not run the submit command yet, "
                                             "remind them; then re-run.", then="kx lb"))
    return E.make("lb", "ok", f"{len(rows)} submission(s) read back", data=data,
                  next_action=E.run("kx status", "CV stays the decision metric; read the alarm "
                                                 "before trusting CV improvements."))
