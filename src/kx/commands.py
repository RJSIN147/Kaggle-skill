"""The core loop commands: init, status, sync, confirm, metric, new, run, strategy.

Each ``cmd_*(ws, args, adapter)`` returns an envelope dict and never prints.
The adapter is injected (tests pass a fake), never taken from a global.
"""

from __future__ import annotations

import json
from pathlib import Path

from kx import compare, experiment, kernel, metrics, record, strategy, templates_registry, workspace
from kx import envelope as E
from kx.adapter import CredentialUnavailable
from kx.credentials import NO_CREDENTIAL_INSTRUCTIONS, detect_source, permission_warnings
from kx.ledger import read_ledger
from kx.profile import build_profile, effective
from kx.util import KxError, git_commit_paths, git_head, read_json, utc_now, write_json

DEFAULT_WAIT_S = 90


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _metric_cfg(ws: Path) -> dict | None:
    m = workspace.load_config(ws).get("metric")
    return m if isinstance(m, dict) and m.get("name") else None


def _require_metric(ws: Path, suggestion: str | None = None) -> dict:
    m = _metric_cfg(ws)
    if m is None:
        cmd = f"kx metric {suggestion}" if suggestion else "kx metric <name>"
        raise KxError("invalid", "no evaluation metric is set", errors=["metric_unset"],
                      next_action=E.run(cmd, "Confirm the metric key matches the competition's "
                                             "evaluation metric."))
    return m


def _require_confirmed(profile: dict) -> dict:
    if not profile.get("confirmed"):
        raise KxError("invalid", "the competition profile is not confirmed yet",
                      errors=["profile_unconfirmed"],
                      next_action=E.run("kx confirm", "Show the user the profile evidence "
                                                      "(kx status data.profile) and confirm or "
                                                      "correct it first."))
    eff = effective(profile)
    return eff


def _verdict_pending(exp_dir: Path) -> bool:
    v = exp_dir / "VERDICT.md"
    return not v.exists() or "_TODO" in v.read_text()


def _tried(ws: Path) -> list[str]:
    from kx import validation

    return strategy.tried_lines(read_ledger(ws), validation.reference_hash(ws))


def _profile_summary(profile: dict) -> dict:
    eff = effective(profile)
    keys = ("submission_mode", "api_served", "modality", "sample_submission", "expected_output",
            "metric", "metric_suggestion", "daily_limit", "code_only", "closed",
            "late_submissions_open", "total_bytes", "file_count", "local_feasible", "reasons")
    return {"slug": profile.get("slug"), "canonical_ref": profile.get("canonical_ref"),
            "title": (profile.get("competition") or {}).get("title"),
            "user_has_entered": (profile.get("competition") or {}).get("user_has_entered"),
            "sync_pass": profile.get("sync_pass"), "confirmed": bool(profile.get("confirmed")),
            **{k: eff.get(k) for k in keys},
            "type_guides": type_guides(eff) if profile.get("confirmed") else None}


def type_guides(eff: dict) -> list[str]:
    """The per-type guides to load for a confirmed profile (and no others)."""
    mode, modality = eff.get("submission_mode"), eff.get("modality")
    base = "references/types/"
    if mode == "agent":
        return [base + "simulation.md"]
    if mode == "writeup":
        return [base + "writeup.md"]
    if mode not in ("csv_upload", "code_kernel"):
        return [base + "other.md"]
    guides = [base + ("tabular.md" if modality == "tabular" else
                      "deep-learning.md" if modality in ("image", "text", "audio") else
                      "other.md")]
    if mode == "code_kernel":
        guides.append(base + "code-competition.md")
    return guides


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #
def cmd_init(ws: Path, args, adapter) -> dict:
    ws.mkdir(parents=True, exist_ok=True)
    if workspace.is_workspace(ws):
        workspace.require_workspace(ws)
    created = workspace.scaffold(ws)
    warnings = permission_warnings()
    src = detect_source()
    state = workspace.load_state(ws)
    competition = getattr(args, "competition", None)
    if competition:
        cfg = workspace.load_config(ws)
        cfg["competition"] = competition.lower()
        workspace.save_config(ws, cfg)

    if src["source"] is None:
        state["credentials"] = {"status": "MISSING", "checked_at": utc_now()}
        workspace.save_state(ws, state)
        return E.make("init", "needs_user", "workspace ready; no Kaggle credential found",
                      data={"created": created, "credential": src}, warnings=warnings,
                      errors=["no_credential"],
                      next_action=E.ask_user(NO_CREDENTIAL_INSTRUCTIONS, then="kx init"))
    try:
        username = adapter.validate()
    except CredentialUnavailable:
        state["credentials"] = {"status": "INVALID", "source": src["source"], "checked_at": utc_now()}
        workspace.save_state(ws, state)
        return E.make("init", "needs_user", "the Kaggle credential was rejected",
                      data={"created": created, "credential": src}, warnings=warnings,
                      errors=["credential_invalid"],
                      next_action=E.ask_user("The credential at " + str(src["source"]) +
                                             " did not authenticate. " + NO_CREDENTIAL_INSTRUCTIONS,
                                             then="kx init"))
    state["credentials"] = {"status": "VALIDATED", "username": username, "source": src["source"],
                            "type": src["type"], "validated_at": utc_now()}
    workspace.save_state(ws, state)
    if not git_head(ws):
        git_commit_paths(ws, "kx: scaffold workspace",
                         [".gitignore", ".githooks/pre-commit", "README.md", "strategy.md",
                          "control/config.json", "control/state.json", "control/ledger.jsonl"])
    comp = workspace.load_config(ws).get("competition")
    na = (E.run(f"kx sync {comp}") if comp else
          E.ask_user("Ask the user which Kaggle competition to work on (its URL slug).",
                     then="kx sync <competition>"))
    return E.make("init", "ok", f"workspace ready; credential validated for {username}",
                  data={"created": created, "credential": src, "username": username},
                  warnings=warnings, next_action=na)


# --------------------------------------------------------------------------- #
# sync
# --------------------------------------------------------------------------- #
def cmd_sync(ws: Path, args, adapter) -> dict:
    workspace.require_workspace(ws)
    cfg = workspace.load_config(ws)
    slug = (getattr(args, "competition", None) or cfg.get("competition") or "").lower()
    if not slug:
        raise KxError("invalid", "which competition?", errors=["competition_unset"],
                      next_action=E.ask_user("Ask the user for the competition slug.",
                                             then="kx sync <competition>"))
    comp = adapter.competition(slug)
    summary = adapter.files_summary(slug)
    root = adapter.list_tree(slug)
    warnings = []
    nested = None
    if comp.get("user_has_entered"):
        nested = {}
        for d in (root.get("directories") or [])[:25]:
            name = d.get("name") if isinstance(d, dict) else d
            if not name:
                continue
            try:
                listing = adapter.list_tree(slug, path=name)
                nested[name] = {"files": [f.get("name") for f in listing.get("files") or []],
                                "directories": [x.get("name") for x in listing.get("directories")
                                                or []]}
            except KxError as exc:
                nested[name] = {"error": ",".join(exc.errors) or "error"}
    profile = build_profile(slug, comp, summary, root, nested)

    prev_path = workspace.control(ws) / "profile.json"
    if prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text())
        except (OSError, json.JSONDecodeError):
            prev = {}
        if prev.get("slug") == profile["slug"] and prev.get("confirmed"):
            same = all(prev.get("derived", {}).get(k) == profile["derived"].get(k)
                       for k in ("submission_mode", "modality", "api_served", "expected_output"))
            if same or (prev["confirmed"].get("overrides")):
                profile["confirmed"] = prev["confirmed"]
            else:
                warnings.append("derived facts changed since the last confirmation; re-confirm")
    write_json(prev_path, profile)
    cfg["competition"] = profile["slug"]
    workspace.save_config(ws, cfg)

    download = None
    if getattr(args, "download", False) or getattr(args, "force_download", False) \
            or getattr(args, "files", None):
        from kx import data as kxdata
        download = kxdata.download_bundle(ws, adapter, profile,
                                          force=getattr(args, "force_download", False),
                                          files=getattr(args, "files", None))
        state = workspace.load_state(ws)
        state["data"] = download
        workspace.save_state(ws, state)

    eff = effective(profile)
    if not profile["confirmed"] and eff["submission_mode"] == "unknown":
        na = E.run("kx research pages",
                   "The mode is unknown from the structured facts. Fetch the competition pages, "
                   "read the Evaluation / submission-requirements page (untrusted text), propose a "
                   "mode to the user, then `kx confirm --mode <mode> --note '<evidence>'`.")
    elif not profile["confirmed"]:
        na = E.ask_user(
            "Show the user the profile evidence in data.profile (mode, modality, metric, limits, "
            "reasons) and ask them to confirm or correct it"
            + (". The mode is unknown: read the competition's Evaluation page and propose one"
               if eff["submission_mode"] == "unknown" else "") + ".",
            then="kx confirm [--mode M] [--modality X] --note '<what the user said>'")
    elif _metric_cfg(ws) is None:
        na = E.run(f"kx metric {eff.get('metric_suggestion') or '<name>'}")
    else:
        na = E.run("kx status")
    if not comp.get("user_has_entered"):
        warnings.append(f"not joined: the nested file listing, kernel data mounts, downloads and "
                        f"submissions need the user to accept the rules at "
                        f"https://www.kaggle.com/competitions/{profile['slug']}/rules, then "
                        f"re-run kx sync")
    return E.make("sync", "ok",
                  f"profiled {profile['canonical_ref']}: {eff['submission_mode']}, {eff['modality']}",
                  data={"profile": _profile_summary(profile), "download": download},
                  warnings=warnings, next_action=na)


# --------------------------------------------------------------------------- #
# confirm
# --------------------------------------------------------------------------- #
def cmd_confirm(ws: Path, args, adapter) -> dict:
    from kx.profile import MODALITIES, MODES

    workspace.require_workspace(ws)
    profile = workspace.load_profile(ws)
    overrides = {}
    if getattr(args, "mode", None):
        if args.mode not in MODES:
            raise KxError("invalid", f"mode must be one of {MODES}", errors=["bad_mode"])
        overrides["submission_mode"] = args.mode
    if getattr(args, "modality", None):
        if args.modality not in MODALITIES:
            raise KxError("invalid", f"modality must be one of {MODALITIES}", errors=["bad_modality"])
        overrides["modality"] = args.modality
    if getattr(args, "expected_output", None):
        overrides["expected_output"] = args.expected_output
    eff = dict(profile["derived"]) | overrides
    if eff["submission_mode"] == "unknown":
        raise KxError("invalid", "the submission mode is unknown; it must be set before confirming",
                      errors=["mode_unknown"],
                      next_action=E.ask_user("Read the competition's Evaluation / submission page, "
                                             "propose a mode to the user, then confirm it.",
                                             then="kx confirm --mode <mode> --note '<evidence>'"))
    if not getattr(args, "note", None):
        raise KxError("invalid", "record what the user confirmed with --note",
                      errors=["note_required"])
    profile["confirmed"] = {"at": utc_now(), "by": "user", "overrides": overrides,
                            "note": args.note}
    write_json(workspace.control(ws) / "profile.json", profile)
    tmpl, why = templates_registry.select(eff)
    if eff["submission_mode"] == "writeup":
        na = E.run("kx submit --writeup", "Writeup competitions get a drafting checklist.")
    elif tmpl is None:
        na = E.ask_user(f"kx has no experiment template here ({why}). Follow the type guide and "
                        "agree the approach with the user; kx cannot run or submit this type.")
    elif _metric_cfg(ws) is None and templates_registry.TEMPLATES[tmpl].get("needs_metric"):
        na = E.run(f"kx metric {eff.get('metric_suggestion') or '<name>'}",
                   "Confirm the metric key matches the evaluation metric "
                   f"({eff.get('metric')!r}); use `kx metric custom` when none fits.")
    else:
        na = E.run("kx new --idea '...' --hypothesis '...'")
    guides = type_guides(eff)
    na["instruction"] = (f"First read {', '.join(guides)} (under the skill dir) and no other type "
                         "guide. " + na.get("instruction", "")).strip()
    return E.make("confirm", "ok", f"profile confirmed: {eff['submission_mode']}, {eff['modality']}",
                  data={"profile": _profile_summary(profile), "template": tmpl,
                        "template_reason": why, "type_guides": guides}, next_action=na)


# --------------------------------------------------------------------------- #
# metric
# --------------------------------------------------------------------------- #
def cmd_metric(ws: Path, args, adapter) -> dict:
    workspace.require_workspace(ws)
    name = args.name
    if name not in metrics.REGISTRY:
        raise KxError("invalid", f"unknown metric {name!r}", errors=["unknown_metric"],
                      data={"supported": list(metrics.SUPPORTED)})
    reg = metrics.REGISTRY[name]
    gib = reg["greater_is_better"]
    if args.direction:
        gib = args.direction == "higher"
    if gib is None:
        raise KxError("invalid", "a custom metric needs --direction higher|lower",
                      errors=["direction_required"])
    lo, hi = reg["range"]
    if args.range:
        lo, hi = args.range
    ptype = args.prediction_type or reg["prediction_type"] or "raw"
    cfg = workspace.load_config(ws)
    host = (cfg.get("metric") or {}).get("host_metric")
    cfg["metric"] = {"name": name, "greater_is_better": gib, "prediction_type": ptype,
                     **({"host_metric": host} if host else {}),
                     "range": [None if lo == float("-inf") else lo,
                               None if hi == float("inf") else hi],
                     "set_at": utc_now()}
    workspace.save_config(ws, cfg)
    na = E.run("kx new --idea '...' --hypothesis '...'")
    from kx import diagnose

    if not diagnose.has_diagnostic(ws) and all(diagnose.diagnosable(workspace.load_profile(ws))):
        na = E.run("kx diagnose", "Before the first experiment: check how test differs from "
                                  "train (adversarial validation, time, entities, leaks) so the "
                                  "CV scheme mirrors it.")
    return E.make("metric", "ok", f"metric set to {name} ({'higher' if gib else 'lower'} is better)",
                  data={"metric": cfg["metric"]}, next_action=na)


# --------------------------------------------------------------------------- #
# new
# --------------------------------------------------------------------------- #
def _pick_parent(ws: Path, args, metric_cfg: dict | None) -> tuple[str | None, str]:
    """(parent exp id or None, why): --parent, else the --after upstream, else the best run."""
    want = getattr(args, "parent", None)
    if want:
        if want.lower() == "none":
            return None, "--parent none: a fresh baseline"
        workspace.exp_dir(ws, want)  # refuses a bad or missing id
        return want, "--parent"
    if args.after:
        return args.after[0], "the --after upstream"
    from kx import validation

    gib = bool((metric_cfg or {}).get("greater_is_better", True))
    best = strategy.best_row(read_ledger(ws), gib, validation.reference_hash(ws))
    if best:
        return best["exp_id"], "default: the current best"
    return None, "no recorded run yet: a baseline"


def _expected_effect(args, parent: str | None, template: str) -> dict | None:
    """The pre-registered prediction; required whenever there is a parent to compare with."""
    direction = getattr(args, "expect", None)
    delta = getattr(args, "expect_delta", None)
    if direction is None and parent and template in ("deep-infer", "inference"):
        direction = "same"  # an inference stage inherits its upstream's CV
    if direction is None and getattr(args, "cv_check", False):
        return None  # another CV scheme: the scores are not comparable fold by fold
    if direction is None:
        if parent:
            raise KxError("invalid", f"pre-register a prediction: how will this compare with "
                          f"{parent}? Pass --expect better|worse|same (or --parent none)",
                          errors=["expect_required"], data={"parent": parent})
        if delta is not None:
            raise KxError("invalid", "--expect-delta needs --expect", errors=["expect_required"])
        return None
    return {"direction": direction, "delta": delta}


def cmd_new(ws: Path, args, adapter) -> dict:
    workspace.require_workspace(ws)
    profile = workspace.load_profile(ws)
    eff = _require_confirmed(profile)
    picked, why = templates_registry.select(eff)
    if args.after and not args.template:
        from kx import pipeline

        up_t = pipeline.upstream_template(ws, args.after[0])
        if up_t is None:
            raise KxError("invalid", f"no upstream experiment {args.after[0]}",
                          errors=["no_such_upstream"])
        if up_t == "deep":
            picked, why = "deep-infer", f"inference stage for {args.after[0]} (deep)"
        elif up_t in ("tabular", "timeseries"):
            picked, why = "inference", f"inference stage for {args.after[0]} ({up_t})"
    cv_check_of = None
    if getattr(args, "cv_check", False):
        if args.after or args.template:
            raise KxError("invalid", "--cv-check reruns the parent's own template; drop "
                          "--after/--template", errors=["bad_cv_check"])
        cv_check_of, _ = _pick_parent(ws, args, _metric_cfg(ws))
        if cv_check_of is None:
            raise KxError("invalid", "--cv-check needs a recorded run to re-check: pass --parent",
                          errors=["cv_check_needs_parent"])
        up = read_json(ws / "experiments" / cv_check_of / "experiment.json")
        if up.get("template") not in ("tabular", "timeseries", "deep", "custom"):
            raise KxError("invalid", f"{cv_check_of} ({up.get('template')}) has no CV scheme "
                          "to re-check", errors=["bad_cv_check"])
        picked, why = up["template"], f"CV-scheme check of {cv_check_of}"
    name = args.template or picked
    reason = why
    if args.template and args.template != picked:
        if not args.template_reason:
            raise KxError("invalid", "overriding the selected template needs --template-reason",
                          errors=["template_reason_required"],
                          data={"selected": picked, "selected_reason": why})
        reason = f"AI override of {picked!r}: {args.template_reason}"
    if name is None:
        raise KxError("invalid", why, errors=["no_template"],
                      next_action=E.ask_user(
                          "This competition type has no experiment template. For writeups run "
                          "`kx submit --writeup`; otherwise discuss the approach with the user."))
    if name not in templates_registry.TEMPLATES:
        raise KxError("invalid", f"unknown template {name!r}", errors=["unknown_template"],
                      data={"templates": sorted(templates_registry.TEMPLATES)})
    if name == "diagnose":
        raise KxError("invalid", "diagnostics are scaffolded by `kx diagnose`",
                      errors=["use_kx_diagnose"], next_action=E.run("kx diagnose"))
    info = templates_registry.TEMPLATES[name]
    metric_cfg = _require_metric(ws, eff.get("metric_suggestion")) if info.get("needs_metric") \
        else _metric_cfg(ws)
    idea_row = None
    if getattr(args, "from_idea", None):
        from kx import research

        idea_row = next((r for r in research.read_ideas(ws) if r.get("n") == args.from_idea), None)
        if idea_row is None:
            raise KxError("invalid", f"no research idea #{args.from_idea}", errors=["no_such_idea"])
        args.idea = args.idea or f"{idea_row['idea']} [from {idea_row['source_type']}: " \
                                 f"{idea_row['source']}]"
    for flag in ("idea", "hypothesis"):
        if not (getattr(args, flag) or "").strip():
            raise KxError("invalid", f"--{flag} is required", errors=[f"{flag}_required"])
    parent, parent_reason = _pick_parent(ws, args, metric_cfg)
    expected = _expected_effect(args, parent, name)
    evidence = None
    if getattr(args, "evidence", None):
        from kx import diagnose

        evidence = [diagnose.resolve_evidence(ws, ref) for ref in args.evidence]

    exp_id = workspace.mint_exp_id(ws)
    exp_dir = ws / "experiments" / exp_id
    exp_dir.mkdir(parents=True)
    spec = experiment.draft(exp_id, utc_now(), args.idea.strip(), args.hypothesis.strip(), name,
                            reason, profile["slug"], n_folds=args.folds,
                            accelerator=args.accelerator or info.get("default_accelerator", "cpu"),
                            limit_s=args.limit or info.get("default_limit_s", 1800),
                            target="local" if (args.local or info.get("target") == "local")
                            else "kernel", parent=parent, expected_effect=expected)
    spec["code_file"] = info.get("code_file", "train.py")
    if evidence:
        spec["evidence"] = evidence
    if cv_check_of:
        up = read_json(ws / "experiments" / cv_check_of / "experiment.json")
        spec["kind"] = "cv_check"
        spec["runtime"] = dict(up["runtime"]) | ({"target": "local"} if args.local else {})
        spec["sources"] = dict(up["sources"])
        if up.get("local"):
            spec["local"] = dict(up["local"])
    if not info.get("needs_cv", True):
        spec["cv"] = {"n_folds": args.folds, "reasoning": "n/a: this template has no CV loop"}
    if args.local:
        spec["local"] = {"subsample": args.subsample}
    if args.after:
        spec["sources"]["kernels"] = [f"@{a}" for a in args.after]
        if name in ("deep-infer", "inference"):
            up = read_json(ws / "experiments" / args.after[0] / "experiment.json")
            spec["cv"] = {"n_folds": up["cv"]["n_folds"],
                          "reasoning": f"inherits {args.after[0]}'s CV (its OOF predictions)"}
            spec["sources"]["models"] = list(up["sources"].get("models") or [])
    for key, vals, rx in (("models", args.model, experiment._MODEL_RE),
                          ("datasets", args.dataset, experiment._DATASET_RE)):
        for v in vals or []:
            if not rx.match(v):
                raise KxError("invalid", f"--{key[:-1]} {v!r} is not a Kaggle {key[:-1]} handle",
                              errors=[f"bad_{key[:-1]}_handle"])
            if v not in spec["sources"][key]:
                spec["sources"][key].append(v)
    code = templates_registry.render(name, spec, profile | {"effective": eff, "_ws": ws}, metric_cfg)
    carry = args.after[0] if name in ("deep-infer", "inference") else cv_check_of
    if carry:
        # An inference stage must rebuild the upstream's exact model, and a CV-scheme check
        # must rerun the parent's exact model: carry its AI block over.
        up_spec = read_json(ws / "experiments" / carry / "experiment.json")
        up_code = (ws / "experiments" / carry / up_spec["code_file"]).read_text()
        code = templates_registry.copy_ai_block(up_code, code)
    (exp_dir / spec["code_file"]).write_text(code)
    spec["harness_sha256"] = experiment.harness_hash(code)
    write_json(exp_dir / "experiment.json", spec)
    if idea_row:
        from kx import research

        research.mark_idea(ws, idea_row["n"], exp_id)
    tried = _tried(ws)
    from kx import diagnose, validation

    warnings = validation.warnings(ws)
    if validation.get(ws)["status"] == "unchecked" and not diagnose.has_diagnostic(ws) \
            and all(diagnose.diagnosable(profile)):
        warnings.append("validation is unchecked: `kx diagnose` shows how test differs from "
                        "train before you trust a CV scheme")
    instruction = (f"Write the AI BLOCK in experiments/{exp_id}/{spec['code_file']} for this "
                   f"idea and replace <TODO> in experiments/{exp_id}/experiment.json "
                   "cv.reasoning with why this CV scheme mirrors the train/test split. Do not "
                   "repeat an idea in data.tried.")
    if cv_check_of:
        instruction = (f"The AI BLOCK of experiments/{exp_id}/{spec['code_file']} is "
                       f"{cv_check_of}'s. Change ONLY assign_folds to the CV scheme under test "
                       f"and write why in cv.reasoning of experiments/{exp_id}/experiment.json.")
    return E.make(
        "new", "ok", f"scaffolded {exp_id} from the {name} template",
        data={"exp_id": exp_id, "template": name, "template_reason": reason,
              "parent": parent, "parent_reason": parent_reason, "expected_effect": expected,
              "evidence": evidence,
              "files": [f"experiments/{exp_id}/experiment.json",
                        f"experiments/{exp_id}/{spec['code_file']}"],
              "tried": tried},
        warnings=warnings, next_action=E.edit(instruction, then=f"kx run {exp_id}"))


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def _load_spec(exp_dir: Path) -> dict:
    return read_json(exp_dir / "experiment.json", what=f"{exp_dir.name}/experiment.json")


def _validate_spec(ws: Path, exp_dir: Path, spec: dict, profile: dict) -> None:
    errs = experiment.validate(spec, exp_dir=exp_dir, profile=profile,
                               templates=templates_registry.TEMPLATES)
    if errs:
        raise KxError("invalid", f"{exp_dir.name}/experiment.json is invalid; nothing was pushed",
                      errors=errs,
                      next_action=E.edit(f"Fix experiments/{exp_dir.name}/experiment.json "
                                         f"(see errors).", then=f"kx run {exp_dir.name}"))


def _record_and_envelope(ws: Path, exp_dir: Path, spec: dict, run: dict, log_text,
                         warnings: list[str], data: dict) -> dict:
    tinfo = templates_registry.TEMPLATES.get(spec.get("template"), {})
    diagnostic = spec.get("kind") == "diagnostic"
    if spec.get("template") == "agent":
        metric_cfg = {"name": "win_rate", "greater_is_better": True, "range": [0.0, 1.0]}
    elif diagnostic:
        from kx import diagnose

        metric_cfg = diagnose.METRIC_CFG
    else:
        metric_cfg = _require_metric(ws)
    verdict_stub = workspace.render("VERDICT.md.tmpl", exp_id=spec["exp_id"])
    meta, ledger_warnings = record.record(ws, exp_dir, spec, run, metric_cfg, log_text,
                                          verdict_stub, tinfo.get("predictions", True))
    run["recorded"] = True
    run["record_status"] = meta["status"]
    run["resumable"] = bool(meta.get("resumable"))
    if run.get("backend") == "kernel":
        kernel.save_run(exp_dir, run)
    else:
        write_json(exp_dir / "local_run.json", run)
    warnings += ledger_warnings
    exp_id = spec["exp_id"]
    data |= {"exp_id": exp_id, "result": meta["status"], "failure_reason": meta["failure_reason"],
             "metric": meta["metric"], "cv_mean": meta["cv_mean"], "cv_std": meta["cv_std"],
             "fold_scores": meta["fold_scores"], "failure_detail": meta.get("failure_detail"),
             "subsample": meta.get("subsample"), "parent": meta.get("parent"),
             "vs_parent": meta.get("vs_parent"), "prediction": meta.get("prediction")}
    if meta["status"] == "SUCCESS":
        summary = (f"{exp_id} recorded SUCCESS: {meta['metric']} "
                   f"{strategy.fmt_score(meta['cv_mean'], meta['cv_std'])} ({meta['n_folds']} folds)")
        line = compare.summary(meta.get("vs_parent"))
        if line:
            summary += f"; {line}" + (f"; prediction {meta['prediction']}"
                                      if meta.get("prediction") else "")
    else:
        summary = f"{exp_id} recorded FAILED ({meta['failure_reason']}); no score recorded"
    if diagnostic:
        return _diagnostic_envelope(ws, exp_dir, meta, data, warnings)
    from kx import validation

    warnings += validation.warnings(ws)
    if run["resumable"]:
        data["resumable"] = True
        return E.make("run", "ok", f"{exp_id} stopped at its time budget with checkpoints saved "
                                   "(recorded FAILED runtime_limit until it finishes)",
                      data=data, warnings=warnings,
                      next_action=E.run(f"kx run {exp_id} --resume",
                                        "Continues from the saved checkpoints; the kernel mounts "
                                        "its own previous output."))
    return E.make("run", "ok", summary, data=data, warnings=warnings,
                  next_action=E.edit(
                      f"Write the verdict in experiments/{exp_id}/VERDICT.md (replace every _TODO) "
                      f"and a reasoning fragment (hypothesis queue + next action) in "
                      f"experiments/{exp_id}/reasoning.md.",
                      then=f"kx strategy --reasoning-file experiments/{exp_id}/reasoning.md"))


def _diagnostic_envelope(ws: Path, exp_dir: Path, meta: dict, data: dict,
                         warnings: list[str]) -> dict:
    from kx import diagnose

    exp_id = meta["exp_id"]
    then = f"kx strategy --reasoning-file experiments/{exp_id}/reasoning.md"
    if meta["status"] != "SUCCESS":
        return E.make("run", "ok", f"diagnostic {exp_id} recorded FAILED "
                                   f"({meta['failure_reason']}); no facts published",
                      data=data, warnings=warnings,
                      next_action=E.edit(f"Read the traceback, fix the AI BLOCK of experiments/"
                                         f"{exp_id}/diagnose.py (e.g. load_tables) and re-run "
                                         f"with --rerun, or write its VERDICT.md.", then=then))
    from kx import validation

    found = diagnose.publish(ws, exp_id, exp_dir)
    high = [f for f in found if f["severity"] == "high"]
    data["validation"] = validation.after_diagnostic(ws, exp_id, found)["status"]
    warnings += validation.warnings(ws)
    adv = ("adversarial AUC " + strategy.fmt_score(meta["cv_mean"], meta["cv_std"])
           if meta["cv_mean"] is not None else "adversarial validation skipped")
    data |= {"findings": found, "facts": "control/facts.json"}
    return E.make("run", "ok", f"diagnostic {exp_id} recorded: {adv}; {len(found)} finding(s), "
                               f"{len(high)} high", data=data, warnings=warnings,
                  next_action=E.edit(
                      f"Read data.findings (and control/facts.json). Write experiments/{exp_id}/"
                      "VERDICT.md: what each finding means for the CV scheme and the features. "
                      f"Write experiments/{exp_id}/reasoning.md with the CV scheme to use next. "
                      "Cite facts in later hypotheses with `kx new --evidence facts:<path>`.",
                      then=then))


def cmd_run(ws: Path, args, adapter) -> dict:
    workspace.require_workspace(ws)
    exp_dir = workspace.exp_dir(ws, args.exp_id)
    spec = _load_spec(exp_dir)
    profile = workspace.load_profile(ws)
    run_path = exp_dir / "kernel_run.json"
    existing = read_json(run_path) if run_path.exists() else None

    resume = getattr(args, "resume", False)
    if resume:
        if not existing or existing.get("status") != "COMPLETE" or not existing.get("resumable"):
            raise KxError("invalid", "nothing to resume: --resume continues a run that stopped "
                                     "at its time budget (recorded FAILED runtime_limit, resumable)",
                          errors=["not_resumable"], next_action=E.run("kx status"))
        args.rerun = True
    if existing and existing.get("recorded") and not args.rerun:
        return E.make("run", "ok", f"{exp_dir.name} is already recorded "
                                   f"({existing.get('record_status')}); use --rerun to run again",
                      data={"exp_id": exp_dir.name, "result": existing.get("record_status")},
                      next_action=E.run("kx status"))

    if spec.get("runtime", {}).get("target") == "local":
        from kx import local

        lr = exp_dir / "local_run.json"
        prev = read_json(lr) if lr.exists() else None
        if prev and prev.get("recorded") and not args.rerun:
            return E.make("run", "ok", f"{exp_dir.name} is already recorded "
                                       f"({prev.get('record_status')}); use --rerun to run again",
                          data={"exp_id": exp_dir.name, "result": prev.get("record_status")},
                          next_action=E.run("kx status"))
        _validate_spec(ws, exp_dir, spec, profile)
        _require_confirmed(profile)
        if spec.get("template") == "agent":
            run, log_text = local.run_agent_eval(ws, exp_dir, spec, profile,
                                                 timeout=args.wait_local)
            return _record_and_envelope(ws, exp_dir, spec, run, log_text, [],
                                        {"backend": "local", "seconds": run["seconds"]})
        if templates_registry.TEMPLATES.get(spec["template"], {}).get("needs_metric", True):
            _require_metric(ws)
        run, log_text = local.run_local(ws, exp_dir, spec, profile, timeout=args.wait_local)
        warnings = [f"local run on a {run['subsample']:g} subsample: not comparable to full-data "
                    "CV"] if run.get("subsample") else []
        return _record_and_envelope(ws, exp_dir, spec, run, log_text, warnings,
                                    {"backend": "local", "seconds": run["seconds"]})

    warnings: list[str] = []
    if existing is None or args.rerun:
        _validate_spec(ws, exp_dir, spec, profile)
        _require_confirmed(profile)
        if templates_registry.TEMPLATES.get(spec["template"], {}).get("needs_metric", True):
            _require_metric(ws)
        if spec["runtime"].get("internet") and spec.get("template") in ("inference", "deep-infer") \
                and effective(profile).get("submission_mode") == "code_kernel":
            raise KxError("invalid", "this inference stage is what gets submitted, and code "
                          "competitions rerun it with internet off",
                          errors=["internet_on_submitted_stage"],
                          next_action=E.edit(f"Set runtime.internet to false in experiments/"
                                             f"{exp_dir.name}/experiment.json; download weights "
                                             "in the training stage and save them to its output.",
                                             then=f"kx run {exp_dir.name}"))
        upstream = None
        if spec["sources"].get("kernels"):
            from kx import pipeline

            upstream = pipeline.resolve_upstream(ws, spec, adapter)
            if upstream.get("status") != "ready":
                return upstream["envelope"]
        cfg = workspace.load_config(ws)
        owner = adapter.username or (workspace.load_state(ws).get("credentials") or {}).get("username")
        if owner is None:
            adapter.load()
            owner = adapter.username
        slug = kernel.kernel_slug(profile["slug"], cfg.get("workspace_id", "ws"), exp_dir.name)
        meta = kernel.build_metadata(owner, slug, spec, profile)
        if upstream:
            meta["kernel_sources"] = upstream["kernel_sources"]
        if resume:
            # Mount this kernel's own last COMPLETE output (its checkpoints) at
            # /kaggle/input/<slug>/ so training continues instead of restarting.
            meta["kernel_sources"] = [*meta["kernel_sources"], f"{owner}/{slug}"]
        write_json(exp_dir / "kernel-metadata.json", meta)
        commit = git_commit_paths(ws, f"kx: {exp_dir.name} code before push",
                                  [f"experiments/{exp_dir.name}/experiment.json",
                                   f"experiments/{exp_dir.name}/{spec['code_file']}",
                                   f"experiments/{exp_dir.name}/kernel-metadata.json"]) \
            or git_head(ws)
        code_text = (exp_dir / spec["code_file"]).read_text()
        try:
            pushed = kernel.push_checked(adapter, meta, code_text, spec["runtime"]["limit_s"])
        except KxError as exc:
            if exc.status == "error" and exc.next_action is None:
                # A push can fail client-side after Kaggle accepted it; a retry makes the
                # next version and kx polls whichever version it reads back.
                exc.next_action = E.run(f"kx run {exp_dir.name}", "Retry once.")
            raise
        run = kernel.new_run_record(meta, spec, pushed, commit or "uncommitted")
        if upstream:
            run["upstream"] = upstream["used"]
            for u in upstream["used"]:
                warnings += u.get("warnings") or []
        if resume:
            run["resumed_from_version"] = existing["kernel_version"]
        if spec["runtime"].get("internet"):
            warnings.append("internet is ON for this kernel (declared in experiment.json)")
        kernel.save_run(exp_dir, run)
    else:
        run = existing

    owner, slug = run["kernel_ref"].split("/", 1)

    def status_fn():
        s = adapter.kernel_status(owner, slug)
        return s.get("status"), s.get("failure_message")

    outcome = kernel.poll(status_fn, budget_s=args.wait)
    run["last_polled"] = utc_now()
    if outcome["outcome"] != "terminal":
        if outcome.get("status"):
            run["status"] = outcome["status"]
        kernel.save_run(exp_dir, run)
        if outcome["outcome"] == "transient":
            return E.make("run", "error", "could not read the kernel status (repeated errors)",
                          data={"exp_id": exp_dir.name, "kernel": run["kernel_ref"]},
                          errors=["status_unavailable"],
                          next_action=E.run(f"kx run {exp_dir.name}", "Retry in a minute; the "
                                                                    "kernel is not re-pushed."))
        return E.make("run", "running",
                      f"{run['kernel_ref']} v{run['kernel_version']} is {run.get('status')}; "
                      "re-run to keep waiting (it is never re-pushed)",
                      data={"exp_id": exp_dir.name, "kernel": run["kernel_ref"],
                            "version": run["kernel_version"], "kernel_status": run.get("status")},
                      warnings=warnings,
                      next_action=E.run(f"kx run {exp_dir.name}",
                                        "Re-run to resume polling. For long kernels pass "
                                        "--wait 540 with a 600 s tool timeout, or end the session "
                                        "and run it later."))

    run["status"] = outcome["status"]
    if outcome.get("failure_message"):
        _quarantine(ws, f"kernel failure message for {run['kernel_ref']}:\n"
                        f"{outcome['failure_message']}")
        run["failure_message_quarantined"] = True
    md = adapter.get_kernel(owner, slug)
    if md.get("current_version_number") != run["kernel_version"]:
        kernel.save_run(exp_dir, run)
        raise KxError("error", "the kernel has a newer version than this run pushed; its outputs "
                               "belong to another run, so nothing was recorded",
                      errors=["version_mismatch"],
                      data={"expected": run["kernel_version"],
                            "current": md.get("current_version_number")},
                      next_action=E.run(f"kx run {exp_dir.name} --rerun"))
    run["docker_image"] = md.get("docker_image") or run.get("docker_image")
    run["machine_shape"] = kernel.clean(md.get("machine_shape")) or run.get("machine_shape")
    pulled = kernel.pull(adapter, owner, slug, exp_dir / "output")
    if pulled["refused"]:
        warnings.append(f"refused {len(pulled['refused'])} unsafe output file name(s)")
    run["log_file"] = f"experiments/{exp_dir.name}/output/kernel.log" if pulled["log_file"] else None
    run["pulled_files"] = pulled["files"]
    if run.get("upstream"):
        from kx import pipeline

        run["upstream"] = pipeline.consumed(ws, exp_dir, run)
    kernel.save_run(exp_dir, run)
    return _record_and_envelope(ws, exp_dir, spec, run, pulled["log_text"], warnings,
                                {"backend": "kernel", "kernel": run["kernel_ref"],
                                 "kernel_version": run["kernel_version"],
                                 "kernel_status": run["status"],
                                 "docker_image": run.get("docker_image")})


def _quarantine(ws: Path, text: str) -> None:
    raw = workspace.control(ws) / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "last-error.txt").write_text(text + "\n")


# --------------------------------------------------------------------------- #
# strategy
# --------------------------------------------------------------------------- #
def cmd_strategy(ws: Path, args, adapter) -> dict:
    workspace.require_workspace(ws)
    metric_cfg = _require_metric(ws)
    reasoning_path = (ws / args.reasoning_file).resolve() if not Path(args.reasoning_file) \
        .is_absolute() else Path(args.reasoning_file)
    if not reasoning_path.is_file():
        raise KxError("invalid", "the reasoning file does not exist", errors=["reasoning_missing"],
                      next_action=E.edit("Write the hypothesis queue + next action as markdown.",
                                         then=f"kx strategy --reasoning-file {args.reasoning_file}"))
    reasoning = reasoning_path.read_text()
    if not reasoning.strip():
        raise KxError("invalid", "the reasoning file is empty", errors=["reasoning_empty"])
    rows = read_ledger(ws)
    pending = [r["exp_id"] for r in rows
               if _verdict_pending(ws / "experiments" / r["exp_id"])]
    if pending:
        raise KxError("invalid", f"write the verdict first: {', '.join(pending)}",
                      errors=["verdict_pending"], data={"pending": pending},
                      next_action=E.edit(f"Replace every _TODO in experiments/{pending[0]}/VERDICT.md.",
                                         then=f"kx strategy --reasoning-file {args.reasoning_file}"))
    profile = workspace.load_profile(ws)
    sub_rows = [r for r in strategy.read_jsonl(ws / "control" / "submissions.jsonl")
                if r.get("mode") != "agent"]
    ideas = strategy.read_jsonl(ws / "research" / "ideas.jsonl")
    from kx import validation

    ref = validation.reference_hash(ws)
    strategy.write(ws, profile.get("canonical_ref") or profile.get("slug"), rows, sub_rows, ideas,
                   bool(metric_cfg["greater_is_better"]), reasoning, validation.body(ws), ref)
    state = workspace.load_state(ws)
    state["last_strategy"] = {"at": utc_now(), "n_experiments": len(rows),
                              "last_exp": rows[-1]["exp_id"] if rows else None}
    workspace.save_state(ws, state)
    paths = ["strategy.md", "control/ledger.jsonl", "control/config.json", "control/state.json",
             "control/profile.json", "control/submissions.jsonl", "control/facts.json"]
    try:
        paths.append(str(reasoning_path.relative_to(ws.resolve())))
    except ValueError:
        pass
    for r in rows:
        e = f"experiments/{r['exp_id']}"
        paths += [f"{e}/meta.json", f"{e}/VERDICT.md", f"{e}/experiment.json", f"{e}/kernel_run.json",
                  f"{e}/local_run.json", f"{e}/kernel-metadata.json", f"{e}/output/result.json",
                  f"{e}/output/kx_manifest.json"]
        spec_path = ws / e / "experiment.json"
        if spec_path.exists():
            try:
                paths.append(f"{e}/{json.loads(spec_path.read_text()).get('code_file', 'train.py')}")
            except json.JSONDecodeError:
                pass
    if (ws / "research").is_dir():
        paths += [str(p.relative_to(ws)) for p in sorted((ws / "research").glob("*.md"))]
        paths.append("research/ideas.jsonl")
    commit = git_commit_paths(ws, f"kx: strategy after {len(rows)} experiment(s)", paths)
    best = strategy.best_row(rows, bool(metric_cfg["greater_is_better"]), ref)
    warns = validation.warnings(ws)
    na = E.run("kx new --idea '...' --hypothesis '...' --expect better|worse|same",
               "Pick the top of the hypothesis queue, or stop when the user is satisfied. "
               "Submitting is `kx submit <exp>`.")
    if warns:
        na = E.run("kx new --cv-check --idea '...' --hypothesis '...'", validation.STEER)
    return E.make("strategy", "ok", f"strategy.md regenerated from {len(rows)} ledger row(s)",
                  data={"best": best, "tried": strategy.tried_lines(rows, ref), "commit": commit,
                        "validation": validation.get(ws)["status"]},
                  warnings=warns, next_action=na)


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #
def cmd_status(ws: Path, args, adapter) -> dict:
    if not workspace.is_workspace(ws):
        return E.make("status", "ok", "not a kx workspace yet", data={"workspace": False},
                      next_action=E.run("kx init"))
    workspace.require_workspace(ws)
    state = workspace.load_state(ws)
    cfg = workspace.load_config(ws)
    data = {"workspace": True, "competition": cfg.get("competition"),
            "credentials": (state.get("credentials") or {}).get("status"),
            "metric": (cfg.get("metric") or {}).get("name")}

    def out(summary, na):
        return E.make("status", "ok", summary, data=data, next_action=na)

    if data["credentials"] != "VALIDATED":
        return out("the Kaggle credential is not validated", E.run("kx init"))
    ppath = workspace.control(ws) / "profile.json"
    if not ppath.exists():
        comp = cfg.get("competition")
        return out("no competition profile yet",
                   E.run(f"kx sync {comp}") if comp else
                   E.ask_user("Ask the user which competition to work on.",
                              then="kx sync <competition>"))
    profile = read_json(ppath)
    data["profile"] = _profile_summary(profile)
    if not profile.get("confirmed"):
        return out("the profile needs the user's confirmation",
                   E.ask_user("Show the user data.profile (evidence + reasons) and ask them to "
                              "confirm or correct it.",
                              then="kx confirm [--mode M] [--modality X] --note '...'"))
    eff = effective(profile)
    tmpl, _ = templates_registry.select(eff)
    needs_metric = tmpl is None or templates_registry.TEMPLATES[tmpl].get("needs_metric")
    if cfg.get("metric") is None and needs_metric and eff["submission_mode"] != "writeup":
        return out("no metric set", E.run(f"kx metric {eff.get('metric_suggestion') or '<name>'}"))
    exps = workspace.list_experiments(ws)
    data["experiments"] = len(exps)
    data["tried"] = _tried(ws)
    from kx import subs

    sub_rows = subs.read(ws)
    proposed = [r["exp_id"] for r in sub_rows if r.get("status") == "PROPOSED"]
    unread = [r["exp_id"] for r in sub_rows if r.get("status") in
              ("HANDED_OVER", "SUBMITTING", "SUBMITTED", "SUBMIT_ERROR", "PENDING")]
    data["submissions"] = {"proposed": proposed, "awaiting_read_back": unread}
    for exp_id in reversed(exps):
        d = ws / "experiments" / exp_id
        run_path = d / "kernel_run.json"
        if (d / "meta.json").exists():
            if _verdict_pending(d):
                return out(f"{exp_id} is recorded; its verdict is pending",
                           E.edit(f"Write experiments/{exp_id}/VERDICT.md and "
                                  f"experiments/{exp_id}/reasoning.md.",
                                  then=f"kx strategy --reasoning-file experiments/{exp_id}/reasoning.md"))
            last = (state.get("last_strategy") or {}).get("last_exp")
            if last != exp_id:
                return out(f"{exp_id} has a verdict; the strategy is stale",
                           E.run(f"kx strategy --reasoning-file experiments/{exp_id}/reasoning.md"))
            break
        if run_path.exists():
            run = read_json(run_path)
            return out(f"{exp_id} was pushed ({run.get('status')}); resume it",
                       E.run(f"kx run {exp_id}", "Resumes polling; never re-pushes."))
        spec = read_json(d / "experiment.json") if (d / "experiment.json").exists() else {}
        if json.dumps(spec).find(experiment.PLACEHOLDER) >= 0:
            return out(f"{exp_id} is scaffolded; its AI block and CV reasoning are unwritten",
                       E.edit(f"Write the AI BLOCK and cv.reasoning for {exp_id}.",
                              then=f"kx run {exp_id}"))
        return out(f"{exp_id} is ready to run", E.run(f"kx run {exp_id}"))
    if unread:
        return out(f"submission(s) awaiting read-back: {', '.join(unread)}", E.run("kx lb"))
    if proposed:
        return out(f"a submission proposal for {proposed[-1]} has no answer yet",
                   E.run(f"kx submit {proposed[-1]}", "Re-propose and ask the user to confirm "
                                                      "(the old token may have expired), or "
                                                      "move on if they declined."))
    if eff["submission_mode"] == "writeup":
        return out("writeup competition", E.run("kx submit --writeup"))
    from kx import diagnose, validation

    v = validation.get(ws)
    data["validation"] = v["status"]
    if v["status"] == "suspect":
        return out("validation is suspect: diagnose before trusting CV",
                   E.run("kx new --cv-check --idea '...' --hypothesis '...'", validation.STEER))
    if v["status"] == "unchecked" and not diagnose.has_diagnostic(ws) \
            and all(diagnose.diagnosable(profile)):
        return out("ready; validation is unchecked",
                   E.run("kx diagnose", "Recommended before the first experiments; or go "
                                        "straight to `kx new`."))
    return out("ready for the next idea", E.run("kx new --idea '...' --hypothesis '...'"))
