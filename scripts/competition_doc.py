#!/usr/bin/env python3
"""competition_doc.py — the ONE section-safe-merge helper for ``competition.md``.

``init_workspace.create_if_absent`` is whole-file granular: it creates the doc from
the template once and never touches it again. But Phase 2 fills the doc from TWO
independent scripts — ``capture_competition.py`` (Evaluation metric, Rules & limits)
and ``analyze_data.py`` (Data schema, Cross-validation, Adversarial validation) —
each of which must populate ITS sections without clobbering the other's, or a human
edit. So both import THIS single ``replace_section`` (D-04 at SECTION granularity);
neither reimplements a section parser.

The merge rule is deliberately conservative and mechanical (pure stdlib string work,
never a real markdown parser): a section body is replaced ONLY WHILE it still holds
the template-default sentinel ``_TODO (Phase 2)_``. Once populated (by either script)
or curated (by a human), the sentinel is gone and the section is left untouched — so
a re-run is idempotent and a curated rationale always survives.

Portability: stdlib-only, importable, no side effects on import.
"""

from __future__ import annotations

# The template-default sentinel every fillable ``competition.md`` section carries
# until it is populated. Kept in sync with ``scripts/templates/competition.md.tmpl``.
_TODO = "_TODO (Phase 2)_"


def replace_section(md_text: str, header: str, body: str) -> str:
    """Replace the ``## {header}`` section body IFF it is still the template default.

    Section boundary (mechanical, not a parser): the line ``## {header}`` up to the
    next line beginning ``## `` (any following level-2 heading) or EOF. The body
    between them is replaced with ``body`` ONLY IF it still contains the
    ``_TODO (Phase 2)_`` sentinel; otherwise ``md_text`` is returned unchanged
    (a populated / curated / already-edited section survives — D-04). A ``header``
    that is absent leaves ``md_text`` unchanged.
    """
    target = f"## {header}"
    lines = md_text.splitlines(keepends=True)

    start = None
    for i, line in enumerate(lines):
        if line.rstrip("\n") == target:
            start = i
            break
    if start is None:
        return md_text  # missing header → unchanged

    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break

    current_body = "".join(lines[start + 1 : end])
    if _TODO not in current_body:
        return md_text  # already populated / curated → skip (idempotent)

    prefix = "".join(lines[: start + 1])   # through the header line (keeps its newline)
    suffix = "".join(lines[end:])          # the next section onward
    return f"{prefix}\n{body.strip()}\n\n{suffix}"
