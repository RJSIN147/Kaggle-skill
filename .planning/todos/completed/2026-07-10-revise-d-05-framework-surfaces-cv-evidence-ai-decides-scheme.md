---
created: 2026-07-10T17:38:28.964Z
title: "Enforce D-05: AI decides CV scheme, tooling persists it validated"
area: planning
resolves_phase: 2
files:
  - scripts/cv_evidence.py
  - scripts/analyze_data.py:427
  - SKILL.md
  - .planning/phases/02-competition-context-data/02-CONTEXT.md
  - .planning/phases/02-competition-context-data/02-VERIFICATION.md
---

## Problem

The CV scheme is an ML methodology **decision** that must belong to the
practitioner + the AI in the loop, not the framework's plumbing. As BUILT,
`analyze_data.py` auto-commits the **mechanical** recommendation from
`cv_evidence.recommend_cv` by default, and SKILL.md never tells the AI to review
the evidence and choose — so the framework effectively decides.

Key finding: D-05 as WRITTEN already says "Tooling recommends → **AI reasons** →
tooling writes" — the AI is supposed to decide; the tooling write exists only so
the field is enum-validated instead of free-typed (anti-hallucination). The
implementation violated its own decision by auto-committing the mechanical
default. So this is **enforcing D-05's intent**, not overturning it.

The Titanic false-positive (GroupKFold committed where StratifiedKFold is
correct) is the symptom: `detect_group_candidates` flags continuous numerics
(Age/Fare/Cabin) as group ids, and because the mechanical value was auto-committed
with no AI decision step, the wrong scheme landed in `config.json`/`competition.md`
as trusted ground truth.

## Solution

Operator decision (2026-07-10): **framework surfaces evidence + an advisory hint;
AI decides; tooling persists the AI's chosen value enum-validated.** This keeps
both "AI decides, not the framework" AND D-05's anti-free-text write mechanism.
The Phase 2→3 contract is UNCHANGED: Phase 3 still reads `config.json cv.scheme`,
now guaranteed to be an AI decision rather than a mechanical auto-commit.

- `analyze_data.py`: **remove the auto-commit of the mechanical default.**
  `config.json cv.scheme` is written ONLY from the AI's explicit choice (the
  existing enum-validated `--cv-scheme` arg). No silent mechanical fallback that
  lands a scheme without an AI decision.
- `cv_evidence.py`: keep emitting structural evidence AND a mechanical
  recommendation to `control/raw/cv-evidence.json`, but label the recommendation
  a **non-authoritative HINT** (advisory). Degrade to "no tabular structure
  detected" for non-tabular data (images/audio/text) rather than emitting a bogus
  tabular scheme.
- `SKILL.md`: document the flow — the AI reads `cv-evidence.json`, reasons, and
  passes its chosen `--cv-scheme`; the framework persists it enum-validated; the
  framework never picks the value.
- Still **tighten `detect_group_candidates`** so the advisory hint isn't
  egregiously wrong on ordinary continuous features, and pin a titanic-shaped
  fixture in `tests/cv_fixtures.py`. (Now advisory-quality, not
  correctness-critical, since the AI decides — but a confidently-wrong hint is
  still bad.)
- **Clarify D-05** in 02-CONTEXT.md (amendment note, not overturn): the mechanical
  recommendation is advisory; the AI decides; tooling persists the AI's chosen
  value (enum-validated); the framework must NOT auto-commit the mechanical
  default.

Also fold in Gap 2 (WR-01): `download_data.py` must mirror
`capture_competition._gateway_failure` — surface 127 (CLI missing) and 124
(timeout) distinctly instead of collapsing them into the exit-77 UI-gate path.

Route the actual code change through `/gsd:plan-phase 2 --gaps` →
`/gsd:execute-phase 2 --gaps-only`; this todo is the captured direction.

Deferred to a future milestone (out of scope for the gap fix): should
`cv_evidence` become an explicit *tabular-modality* helper (named as such) rather
than "the framework's CV logic"?
