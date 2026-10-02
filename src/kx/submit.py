"""kx submit / kx lb: propose, submit on the user's confirmation, read back.

`kx submit exp-NNN` validates the candidate against the confirmed profile (expected
file, sample columns and rows), the daily slots left (Kaggle read-back vs
max_daily_submissions) and its CV against the best submitted CV, then records a
PROPOSED row and returns needs_user with the details to show the user and a one-time
confirm token. Only `kx submit exp-NNN --confirm <token>`, run after the user said yes,
submits: it re-runs every check, refuses if the candidate changed (file sha256 / kernel
version) or the proposal is over an hour old, and submits once (never retried).
`kx lb` reads back by marker, polls scoring within a budget, records public/private
scores (or the agent rating and W/L/D from replays) and shows LB next to CV with the
gap trend and the divergence alarm.
"""

from __future__ import annotations

import csv
import secrets
import shlex
import time
from datetime import datetime, timezone
from pathlib import Path

from kx import envelope as E
from kx import lb_gap, subs, validation, workspace
from kx.ledger import read_ledger
from kx.profile import effective
from kx.strategy import tried_lines
from kx.util import KxError, read_json, utc_now

LB_POLL_S = 20
PROPOSAL_TTL_S = 3600
# A confirmed submit that Kaggle still does not list after this long never landed.
NOT_LANDED_S = 600
# Rows that occupy (or may occupy) a leaderboard slot: they set the CV bar to beat.
SUBMITTED_STATES = ("HANDED_OVER", "SUBMITTING", "SUBMITTED", "PENDING", "SCORED")


def _age_s(stamp) -> float:
    """Seconds since an ISO timestamp; a missing or unreadable one counts as very old."""
    t = subs.parse_utc(stamp)
    return (datetime.now(timezone.utc) - t).total_seconds() if t else float("inf")


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


def _best_submitted_cv(ws: Path, gib: bool, fold_hash: str | None = None) -> dict | None:
    """The best CV among submitted runs. With the candidate's fold_hash, only runs on the
    same folds count (runs recorded before fold hashes existed count as the same)."""
    ledger = {r["exp_id"]: r for r in read_ledger(ws)}
    cands = []
    for s in subs.read(ws):
        if s.get("status") in SUBMITTED_STATES:
            row = ledger.get(s.get("exp_id"))
            if row and isinstance(row.get("cv_mean"), (int, float)):
                cands.append(row)
    if fold_hash:
        cands = [r for r in cands if r.get("fold_hash") in (None, fold_hash)]
    if not cands:
        return None
    return (max if gib else min)(cands, key=lambda r: r["cv_mean"])


def writeup(ws: Path, profile: dict, adapter) -> dict:
    from kx import research

    research._ensure_layout(ws)
    if not any((ws / "research/cache/pages").glob("*.md")):
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
    if meta.get("kind") == "diagnostic":
        raise KxError("invalid", f"{args.exp_id} is a diagnostic, not a submission candidate",
                      errors=["not_a_candidate"])
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
    best = _best_submitted_cv(ws, gib, meta.get("fold_hash"))
    other_scheme = _best_submitted_cv(ws, gib) if best is None else None
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
    text = args.message[:200] if args.message else str(meta.get("idea") or "")[:60]
    msg = f"{marker} {text}".strip()
    row = {"marker": marker, "exp_id": args.exp_id, "mode": mode, "status": "PROPOSED",
           "proposed_at": utc_now(), "cv_mean": cand, "message": msg}
    what: list[str] = []

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
            row.update({"kernel": {"ref": run["kernel_ref"], "version": run["kernel_version"]},
                        "file": expected,
                        "fingerprint": f"{run['kernel_ref']}@v{run['kernel_version']}"})
            what = [(f"kernel {run['kernel_ref']} version {run['kernel_version']} "
                     f"(internet off), output {expected}"),
                    "Kaggle re-runs this kernel on the hidden test set to score it"]
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
            sha = subs.file_sha256(f)
            row.update({"file": str(f), "file_sha256": sha, "fingerprint": sha})
            size = f"{f.stat().st_size / 1024:.1f} KiB"
            what = [f"{'agent' if mode == 'agent' else 'file'} {f} ({size}, {sha[:19]}…)"]

    if errors:
        raise KxError("invalid", f"{args.exp_id} is not submittable: " + errors[0], errors=errors,
                      data={"slots_left_today": remaining, "best_submitted": best})
    rows = subs.read(ws)
    if args.confirm:
        return _submit_confirmed(ws, args, adapter, profile, rows, row, remote)

    rows = [r for r in rows if r.get("status") != "PROPOSED" or  # drop expired proposals
            _age_s(r.get("proposed_at")) <= PROPOSAL_TTL_S]
    row["confirm_token"] = secrets.token_hex(4)
    rows.append(row)
    subs.write(ws, rows)
    mcfg = workspace.load_config(ws).get("metric") or {}
    metric = mcfg.get("label") or mcfg.get("name") or "CV"
    confirmation = [
        f"competition: {canonical}, mode {mode}"
        + (" — LATE submission (not ranked)" if eff.get("closed") else ""),
        f"experiment: {args.exp_id} — {meta.get('idea') or ''}",
        *[f"submits: {w}" for w in what],
        f"CV: {metric} {cand:g}" if isinstance(cand, (int, float)) else "CV: none (agent)"
        if mode == "agent" else "CV: none",
        f"best submitted CV so far: {best['cv_mean']:g} ({best['exp_id']})" if best
        else (f"CV bar skipped: the best submitted CV ({other_scheme['cv_mean']:g}, "
              f"{other_scheme['exp_id']}) used a different CV scheme" if other_scheme
              else "best submitted CV so far: none"),
        *[f"WARNING: {w}" for w in validation.warnings(ws)],
        f"daily slots: {remaining} of {limit} left today (UTC); this uses one"
        if remaining is not None else "daily slots: limit unknown",
        f"message: {msg}",
    ]
    confirm_cmd = f"kx submit {args.exp_id} --confirm {row['confirm_token']}" + \
        (" --force-cv" if args.force_cv else "") + \
        (f" --file {shlex.quote(args.file)}" if args.file else "")
    return E.make("submit", "needs_user",
                  f"{args.exp_id} is ready to submit; waiting for the user's confirmation",
                  data={"confirmation": confirmation, "confirm_command": confirm_cmd,
                        "marker": marker, "slots_left_today": remaining, "daily_limit": limit,
                        "cv_mean": cand, "best_submitted_cv": best["cv_mean"] if best else None},
                  next_action=E.ask_user(
                      "Show the user every line of data.confirmation and ask whether to submit "
                      "(yes/no). Only on an explicit yes, run the `then` command; on anything "
                      "else, do not submit. Never confirm on the user's behalf.",
                      then=confirm_cmd))


def _submit_confirmed(ws: Path, args, adapter, profile: dict, rows: list[dict], fresh: dict,
                      remote: list[dict]) -> dict:
    """Submit the proposal the user confirmed: same token, same candidate, still valid."""
    prop = next((r for r in rows if r.get("exp_id") == args.exp_id
                 and r.get("status") == "PROPOSED" and r.get("confirm_token") == args.confirm),
                None)
    again = E.run(f"kx submit {args.exp_id}", "Propose again and ask the user to confirm.")
    if prop is None:
        raise KxError("invalid", f"no pending proposal for {args.exp_id} with that token "
                      "(already submitted, or never proposed)", errors=["no_proposal"],
                      next_action=again)
    if _age_s(prop.get("proposed_at")) > PROPOSAL_TTL_S:
        raise KxError("invalid", "the confirmed proposal is older than an hour",
                      errors=["proposal_expired"], next_action=again)
    if prop.get("fingerprint") != fresh.get("fingerprint"):
        raise KxError("invalid", f"{args.exp_id} changed since the user confirmed it "
                      f"({prop.get('fingerprint')} -> {fresh.get('fingerprint')})",
                      errors=["candidate_changed"], next_action=again)
    if any(prop["marker"] in str(s.get("description") or "") for s in remote):
        subs.reconcile(rows, remote)  # already on Kaggle (e.g. run by hand): never twice
        subs.write(ws, rows)
        return E.make("submit", "ok", f"{args.exp_id} is already on Kaggle; not submitted again",
                      data={"marker": prop["marker"]}, next_action=E.run("kx lb"))
    prop.pop("confirm_token", None)
    prop.update({"status": "SUBMITTING", "confirmed_at": utc_now()})
    subs.write(ws, rows)  # a crash mid-call leaves SUBMITTING: `kx lb` finds it by marker
    try:
        if prop.get("kernel"):
            resp = adapter.submit(profile["canonical_ref"], prop["message"],
                                  kernel=prop["kernel"]["ref"], version=prop["kernel"]["version"],
                                  file_name=prop["file"])
        else:
            resp = adapter.submit(profile["canonical_ref"], prop["message"], file=prop["file"])
    except KxError as exc:
        prop.update({"status": "SUBMIT_ERROR", "error": exc.summary})
        subs.write(ws, rows)
        exc.next_action = E.run("kx lb", "The request may still have reached Kaggle: read back "
                                         "before proposing again, never resubmit blind.")
        raise
    if not resp.get("ref"):
        prop.update({"status": "SUBMIT_ERROR", "error": "Kaggle returned no submission ref"})
        subs.write(ws, rows)
        raise KxError("error", "Kaggle did not accept the submission (no ref returned)",
                      errors=["submit_rejected"], quarantine=str(resp.get("message") or ""),
                      next_action=E.run("kx lb", "Read back before proposing again."))
    prop.update({"status": "SUBMITTED", "kaggle_ref": resp["ref"], "submitted_by": "kx",
                 "submitted_at": utc_now()})
    subs.write(ws, rows)
    return E.make("submit", "ok", f"{args.exp_id} submitted (Kaggle ref {resp['ref']})",
                  data={"marker": prop["marker"], "kaggle_ref": resp["ref"],
                        "message": resp.get("message")},
                  next_action=E.run("kx lb", "Read the score back (scoring can take minutes; "
                                             "code competitions re-run the kernel)."))


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
    all_rows = subs.read(ws)
    none_yet = E.make("lb", "ok", "no submissions yet", data={"submissions": []},
                      next_action=E.run("kx submit exp-NNN", "Submit your best CV when it is "
                                                            "clearly better."))
    if not all_rows:
        return none_yet
    start = time.monotonic()
    while True:
        remote = adapter.submissions(profile["slug"])
        subs.reconcile(all_rows, remote)  # a proposal run by hand is found by its marker
        pending = [r for r in all_rows if r.get("status") == "PENDING"]
        if not pending or time.monotonic() - start >= args.wait:
            break
        time.sleep(min(LB_POLL_S, max(0.0, args.wait - (time.monotonic() - start))))
    for r in all_rows:  # confirmed, but Kaggle never listed it: it did not land
        if r.get("status") in ("SUBMITTING", "SUBMIT_ERROR") and \
                _age_s(r.get("confirmed_at")) > NOT_LANDED_S:
            r["status"] = "NOT_SUBMITTED"
    rows = [r for r in all_rows if r.get("status") != "PROPOSED"]  # never confirmed
    if not rows:
        subs.write(ws, all_rows)
        return none_yet
    for r in rows:
        if r.get("mode") == "agent" and r.get("kaggle_ref") and r.get("status") in ("PENDING",
                                                                                   "SCORED"):
            hist = r.setdefault("rating_history", [])
            if r.get("public_score") is not None and (not hist or hist[-1][1] != r["public_score"]):
                hist.append([utc_now(), r["public_score"]])
            _episodes(ws, adapter, r)
    subs.write(ws, all_rows)

    ledger = read_ledger(ws)
    gib = bool((workspace.load_config(ws).get("metric") or {}).get("greater_is_better", True))
    # Agent ratings are not on the CV scale (win rate): they get their own trend line.
    joined = lb_gap.join_cv_lb([r for r in rows if r.get("mode") != "agent"], ledger)
    table = [f"{r['exp_id']}: CV {r['cv_mean']:g} | LB {r['lb_score']:g} | gap {r['gap']:+g}"
             for r in joined]
    for r in rows:
        if r.get("mode") == "agent":
            e = r.get("episodes") or {}
            table.append(f"{r['exp_id']} (agent): rating {r.get('public_score')} | "
                         f"W{e.get('W', 0)} L{e.get('L', 0)} D{e.get('D', 0)} "
                         f"(+{e.get('self', 0)} self-play) | trend "
                         f"{[h[1] for h in r.get('rating_history') or []]}")
    pairs = lb_gap.to_pairs(joined)
    alarm = lb_gap.alarm_body(pairs, gib)
    opened = validation.after_lb(ws, lb_gap.alarm_state(pairs, gib)["inversions"])
    not_found = [r["exp_id"] for r in rows
                 if r.get("status") in ("HANDED_OVER", "SUBMITTING", "SUBMITTED", "SUBMIT_ERROR")]
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
                      next_action=E.run("kx lb", "Kaggle lists a new submission within a minute "
                                                 "or two; re-run. A confirmed submit still "
                                                 "unlisted after 10 min becomes NOT_SUBMITTED "
                                                 "(it did not land; propose it again)."))
    data["validation"] = validation.get(ws)["status"]
    if opened:
        return E.make("lb", "ok", f"{len(rows)} submission(s) read back; CV and LB rankings "
                                  "disagree: validation is now suspect", data=data,
                      warnings=validation.warnings(ws),
                      next_action=E.run("kx diagnose", validation.STEER))
    return E.make("lb", "ok", f"{len(rows)} submission(s) read back", data=data,
                  warnings=validation.warnings(ws),
                  next_action=E.run("kx status", "CV stays the decision metric; read the alarm "
                                                 "before trusting CV improvements."))
