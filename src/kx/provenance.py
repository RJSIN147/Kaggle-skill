"""Third-party code: an experiment whose idea, evidence or code cites a public Kaggle notebook
is marked as containing ported code, and the user confirms it before its first push.

``experiment.json → third_party``:
  sources    the notebooks it cites (``owner/slug``)
  confirmed  null, or {"at", "note", "sources"}: what the user said, for exactly those sources

Warn-only in spirit: kx never refuses ported code. It asks once (license, the competition's
rules on external code, credit to the author) and records the answer; a child that starts
from a confirmed parent's code inherits the confirmation unless it cites something new.
"""

from __future__ import annotations

import json
import re

from kx.util import KxError, utc_now

# kaggle.com/code/<owner>/<slug> (and the older kaggle.com/<owner>/<slug> notebook URLs)
_URL = re.compile(r"kaggle\.com/(?:code/)?([A-Za-z0-9][\w-]{1,49})/([A-Za-z0-9][\w.-]{1,99})")
# a bare owner/slug: verified against Kaggle before it counts
_HANDLE = re.compile(r"(?<![\w/.@:-])([A-Za-z0-9][\w-]{1,49})/([A-Za-z0-9][\w.-]{2,99})(?![\w/])")
_NOT_OWNERS = {"competitions", "datasets", "models", "discussions", "discussion", "code",
               "c", "d", "m", "settings", "learn", "www", "docs", "kernels", "notebooks"}
MAX_LOOKUPS = 8


def url_refs(text: str) -> list[str]:
    """Notebook refs from Kaggle code URLs (no API call: a code URL is a notebook)."""
    out = []
    for owner, slug in _URL.findall(text or ""):
        if owner.lower() not in _NOT_OWNERS:
            out.append(f"{owner}/{slug.rstrip('.')}".lower())
    return list(dict.fromkeys(out))


def cited_notebooks(texts: list[str], adapter, me: str | None) -> list[str]:
    """Public notebooks of other users that ``texts`` cite: code URLs, plus bare owner/slug
    handles Kaggle confirms are public notebooks (at most MAX_LOOKUPS lookups)."""
    text = "\n".join(t for t in texts if t)
    found = url_refs(text)
    me = (me or "").lower()
    cands = []
    for owner, slug in _HANDLE.findall(_URL.sub(" ", text)):
        ref = f"{owner}/{slug.rstrip('.')}".lower()
        if owner.lower() in _NOT_OWNERS or owner.lower() == me or ref.startswith("exp-") \
                or not re.search(r"[a-z]", slug.lower()) or ref in found or ref in cands:
            continue
        cands.append(ref)
    for ref in cands[:MAX_LOOKUPS]:
        owner, slug = ref.split("/", 1)
        try:
            md = adapter.get_kernel(owner, slug)
        except KxError:
            continue  # not a notebook (or not visible): not a cited notebook
        if md and md.get("is_private") is False:
            found.append(ref)
    return [r for r in found if r.split("/", 1)[0] != me]


def merged(own: list[str], inherited: dict | None) -> dict | None:
    """The third_party block: own citations plus what the code was carried from."""
    inherited = inherited or {}
    sources = list(dict.fromkeys([*(inherited.get("sources") or []), *own]))
    if not sources:
        return None
    conf = inherited.get("confirmed")
    if conf and set(sources) <= set(conf.get("sources") or []):
        return {"sources": sources, "confirmed": conf}
    return {"sources": sources, "confirmed": None}


def combine(blocks: list[dict | None]) -> dict | None:
    """A blend's block: every member's sources; confirmed only for what members confirmed."""
    blocks = [b for b in blocks if b]
    if not blocks:
        return None
    sources = list(dict.fromkeys(s for b in blocks for s in b["sources"]))
    ok = [s for b in blocks for s in ((b.get("confirmed") or {}).get("sources") or [])]
    if set(sources) <= set(ok):
        notes = "; ".join(dict.fromkeys(b["confirmed"]["note"] for b in blocks))
        return {"sources": sources,
                "confirmed": {"at": utc_now(), "note": f"from the members: {notes}"[:500],
                              "sources": sources}}
    return {"sources": sources, "confirmed": None}


def validate(block) -> list[str]:
    if block is None:
        return []
    if not isinstance(block, dict) or not isinstance(block.get("sources"), list) or \
            not all(isinstance(s, str) and "/" in s for s in block["sources"]):
        return ["third_party must be {sources: [owner/slug, ...], confirmed: null|{...}}"]
    conf = block.get("confirmed")
    if conf is not None and not (isinstance(conf, dict) and str(conf.get("note") or "").strip()):
        return ["third_party.confirmed must be null or carry the user's note"]
    return []


def unconfirmed(block: dict | None) -> list[str]:
    if not block:
        return []
    conf = block.get("confirmed") or {}
    return [s for s in block["sources"] if s not in (conf.get("sources") or [])]


def confirm(block: dict, note: str) -> dict:
    return {"sources": block["sources"],
            "confirmed": {"at": utc_now(), "note": note.strip(), "sources": list(block["sources"])}}


def ask(exp_id: str, sources: list[str]) -> dict:
    return {"kind": "ask_user",
            "instruction": (f"{exp_id} contains code ported from public notebook(s) "
                            f"{', '.join(sources)}. Before kx pushes it, ask the user: have "
                            "they checked its license and the competition's rules on external "
                            "code, and will the author be credited where the rules require it? "
                            "(yes/no). Only on an explicit yes, run `then` with their words as "
                            "the note."),
            "then": f"kx run {exp_id} --third-party-ok '<what the user said>'"}


def line(block: dict | None) -> str | None:
    """One confirmation/strategy line, or None."""
    if not block:
        return None
    conf = block.get("confirmed")
    srcs = ", ".join(block["sources"])
    if conf:
        return f"contains code ported from {srcs} (the user confirmed {conf['at'][:10]}: " \
               f"{json.dumps(conf['note'])[1:-1][:120]})"
    return f"contains code ported from {srcs} (NOT confirmed by the user)"
