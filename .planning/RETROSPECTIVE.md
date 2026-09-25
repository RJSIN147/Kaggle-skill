# Project Retrospective

*A living document, updated after each milestone. Its lessons feed forward into future planning.*

## Milestone: v1.0 — Experiment Loop MVP

**Shipped:** 2026-09-25
**Phases:** 5 | **Plans:** 29 | **Sessions:** not tracked

### What Was Built

- A one-command workspace init, with a live credential check, an egress allowlist and a pre-commit leak guard.
- A machine-derived competition constitution and zip-slip-safe data download, behind a single fail-closed Kaggle
  CLI gateway.
- A local idea → run → verdict → ledger → strategy loop with a fail-closed `result.json` contract. The ledger
  rebuilds from the per-experiment folders.
- A Kaggle kernel path (convert → push → poll → pull → record) with detach/resume.
- CV-first submission gating, daily-budget accounting and a CV→LB gap alarm.

### What Worked

- **Fail-closed contracts.** Tooling writes scores; a lying or throwing run is recorded as FAILED. This held up in
  every review.
- **Pinning locked decisions as tests first** (the Nyquist "wave 0" RED suites) caught drift before implementation.
- **Treating ingested web content as untrusted from day one:** fenced pages, no execution of anything derived from
  them.

### What Was Inefficient

- **341 fixture tests passed, yet the first live kernel run exposed 4 bugs:**
  - a missing kernelspec
  - papermill's `-f` argv
  - `SystemExit` under ipykernel
  - the flat `/kaggle/working` output

  Live checks were deferred to "operator" steps for too long, and fixtures encoded our assumptions about Kaggle
  rather than Kaggle's actual behaviour.
- **Regex over rules prose for competition type and limits** mislabelled Titanic as a code competition. The
  structured SDK fields existed all along; the "stdlib-only" rule hid them.
- **28 scripts plus an exit-code protocol** (65/69/75/77/78) made SKILL.md 488 lines. That is a heavy per-session
  context cost for one loop.
- **Scope was tabular and CSV-only in practice.** Code-only, API-served, simulation and writeup competitions, which
  are most prize competitions, had no path.

### Patterns Established

- Keep a machine-checked result contract; never let the AI write numbers.
- Treat external Kaggle content as untrusted: read it, label it, never execute it or obey it.
- Humans run irreversible actions (submissions). Tooling prepares, validates and reads back.

### Key Lessons

1. **"Done" means a live run on a real competition, not a test count.** Fixtures guard against regressions; they
   don't prove platform behaviour. This is now a v2 requirement.
2. **Spike the platform before designing.** A few live CPU kernels answered questions that weeks of fixture work had
   assumed wrong: the mount paths, script-kernel submission and the dropped version pins.
3. **Prefer structured API fields over scraping,** even at the cost of a dependency the project already has.
4. **Design for the breadth of the domain early.** "Kaggle competition" covers at least six submission modes.

### Cost Observations

- Model mix: not tracked (the `quality` profile, Opus-heavy).
- Notable: live verification was cheap (CPU kernels, a trivial GPU run) compared with the rework it prevented.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | not tracked | 5 | Fixture-first TDD; live checks deferred to the end (4 live bugs found late) |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v1.0 | 341 passing | not measured | 29 stdlib-only scripts |

### Top Lessons (Verified Across Milestones)

1. (Needs a second milestone to cross-validate.)
