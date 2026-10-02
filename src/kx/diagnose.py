"""kx diagnose: data facts, adversarial validation and leak hints, before trusting CV.

`kx diagnose` scaffolds a ``diagnostic`` experiment from the ``diagnose`` template; `kx run`
runs it (kernel or local) like any experiment. The script writes ``output/facts.json``
(kx-facts/1); kx validates it fail-closed, derives findings with fixed thresholds
(``findings``) and publishes the facts to ``control/facts.json`` (tracked), where
`kx new --evidence facts:<path>` can cite them. A diagnostic is never ranked against
model runs, blended or submitted.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

from kx import envelope as E
from kx import experiment, templates_registry, workspace
from kx.profile import effective
from kx.util import KxError, read_json, utc_now, write_json

FACTS_FORMAT = "kx-facts/1"
METRIC_CFG = {"name": "adv_auc", "greater_is_better": False, "range": [0.0, 1.0]}
IDEA = "validation diagnosis: data facts, adversarial validation, leak checks"
HYPOTHESIS = ("train and test come from the same distribution, and a CV scheme can mirror "
              "how test differs from train")

# Thresholds for findings (kx-side, so they are testable without a kernel).
ADV_HIGH = 0.70
ADV_MEDIUM = 0.60
LEAK_SCORE = 0.98
TEST_IN_TRAIN = 0.01
TRAIN_DUPLICATES = 0.05
UNSEEN_ENTITY_OVERLAP = 0.5
SEVERITIES = ("high", "medium", "info")
EVIDENCE_MAX_CHARS = 2000


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def diagnosable(profile: dict) -> tuple[str | None, str | None]:
    """(train file, test file) at the data root, or Nones when there is no tabular pair."""
    files = [f.get("name") or "" for f in (profile.get("root_listing") or {}).get("files") or []]
    return (templates_registry._pick_file(files, "train"),
            templates_registry._pick_file(files, "test"))


def has_diagnostic(ws: Path) -> bool:
    for exp in workspace.list_experiments(ws):
        p = ws / "experiments" / exp / "experiment.json"
        try:
            if json.loads(p.read_text()).get("kind") == "diagnostic":
                return True
        except (OSError, json.JSONDecodeError):
            continue
    return False


# --------------------------------------------------------------------------- #
# facts.json: validation (the recorder's diagnostic rung)
# --------------------------------------------------------------------------- #
def read_facts(output_dir: Path) -> tuple[dict | None, str | None, dict | None]:
    """(facts, failure reason, result-like dict for meta). Fail closed on any doubt."""
    try:
        facts = json.loads((output_dir / "facts.json").read_text())
    except FileNotFoundError:
        return None, "missing_result", None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None, "schema_invalid", None
    if not isinstance(facts, dict) or facts.get("format") != FACTS_FORMAT:
        return None, "schema_invalid", None
    for key, typ in (("n_train", int), ("n_test", int), ("columns", dict), ("time", list),
                     ("entities", list), ("single_feature", list), ("duplicates", dict),
                     ("adversarial", dict)):
        if not isinstance(facts.get(key), typ) or isinstance(facts.get(key), bool):
            return None, "schema_invalid", None
    if facts["n_train"] < 1 or facts["n_test"] < 0:
        return None, "schema_invalid", None
    adv = facts["adversarial"]
    if adv.get("status") == "skipped":
        if not isinstance(adv.get("reason"), str):
            return None, "schema_invalid", None
        return facts, None, {"n_folds": None, "fold_scores": [], "cv_mean": None,
                             "cv_std": None, "predictions": None}
    if adv.get("status") != "ok":
        return None, "schema_invalid", None
    aucs, mean = adv.get("fold_aucs"), adv.get("auc_mean")
    if not isinstance(aucs, list) or len(aucs) < 2 or not all(_is_number(a) for a in aucs) \
            or not _is_number(mean):
        return None, "schema_invalid", None
    if not all(math.isfinite(a) for a in aucs) or not math.isfinite(mean):
        return None, "non_finite", None
    if not all(0.0 <= a <= 1.0 for a in aucs):
        return None, "out_of_range", None
    if abs(mean - statistics.mean(aucs)) >= 1e-6:
        return None, "schema_invalid", None
    return facts, None, {"n_folds": len(aucs), "fold_scores": aucs,
                         "cv_mean": statistics.mean(aucs), "cv_std": statistics.pstdev(aucs),
                         "predictions": None}


# --------------------------------------------------------------------------- #
# findings
# --------------------------------------------------------------------------- #
def _f(severity: str, code: str, message: str) -> dict:
    return {"severity": severity, "code": code, "message": message}


def findings(facts: dict) -> list[dict]:
    """Readable findings from facts, most severe first. Thresholds are the constants above."""
    out: list[dict] = []
    adv = facts.get("adversarial") or {}
    if adv.get("status") == "ok":
        auc = adv["auc_mean"]
        top = ", ".join(str(t.get("column")) for t in (adv.get("top_features") or [])[:5]) or "—"
        if auc >= ADV_MEDIUM:
            out.append(_f("high" if auc >= ADV_HIGH else "medium", "adversarial_shift",
                          f"a model tells train rows from test rows (adversarial AUC {auc:.3f}); "
                          f"most telling features: {top}. Make the CV folds mirror this shift, "
                          "or drop or transform those features."))
    elif adv.get("status") == "skipped":
        out.append(_f("info", "adversarial_skipped",
                      f"adversarial validation skipped: {adv.get('reason')}"))
    for t in facts.get("time") or []:
        if t.get("relation") == "test_after_train":
            out.append(_f("high", "test_after_train",
                          f"test rows come after train in {t.get('column')} (train ends "
                          f"{t.get('train_max')}, test starts {t.get('test_min')}): use "
                          "walk-forward CV (the timeseries template), never shuffled folds."))
        elif t.get("relation") == "overlap":
            out.append(_f("info", "time_overlap",
                          f"train and test overlap in time ({t.get('column')})."))
    for e in facts.get("entities") or []:
        ov = e.get("test_overlap")
        if not _is_number(ov):
            continue
        if ov < UNSEEN_ENTITY_OVERLAP:
            out.append(_f("high", "unseen_entities",
                          f"{e.get('column')} repeats in train (~{e.get('rows_per_value', 0):.1f} "
                          f"rows per value) but {1 - ov:.0%} of test rows with a value have one "
                          f"never seen in train: group the folds by {e.get('column')} "
                          "(GroupKFold)."))
        else:
            out.append(_f("info", "shared_entities",
                          f"{ov:.0%} of test rows share a {e.get('column')} value with train; "
                          "random folds mirror that only if rows of one entity can sit in both."))
    for s in facts.get("single_feature") or []:
        if _is_number(s.get("score")) and s["score"] >= LEAK_SCORE:
            out.append(_f("high", "single_feature_leak",
                          f"{s.get('column')} alone predicts the target ({s.get('kind')} "
                          f"{s['score']:.3f}): check it for target leakage before trusting CV."))
    dup = facts.get("duplicates") or {}
    if _is_number(dup.get("test_in_train")) and dup["test_in_train"] >= TEST_IN_TRAIN:
        out.append(_f("medium", "test_rows_in_train",
                      f"{dup['test_in_train']:.1%} of test rows exactly match a train row's "
                      "features."))
    if _is_number(dup.get("train_internal")) and dup["train_internal"] >= TRAIN_DUPLICATES:
        out.append(_f("info", "train_duplicates",
                      f"{dup['train_internal']:.1%} of train rows duplicate another train row's "
                      "features: keep duplicates in the same fold."))
    return sorted(out, key=lambda f: SEVERITIES.index(f["severity"]))


def publish(ws: Path, exp_id: str, exp_dir: Path) -> list[dict]:
    """After a SUCCESS: control/facts.json (tracked) with the findings. Returns them."""
    facts, _, _ = read_facts(exp_dir / "output")
    found = findings(facts)
    write_json(workspace.control(ws) / "facts.json",
               {"from": exp_id, "published": utc_now(), "findings": found, **facts})
    return found


# --------------------------------------------------------------------------- #
# evidence references (kx new --evidence)
# --------------------------------------------------------------------------- #
def _walk(obj, path: list[str], ref: str):
    for part in path:
        if isinstance(obj, dict) and part in obj:
            obj = obj[part]
        elif isinstance(obj, list) and part.lstrip("-").isdigit() and \
                -len(obj) <= int(part) < len(obj):
            obj = obj[int(part)]
        else:
            raise KxError("invalid", f"evidence {ref!r}: no {part!r} there",
                          errors=["bad_evidence_ref"])
    return obj


def resolve_evidence(ws: Path, ref: str) -> dict:
    """{"ref", "value"}: the value read by kx, so evidence numbers are never typed."""
    kind, _, rest = (ref or "").partition(":")
    if not rest:
        raise KxError("invalid", f"evidence {ref!r} must be facts:<path>, exp-NNN:<key> or "
                                 "idea:<n>", errors=["bad_evidence_ref"])
    if kind == "facts":
        p = workspace.control(ws) / "facts.json"
        if not p.exists():
            raise KxError("invalid", "no control/facts.json yet: run `kx diagnose` first",
                          errors=["no_facts"], next_action=E.run("kx diagnose"))
        value = _walk(read_json(p), rest.split("."), ref)
    elif experiment.EXP_ID_RE.match(kind):
        mp = ws / "experiments" / kind / "meta.json"
        if not mp.exists():
            raise KxError("invalid", f"evidence {ref!r}: {kind} is not recorded",
                          errors=["bad_evidence_ref"])
        value = _walk(read_json(mp), rest.split("."), ref)
    elif kind == "idea":
        from kx import research

        n = rest.lstrip("#")
        row = next((r for r in research.read_ideas(ws) if str(r.get("n")) == n), None)
        if row is None:
            raise KxError("invalid", f"evidence {ref!r}: no research idea #{n}",
                          errors=["bad_evidence_ref"])
        value = {"idea": row.get("idea"), "source": row.get("source")}
    else:
        raise KxError("invalid", f"evidence {ref!r} must start with facts:, exp-NNN: or idea:",
                      errors=["bad_evidence_ref"])
    if len(json.dumps(value, default=str)) > EVIDENCE_MAX_CHARS:
        raise KxError("invalid", f"evidence {ref!r} is too broad: point at a single fact",
                      errors=["evidence_too_broad"])
    return {"ref": ref, "value": value}


# --------------------------------------------------------------------------- #
# kx diagnose
# --------------------------------------------------------------------------- #
def cmd_diagnose(ws: Path, args, adapter) -> dict:
    workspace.require_workspace(ws)
    profile = workspace.load_profile(ws)
    if not profile.get("confirmed"):
        raise KxError("invalid", "the competition profile is not confirmed yet",
                      errors=["profile_unconfirmed"], next_action=E.run("kx status"))
    train, test = diagnosable(profile)
    if not (train and test):
        raise KxError("invalid", "no tabular train/test files at the data root: kx diagnose "
                                 "compares a train table with a test table",
                      errors=["not_diagnosable"],
                      next_action=E.run("kx new --idea '...' --hypothesis '...'",
                                        "Continue without the diagnosis."))
    eff = effective(profile)
    exp_id = workspace.mint_exp_id(ws)
    exp_dir = ws / "experiments" / exp_id
    exp_dir.mkdir(parents=True)
    info = templates_registry.TEMPLATES["diagnose"]
    spec = experiment.draft(exp_id, utc_now(), IDEA, HYPOTHESIS, "diagnose",
                            "kx diagnose", profile["slug"],
                            limit_s=args.limit or info["default_limit_s"],
                            target="local" if args.local else "kernel", kind="diagnostic")
    spec["code_file"] = info["code_file"]
    spec["cv"] = {"n_folds": 5, "reasoning": "n/a: a diagnostic (adversarial validation uses "
                                             "its own 5 stratified folds)"}
    code = templates_registry.render("diagnose", spec, profile | {"effective": eff, "_ws": ws},
                                     workspace.load_config(ws).get("metric"))
    (exp_dir / spec["code_file"]).write_text(code)
    spec["harness_sha256"] = experiment.harness_hash(code)
    write_json(exp_dir / "experiment.json", spec)
    return E.make("diagnose", "ok", f"scaffolded diagnostic {exp_id} ({train} vs {test})",
                  data={"exp_id": exp_id, "train_file": train, "test_file": test,
                        "files": [f"experiments/{exp_id}/experiment.json",
                                  f"experiments/{exp_id}/{spec['code_file']}"]},
                  next_action=E.run(f"kx run {exp_id}",
                                    "Target, id, time and entity columns are auto-detected; "
                                    "edit only the AI BLOCK (load_tables, TIME_COL, GROUP_COLS) "
                                    "if the data needs it."))
