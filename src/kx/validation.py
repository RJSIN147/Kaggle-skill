"""Validation status: can the CV scheme be trusted to predict the leaderboard?

``control/state.json["validation"]``:
  status     unchecked | ok | suspect
  reasons    why it is suspect (readable lines)
  source     what opened it (``diagnose exp-NNN`` / ``lb rank inversion``)
  signature  the event that opened it; an acknowledged signature never re-opens it
  reference  {exp_id, fold_hash}: the adopted CV scheme (``kx validation ok --scheme``)
  history    every change, with the note that closed it

Warn-only by design (the user's choice): kx never refuses work because validation is
suspect. It warns on new / run / strategy / submit and steers next_action to a diagnosis
or a CV-scheme check (``kx new --cv-check``).
"""

from __future__ import annotations

from pathlib import Path

from kx import envelope as E
from kx import workspace
from kx.util import KxError, read_json, utc_now

STATUSES = ("unchecked", "ok", "suspect")


def get(ws: Path) -> dict:
    v = dict(workspace.load_state(ws).get("validation") or {})
    v.setdefault("status", "unchecked")
    v.setdefault("reasons", [])
    v.setdefault("acknowledged", [])
    v.setdefault("history", [])
    v.setdefault("reference", None)
    return v


def _save(ws: Path, v: dict) -> None:
    state = workspace.load_state(ws)
    state["validation"] = v
    workspace.save_state(ws, state)


def reference_hash(ws: Path) -> str | None:
    return (get(ws).get("reference") or {}).get("fold_hash")


def open_suspect(ws: Path, source: str, reasons: list[str], signature: str) -> bool:
    """Mark validation suspect, unless this exact event was already acknowledged."""
    v = get(ws)
    if signature in v["acknowledged"] or (v["status"] == "suspect"
                                          and v.get("signature") == signature):
        return False
    v.update({"status": "suspect", "reasons": reasons, "source": source,
              "signature": signature, "since": utc_now()})
    v["history"].append({"at": utc_now(), "event": "suspect", "source": source,
                         "reasons": reasons})
    _save(ws, v)
    return True


def after_diagnostic(ws: Path, exp_id: str, found: list[dict]) -> dict:
    """A diagnostic's high findings make validation suspect; a clean one makes it ok
    (unless an unexplained leaderboard inversion is what made it suspect)."""
    high = [f["message"] for f in found if f["severity"] == "high"]
    if high:
        open_suspect(ws, f"diagnose {exp_id}", high, f"diagnose:{exp_id}")
    else:
        v = get(ws)
        if v["status"] == "unchecked" or str(v.get("source", "")).startswith("diagnose"):
            v.update({"status": "ok", "reasons": [], "source": f"diagnose {exp_id}",
                      "signature": f"diagnose:{exp_id}"})
            v["history"].append({"at": utc_now(), "event": "ok", "source": f"diagnose {exp_id}",
                                 "note": "no high-severity finding"})
            _save(ws, v)
    return get(ws)


def _acknowledged_pairs(v: dict) -> set[str]:
    out: set[str] = set()
    for sig in v["acknowledged"]:
        if sig.startswith("lb:"):
            out |= set(sig[3:].split(";"))
    return out


def after_lb(ws: Path, inversions: list[tuple]) -> bool:
    """A CV-vs-LB rank inversion makes validation suspect. Each inverted pair counts once:
    a pair acknowledged with ``kx validation ok`` never re-opens it, so only a new pair can."""
    acked = _acknowledged_pairs(get(ws))
    new = [(a, b) for a, b, *_ in inversions if f"{a}>{b}" not in acked]
    if not new:
        return False
    pairs = sorted({f"{a}>{b}" for a, b in new})
    reasons = [f"{a} has the better CV but {b} the better leaderboard score (same folds)"
               for a, b in dict.fromkeys(new)]
    return open_suspect(ws, "lb rank inversion", reasons, "lb:" + ";".join(pairs))


STEER = ("Diagnose before trusting CV again: `kx diagnose` if there is no diagnosis yet, or "
         "rerun the best model under a different CV scheme with `kx new --cv-check --parent "
         "<exp> --idea '...' --hypothesis '...'` (change only assign_folds). Then record the "
         "decision with `kx validation ok --note '...' [--scheme <exp>]`.")


def warnings(ws: Path) -> list[str]:
    v = get(ws)
    if v["status"] != "suspect":
        return []
    first = (v["reasons"][0] if v["reasons"] else "").rstrip(".")
    more = f" (+{len(v['reasons']) - 1} more)" if len(v["reasons"]) > 1 else ""
    return [f"validation is SUSPECT ({v.get('source')}): {first}{more}. CV may not predict the "
            "leaderboard. " + STEER]


def body(ws: Path) -> str:
    """The strategy.md section."""
    v = get(ws)
    lines = [f"Status: **{v['status']}**" + (f" ({v.get('source')})" if v.get("source") else "")]
    lines += [f"- {r}" for r in v["reasons"]]
    ref = v.get("reference")
    if ref:
        lines.append(f"Reference CV scheme: the folds of {ref['exp_id']} (best is ranked within "
                     "this scheme only).")
    notes = [h for h in v["history"] if h.get("note")]
    if notes:
        lines += ["", "History:"] + [f"- {h['at']}: {h['note']}" for h in notes[-5:]]
    if v["status"] == "unchecked":
        lines.append("_Not checked yet: run `kx diagnose`._")
    return "\n".join(lines)


def cmd_validation(ws: Path, args, adapter) -> dict:
    workspace.require_workspace(ws)
    if args.action == "show":
        v = get(ws)
        return E.make("validation", "ok", f"validation is {v['status']}", data={"validation": v},
                      warnings=warnings(ws),
                      next_action=E.run("kx status") if v["status"] != "suspect"
                      else E.run("kx diagnose", STEER))
    if not (args.note or "").strip():
        raise KxError("invalid", "say why validation can be trusted now: --note '...'",
                      errors=["note_required"])
    v = get(ws)
    ref = None
    if args.scheme:
        exp_dir = workspace.exp_dir(ws, args.scheme)
        mp = exp_dir / "meta.json"
        meta = read_json(mp) if mp.exists() else {}
        if meta.get("status") != "SUCCESS" or not meta.get("fold_hash"):
            raise KxError("invalid", f"{args.scheme} is not a recorded SUCCESS with out-of-fold "
                                     "predictions, so its folds cannot be the reference",
                          errors=["bad_scheme"])
        ref = {"exp_id": args.scheme, "fold_hash": meta["fold_hash"]}
        v["reference"] = ref
    if v.get("signature") and v["signature"] not in v["acknowledged"]:
        v["acknowledged"].append(v["signature"])
    v.update({"status": "ok", "reasons": [], "source": "user decision"})
    v["history"].append({"at": utc_now(), "event": "ok", "note": args.note.strip(),
                         **({"reference": args.scheme} if ref else {})})
    _save(ws, v)
    return E.make("validation", "ok", "validation marked ok"
                  + (f"; CV scheme of {args.scheme} is the reference" if ref else ""),
                  data={"validation": get(ws)},
                  next_action=E.run("kx new --idea '...' --hypothesis '...'"))
