# Phase 1: Workspace, Credentials & Egress Guardrails - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-09
**Phase:** 1-Workspace, Credentials & Egress Guardrails
**Areas discussed:** Init interaction model, Credential posture, Egress allowlist breadth, Workspace layout & naming, Credential-failure behavior, Python env scaffolding, Git tracks vs. ignores, Leak-check strength

---

## Init interaction model

### Q1 — Setup experience feel

| Option | Description | Selected |
|--------|-------------|----------|
| Guided, then scaffold | Ask key choices (competition slug, execution target) up front, confirm, THEN scaffold. Nothing created until answered. | ✓ |
| Scaffold-first with defaults | Scaffold immediately with defaults, validate creds, report; tweak config after. | |
| Hybrid (defaults + confirm) | Propose defaults in one summary, confirm/amend in one step, then scaffold. | |

### Q2 — Non-empty folder behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Refuse unless forced | Abort on existing files unless --force. | |
| Safe-merge | Only create files that don't exist; never overwrite; re-runnable to repair idempotently. | ✓ |
| Refuse only on conflict | Proceed unless a real workspace file already exists. | |

**Notes:** Clarified that in Claude Code, `init` is a skill invocation (Claude gathers inputs, runs a scaffolder), not a flags-only CLI. Also established that init records the competition slug in config.json but the constitution/data download is Phase 2.

---

## Credential posture

### Q1 — What to do with a fixable credential problem

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-fix with consent | Show the exact fix; apply only after confirmation; never silent. | ✓ |
| Detect and instruct only | Never touch credential files; print commands for the user. | |
| Silent auto-fix | Fix without asking. | |

### Q2 — Canonical credential source

| Option | Description | Selected |
|--------|-------------|----------|
| kaggle.json canonical | ~/.kaggle/kaggle.json as source of truth; map others into it. | |
| Env vars canonical | KAGGLE_USERNAME/KAGGLE_KEY (or KAGGLE_API_TOKEN); map others into env vars. | ✓ |
| Accept any, don't normalize | Validate whatever works; no canonical form. | |

### Q3 — Where canonical env vars persist

| Option | Description | Selected |
|--------|-------------|----------|
| Workspace .env (gitignored) | init creates a .env stub; runner sources it; .gitignore covers it. | ✓ |
| User shell profile | Instruct user to export in ~/.bashrc etc.; skill never edits it. | |
| Session-only, no persistence | Validate exported env vars; never persist. | |

**Notes:** The env-vars-canonical + .env-persistence combination reconciles the "auto-fix with consent" surface (chmod fallback kaggle.json, populate .env from kaggle.json, or instruct) — captured as D-06 in CONTEXT.md.

---

## Egress allowlist breadth

### Q1 — Allowlist breadth

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal but complete | kaggle.com + GCS backend + PyPI. | |
| Standard package sources | Minimal + github.com/raw.githubusercontent.com + conda channels. | ✓ |
| Broad (ML-ready) | Standard + huggingface.co / model CDNs. | |

### Q2 — Where the allowlist is written

| Option | Description | Selected |
|--------|-------------|----------|
| Workspace settings + documented | Write into workspace .claude/settings.json AND document egress requirement for portability. | ✓ |
| Workspace settings only | Only write .claude/settings.json. | |
| Ship in skill package | Allowlist lives in the skill's bundled settings. | |

**Notes:** Surfaced the GCS-redirect gotcha — a kaggle.com-only allowlist silently breaks data download. Hugging Face deferred to the Phase 4 GPU path.

---

## Workspace layout & naming

### Q1 — Workspace organization

| Option | Description | Selected |
|--------|-------------|----------|
| Docs at root, control-plane tucked away | Docs at root; config/state/ledger under control/; data/ + experiments/ at root. | ✓ |
| Flat root | Everything at root. | |
| Everything under one framework dir | All framework files under a single hidden dir. | |

### Q2 — Experiment identification/naming

| Option | Description | Selected |
|--------|-------------|----------|
| Zero-padded sequential | exp-001, exp-002; ledger id = exp-NNN. | ✓ |
| Sequential + hypothesis slug | exp-001-lgbm-baseline. | |
| Date-prefixed | 2026-07-09-exp-01. | |

**Notes:** Confirmed the skill-vs-workspace relationship (skill installed globally, operates on the cwd folder).

---

## Credential-failure behavior

### Q1 — If live validation fails during init

| Option | Description | Selected |
|--------|-------------|----------|
| Scaffold anyway, flag creds | Complete scaffold, record status UNVALIDATED, print remediation; block only credential-dependent ops later. | ✓ |
| Abort until creds valid | Create nothing until the check passes. | |
| Scaffold if absent, abort if invalid | Scaffold when creds missing; abort when present-but-invalid. | |

---

## Python env scaffolding

### Q1 — Does Phase 1 lay down the Python env declaration

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal pyproject stub now | Bare pyproject.toml (metadata, Python ≥3.11 floor, uv config); full ML deps in Phase 3. | ✓ |
| Full ML stack declared now | Complete ML stack + floors from CLAUDE.md now. | |
| Defer entirely to Phase 3 | No Python-env scaffolding in Phase 1. | |

---

## Git tracks vs. ignores

### Q1 — What the git-backed workspace tracks vs. ignores

| Option | Description | Selected |
|--------|-------------|----------|
| Code+ledger+docs tracked; data+heavy artifacts ignored | Track control/, docs, exp code, meta.json; ignore secrets, data/, artifacts, __pycache__/.venv. | ✓ |
| Track everything except secrets | Only secrets ignored; data + artifacts committed. | |
| Minimal — docs + ledger only | Track only docs + ledger metadata. | |

**Notes:** .gitignore written in Phase 1 must anticipate Phase 3 experiment artifacts to avoid a later rewrite.

---

## Leak-check strength

### Q1 — Strength of the credential-leak check

| Option | Description | Selected |
|--------|-------------|----------|
| Both: .gitignore + pre-commit scan | Assert .gitignore coverage AND install a pre-commit guard scanning staged content for token patterns. | ✓ |
| Active pre-commit scan only | Rely on the content scan alone. | |
| Static .gitignore assertion only | Just verify .gitignore covers the secret files. | |

---

## Claude's Discretion

- Initial commit: `init` makes one `chore: scaffold workspace` commit AFTER the pre-commit guard is installed, so the baseline is scanned.
- Git init specifics (default branch name, local user/email).
- The exact live-validation command (must be exit-code-based, no secret leakage to stdout).
- Exact `.claude/settings.json` allowlist host syntax (researcher to verify against current schema).

## Deferred Ideas

- Hugging Face / model-CDN egress hosts — add when the Phase 4 GPU/DL path needs weights.
- Per-experiment execution-target override — Phase 3.
- Full ML dependency declaration + uv.lock — Phase 3, with the local runner.
