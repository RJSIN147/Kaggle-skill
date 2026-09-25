# Milestones

## v1.0 Experiment Loop MVP (Shipped: 2026-09-25)

**Delivered:** A standalone Claude Code skill. It turns an empty folder into a git-backed Kaggle experiment
workspace, and runs the idea → run → verdict → ledger → strategy loop locally or on a Kaggle kernel, with
CV-first submission gating.

**Phases completed:** 5 phases (1–5), 29 plans, 39 tasks
**Timeline:** 2026-07-09 → 2026-09-25 (284 commits on `main`)
**Size:** 29 helper scripts (~9.4k LOC Python), 42 test modules (~9.6k LOC), SKILL.md 488 lines
**Archive:** [v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md) · [v1.0-REQUIREMENTS.md](milestones/v1.0-REQUIREMENTS.md) · [v1.0-phases/](milestones/v1.0-phases/)

**Key accomplishments:**

- **Workspace setup:**
  - One init turns an empty folder into a git-tracked workspace.
  - The Kaggle credential is checked with a live call, masked and never echoed.
  - A deny-by-default egress allowlist and a pre-commit leak guard are installed.
- **Competition context and data:**
  - A single Kaggle CLI gateway with fail-closed 403 and rules-gate handling.
  - A machine-derived `competition.md` constitution, with ingested pages fenced as untrusted content.
  - Zip-slip-safe data download.
  - Advisory CV-scheme evidence, never auto-committed.
- **Local experiment loop:**
  - A kernel-portable `experiment.py` scaffold with a leakage-safe `run_cv` harness.
  - A fail-closed `result.json` contract: tooling writes scores, and a throwing or lying run is recorded as FAILED.
  - A git-backed ledger that rebuilds from per-experiment folders.
  - `strategy.md` regenerated from the ledger, with a never-repeat digest.
- **Kaggle kernel path:**
  - convert → push → poll → pull → record, with detach/resume.
  - Kernel status is authoritative: `ERROR` and `CANCEL_*` are recorded as FAILED.
  - Live-verified on 2026-09-25, after 4 live bugs were fixed in quick task 260925-66x (parity CV 0.8305).
- **Submissions and leaderboard:**
  - CV-first submission gate with daily-budget accounting. `submissions.date` was confirmed to be UTC, live.
  - Submissions confirmed by read-back.
  - A CV→LB gap trend with a divergence alarm.

**Known gaps / caveats at close:**

- **SETUP-04:** the egress half was only partially demonstrated. The 01-03 `example.com` anomaly (a host outside
  the allowlist was reached) is unresolved.
- **SCORE-01:** the live submit path was exercised with the raw CLI (spikes 003/004), not through
  `scripts/submit.py`.
- **EXP-05:** the T4×2 accelerator string is unverified.
- **Scope limit:** v1 is tabular and CSV-shaped. Scraping competition type from rules prose mislabelled Titanic
  as a code competition. v2.0 (Kaggle-general) supersedes this with API-derived competition profiles; see
  `.planning/spikes/` and the `spike-findings-kaggle-skill` skill.

Known deferred items at close: 2. Both are pre-close audit false positives: quick tasks 260925-5z0 and 260925-66x
are complete, but their summaries are named `<id>-SUMMARY.md`, not `SUMMARY.md`. See STATE.md Deferred Items.

---
